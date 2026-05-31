"""Shared CSV row parsing for character import scripts."""

from __future__ import annotations

from datetime import date

from _character_ids import resolve_character_id


def parse_rarity(class_field: str) -> int:
    """Parse rarity from star emoji field."""
    star_count = class_field.count("⭐️")
    if star_count == 0:
        star_count = len(class_field) // 2 if class_field else 5
    return max(3, min(5, star_count))


def parse_weakness_coverage(weakness_str: str) -> list[str]:
    """Parse 'Weakness to hit' field into normalized list."""
    if not weakness_str:
        return []

    name_map = {
        "polearm": "polearm",
        "spear": "polearm",
        "lightning": "lightning",
        "thunder": "lightning",
    }

    items = [w.strip().lower() for w in weakness_str.split(",")]
    return [name_map.get(item, item) for item in items if item]


def parse_influence(influence_str: str) -> str:
    if not influence_str:
        return ""
    return influence_str.strip().lower()


def parse_job(job_str: str) -> str:
    if not job_str:
        return ""
    return job_str.strip().lower()


def parse_int_or_none(value: str) -> int | None:
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def bool_from_availability(value: str) -> bool:
    if not value:
        return False
    return "available in gl" in value.lower()


def row_to_stats_update(row: dict) -> dict:
    """Extract stat/tier fields from a CSV row for YAML merge."""
    name = row.get("Name", "").strip()
    char_id = resolve_character_id(name)

    update: dict = {
        "id": char_id,
        "display_name": name,
        "rarity": parse_rarity(row.get("Class", "")),
        "job": parse_job(row.get("Job", "")),
        "influence": parse_influence(row.get("Influence", "")),
        "origin": row.get("Continent", "").strip(),
        "weakness_coverage": parse_weakness_coverage(row.get("Weakness to hit", "")),
        "hp": parse_int_or_none(row.get("HP", "")),
        "hp_120": parse_int_or_none(row.get("HP (Lv. 120)", "")),
        "p_atk": parse_int_or_none(row.get("P.Atk", "")),
        "p_atk_120": parse_int_or_none(row.get("P.Atk (Lv. 120)", "")),
        "p_def": parse_int_or_none(row.get("P.Def", "")),
        "p_def_120": parse_int_or_none(row.get("P.Def (Lv. 120)", "")),
        "e_atk": parse_int_or_none(row.get("E.Atk", "")),
        "e_atk_120": parse_int_or_none(row.get("E.Atk (Lv. 120)", "")),
        "e_def": parse_int_or_none(row.get("E.Def", "")),
        "e_def_120": parse_int_or_none(row.get("E.Def (Lv. 120)", "")),
        "speed": parse_int_or_none(row.get("Spd", "")),
        "speed_120": parse_int_or_none(row.get("Spd (Lv. 120)", "")),
        "crit": parse_int_or_none(row.get("Crit", "")),
        "crit_120": parse_int_or_none(row.get("Crit (Lv. 120)", "")),
        "sp": parse_int_or_none(row.get("SP", "")),
        "sp_120": parse_int_or_none(row.get("SP (Lv. 120)", "")),
        "gl_tier": row.get("GL Tier", "").strip() or None,
        "jp_tier": row.get("JP Tier", "").strip() or None,
        "has_blessing_of_lantern": bool_from_availability(row.get("Blessing of the Lantern", "")),
        "has_limit_break": bool_from_availability(row.get("Class Breakthrough", "")),
        "last_updated": date.today().isoformat(),
        "data_source": "Community spreadsheet CSV export",
    }
    return update
