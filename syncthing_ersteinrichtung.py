#!/usr/bin/env python3
"""Windows-Gegenstelle: frisch generierte Syncthing-Konfiguration vor dem ersten Start begrenzen."""
import argparse
from pathlib import Path
import socket
import xml.etree.ElementTree as ET
from configure_local import allowed_ip, set_element


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('state_directory', type=Path)
    p.add_argument('local_ipv4')
    args = p.parse_args()
    address = allowed_ip(args.local_ipv4)
    allowed = {'config.xml', 'cert.pem', 'key.pem', 'https-cert.pem', 'https-key.pem'}
    entries = list(args.state_directory.iterdir())
    if any(e.name not in allowed or e.is_symlink() or not e.is_file() for e in entries):
        p.error('Kein frischer Konfigurationsordner. Bestehende Installationen nicht mit diesem Skript bearbeiten.')
    for ip, port in [('127.0.0.1',8384), (address,22000)]:
        with socket.socket() as sock:
            try: sock.bind((ip,port))
            except OSError as e: p.error(f'Adresse/Port nicht nutzbar: {ip}:{port}: {e}')
    path = args.state_directory / 'config.xml'
    tree = ET.parse(path); root = tree.getroot()
    gui, opts = root.find('gui'), root.find('options')
    if gui is None or opts is None: p.error('Unbekanntes Konfigurationsformat.')
    gui.set('enabled','true'); gui.set('tls','false')
    set_element(gui,'address','127.0.0.1:8384')
    for name, value in {
        'listenAddress': f'tcp://{address}:22000',
        'globalAnnounceEnabled':'false','localAnnounceEnabled':'false',
        'relaysEnabled':'false','natEnabled':'false','urAccepted':'-1',
        'crashReportingEnabled':'false','autoUpgradeIntervalH':'0',
        'releasesURL':'','startBrowser':'false',
    }.items(): set_element(opts,name,value)
    for folder in root.findall('folder'): root.remove(folder)
    ET.indent(tree, space='    '); tree.write(path,encoding='utf-8',xml_declaration=True)
    print('Konfiguration vorbereitet. Kein Prozess gestartet. GUI-Passwort nach dem lokalen Start setzen.')


if __name__ == '__main__':
    main()
