#!/usr/bin/env python3
"""
Report character data quality: empty roles, junk skill names, truncated effects.

Usage:
    uv run python scripts/audit_character_data.py
    uv run python scripts/audit_character_data.py --worst 25
"""

import argparse
import re
from collections import Counter
from pathlib import Path

import yaml

CHARACTERS_DIR = Path(__file__).parent.parent / "data" / "characters"

JUNK_NAME = re.compile(r"^(Lv\.\d+.*|\(Initial\)|\(EX\)|.*\|.*)$")
TRUNCATED_ENDING = re.compile(r"\b(Phys|Elem|Atk|Def|Res|their|with|deal|and|of)$")


def _texts(entry: dict) -> list[str]:
    texts = list(entry.get("effects") or [])
    for key in ("effect", "limit_break_upgrade"):
        if entry.get(key):
            texts.append(entry[key])
    return texts


def audit_character(data: dict) -> Counter:
    counts: Counter = Counter()
    skills = data.get("skills") or []
    counts["skills"] = len(skills)
    for skill in skills:
        name = skill.get("name")
        if not name:
            counts["unnamed_skills"] += 1
        elif JUNK_NAME.match(name):
            counts["junk_name_skills"] += 1
    for entry in skills + (data.get("passives") or []):
        for text in _texts(entry):
            if TRUNCATED_ENDING.search(text.strip().rstrip(".")):
                counts["truncated_effects"] += 1
    if not data.get("roles"):
        counts["empty_roles"] += 1
    if data.get("buff_categories"):
        counts["buff_categories"] += 1
    if data.get("tank_type"):
        counts["tank_type"] += 1
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worst", type=int, default=15, help="List N worst characters")
    args = parser.parse_args()

    totals: Counter = Counter()
    confidence: Counter = Counter()
    per_char: dict[str, Counter] = {}

    for path in sorted(CHARACTERS_DIR.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        counts = audit_character(data)
        per_char[data.get("id", path.stem)] = counts
        totals.update(counts)
        totals["characters"] += 1
        confidence[data.get("data_confidence", "missing")] += 1

    for key in (
        "characters",
        "skills",
        "empty_roles",
        "unnamed_skills",
        "junk_name_skills",
        "truncated_effects",
        "buff_categories",
        "tank_type",
    ):
        print(f"{key:20} {totals[key]}")
    print(f"{'data_confidence':20} {dict(confidence)}")

    def badness(c: Counter) -> int:
        return c["junk_name_skills"] * 2 + c["truncated_effects"] + c["empty_roles"] * 3

    worst = sorted(per_char.items(), key=lambda kv: badness(kv[1]), reverse=True)[: args.worst]
    print("\nworst:")
    for char_id, c in worst:
        print(
            f"  {char_id:32} junk={c['junk_name_skills']} "
            f"truncated={c['truncated_effects']} empty_roles={c['empty_roles']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
