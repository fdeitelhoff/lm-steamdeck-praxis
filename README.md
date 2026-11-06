# Steam Deck als Homeserver – Praxistest

Begleitskripte zum Linux-Magazin-Praxistest: Ein Steam Deck (SteamOS, x86_64) dient im
Heimnetz als kleiner Server mit **Caddy** (statischer Webserver) und **Syncthing**
(Dateisynchronisation). Die Skripte richten eine isolierte Testinstallation unter
`~/steamdeck-homeserver` ein, messen Erreichbarkeit und Durchsatz und prüfen Backup
und Wiederherstellung.

> **Hinweis:** Die Skripte sind für einen kontrollierten Test im privaten Netz gedacht,
> nicht als Produktivinstallation. Sie arbeiten ausschließlich mit synthetischen
> Testdaten, binden nur an Loopback bzw. private IPv4-Adressen und überschreiben keine
> bestehenden Dateien.

## Voraussetzungen

- Steam Deck (oder anderes Linux x86_64) mit `bash`, `python3` (≥ 3.9), `systemctl`,
  `sha256sum` – ohne Root-Rechte, ohne `pacman`
- Offizielle Binärdateien von [Caddy](https://caddyserver.com/docs/install) und
  [Syncthing](https://syncthing.net/downloads/) für Linux amd64 samt bekannter SHA256-Werte
- Ein zweiter Rechner im selben LAN (Messungen, Syncthing-Gegenstelle; Beispiel: Windows)
  mit Python ≥ 3.9
- Freie Ports: 8080 (Caddy), 8384 (Syncthing-GUI, nur lokal), 22000 (Syncthing-Sync)

## Dateien

| Datei | Läuft auf | Zweck |
|---|---|---|
| `00-bestandsaufnahme.sh` | Deck | Nur lesende Bestandsaufnahme (OS, Kernel, Netz, Speicher, Werkzeuge) |
| `01-vorbereiten.sh` | Deck | Prüft Hashes, legt `~/steamdeck-homeserver` an, erzeugt Konfiguration und systemd-Units – startet nichts |
| `02-lan-einstellen.sh` | Deck | Bindet Caddy und Syncthing-Sync an die LAN-IPv4 des Decks |
| `configure_local.py` | Deck | Gemeinsame Konfigurationslogik für 01/02 (Caddyfile, Syncthing `config.xml`) |
| `03-backup.py` | Deck | Sicherung erstellen, prüfen und in neuen Ordner entpacken |
| `http_probe.py` | Zweitrechner | HTTP-Stichproben zur Erreichbarkeit (CSV + JSON-Zusammenfassung) |
| `http_load.py` | Zweitrechner | Begrenztes Download-Lastprofil mit 1–8 Workern |
| `syncthing_ersteinrichtung.py` | Zweitrechner | Frisch generierte Syncthing-Konfiguration der Gegenstelle einschränken |
| `make_test_data.py` | beliebig | Reproduzierbarer Testkorpus mit SHA256-Manifest |
| `verify_test_data.py` | beliebig | Synchronisierten Korpus gegen das Manifest prüfen |
| `Artikel_Quellen.txt` | – | Quellenangaben des Artikels |

`http_load.py` importiert `http_probe.py`, `syncthing_ersteinrichtung.py` importiert
`configure_local.py` – die Skripte daher gemeinsam in einem Ordner belassen.

## Ablauf

### Schritt 1 – Bestandsaufnahme

```bash
bash 00-bestandsaufnahme.sh
```

Schreibt `bestandsaufnahme-<Zeitstempel>.txt`. Seriennummern und Adressen werden nicht
erfasst. Updatekanal, Dock, Netzteil, Ladegrenze usw. manuell ergänzen.

### Schritt 2 – Testinstallation vorbereiten

Caddy und Syncthing herunterladen, entpacken und die Prüfsummen mit den Angaben der
Projekte abgleichen. Dann:

```bash
bash 01-vorbereiten.sh /pfad/caddy CADDY_SHA256 /pfad/syncthing SYNCTHING_SHA256
```

Das Skript bricht ab, wenn `~/steamdeck-homeserver` schon existiert, ein Hash nicht passt
oder ein Port belegt ist. Es erzeugt Testseite, 1-MiB-Testdatei, Caddyfile und die Units
`decklab-caddy.service` und `decklab-syncthing.service` in `units/` – zunächst nur an
`127.0.0.1` gebunden.

### Schritt 3 – Dienste lokal starten und prüfen

```bash
systemctl --user link ~/steamdeck-homeserver/units/decklab-caddy.service
systemctl --user link ~/steamdeck-homeserver/units/decklab-syncthing.service
systemctl --user start decklab-caddy.service decklab-syncthing.service
systemctl --user status decklab-caddy.service decklab-syncthing.service
curl http://127.0.0.1:8080/health.txt   # erwartet: deck-homeserver-ok
```

Die Syncthing-GUI unter `http://127.0.0.1:8384` lokal öffnen und **sofort ein
GUI-Passwort setzen**. Sollen die Dienste ohne angemeldete Sitzung weiterlaufen:

```bash
loginctl enable-linger "$USER"
systemctl --user enable decklab-caddy.service decklab-syncthing.service
```

### Schritt 4 – Im LAN freigeben

Dienste stoppen, an die LAN-Adresse des Decks binden, wieder starten:

```bash
systemctl --user stop decklab-caddy.service decklab-syncthing.service
bash 02-lan-einstellen.sh 192.168.1.50
systemctl --user start decklab-caddy.service decklab-syncthing.service
```

Erlaubt sind nur private IPv4-Adressen (10/8, 172.16/12, 192.168/16). Die Syncthing-GUI
bleibt auf `127.0.0.1:8384`; Discovery, Relays, NAT-Traversal und Telemetrie sind aus.

### Schritt 5 – Erreichbarkeit und Last messen (Zweitrechner)

```bash
python3 http_probe.py http://192.168.1.50:8080/health.txt --interval 2 --count 300 --output probe-1.csv
python3 http_load.py  http://192.168.1.50:8080/test-1MiB.bin --workers 4 --duration 180 --output load-4w.csv
```

Jede Messung schreibt eine CSV-Datei und eine `.csv.json`-Zusammenfassung. Vorhandene
Ausgabedateien werden nie überschrieben. Die Werte sind Stichproben bzw. ein begrenztes
Lastprofil – kein SSD- oder Netzwerk-Maximalbenchmark.

### Schritt 6 – Syncthing-Gegenstelle einrichten (Zweitrechner)

```powershell
syncthing.exe generate --home=C:\decklab\syncthing-state
python syncthing_ersteinrichtung.py C:\decklab\syncthing-state 192.168.1.20
syncthing.exe serve --home=C:\decklab\syncthing-state --no-browser
```

Das Skript akzeptiert nur einen frisch generierten Konfigurationsordner. Danach in beiden
GUIs Passwort setzen, Geräte gegenseitig hinzufügen (Adresse `tcp://<IP>:22000`) und einen
Ordner unterhalb von `~/steamdeck-homeserver/sync-data` freigeben.

### Schritt 7 – Synchronisation mit Testkorpus prüfen

```bash
python3 make_test_data.py ~/steamdeck-homeserver/sync-data/testdaten-run1 --seed run1
# nach abgeschlossener Synchronisation auf der Gegenstelle:
python3 verify_test_data.py C:\decklab\sync\testdaten-run1
```

Standard: 1 GiB große Datei plus 1000 × 4 KiB. Für jeden Wiederholungslauf einen neuen
`--seed` und neuen Zielordner verwenden. `verify_test_data.py` endet mit Exit-Code 1, wenn
Dateien fehlen oder abweichen.

### Schritt 8 – Backup und Wiederherstellung

```bash
systemctl --user stop decklab-caddy.service decklab-syncthing.service
python3 03-backup.py create  --output ~/decklab-backup-1.tar.gz
python3 03-backup.py verify  ~/decklab-backup-1.tar.gz
python3 03-backup.py extract ~/decklab-backup-1.tar.gz ~/decklab-restore-test
```

`create` verlangt gestoppte Dienste, schreibt ein SHA256-Manifest ins Archiv und eine
`.sha256`-Datei daneben. `extract` entpackt nur in einen **neuen** Ordner und ersetzt keine
Live-Daten. Für einen funktionalen Restore die Dienste gestoppt lassen, die bisherige
Installation umbenennen, die Prüfkopie `~/decklab-restore-test/steamdeck-homeserver` nach
`~/steamdeck-homeserver` verschieben, Dienste starten und Schritt 5 und 7 wiederholen.

> **Achtung:** Das Sicherungsarchiv, das Sie in diesem Schritt auf Ihrem Deck erzeugen,
> enthält den privaten Syncthing-Schlüssel Ihres Geräts (`key.pem`). Wer das Archiv hat,
> kann sich gegenüber Ihren anderen Syncthing-Geräten als Ihr Deck ausgeben. Archiv daher
> privat aufbewahren und nicht weitergeben – etwa nicht in Foren oder Fehlerberichten.
> Dieses Repository selbst enthält keine Schlüssel; jede Installation erzeugt in Schritt 2
> ihr eigenes Schlüsselpaar.

## Aufräumen

```bash
systemctl --user disable --now decklab-caddy.service decklab-syncthing.service
loginctl disable-linger "$USER"   # nur falls zuvor aktiviert
rm -r ~/steamdeck-homeserver
```

## Lizenz

[MIT](LICENSE)
