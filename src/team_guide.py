"""Load team-building guide from reference YAML for MCP tools."""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

import yaml

EX_SCALING_PATTERNS: dict[str, Any] = {
    "ex1": {
        "hp_multiplier": "~2x base",
        "speed_bonus": "+50-100",
        "actions_per_turn": 2,
        "shield_bonus": "+3-5",
        "provoke_immunity": True,
        "recommended_hp": 3000,
    },
    "ex2": {
        "hp_multiplier": "~3x base",
        "speed_bonus": "+100-150",
        "actions_per_turn": "2-3",
        "shield_bonus": "+5-7",
        "provoke_immunity": True,
        "recommended_hp": 3500,
    },
    "ex3": {
        "hp_multiplier": "~5x base",
        "speed_bonus": "+150-250",
        "actions_per_turn": 3,
        "shield_bonus": "+8-12",
        "provoke_immunity": True,
        "recommended_hp": 4000,
        "notes": (
            "Extreme difficulty. Requires speedkill (Solon+Primrose EX) "
            "or full turtle strategy."
        ),
    },
}


@functools.lru_cache(maxsize=4)
def _load_llm_guidelines_yaml(data_dir_str: str) -> dict[str, Any]:
    """Parse llm_guidelines.yaml once per resolved data_dir path."""
    path = Path(data_dir_str) / "reference" / "llm_guidelines.yaml"
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _build_role_priorities(roles: dict[str, Any]) -> dict[str, Any]:
    tank = roles.get("tank", {})
    tank_subtypes = tank.get("subtypes", [])
    subtype_names = [
        s.get("name", "").lower().replace(" tank", "").replace(" ", "_")
        for s in tank_subtypes
    ]
    # Normalize subtype keys: "Provoke Tank" -> "provoke", "HP Barrier Tank" -> "hp_barrier"
    normalized_subtypes: list[str] = []
    for name in subtype_names:
        if "hp_barrier" in name or "barrier" in name:
            normalized_subtypes.append("hp_barrier")
        elif "provoke" in name:
            normalized_subtypes.append("provoke")
        elif "dodge" in name:
            normalized_subtypes.append("dodge")
        elif "cover" in name:
            normalized_subtypes.append("cover")
        else:
            normalized_subtypes.append(name)

    dodge_chars: list[str] = []
    cover_chars: list[str] = []
    for st in tank_subtypes:
        st_name = st.get("name", "").lower()
        chars = st.get("characters", [])
        if "dodge" in st_name:
            dodge_chars.extend(chars)
        if "cover" in st_name:
            cover_chars.extend(chars)

    ex_notes_parts = ["Most EX bosses are provoke immune!"]
    if dodge_chars:
        dodge_names = ", ".join(dodge_chars[:3])
        ex_notes_parts.append(f"Use dodge ({dodge_names})")
    if cover_chars:
        cover_names = ", ".join(cover_chars)
        ex_notes_parts.append(f"or cover ({cover_names})")
    ex_notes = " ".join(ex_notes_parts) + "."

    tank_top: list[str] = []
    for st in tank_subtypes:
        tank_top.extend(st.get("characters", []))
    # Prefer cover/dodge picks for EX context
    seen: set[str] = set()
    tank_top_picks: list[str] = []
    for cid in cover_chars + dodge_chars + tank_top:
        if cid not in seen:
            seen.add(cid)
            tank_top_picks.append(cid)

    healer = roles.get("healer", {})
    buffer = roles.get("buffer", {})
    debuffer = roles.get("debuffer", {})
    breaker = roles.get("breaker", {})
    dps = roles.get("dps", {})

    debuff_categories = debuffer.get("categories", [])
    debuff_priority = debuff_categories[0] if debuff_categories else "E.ATK Down"

    return {
        "tank": {
            "subtypes": normalized_subtypes or ["provoke", "dodge", "cover", "hp_barrier"],
            "ex_notes": ex_notes,
            "top_picks": tank_top_picks[:6],
        },
        "healer": {
            "key_skills": healer.get("key_skills", []),
            "top_picks": healer.get("top_healers", []),
        },
        "buffer": {
            "buff_caps": buffer.get("buff_caps", "30% per category"),
            "categories": buffer.get("categories", []),
            "top_picks": buffer.get("top_buffers", []),
        },
        "debuffer": {
            "cap": debuffer.get("debuff_caps", "30% per category"),
            "priority": debuff_priority,
            "top_picks": debuffer.get("top_debuffers", []),
        },
        "breaker": {
            "notes": (breaker.get("notes") or "").strip(),
            "top_picks": breaker.get("top_breakers", []),
        },
        "dps": {
            "damage_formula": "Weakness (2.5x) + Break (2x) = 5x damage window",
            "buff_categories": [
                "Active skills (30%)",
                "Passives (30%)",
                "Ultimate (varies)",
                "Pet",
                "Divine Beast",
            ],
            "top_picks": dps.get("top_dps", []),
        },
    }


def _flatten_common_mistakes(mistakes: list[dict[str, str]]) -> list[str]:
    return [
        f"{item['mistake']} → {item['correct']}"
        for item in mistakes
        if item.get("mistake") and item.get("correct")
    ]


def _build_recommendation_format(fmt: dict[str, Any]) -> dict[str, Any]:
    sections = fmt.get("sections", [])
    numbered = [
        f"{i + 1}. {s.get('name', 'Section')}"
        for i, s in enumerate(sections)
    ]
    return {"sections": numbered}


def load_team_building_guide(data_dir: Path) -> dict[str, Any]:
    """
    Build MCP team-building guide dict from reference YAML.

    Parsed YAML is cached in memory per resolved data_dir (see _load_llm_guidelines_yaml).
    """
    guidelines = _load_llm_guidelines_yaml(str(data_dir.resolve()))
    roles = guidelines.get("roles", {})

    return {
        "party_structure": {
            "total_characters": 8,
            "front_row": 4,
            "back_row": 4,
            "notes": "ALWAYS recommend 8 characters. Front row is active, back row swaps in.",
        },
        "skill_slots": {
            "awakening_0_1": 3,
            "awakening_2_plus": 4,
            "notes": "Recommend specific skills to equip for each character.",
        },
        "ex_scaling_patterns": EX_SCALING_PATTERNS,
        "role_priorities": _build_role_priorities(roles),
        "recommendation_format": _build_recommendation_format(
            guidelines.get("team_recommendation_format", {})
        ),
        "common_mistakes": _flatten_common_mistakes(guidelines.get("common_mistakes", [])),
    }
