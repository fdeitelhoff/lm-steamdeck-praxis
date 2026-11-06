#!/usr/bin/env bash
# Erstellt eine neue Testinstallation; startet/aktiviert keine Dienste.
set -euo pipefail
umask 077
if [[ $# != 4 ]]; then
  printf 'Aufruf: bash 01-vorbereiten.sh /pfad/caddy CADDY_SHA256 /pfad/syncthing SYNCTHING_SHA256\n' >&2
  exit 2
fi
[[ $EUID != 0 ]] || { printf 'Bitte als normaler Benutzer, nicht mit sudo starten.\n' >&2; exit 1; }
[[ $(uname -m) == x86_64 ]] || { printf 'Diese Anleitung erwartet Linux x86_64.\n' >&2; exit 1; }
for tool in python3 sha256sum systemctl install; do command -v "$tool" >/dev/null || { printf '%s fehlt. Erst klaeren, nicht pacman ausfuehren.\n' "$tool" >&2; exit 1; }; done
base="$HOME/steamdeck-homeserver"
[[ ! -e "$base" ]] || { printf 'Abbruch: %s existiert. Keine Dateien wurden ersetzt.\n' "$base" >&2; exit 1; }
# Einfacher Pfad fuer systemd ExecStart und Caddyfile; Standard /home/deck passt.
[[ "$HOME" =~ ^/[A-Za-z0-9_./-]+$ ]] || { printf 'Home-Pfad enthaelt Sonderzeichen. Anleitung manuell anpassen.\n' >&2; exit 1; }
for src in "$1" "$3"; do [[ -f "$src" && ! -L "$src" ]] || { printf 'Keine regulaere Binaerdatei: %s\n' "$src" >&2; exit 1; }; done
for hash in "$2" "$4"; do [[ "$hash" =~ ^[[:xdigit:]]{64}$ ]] || { printf 'Erwartet wird ein SHA256 mit 64 Hex-Zeichen.\n' >&2; exit 1; }; done
actual_caddy=$(sha256sum -- "$1"); actual_caddy=${actual_caddy%% *}
actual_sync=$(sha256sum -- "$3"); actual_sync=${actual_sync%% *}
[[ "${actual_caddy,,}" == "${2,,}" && "${actual_sync,,}" == "${4,,}" ]] || { printf 'SHA256 stimmt nicht ueberein. Abbruch vor Ausfuehrung.\n' >&2; exit 1; }
python3 - <<'PY'
import socket
for port in (8080, 8384, 22000):
    with socket.socket() as sock:
        try: sock.bind(('127.0.0.1', port))
        except OSError as e: raise SystemExit(f'Port {port} belegt/nicht nutzbar: {e}')
PY
mkdir -m 700 "$base"
mkdir -p "$base"/{bin,config,site,sync-data,syncthing-state,units,results}
install -m 700 -- "$1" "$base/bin/caddy"
install -m 700 -- "$3" "$base/bin/syncthing"
{
  printf 'UTC: %s\n' "$(date -u +%FT%TZ)"
  "$base/bin/caddy" version
  "$base/bin/syncthing" --version
  sha256sum "$base/bin/caddy" "$base/bin/syncthing"
} > "$base/results/versionen.txt"
# generate erzeugt Identitaet/Konfiguration, startet aber keinen Sync-Server.
"$base/bin/syncthing" generate --home="$base/syncthing-state" --no-port-probing
python3 "$(dirname "$0")/configure_local.py" "$base" 127.0.0.1 --initial
cat > "$base/units/decklab-caddy.service" <<'UNIT'
[Unit]
Description=Steam Deck Artikel Caddy
StartLimitIntervalSec=0

[Service]
Type=simple
WorkingDirectory=%h/steamdeck-homeserver
ExecStart=%h/steamdeck-homeserver/bin/caddy run --config %h/steamdeck-homeserver/config/Caddyfile --adapter caddyfile
Restart=on-failure
RestartSec=5
UMask=0077
NoNewPrivileges=true

[Install]
WantedBy=default.target
UNIT
cat > "$base/units/decklab-syncthing.service" <<'UNIT'
[Unit]
Description=Steam Deck Artikel Syncthing
StartLimitIntervalSec=0

[Service]
Type=simple
ExecStart=%h/steamdeck-homeserver/bin/syncthing serve --home=%h/steamdeck-homeserver/syncthing-state --no-browser --no-restart --no-upgrade --no-port-probing
Restart=on-failure
RestartSec=5
UMask=0077
NoNewPrivileges=true

[Install]
WantedBy=default.target
UNIT
printf 'deck-homeserver-ok\n' > "$base/site/health.txt"
cat > "$base/site/index.html" <<'HTML'
<!doctype html><html lang="de"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Steam Deck Homeserver</title><body><h1>Steam Deck Homeserver</h1><p>Testseite für den Linux-Magazin-Praxistest.</p><p><a href="health.txt">Erreichbarkeit</a> · <a href="test-1MiB.bin">Testdatei 1 MiB</a></p><p>Die Seite enthält ausschließlich synthetische Testdaten.</p></body></html>
HTML
python3 - "$base/site/test-1MiB.bin" <<'PY'
from pathlib import Path
import sys
# Reproduzierbares Byte-Muster, keine Kompression im Caddyfile.
with Path(sys.argv[1]).open('xb') as f:
    chunk = bytes(range(256)) * 4096
    f.write(chunk)
PY
sha256sum "$base/site/test-1MiB.bin" > "$base/results/testdatei.sha256"
"$base/bin/caddy" validate --config "$base/config/Caddyfile" --adapter caddyfile
printf '\nVorbereitet: %s\nNoch kein Dienst gestartet. README Schritt 3 fortsetzen.\n' "$base"
