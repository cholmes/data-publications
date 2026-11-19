#!/usr/bin/env python3
"""Capture and verify NOAA's mesonet provider and restrictions pages."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.request import HTTPRedirectHandler, Request, build_opener

from bs4 import BeautifulSoup

BASE = 'https://madis.ncep.noaa.gov/'
POLICY_URLS = {
    'provider': BASE + 'mesonet_providers.shtml',
    'restrictions': BASE + 'madis_restrictions.shtml',
}
CATEGORIES = {'2', '2*', '3', '4'}
MAX_POLICY_BYTES = 1024 * 1024


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def fetch(url, limit):
    request = Request(
        url,
        headers={
            'User-Agent': 'MADIS-station-workflow/1',
            'Accept-Encoding': 'identity',
        },
    )
    with build_opener(NoRedirect()).open(request, timeout=90) as response:
        body = response.read(limit + 1)
        if (
            response.status != 200
            or response.url != url
            or len(body) > limit
            or not body
            or response.headers.get('Content-Encoding', 'identity') != 'identity'
        ):
            raise ValueError(f'Unexpected response from {url}')
    return body


def strict_providers(body):
    policy = {}
    for tr in BeautifulSoup(body, 'html.parser').find_all('tr'):
        cells = tr.find_all(['td', 'th'], recursive=False)
        if len(cells) != 7:
            continue
        texts = [' '.join(cell.get_text(' ', strip=True).split()) for cell in cells]
        if texts[5] not in CATEGORIES:
            continue
        provider = texts[1].removesuffix(' (subproviders)')
        subproviders = {}
        for sibling in tr.find_next_siblings('tr'):
            if len(sibling.find_all(['td', 'th'], recursive=False)) == 7:
                break
            for nested in sibling.find_all('tr'):
                children = nested.find_all(['td', 'th'], recursive=False)
                if not children or any(cell.name == 'th' for cell in children):
                    continue
                row = [cell.get_text(' ', strip=True) for cell in children]
                if len(row) != 3 or not row[0] or row[-1] not in CATEGORIES:
                    raise ValueError('Unknown or malformed subprovider permission')
                if row[0] in subproviders:
                    raise ValueError('Duplicate subprovider permission')
                subproviders[row[0]] = row[-1]
        if '(subproviders)' in texts[1] and not subproviders:
            raise ValueError('Declared subproviders have no permission rows')
        record = {'weather': texts[5], 'subproviders': subproviders}
        if not provider or (provider in policy and policy[provider] != record):
            raise ValueError('Missing or conflicting official provider ID')
        policy[provider] = record
    if not policy:
        raise ValueError('No explicit weather categories parsed')
    return policy


def classify(provider, policy):
    record = policy.get(provider)
    if not record:
        return 'unresolved'
    if record['weather'] != '3':
        return 'restricted'
    if any(category != '3' for category in record['subproviders'].values()):
        return 'unresolved'
    return 'eligible'


def verified_policy(root):
    hashes = {}
    for label, url in POLICY_URLS.items():
        body = (root / f'{label}.html').read_bytes()
        receipt = json.loads((root / f'{label}.receipt.json').read_bytes())
        checksum = hashlib.sha256(body).hexdigest()
        if (receipt['url'], receipt['status'], receipt['bytes'], receipt['sha256']) != (
            url,
            200,
            len(body),
            checksum,
        ) or not 0 < len(body) <= MAX_POLICY_BYTES:
            raise ValueError(f'Official NOAA receipt mismatch for {label}')
        hashes[label] = checksum
        if label == 'provider':
            policy = strict_providers(body)
    return policy, hashes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        'output', type=Path, help='new directory for NOAA policy captures'
    )
    args = parser.parse_args()
    args.output.mkdir(mode=0o700)
    for label, url in POLICY_URLS.items():
        body = fetch(url, MAX_POLICY_BYTES)
        receipt = {
            'url': url,
            'status': 200,
            'bytes': len(body),
            'sha256': hashlib.sha256(body).hexdigest(),
            'captured_at': datetime.now(timezone.utc).isoformat(),
        }
        (args.output / f'{label}.html').write_bytes(body)
        (args.output / f'{label}.receipt.json').write_text(
            json.dumps(receipt, indent=2) + '\n'
        )
    policy, hashes = verified_policy(args.output)
    print(json.dumps({'providers': len(policy), 'sha256': hashes}, indent=2))


if __name__ == '__main__':
    main()
