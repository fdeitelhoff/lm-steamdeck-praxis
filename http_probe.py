#!/usr/bin/env python3
"""HTTP-Stichproben vom zweiten Rechner. Standardbibliothek; Python >= 3.9."""
import argparse
import collections
import csv
from datetime import datetime, timezone
import ipaddress
import http.client
import json
import math
from pathlib import Path
import socket
import time
import urllib.error
import urllib.parse
import urllib.request


def local_url(value):
    u = urllib.parse.urlsplit(value)
    try:
        ip = ipaddress.IPv4Address(u.hostname)
    except (ValueError, TypeError):
        raise argparse.ArgumentTypeError('Eine lokale IPv4-Adresse, keinen Hostnamen verwenden.')
    nets = ['10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '127.0.0.1/32']
    if u.scheme != 'http' or u.username or u.password or not any(ip in ipaddress.ip_network(n) for n in nets):
        raise argparse.ArgumentTypeError('Nur HTTP zu einer privaten IPv4-Adresse oder 127.0.0.1 erlaubt.')
    try:
        _ = u.port
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e))
    return value


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request_once(url, timeout=2.0, expect_text='deck-homeserver-ok', expected_bytes=None):
    stamp = datetime.now(timezone.utc).isoformat(timespec='milliseconds')
    start = time.perf_counter()
    status, size, outcome, detail = '', 0, 'network_error', ''
    # Kein Systemproxy; keine Redirects auf andere Hosts. Cache-Control ist keine Latenzgarantie.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    req = urllib.request.Request(url, headers={'Cache-Control': 'no-cache', 'Accept-Encoding': 'identity'})
    try:
        with opener.open(req, timeout=timeout) as response:
            status = response.status
            body = response.read(20 * 1024 * 1024 + 1)
            size = len(body)
            if size > 20 * 1024 * 1024:
                outcome, detail = 'content_error', 'response_above_20MiB_limit'
            elif status != 200:
                outcome, detail = 'http_error', f'HTTP {status}'
            elif expected_bytes is not None and size != expected_bytes:
                outcome, detail = 'content_error', f'expected {expected_bytes} bytes'
            elif expect_text and expect_text.encode('utf-8') not in body:
                outcome, detail = 'content_error', 'expected_text_missing'
            else:
                outcome = 'ok'
    except urllib.error.HTTPError as e:
        status, outcome, detail = e.code, 'http_error', f'HTTP {e.code}'
    except (TimeoutError, socket.timeout):
        outcome, detail = 'timeout', 'socket_timeout'
    except urllib.error.URLError as e:
        outcome = 'timeout' if isinstance(e.reason, (socket.timeout, TimeoutError)) else 'network_error'
        detail = type(e.reason).__name__
    except (ConnectionError, OSError) as e:
        outcome, detail = 'network_error', type(e).__name__
    except http.client.HTTPException as e:
        outcome, detail = 'network_error', type(e).__name__
    return {'utc_start': stamp, 'elapsed_ms': round((time.perf_counter() - start) * 1000, 3),
            'outcome': outcome, 'http_status': status, 'bytes': size, 'detail': detail}


def percentile(values, q):
    if not values:
        return None
    items = sorted(values)
    return items[max(0, math.ceil(q * len(items)) - 1)]


def summarize(rows, interval, timeout, elapsed):
    counts = collections.Counter(row['outcome'] for row in rows)
    ok = [row['elapsed_ms'] for row in rows if row['outcome'] == 'ok']
    longest = current = 0
    for row in rows:
        current = current + 1 if row['outcome'] != 'ok' else 0
        longest = max(longest, current)
    return {'samples': len(rows), 'counts': dict(counts), 'success_fraction': len(ok)/len(rows) if rows else None,
            'p50_ms_success_only': percentile(ok, .50), 'p95_ms_success_only': percentile(ok, .95),
            'longest_failed_sample_run': longest, 'requested_interval_s': interval,
            'socket_timeout_s': timeout, 'elapsed_s': round(elapsed, 3),
            'note': 'Stichproben, keine zeitgewichtete Verfuegbarkeit. Keine Ausfalldauer aus Anzahl*Intervall ableiten. Intervalle koennen bei Timeout laenger werden.'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('url', type=local_url)
    p.add_argument('--interval', type=float, default=2)
    p.add_argument('--count', type=int, default=300)
    p.add_argument('--timeout', type=float, default=2)
    p.add_argument('--expect-text', default='deck-homeserver-ok')
    p.add_argument('--expected-bytes', type=int)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if args.interval < 0 or not 1 <= args.count <= 1000000 or not 0 < args.timeout <= 60:
        p.error('interval >= 0, count 1..1000000, timeout > 0 und <= 60 erforderlich.')
    if args.expected_bytes is not None and not 0 <= args.expected_bytes <= 20*1024*1024:
        p.error('expected-bytes muss zwischen 0 und 20 MiB liegen.')
    summary_path = args.output.with_suffix(args.output.suffix + '.json')
    if args.output.exists() or summary_path.exists():
        p.error('Ausgabedatei existiert. Neuen Dateinamen verwenden.')
    rows, started = [], time.monotonic()
    with args.output.open('x', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['utc_start','elapsed_ms','outcome','http_status','bytes','detail'])
        writer.writeheader()
        try:
            for _ in range(args.count):
                tick = time.monotonic()
                row = request_once(args.url, args.timeout, args.expect_text, args.expected_bytes)
                writer.writerow(row); f.flush(); rows.append(row)
                if len(rows) < args.count:
                    time.sleep(max(0, args.interval - (time.monotonic() - tick)))
        except KeyboardInterrupt:
            print('Abgebrochen; bisherige Stichproben werden ausgewertet.')
    summary = summarize(rows, args.interval, args.timeout, time.monotonic()-started)
    summary['url'] = args.url
    with summary_path.open('x', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
