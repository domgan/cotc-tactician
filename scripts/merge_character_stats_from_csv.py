#!/usr/bin/env python3
"""
Merge character stats/tiers from CSV into existing YAML without touching curated fields.

Uses ruamel.yaml round-trip mode to preserve comments and key order.

Usage:
    python scripts/merge_character_stats_from_csv.py --dry-run
    python scripts/merge_character_stats_from_csv.py
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from ruamel.yaml import YAML

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from _character_ids import find_default_character_csv, resolve_character_id  # noqa: E402
from _csv_row import row_to_stats_update  # noqa: E402

STAT_KEYS = (
    "rarity",
    "job",
    "influence",
    "origin",
    "weakness_coverage",
    "hp",
    "p_atk",
    "p_def",
    "e_atk",
    "e_def",
    "speed",
    "crit",
    "sp",
    "hp_120",
    "p_atk_120",
    "p_def_120",
    "e_atk_120",
    "e_def_120",
    "speed_120",
    "crit_120",
    "sp_120",
    "has_blessing_of_lantern",
    "has_limit_break",
    "gl_tier",
    "jp_tier",
    "last_updated",
    "data_source",
)


def _yaml_loader() -> YAML:
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.default_flow_style = False
    yaml.width = 4096
    return yaml


def merge_stats_into_yaml(yaml_path: Path, update: dict, yaml: YAML) -> bool:
    """Apply stat-only updates to an existing character YAML file."""
    if not yaml_path.exists():
        return False

    with yaml_path.open(encoding="utf-8") as f:
        data = yaml.load(f)

    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in {yaml_path}")

    data["display_name"] = update["display_name"]

    for key in STAT_KEYS:
        value = update.get(key)
        if value is None:
            continue
        if key in ("gl_tier", "jp_tier") and value is None:
            continue
        data[key] = value

    with yaml_path.open("w", encoding="utf-8") as f:
        yaml.dump(data, f)

    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge CSV stats into character YAML")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--csv-path", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    project_root = SCRIPT_DIR.parent
    csv_path = args.csv_path or find_default_character_csv(project_root)
    output_dir = project_root / "data" / "characters"

    if csv_path is None or not csv_path.exists():
        print(f"ERROR: CSV file not found: {csv_path}")
        return 1

    with csv_path.open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    print(f"Using CSV: {csv_path}")
    print(f"Found {len(rows)} characters in CSV")

    if args.limit:
        rows = rows[: args.limit]

    yaml = _yaml_loader()
    updated = 0
    missing = 0
    errors = 0

    for row in rows:
        name = row.get("Name", "").strip()
        if not name:
            continue

        char_id = resolve_character_id(name)
        yaml_path = output_dir / f"{char_id}.yaml"
        update = row_to_stats_update(row)

        try:
            if not yaml_path.exists():
                print(f"  MISSING YAML: {char_id} ({name})")
                missing += 1
                continue

            if args.dry_run:
                print(f"  WOULD UPDATE: {char_id}")
            else:
                merge_stats_into_yaml(yaml_path, update, yaml)
                print(f"  UPDATED: {char_id}")
            updated += 1
        except Exception as exc:
            print(f"  ERROR: {char_id} - {exc}")
            errors += 1

    print("\nSummary:")
    print(f"  Updated: {updated}")
    print(f"  Missing YAML: {missing}")
    print(f"  Errors: {errors}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
