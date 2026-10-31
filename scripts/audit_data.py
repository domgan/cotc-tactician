#!/usr/bin/env python3
"""
Report data gaps across characters, bosses and teams, plus roster-based priorities.

Usage:
    uv run python scripts/audit_data.py
    uv run python scripts/audit_data.py --worst 25 --list
"""

import argparse
import os
import re
from collections import Counter
from pathlib import Path

import yaml

DATA_DIR = Path(__file__).parent.parent / "data"
JUNK_NAME = re.compile(r"^(Lv\.\d+.*|\(Initial\)|\(EX\)|.*\|.*)$")
TRUNCATED_ENDING = re.compile(r"\b(Phys|Elem|Atk|Def|Res|their|with|deal|and|of)$")


def load_dir(kind: str) -> dict[str, dict]:
    files = sorted((DATA_DIR / kind).glob("*.yaml"))
    return {
        p.stem: yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        for p in files
        if not p.name.startswith("_")
    }


def audit_character(data: dict) -> Counter:
    counts: Counter = Counter()
    skills = data.get("skills") or []
    for skill in skills:
        name = skill.get("name")
        if name and JUNK_NAME.match(name):
            counts["junk_name_skills"] += 1
    for entry in skills + (data.get("passives") or []):
        texts = list(entry.get("effects") or []) + [entry.get("effect") or ""]
        counts["truncated_effects"] += sum(
            1 for t in texts if t and TRUNCATED_ENDING.search(t.strip().rstrip("."))
        )
    counts["empty_roles"] += not data.get("roles")
    counts["no_buff_categories"] += not (
        data.get("buff_categories") or data.get("debuff_categories")
    )
    counts["no_tank_type"] += not data.get("tank_type")
    counts["no_gl_tier"] += not data.get("gl_tier")
    return counts


def boss_has_weaknesses(data: dict) -> bool:
    sources = [data.get("weaknesses") or {}] + [
        e.get("weaknesses") or {} for e in data.get("enemies") or []
    ]
    return any(w.get("elements") or w.get("weapons") for w in sources)


def audit_bosses(bosses: dict[str, dict]) -> dict[str, list[str]]:
    gaps: dict[str, list[str]] = {
        "no_weaknesses": [],
        "todo_strategy": [],
        "ex_without_base_id": [],
        "ex_base_missing": [],
        "ex_without_hp": [],
        "id_filename_mismatch": [],
    }
    for stem, data in bosses.items():
        if data.get("id") != stem:
            gaps["id_filename_mismatch"].append(stem)
        if not boss_has_weaknesses(data):
            gaps["no_weaknesses"].append(stem)
        if "TODO" in str(data.get("general_strategy", "")):
            gaps["todo_strategy"].append(stem)
        if data.get("ex_rank"):
            base = data.get("base_boss_id")
            if not base:
                gaps["ex_without_base_id"].append(stem)
            elif base not in bosses:
                gaps["ex_base_missing"].append(stem)
            if not data.get("hp"):
                gaps["ex_without_hp"].append(stem)
    return gaps


def audit_teams(teams: dict[str, dict], bosses: dict, characters: dict) -> dict[str, list[str]]:
    gaps: dict[str, list[str]] = {"unknown_boss": [], "unresolved_names": [], "unverified": []}
    boss_ids_with_teams = set()
    for stem, team in teams.items():
        boss_id = team.get("boss_id")
        if boss_id:
            boss_ids_with_teams.add(boss_id)
            if boss_id not in bosses:
                gaps["unknown_boss"].append(f"{stem} -> {boss_id}")
        if team.get("unresolved_character_ids"):
            gaps["unresolved_names"].append(
                f"{stem}: {', '.join(team['unresolved_character_ids'])}"
            )
        if not team.get("verified"):
            gaps["unverified"].append(stem)
    ex3_bosses = [b for b, d in bosses.items() if d.get("ex_rank") == "ex3"]
    gaps["ex3_without_specific_team"] = [b for b in ex3_bosses if b not in boss_ids_with_teams]
    return gaps


def load_roster() -> dict:
    path = Path(os.environ.get("COTC_ROSTER_FILE", Path.home() / ".cotc-tactician" / "roster.yaml"))
    if not path.is_file():
        return {}
    return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("characters") or {}


def print_gaps(title: str, gaps: dict[str, list[str]], show: bool) -> None:
    print(f"\n## {title}")
    for key, items in gaps.items():
        print(f"{key:28} {len(items)}")
        if show and items:
            for item in items:
                print(f"    {item}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worst", type=int, default=10, help="List N worst characters")
    parser.add_argument("--list", action="store_true", help="List every gap item")
    args = parser.parse_args()

    characters, bosses, teams = load_dir("characters"), load_dir("bosses"), load_dir("teams")

    totals: Counter = Counter()
    per_char = {cid: audit_character(d) for cid, d in characters.items()}
    for counts in per_char.values():
        totals.update(counts)
    confidence = Counter(d.get("data_confidence", "missing") for d in characters.values())

    print(f"## Characters ({len(characters)})")
    for key in (
        "junk_name_skills",
        "truncated_effects",
        "empty_roles",
        "no_buff_categories",
        "no_tank_type",
        "no_gl_tier",
    ):
        print(f"{key:28} {totals[key]}")
    print(f"{'data_confidence':28} {dict(confidence)}")

    def badness(c: Counter) -> int:
        return c["junk_name_skills"] * 2 + c["truncated_effects"] + c["empty_roles"] * 3

    if args.worst:
        print("worst:")
        for cid, c in sorted(per_char.items(), key=lambda kv: badness(kv[1]), reverse=True)[
            : args.worst
        ]:
            print(f"    {cid:32} junk={c['junk_name_skills']} truncated={c['truncated_effects']}")

    print_gaps(f"Bosses ({len(bosses)})", audit_bosses(bosses), args.list)
    print_gaps(f"Teams ({len(teams)})", audit_teams(teams, bosses, characters), args.list)

    roster = load_roster()
    if roster:
        invested = {
            cid: e
            for cid, e in roster.items()
            if e.get("awakening", 0) > 0 or e.get("au") or e.get("ult_level", 0) > 0
        }
        missing_roles = sorted(cid for cid in roster if per_char.get(cid, Counter())["empty_roles"])
        print(f"\n## Your roster ({len(roster)} owned, {len(invested)} invested)")
        print(f"{'owned_without_roles':28} {len(missing_roles)}")
        priority = [cid for cid in missing_roles if cid in invested]
        print(f"{'invested_without_roles':28} {len(priority)}  <- curate these first")
        if args.list:
            print("    " + ", ".join(priority))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
