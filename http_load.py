#!/usr/bin/env python3
"""Begrenztes HTTP-Downloadprofil im privaten Testnetz, Python >= 3.9."""
import argparse
import collections
from concurrent.futures import ThreadPoolExecutor
import csv
import json
from pathlib import Path
import threading
import time
from http_probe import local_url, percentile, request_once


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('url', type=local_url)
    p.add_argument('--duration', type=float, default=180)
    p.add_argument('--workers', type=int, choices=(1, 2, 4, 8), default=1)
    p.add_argument('--timeout', type=float, default=5)
    p.add_argument('--expected-bytes', type=int, default=1048576)
    p.add_argument('--max-requests', type=int, default=1000000)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if not .1 <= args.duration <= 3600 or not 0 < args.timeout <= 60 or not 1 <= args.max_requests <= 1000000:
        p.error('duration 0.1..3600, timeout >0 und <=60, max-requests 1..1000000 verwenden.')
    if not 1 <= args.expected_bytes <= 20*1024*1024:
        p.error('expected-bytes muss zwischen 1 Byte und 20 MiB liegen.')
    summary_file = args.output.with_suffix(args.output.suffix+'.json')
    if args.output.exists() or summary_file.exists(): p.error('Ausgabe existiert. Neuen Namen verwenden.')
    started = time.monotonic()
    deadline = started + args.duration
    lock = threading.Lock()
    counts = collections.Counter()
    success_times = []
    success_bytes = 0
    issued = 0
    stop = threading.Event()
    with args.output.open('x', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['worker','utc_start','elapsed_ms','outcome','http_status','bytes','detail'])
        writer.writeheader()

        def worker(number):
            nonlocal issued, success_bytes
            while not stop.is_set():
                with lock:
                    if time.monotonic() >= deadline or issued >= args.max_requests: return
                    issued += 1
                row = request_once(args.url, args.timeout, '', args.expected_bytes)
                with lock:
                    writer.writerow({'worker':number, **row}); f.flush()
                    counts[row['outcome']] += 1
                    if row['outcome'] == 'ok':
                        success_times.append(row['elapsed_ms'])
                        success_bytes += row['bytes']

        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(worker, i+1) for i in range(args.workers)]
            try:
                for future in futures: future.result()
            except KeyboardInterrupt:
                stop.set()
                print('Unterbrochen. Laufende Anfragen werden noch beendet.')
    elapsed = time.monotonic()-started
    result = {
        'url':args.url, 'requested_duration_s':args.duration, 'actual_elapsed_s':round(elapsed,3),
        'workers':args.workers, 'counts':dict(counts), 'requests':sum(counts.values()),
        'expected_bytes_per_response':args.expected_bytes, 'success_bytes':success_bytes,
        'success_bytes_per_s':round(success_bytes/elapsed,3) if elapsed else None,
        'success_requests_per_s':round(counts['ok']/elapsed,3) if elapsed else None,
        'p50_ms_success_only':percentile(success_times,.5), 'p95_ms_success_only':percentile(success_times,.95),
        'request_cap_reached':issued >= args.max_requests,
        'note':'Nach Ablauf starten keine neuen Requests; laufende Socketoperationen koennen das Fenster verlaengern. Kein SSD- oder maximaler Netzwerk-Benchmark.'}
    with summary_file.open('x', encoding='utf-8') as f: json.dump(result,f,indent=2,ensure_ascii=False)
    print(json.dumps(result,indent=2,ensure_ascii=False))


if __name__ == '__main__': main()
