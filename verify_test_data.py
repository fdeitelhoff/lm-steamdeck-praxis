#!/usr/bin/env python3
"""Vergleicht einen synchronisierten Testkorpus mit seinem SHA256-Manifest."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory', type=Path)
    args = p.parse_args()
    base = args.directory.resolve()
    hashes = json.loads((base/'HASHES.json').read_text(encoding='utf-8'))
    failed = []
    for name, expected in hashes.items():
        rel = PurePosixPath(name)
        if rel.is_absolute() or '..' in rel.parts:
            raise SystemExit('Unsicherer Manifestpfad.')
        path = base.joinpath(*rel.parts)
        if path.is_symlink() or not path.is_file() or base not in path.resolve().parents:
            failed.append(name); continue
        h = hashlib.sha256()
        with path.open('rb') as f:
            for block in iter(lambda: f.read(1024*1024), b''): h.update(block)
        if h.hexdigest() != expected: failed.append(name)
    print(f'Geprueft: {len(hashes)}, abweichend/fehlend: {len(failed)}')
    for name in failed[:20]: print(name)
    raise SystemExit(1 if failed else 0)


if __name__ == '__main__':
    main()
