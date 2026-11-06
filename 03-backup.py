#!/usr/bin/env python3
"""Konsistente Testsicherung erstellen, pruefen und in neuen Ordner entpacken."""
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import tarfile


def sha_file(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def ensure_stopped(base):
    for unit in ('decklab-caddy.service', 'decklab-syncthing.service'):
        r = subprocess.run(['systemctl', '--user', 'show', unit, '--property=ActiveState', '--value'], capture_output=True, text=True)
        if r.returncode or r.stdout.strip() not in ('inactive', 'failed'):
            raise ValueError(f'{unit} zuerst stoppen. Gestoppter Status nicht bestaetigt.')
    for proc in Path('/proc').glob('[0-9]*/exe'):
        try:
            target = Path(os.readlink(proc))
        except (OSError, PermissionError):
            continue
        if target in (base/'bin/caddy', base/'bin/syncthing'):
            raise ValueError('Ein Testprozess laeuft noch ausserhalb der systemd-Unit.')


def create(output):
    os.umask(0o077)
    base = Path.home() / 'steamdeck-homeserver'
    if not base.is_dir() or base.is_symlink():
        raise ValueError('Testinstallation nicht gefunden oder Basis ist ein Symlink.')
    output = output.resolve()
    if output == base or base in output.parents:
        raise ValueError('Archiv muss ausserhalb der Testinstallation liegen.')
    sidecar = Path(str(output)+'.sha256')
    if output.exists() or sidecar.exists():
        raise ValueError('Ausgabe existiert bereits. Neuen Namen verwenden.')
    ensure_stopped(base)
    files = []
    for path in sorted(base.rglob('*')):
        if path.is_symlink():
            raise ValueError(f'Symlink nicht erlaubt: {path.relative_to(base)}')
        if path.is_file():
            files.append(path)
        elif not path.is_dir():
            raise ValueError(f'Spezialdatei nicht erlaubt: {path.relative_to(base)}')
    manifest = {'format': 1, 'utc': datetime.now(timezone.utc).isoformat(),
                'files': {str(p.relative_to(base)): {'sha256': sha_file(p), 'size': p.stat().st_size} for p in files}}
    blob = json.dumps(manifest, ensure_ascii=False, indent=2).encode()
    # x verhindert Ueberschreiben auch bei einem Rennen zwischen Existenzpruefung und create.
    with output.open('xb') as raw, tarfile.open(fileobj=raw, mode='w:gz') as tar:
        for path in sorted(base.rglob('*')):
            tar.add(path, arcname=str(PurePosixPath('steamdeck-homeserver') / path.relative_to(base)), recursive=False)
        member = tarfile.TarInfo('MANIFEST.json')
        member.size, member.mode = len(blob), 0o600
        tar.addfile(member, io.BytesIO(blob))
    with sidecar.open('x', encoding='utf-8') as f:
        f.write(f'{sha_file(output)}  {output.name}\n')
    validate(output)
    print(f'Archiv: {output}\nSHA256: {sidecar}\nEnthaelt Syncthing-Schluessel. Privat aufbewahren, nicht als Redaktionsmaterial versenden.')


def validate(path):
    expected = Path(str(path)+'.sha256').read_text(encoding='utf-8').split()[0]
    if len(expected) != 64 or sha_file(path) != expected.lower():
        raise ValueError('SHA256 des Archivs stimmt nicht.')
    with tarfile.open(path, 'r:gz') as tar:
        members = tar.getmembers()
        names = set()
        for member in members:
            name = PurePosixPath(member.name)
            if name.is_absolute() or '..' in name.parts or member.name in names:
                raise ValueError('Unsicherer oder doppelter Archivpfad.')
            names.add(member.name)
            if not (member.isfile() or member.isdir()):
                raise ValueError('Symlinks und Spezialdateien im Archiv sind nicht erlaubt.')
            if member.name != 'MANIFEST.json' and (not name.parts or name.parts[0] != 'steamdeck-homeserver'):
                raise ValueError('Unerwarteter Archivpfad.')
        mf = tar.getmember('MANIFEST.json')
        if not mf.isfile() or mf.size > 20*1024*1024:
            raise ValueError('Ungueltiges Manifest.')
        manifest = json.load(tar.extractfile(mf))
        if manifest.get('format') != 1 or not isinstance(manifest.get('files'), dict):
            raise ValueError('Unbekanntes Manifestformat.')
        seen = set()
        for member in members:
            if member.isfile() and member.name != 'MANIFEST.json':
                rel = str(PurePosixPath(member.name).relative_to('steamdeck-homeserver'))
                info = manifest['files'].get(rel)
                if not info or info['size'] != member.size:
                    raise ValueError(f'Groesse/Manifest abweichend: {rel}')
                h = hashlib.sha256()
                with tar.extractfile(member) as f:
                    for block in iter(lambda: f.read(1024*1024), b''):
                        h.update(block)
                if h.hexdigest() != info['sha256']:
                    raise ValueError(f'Datei-Hash abweichend: {rel}')
                seen.add(rel)
        if seen != set(manifest['files']):
            raise ValueError('Manifest enthaelt fehlende Dateien.')
    print(f'Archiv und {len(seen)} Datei-Hashes stimmen.')


def extract(path, dest):
    validate(path)
    if dest.exists():
        raise ValueError('Ziel muss ein NEUER Ordner sein. Keine Live-Daten ersetzen.')
    dest.mkdir(mode=0o700)
    # Manuelles Extrahieren nach Validierung: weder Symlinks noch fremde Besitzer.
    with tarfile.open(path, 'r:gz') as tar:
        for member in tar.getmembers():
            target = dest.joinpath(*PurePosixPath(member.name).parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True, mode=0o700)
            else:
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                with tar.extractfile(member) as source, target.open('xb') as out:
                    for block in iter(lambda: source.read(1024*1024), b''):
                        out.write(block)
                target.chmod(0o700 if member.mode & 0o111 else 0o600)
    print(f'Pruefkopie: {dest}\nNoch kein funktionaler Restore. README Schritt 8 fortsetzen.')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    c = sub.add_parser('create'); c.add_argument('--output', type=Path, required=True)
    v = sub.add_parser('verify'); v.add_argument('archive', type=Path)
    e = sub.add_parser('extract'); e.add_argument('archive', type=Path); e.add_argument('destination', type=Path)
    args = p.parse_args()
    try:
        if args.command == 'create': create(args.output)
        elif args.command == 'verify': validate(args.archive)
        else: extract(args.archive, args.destination)
    except (OSError, ValueError, KeyError, tarfile.TarError, json.JSONDecodeError) as err:
        p.exit(1, f'Abbruch: {err}\n')


if __name__ == '__main__':
    main()
