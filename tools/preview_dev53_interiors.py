"""Offline production-rendered day/night QA, not a live gameplay test."""
from pathlib import Path
import argparse
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.preview_dev52_content import contact_sheet, production_interiors
from worldseed.presentation.visuals import VisualRegistry


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    visuals = VisualRegistry.load_default()
    rows = [(name.replace('_', ' ').title(), visuals.resolve(visuals.ref('interiors', 'core:'+name+'_piece')))
            for name in ('hearth_rug','bedside_runner','hall_carpet')]
    contact_sheet(rows, args.output_dir / 'dev53-carpets.png', columns=3)
    for phase, minute in (('day',720),('night',1380)):
        output = args.output_dir / phase
        output.mkdir(exist_ok=True)
        production_interiors(output, minute)


if __name__ == '__main__':
    main()
