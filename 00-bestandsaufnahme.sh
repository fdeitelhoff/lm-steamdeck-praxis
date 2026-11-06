#!/usr/bin/env bash
# Nur lesende Bestandsaufnahme. Schreibt ausschließlich die angegebene Ergebnisdatei.
set -euo pipefail
umask 077
out="${1:-bestandsaufnahme-$(date +%Y%m%d-%H%M%S).txt}"
if [[ -e "$out" ]]; then printf 'Abbruch: Datei existiert bereits: %s\n' "$out" >&2; exit 1; fi
set -o noclobber
{
  printf 'Steam Deck Homeserver – Bestandsaufnahme\nUTC: %s\n' "$(date -u +%FT%TZ)"
  printf '\nBetriebssystem\n'
  if [[ -r /etc/os-release ]]; then
    awk '/^(NAME|VERSION|VERSION_ID|BUILD_ID|ID|VARIANT_ID)=/' /etc/os-release
  fi
  printf 'Kernel: '; uname -r
  printf 'Architektur: '; uname -m
  if command -v systemctl >/dev/null; then systemctl --version | head -n 1; fi
  printf '\nDMI ohne Seriennummern\n'
  for field in sys_vendor product_name product_version; do
    [[ ! -r "/sys/class/dmi/id/$field" ]] || printf '%s: %s\n' "$field" "$(cat "/sys/class/dmi/id/$field")"
  done
  printf '\nNetzwerk nur Schnittstellenname Typ und Zustand\n'
  for nic in /sys/class/net/*; do
    [[ -d "$nic" ]] || continue
    printf '%s type=%s state=%s\n' "${nic##*/}" "$(cat "$nic/type")" "$(cat "$nic/operstate")"
  done
  printf '\nSpeicher insgesamt\n'
  awk '/^(MemTotal|SwapTotal):/' /proc/meminfo
  printf '\nFreier Platz im Home Dateisystem in KiB\n'
  df -Pk "$HOME" | awk 'NR == 2 {printf "gesamt=%s benutzt=%s frei=%s belegt=%s\n",$2,$3,$4,$5}'
  printf '\nWerkzeuge\n'
  for tool in bash python3 systemctl loginctl curl sha256sum tar ss; do
    if command -v "$tool" >/dev/null; then printf '%s vorhanden\n' "$tool"; else printf '%s FEHLT\n' "$tool"; fi
  done
  printf '\nLinger fuer den aktuellen Benutzer\n'
  if command -v loginctl >/dev/null; then loginctl show-user "$(id -u)" --property=Linger 2>/dev/null || true; fi
  printf '\nManuell ergaenzen: SteamOS Updatekanal, Dock, Netzteil, Ethernet/WLAN, Ladegrenze, Displayprofil.\n'
} > "$out"
printf 'Ergebnis: %s\n' "$out"
