#!/usr/bin/env python3
"""Reproduzierbarer Testkorpus, ausschliesslich in einem neuen Zielordner."""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('destination', type=Path)
    p.add_argument('--large-mib', type=int, default=1024)
    p.add_argument('--small-files', type=int, default=1000)
    p.add_argument('--small-kib', type=int, default=4)
    p.add_argument('--seed', default='run1', help='Fuer jeden unabhaengigen Wiederholungslauf anderen Seed verwenden.')
    args = p.parse_args()
    if not 0 <= args.large_mib <= 1024 or not 0 <= args.small_files <= 10000 or not 1 <= args.small_kib <= 1024 or not (args.large_mib or args.small_files):
        p.error('Grenzen: large-mib 0..1024, small-files 0..10000, small-kib 1..1024; mindestens ein Datensatz.')
    args.destination.mkdir(mode=0o700)  # Existierendes Ziel fuehrt bewusst zum Abbruch.
    manifest = {}
    if args.large_mib:
        big = args.destination / 'gross.bin'
        digest = hashlib.sha256()
        with big.open('xb') as f:
            for i in range(args.large_mib):
                block = hashlib.shake_256(f'deck-test-{args.seed}-large-{i}'.encode()).digest(1024*1024)
                f.write(block); digest.update(block)
        manifest[big.name] = digest.hexdigest()
    small = args.destination / 'klein'
    if args.small_files: small.mkdir()
    for i in range(args.small_files):
        path = small / f'datei-{i:05}.bin'
        content = hashlib.shake_256(f'deck-test-{args.seed}-small-{i}'.encode()).digest(args.small_kib*1024)
        path.write_bytes(content)
        manifest[str(path.relative_to(args.destination)).replace('\\','/')] = hashlib.sha256(content).hexdigest()
    (args.destination / 'HASHES.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(f'{len(manifest)} Dateien, {args.large_mib} MiB + {args.small_files} x {args.small_kib} KiB; Manifest HASHES.json.')


if __name__ == '__main__':
    main()
