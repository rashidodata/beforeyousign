"""Operator-only validation of a licensed listing provider on 10-20 rental URLs.

Never fetches Idealista. Runs 0 paid requests unless --confirm-paid-requests is
passed, AND the operator provides a provider key, rights confirmation, and
import token in environment variables. Never prints or persists secrets.

Examples:
  python -m scripts.evaluate_provider provider_evaluation/listings.csv
  python -m scripts.evaluate_provider provider_evaluation/listings.csv --confirm-paid-requests
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

from beforeyousign.listings import parse_idealista_url
from beforeyousign.property_provider import ProviderError, import_listing, provider_configured

METRICS = ('monthly_rent_eur', 'area_sqm', 'bedrooms', 'bathrooms', 'floor', 'city_or_area')


def main(argv=None) -> int:
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument('csv_file', type=Path, help='CSV with url column; 10-20 genuine rental URLs, collected with permission')
    args.add_argument('--confirm-paid-requests', action='store_true', help='Actually use provider credits; cannot be undone')
    args.add_argument('--output', type=Path, default=Path('provider_evaluation/results.json'))
    a = args.parse_args(argv)
    try:
        with a.csv_file.open(encoding='utf-8-sig', newline='') as f:
            links = [row['url'].strip() for row in csv.DictReader(f) if row.get('url', '').strip()]
    except (OSError, KeyError) as exc:
        print('Cannot read CSV url column:', type(exc).__name__, file=sys.stderr)
        return 2
    if not 10 <= len(links) <= 20:
        print('Pilot expects 10 to 20 genuine rental URLs. Received:', len(links), file=sys.stderr)
        return 2
    try:
        ids = [parse_idealista_url(url)['listing_id'] for url in links]
    except ValueError as exc:
        print('Invalid listing URL:', str(exc), file=sys.stderr)
        return 2
    if len(set(ids)) != len(ids):
        print('Pilot has duplicate listing IDs.', file=sys.stderr)
        return 2
    if not a.confirm_paid_requests:
        print(json.dumps({'mode': 'dry_run', 'valid_urls': len(links), 'paid_requests': 0,
                          'message': 'No requests sent. Re-run with --confirm-paid-requests after obtaining legal rights and credentials.'}, indent=2))
        return 0
    if not provider_configured() or not os.getenv('BYS_IMPORT_OPERATOR_TOKEN'):
        print('Provider authorization, API key and operator token must be configured before a paid pilot.', file=sys.stderr)
        return 3

    entries = []
    for url, id_number in zip(links, ids):
        try:
            result = import_listing(url)
            fields = result.get('fields', {})
            observed = [key for key in METRICS if fields.get(key, {}).get('value') is not None]
            entries.append({'listing_id': id_number, 'status': result['status'], 'fields_found': observed,
                            'field_coverage': round(len(observed)/len(METRICS), 3)})
        except ProviderError:
            entries.append({'listing_id': id_number, 'status': 'provider_error', 'fields_found': [], 'field_coverage': 0})

    successes = [row for row in entries if row['status'] == 'imported']
    report = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'provider': 'opendata',
        'run': 'licensed operator pilot; no screenshots/photos collected',
        'count': len(entries),
        'success_count': len(successes),
        'success_rate': round(len(successes)/len(entries), 3),
        'average_field_coverage': round(sum(r['field_coverage'] for r in entries)/len(entries), 3),
        'methodology': 'Listing IDs from genuine rental links; source values are advertised, not independently verified.',
        'results': entries,
    }
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('Saved aggregated pilot results to', a.output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())