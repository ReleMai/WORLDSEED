"""Classify and persist the item database in its shared canonical order."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from worldseed.content.item_catalog import canonical_item_catalog


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='reject stale classification or ordering')
    args = parser.parse_args()
    path = ROOT / 'worldseed' / 'data' / 'items.json'
    original = json.loads(path.read_text(encoding='utf-8'))
    classified = canonical_item_catalog(original)
    if args.check and original != classified:
        print('Item database classification/order needs updating.')
        return 1
    if not args.check:
        path.write_text(json.dumps(classified, indent=2) + '\n', encoding='utf-8')
    print(f'{len(classified)} items in canonical category/subcategory/name/ID order.')
    print(dict(Counter(row['category'] for row in classified)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
