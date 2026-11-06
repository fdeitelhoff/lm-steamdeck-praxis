#!/usr/bin/env python3
"""Konfiguration vor dem Start, nur für eine neue/gestoppte Testinstallation."""
import argparse
import ipaddress
from pathlib import Path
import socket
import subprocess
import xml.etree.ElementTree as ET


def allowed_ip(value):
    ip = ipaddress.IPv4Address(value)
    networks = ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '127.0.0.1/32')
    if not any(ip in ipaddress.ip_network(n) for n in networks):
        raise ValueError('Nur Loopback oder eine private IPv4-Adresse verwenden.')
    return str(ip)


def set_element(parent, name, value):
    for old in parent.findall(name):
        parent.remove(old)
    ET.SubElement(parent, name).text = value


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('base', type=Path)
    p.add_argument('address')
    p.add_argument('--initial', action='store_true')
    args = p.parse_args()
    base = args.base.resolve()
    if base != Path.home() / 'steamdeck-homeserver':
        p.error('Nur der feste Testpfad ~/steamdeck-homeserver ist vorgesehen.')
    address = allowed_ip(args.address)
    if not args.initial:
        for unit in ('decklab-caddy.service', 'decklab-syncthing.service'):
            r = subprocess.run(['systemctl', '--user', 'show', unit, '--property=ActiveState', '--value'], capture_output=True, text=True)
            if r.returncode or r.stdout.strip() not in ('inactive', 'failed'):
                p.error(f'{unit} zuerst stoppen; Status konnte nicht als gestoppt bestaetigt werden.')
        for port in (8080, 22000):
            with socket.socket() as sock:
                try:
                    sock.bind((address, port))
                except OSError as e:
                    p.error(f'Adresse nicht lokal oder Port {port} belegt: {e}')
    path = base / 'syncthing-state/config.xml'
    tree = ET.parse(path)
    root = tree.getroot()
    gui = root.find('gui')
    opts = root.find('options')
    if gui is None or opts is None:
        p.error('Unbekanntes Syncthing-Konfigurationsformat; nicht starten.')
    gui.set('enabled', 'true')
    gui.set('tls', 'false')
    set_element(gui, 'address', '127.0.0.1:8384')
    for name, value in {
        'listenAddress': f'tcp://{address}:22000',
        'globalAnnounceEnabled': 'false', 'localAnnounceEnabled': 'false',
        'relaysEnabled': 'false', 'natEnabled': 'false', 'urAccepted': '-1',
        'crashReportingEnabled': 'false', 'autoUpgradeIntervalH': '0',
        'releasesURL': '', 'startBrowser': 'false',
    }.items():
        set_element(opts, name, value)
    if args.initial:
        # Kein impliziter Default Folder außerhalb des isolierten Testdatenordners.
        for folder in root.findall('folder'):
            root.remove(folder)
    ET.indent(tree, space='    ')
    tree.write(path, encoding='utf-8', xml_declaration=True)
    (base / 'config/Caddyfile').write_text(
        '{\n    admin off\n    auto_https off\n}\n'
        'http://:8080 {\n'
        f'    bind {address}\n'
        f'    root * {base}/site\n'
        '    file_server\n}\n', encoding='utf-8')
    print(f'Caddy :8080 und Syncthing Sync :22000 an {address}; GUI bleibt 127.0.0.1:8384.')
    print('Konfiguration geändert. Dienste wurden nicht gestartet.')


if __name__ == '__main__':
    main()
