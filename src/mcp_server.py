"""
MCP Server for COTC Tactician.

Exposes the retrieval system as MCP tools that can be called by
Claude in Cursor or other MCP-compatible clients.

Usage:
    cotc-tactician mcp-serve

IMPORTANT: MCP uses stdio for JSON-RPC communication.
- NEVER print() or write to stdout - it corrupts the protocol
- All logging must go to stderr
- Library output (progress bars, etc.) must be suppressed
"""

import logging
import os
import sys
from pathlib import Path
from typing import Any

# Suppress stdout from libraries BEFORE importing them
# This prevents progress bars and other output from corrupting MCP protocol
os.environ["TQDM_DISABLE"] = "1"  # Disable tqdm progress bars
os.environ["TRANSFORMERS_VERBOSITY"] = "error"  # Suppress transformers logging

from mcp.server.fastmcp import FastMCP
from pydantic import ValidationError

from .models import RolePriority, RosterEntry
from .retrieval import RetrievalService, _normalize_weakness, strength_sort_key
from .roster import (
    import_roster_yaml,
    known_character_ids,
    load_roster_with_meta,
    resolve_roster,
    roster_entry_for_character,
    roster_path,
    teams_for_roster,
    upsert_roster_characters,
)
from .roster import (
    remove_roster_characters as remove_chars_from_roster,
)
from .team_guide import load_team_building_guide
from .vector_store import VectorStore

# Configure logging to stderr only (stdout is reserved for MCP protocol)
# Use WARNING level to minimize noise during MCP operation
logging.basicConfig(
    level=logging.WARNING,
    format="%(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)],
    force=True,  # Override any existing config
)

# Suppress noisy loggers from dependencies
logging.getLogger("sentence_transformers").setLevel(logging.ERROR)
logging.getLogger("chromadb").setLevel(logging.ERROR)
logging.getLogger("httpx").setLevel(logging.ERROR)

logger = logging.getLogger(__name__)

# Initialize FastMCP server
mcp = FastMCP("cotc-tactician")

# Global retrieval service (initialized lazily)
_retrieval: RetrievalService | None = None


def get_data_dir() -> Path:
    """Get the data directory path."""
    if env_path := os.environ.get("COTC_DATA_DIR"):
        return Path(env_path)
    # Default to ./data relative to project root
    return Path(__file__).parent.parent / "data"


def get_vector_store_dir() -> Path:
    """Get the vector store directory path."""
    if env_path := os.environ.get("COTC_VECTOR_DIR"):
        return Path(env_path)
    return Path(__file__).parent.parent / ".vectordb"


def get_retrieval() -> RetrievalService:
    """Get the retrieval service, reloading data when YAML files changed on disk."""
    global _retrieval
    if _retrieval is None:
        _retrieval = RetrievalService(
            data_dir=get_data_dir(),
            vector_store=VectorStore(persist_directory=get_vector_store_dir()),
        )
    _retrieval.initialize()
    return _retrieval


def character_to_dict(char: Any) -> dict:
    """Full character kit for JSON output (every skill, passive and stacking category)."""
    kit_fields = {
        "skills",
        "passives",
        "a4_accessory",
        "unique_mechanics",
        "buff_categories",
        "debuff_categories",
    }
    return {
        "id": char.id,
        "display_name": char.display_name,
        "job": char.job.value,
        "rarity": char.rarity,
        "weakness_coverage": char.weakness_coverage,
        "roles": [r.value for r in char.roles],
        "role_notes": char.role_notes,
        "tank_type": char.tank_type.value if char.tank_type else None,
        "gl_tier": char.gl_tier,
        "jp_tier": char.jp_tier,
        "stats": {
            "hp": char.hp,
            "p_atk": char.p_atk,
            "e_atk": char.e_atk,
            "speed": char.speed,
        },
        **char.model_dump(
            mode="json", include=kit_fields, exclude_none=True, exclude_defaults=True
        ),
        "data_confidence": char.data_confidence.value,
        "data_source": char.data_source,
    }


def character_summary(char: Any, roster: Any = None) -> dict:
    """Create a brief summary of a character for list results."""
    summary = {
        "id": char.id,
        "display_name": char.display_name,
        "job": char.job.value,
        "weakness_coverage": char.weakness_coverage,
        "roles": [r.value for r in char.roles],
        "gl_tier": char.gl_tier,
        "jp_tier": char.jp_tier,
    }
    investment = roster_entry_for_character(roster, char.id)
    if investment:
        summary["investment"] = investment
    return summary


def resolve_pool(available_characters: list[str] | None) -> tuple[Any, list[str] | None, Any]:
    """(retrieval, filter_ids, roster) for a tool call; filter_ids None = full database."""
    retrieval = get_retrieval()
    ids, roster = resolve_roster(available_characters, known_ids=known_character_ids(retrieval))
    return retrieval, ids, roster


def pool_meta(filter_ids: list[str] | None) -> dict:
    """Tell the caller whether results are limited to owned characters."""
    return {
        "roster_applied": filter_ids is not None,
        "recommendation_pool": "roster" if filter_ids is not None else "full_database",
    }


def plan_team_character_entry(char: Any, roster: Any = None) -> dict:
    """Compact character entry for plan_team_for_boss recommendations."""
    entry = {
        "id": char.id,
        "display_name": char.display_name,
        "job": char.job.value,
        "roles": [r.value for r in char.roles] if char.roles else [],
        "jp_tier": char.jp_tier,
    }
    investment = roster_entry_for_character(roster, char.id)
    if investment:
        entry["investment"] = investment
    return entry


def team_slot_to_dict(slot: Any) -> dict:
    """Convert a TeamSlot to a JSON-friendly dict."""
    return {
        "position": slot.position,
        "character_id": slot.character_id,
        "role_in_team": slot.role_in_team.value,
        "is_required": slot.is_required,
        "substitutes": slot.substitutes,
        "key_skills_used": slot.key_skills_used,
    }


def team_to_dict(team: Any) -> dict:
    """Convert a Team model to a JSON-friendly dict for MCP output."""
    result = {
        "id": team.id,
        "name": team.name,
        "boss_id": team.boss_id,
        "strategy_type": team.strategy_type.value,
        "investment_level": team.investment_level.value,
        "front_line": [team_slot_to_dict(s) for s in team.front_line],
        "back_line": [team_slot_to_dict(s) for s in team.back_line],
        "why_it_works": team.why_it_works,
        "key_synergies": team.key_synergies,
        "verified": team.verified,
        "data_confidence": team.data_confidence.value,
    }
    if team.target_ex_rank:
        result["target_ex_rank"] = team.target_ex_rank.value
    if team.survival_strategy:
        result["survival_strategy"] = team.survival_strategy.value
    if team.minimum_hp_recommended is not None:
        result["minimum_hp_recommended"] = team.minimum_hp_recommended
    if team.buff_category_coverage:
        result["buff_category_coverage"] = team.buff_category_coverage.model_dump(exclude_none=True)
    return result


# =============================================================================
# MCP TOOLS
# =============================================================================


@mcp.tool()
def search_characters(
    query: str,
    available_characters: list[str] | None = None,
    limit: int = 8,
) -> dict:
    """
    Semantic search over character names, roles, role notes and weakness coverage.

    Good for fuzzy discovery ("wind fan support"). Embeddings do NOT include skill
    text — to find a specific effect (Def down, Damage Limit up, taunt) use
    search_skill_effects instead.

    Args:
        query: Natural language description of what you're looking for.
        available_characters: Optional ID filter. If omitted, the saved roster applies.
        limit: Maximum number of results (default: 8).

    Returns:
        roster_applied, recommendation_pool, characters (summaries + investment).
    """
    retrieval, filter_ids, roster = resolve_pool(available_characters)
    meta = pool_meta(filter_ids)
    if filter_ids is not None and not filter_ids:
        return {**meta, "characters": []}

    results = retrieval.vector_store.search_characters(
        query=query,
        n_results=limit,
        where={"id": {"$in": filter_ids}} if filter_ids is not None else None,
    )
    characters = [
        character_summary(char, roster)
        for result in results
        if (char := retrieval.get_character_by_id(result["id"]))
    ]
    return {**meta, "characters": characters}


@mcp.tool()
def get_character(character_id: str) -> dict | str:
    """
    Get the full kit for one character.

    Includes every skill (with unlock_tier, SP, effects, level/TP upgrades, 6★ upgrade),
    passives, EX, ultimate, A4 accessory, glossary terms (unique_mechanics) and curated
    buff/debuff stacking categories. With a saved roster, includes investment
    (awakening, battle_skill_slots) for loadout planning.

    Args:
        character_id: The character's unique ID (e.g., "richard", "primrose-ex").

    Returns:
        Full character details or error message if not found.
    """
    retrieval, _, roster = resolve_pool(None)
    char = retrieval.get_character_by_id(character_id)
    if char is None:
        return f"Character '{character_id}' not found."

    result = character_to_dict(char)
    investment = roster_entry_for_character(roster, character_id)
    if investment:
        result["investment"] = investment
    else:
        result["loadout_note"] = (
            "No roster entry — assume 3 battle slots (A0-A1) unless user confirms A2+"
        )
    return result


@mcp.tool()
def search_skill_effects(
    terms: list[str],
    sources: list[str] | None = None,
    match_all: bool = False,
    available_characters: list[str] | None = None,
    limit: int = 15,
) -> dict:
    """
    Find characters whose kit text matches effect terms. Main tool for "who in my
    roster can do X" when building teams for hard fights.

    Searches skills, TP skills, EX, ultimate, passives and A4 accessories using the
    game's own wording. Terms are case-insensitive regexes matched per effect
    sentence. Useful phrasings:
    - Def down: "lower.*Phys\\. Def", "lower.*Elem\\. Def"
    - Res down: "lower.*Elem\\. Res", "lower.*Sword Res", "lower.*Fire Res"
    - Atk buffs: "raise.*Phys\\. Atk", "raise.*Elem\\. Atk", "potency"
    - Damage cap: "Damage Limit"
    - Survival: "taunt|provoke", "Sidestep|evade|avoid", "cover", "HP barrier|shield of"
    - Utility: "BP", "Act faster", "Reduce Shield Points"

    Args:
        terms: Regex terms; an entry matches if any term hits (all, with match_all).
        sources: Optional filter: active, tp, ex, special (ultimate), passive, a4.
        match_all: Require every term within the same skill/passive.
        available_characters: Optional ID filter. If omitted, the saved roster applies.
        limit: Max characters returned (strongest JP tier first).

    Returns:
        roster_applied, recommendation_pool, count, results: [{id, display_name, job,
        jp_tier, investment?, matches: [{source, name?, unlock_tier?, sp_cost?, matched}]}]
    """
    retrieval, filter_ids, roster = resolve_pool(available_characters)
    found = retrieval.search_kit_effects(
        terms, character_ids=filter_ids, sources=sources, match_all=match_all
    )
    results = []
    for char, matches in found[:limit]:
        entry = {
            "id": char.id,
            "display_name": char.display_name,
            "job": char.job.value,
            "jp_tier": char.jp_tier,
            "matches": matches,
        }
        investment = roster_entry_for_character(roster, char.id)
        if investment:
            entry["investment"] = investment
        results.append(entry)
    return {**pool_meta(filter_ids), "count": len(found), "results": results}


@mcp.tool()
def find_by_weakness(
    weakness_types: list[str],
    available_characters: list[str] | None = None,
    limit: int = 8,
) -> dict:
    """
    Find characters that can hit specific enemy weaknesses (strongest JP tier first).

    Args:
        weakness_types: sword, polearm, dagger, axe, bow, staff, tome, fan,
                        fire, ice, lightning, wind, light, dark.
        available_characters: Optional ID filter. If omitted, the saved roster applies.
        limit: Maximum number of results (default: 8).

    Returns:
        roster_applied, recommendation_pool, characters with matching_weaknesses.
    """
    retrieval, filter_ids, roster = resolve_pool(available_characters)
    requested = {_normalize_weakness(w) for w in weakness_types}

    characters = []
    for char in retrieval.find_characters_by_weakness_any(requested, character_ids=filter_ids):
        summary = character_summary(char, roster)
        summary["matching_weaknesses"] = sorted(
            requested & {_normalize_weakness(w) for w in char.weakness_coverage}
        )
        characters.append(summary)
    return {**pool_meta(filter_ids), "characters": characters[:limit]}


@mcp.tool()
def list_by_tier(
    tier: str = "S",
    server: str = "jp",
    available_characters: list[str] | None = None,
    limit: int = 20,
) -> dict:
    """
    List characters whose community tier label contains the given tier.

    JP tiers are more up-to-date; GL tiers reflect Global server meta.

    Args:
        tier: e.g. "S+", "S", "A", "B", "C", "D", "H" (substring match on the label).
        server: "jp" or "gl" (default: "jp").
        available_characters: Optional ID filter. If omitted, the saved roster applies.
        limit: Maximum number of results (default: 20).

    Returns:
        roster_applied, recommendation_pool, characters (strongest first).
    """
    retrieval, filter_ids, roster = resolve_pool(available_characters)
    matching = [
        char
        for char in retrieval.character_pool(filter_ids)
        if tier.upper() in ((char.jp_tier if server == "jp" else char.gl_tier) or "").upper()
    ]
    matching.sort(key=strength_sort_key)
    return {
        **pool_meta(filter_ids),
        "characters": [character_summary(c, roster) for c in matching[:limit]],
    }


@mcp.tool()
def list_by_role(
    role: str,
    available_characters: list[str] | None = None,
    limit: int = 20,
) -> dict:
    """
    List characters by team role using exact match on the curated roles field.

    Many characters still have no curated roles; empty results usually mean
    incomplete data. Fall back to search_skill_effects for effect-level needs.

    Args:
        role: tank, healer, buffer, debuffer, breaker, dps (case-insensitive).
        available_characters: Optional ID filter. If omitted, the saved roster applies.
        limit: Maximum number of results (default: 20).

    Returns:
        roster_applied, recommendation_pool, characters (strongest first).
    """
    retrieval, filter_ids, roster = resolve_pool(available_characters)
    chars = retrieval.find_characters_by_role_exact(role, character_ids=filter_ids, limit=limit)
    return {**pool_meta(filter_ids), "characters": [character_summary(c, roster) for c in chars]}


@mcp.tool()
def list_all_character_ids() -> list[str]:
    """
    List all available character IDs in the database.

    Use this to see what characters are available, then use get_character
    to get details on specific ones.

    Returns:
        List of all character IDs (sorted alphabetically).
    """
    return get_retrieval().list_character_ids()


@mcp.tool()
def get_database_stats() -> dict:
    """
    Get statistics about the COTC database.

    Returns:
        Dictionary with counts of characters, bosses, and teams indexed.
    """
    retrieval = get_retrieval()
    return retrieval.vector_store.get_collection_stats()


# =============================================================================
# BOSS & TEAM TOOLS
# =============================================================================


@mcp.tool()
def search_bosses(query: str, limit: int = 5) -> list[dict]:
    """
    Search for bosses by description or mechanics.

    Use this to find bosses matching a description like:
    - "fire weakness"
    - "high shield count"
    - "120 NPC"

    Args:
        query: Natural language description of boss characteristics.
        limit: Maximum number of results (default: 5).

    Returns:
        List of matching bosses with basic info.
    """
    retrieval = get_retrieval()

    results = retrieval.vector_store.search_bosses(
        query=query,
        n_results=limit,
    )

    bosses = []
    for result in results:
        boss = retrieval.get_boss_by_id(result["id"])
        if boss:
            # Handle weaknesses - may be None for multi-enemy encounters
            if boss.weaknesses:
                weaknesses = {
                    "elements": [e.value for e in boss.weaknesses.elements]
                    if boss.weaknesses.elements
                    else [],
                    "weapons": [w.value for w in boss.weaknesses.weapons]
                    if boss.weaknesses.weapons
                    else [],
                }
            elif boss.enemies:
                # Extract from first enemy for multi-enemy encounters
                first_enemy = boss.enemies[0] if boss.enemies else None
                if first_enemy and first_enemy.weaknesses:
                    weaknesses = {
                        "elements": [e.value for e in first_enemy.weaknesses.elements]
                        if first_enemy.weaknesses.elements
                        else [],
                        "weapons": [w.value for w in first_enemy.weaknesses.weapons]
                        if first_enemy.weaknesses.weapons
                        else [],
                    }
                else:
                    weaknesses = {"elements": [], "weapons": []}
            else:
                weaknesses = {"elements": [], "weapons": []}

            bosses.append(
                {
                    "id": boss.id,
                    "display_name": boss.display_name,
                    "content_type": boss.content_type.value if boss.content_type else None,
                    "difficulty": boss.difficulty.value if boss.difficulty else None,
                    "shield_count": boss.shield_count,
                    "weaknesses": weaknesses,
                    "ex_rank": boss.ex_rank.value if boss.ex_rank else None,
                    "data_confidence": boss.data_confidence.value if boss.data_confidence else None,
                }
            )

    return bosses


@mcp.tool()
def get_boss(boss_id: str) -> dict | str:
    """
    Get full details for a specific boss.

    Args:
        boss_id: The boss's unique ID (e.g., "120npc-dignified-tutor").

    Returns:
        Full boss details including mechanics and requirements.
    """
    retrieval = get_retrieval()

    boss = retrieval.get_boss_by_id(boss_id)
    if boss is None:
        return f"Boss '{boss_id}' not found."

    result = {
        "id": boss.id,
        "display_name": boss.display_name,
        "content_type": boss.content_type,
        "difficulty": boss.difficulty.value if boss.difficulty else None,
        "shield_count": boss.shield_count,
        "required_roles": [
            {"role": rr.role.value, "priority": rr.priority, "reason": rr.reason}
            for rr in (boss.required_roles or [])
        ],
        "required_capabilities": boss.required_capabilities,
        "general_strategy": boss.general_strategy,
        "data_confidence": boss.data_confidence.value,
    }

    # Handle weaknesses (can be None for multi-enemy bosses)
    if boss.weaknesses:
        result["weaknesses"] = {
            "elements": [e.value for e in boss.weaknesses.elements]
            if boss.weaknesses.elements
            else [],
            "weapons": [w.value for w in boss.weaknesses.weapons]
            if boss.weaknesses.weapons
            else [],
        }
    else:
        result["weaknesses"] = None

    # Handle multi-enemy encounters
    if boss.enemies:
        result["enemies"] = [
            {
                "name": e.name,
                "name_jp": e.name_jp,
                "is_main_target": e.is_main_target,
                "shield_count": e.shield_count,
                "weaknesses": {
                    "elements": [el.value for el in e.weaknesses.elements]
                    if e.weaknesses and e.weaknesses.elements
                    else [],
                    "weapons": [w.value for w in e.weaknesses.weapons]
                    if e.weaknesses and e.weaknesses.weapons
                    else [],
                }
                if e.weaknesses
                else None,
                "notes": e.notes,
            }
            for e in boss.enemies
        ]

    if boss.mechanics:
        result["mechanics"] = [
            {
                "name": m.name,
                "type": m.mechanic_type,
                "target": m.target,
                "threat_level": m.threat_level,
                "counter_strategy": m.counter_strategy,
            }
            for m in boss.mechanics
        ]

    # Include special mechanics if present
    if boss.special_mechanics:
        result["special_mechanics"] = [
            {
                "name": sm.get("name", ""),
                "description": sm.get("description", ""),
            }
            for sm in boss.special_mechanics
        ]

    # Include actions if present
    if boss.actions:
        result["actions"] = [
            {
                "name": a.name,
                "name_jp": a.name_jp,
                "effect": a.effect,
                "threat_level": a.threat_level,
            }
            for a in boss.actions
        ]

    return result


@mcp.tool()
def list_all_boss_ids() -> list[str]:
    """
    List all available boss IDs in the database.

    Returns:
        List of all boss IDs (sorted alphabetically).
    """
    return get_retrieval().list_boss_ids()


@mcp.tool()
def get_proven_teams(boss_id: str) -> dict | str:
    """
    Get human-curated proven team compositions for a specific boss.

    Returns team YAMLs indexed in the database (front/back line, roles,
    skill loadouts, strategy notes). Prefer these over inferred comps when present.

    Args:
        boss_id: The boss's unique ID (e.g., "arena-tikilen").

    Returns:
        Dictionary with boss_id, count, and teams list; or error if boss not found.
    """
    retrieval = get_retrieval()

    boss = retrieval.get_boss_by_id(boss_id)
    if boss is None:
        return f"Boss '{boss_id}' not found."

    teams = retrieval.get_teams_for_boss(boss_id)
    known = known_character_ids(retrieval)
    _, roster = resolve_roster(None, known_ids=known)
    roster_payload = teams_for_roster(teams, roster, team_to_dict)
    return {
        "boss_id": boss_id,
        "count": len(teams),
        **roster_payload,
    }


@mcp.tool()
def plan_team_for_boss(
    boss_id: str,
    available_characters: list[str] | None = None,
) -> dict:
    """
    Get strategic team planning advice for a specific boss.

    IMPORTANT: COTC parties have 8 characters (4 front + 4 back).
    Use get_team_building_guide() first for full context.

    Returns recommended_characters (weakness matches; filtered to saved roster when
    roster_applied is true), recommended_by_role (same), proven_teams, coverage_gaps,
    role_coverage_gaps, recommendation_pool ("roster" or "full_database"), and
    skill_loadout_guidance. Check roster_applied before using recommendations — when
    false, recommended_* lists the entire character database, not owned units.
    Prioritize proven_teams when non-empty. Recommendations are ranked by JP tier.
    Many characters lack curated roles: fill role/effect needs (Def down, Damage
    Limit, taunt, BP) with search_skill_effects over the same pool.
    Do not invent characters to fill empty weakness or role slots.

    Args:
        boss_id: The boss to plan for.
        available_characters: Optional list of character IDs the user owns.
                             If not provided, uses saved roster when configured.

    Returns:
        Dictionary with boss analysis, proven teams, character recommendations
        grouped by weakness and role, plus coverage gaps.
    """
    retrieval = get_retrieval()

    boss = retrieval.get_boss_by_id(boss_id)
    if boss is None:
        return {"error": f"Boss '{boss_id}' not found."}

    roster_ids, roster = resolve_roster(
        available_characters, known_ids=known_character_ids(retrieval)
    )
    weaknesses = retrieval.get_boss_weaknesses(boss)

    teams = retrieval.get_teams_for_boss(boss_id)
    roster_teams = teams_for_roster(teams, roster, team_to_dict)
    skill_loadout = load_team_building_guide(get_data_dir())["skill_loadout_guidance"]

    result = {
        "party_structure": {
            "note": "COTC parties have 8 characters: 4 FRONT ROW + 4 BACK ROW",
            "front_row": 4,
            "back_row": 4,
            "instruction": "Pick 8 total from recommended characters below",
        },
        "skill_loadout_guidance": skill_loadout,
        "boss": {
            "id": boss.id,
            "display_name": boss.display_name,
            "shield_count": boss.shield_count,
            "hp": boss.hp,
            "speed": boss.speed,
            "weaknesses": weaknesses,
            "difficulty": boss.difficulty.value if boss.difficulty else None,
            "ex_rank": boss.ex_rank.value if boss.ex_rank else None,
            "actions_per_turn": boss.actions_per_turn,
            "provoke_immunity": boss.provoke_immunity,
        },
        "required_roles": [
            {"role": rr.role.value, "priority": rr.priority, "reason": rr.reason}
            for rr in (boss.required_roles or [])
        ],
        "proven_teams": roster_teams["teams"],
        "teams_for_my_roster": roster_teams.get("teams_for_my_roster", []),
        "feasible_proven_teams": roster_teams.get("feasible_proven_teams", []),
        "partial_proven_teams": roster_teams.get("partial_proven_teams", []),
        "roster_applied": roster_teams["roster_applied"],
        "recommendation_pool": "roster" if roster_teams["roster_applied"] else "full_database",
        "recommended_characters": {},
        "recommended_by_role": {},
        "coverage_gaps": [],
        "role_coverage_gaps": [],
        "tactical_notes": [],
    }

    if roster_teams["roster_applied"]:
        result["roster_summary"] = {
            "path": str(roster_path()),
            "owned_count": len(roster_ids) if roster_ids else 0,
        }
    else:
        result["tactical_notes"].insert(
            0,
            "Roster not configured or empty — recommended_characters and recommended_by_role "
            "use the FULL character database. Call get_my_roster() or set roster via roster-ui; "
            "only use picks where you own the character.",
        )

    # Add EX-specific notes
    if boss.ex_rank:
        result["tactical_notes"].append(
            f"EX{boss.ex_rank.value[-1]} fight - provoke likely immune, use dodge/cover tank"
        )
        if boss.actions_per_turn and boss.actions_per_turn >= 3:
            result["tactical_notes"].append(
                "3 actions/turn - very aggressive, prioritize survival and debuffs"
            )

    # Add tactical notes based on shield count
    if boss.shield_count:
        if boss.shield_count >= 35:
            result["tactical_notes"].append(
                f"High shield count ({boss.shield_count}) - prioritize multi-hit breakers"
            )
        if boss.shield_count >= 20:
            result["tactical_notes"].append("Plan for 2+ break cycles unless very strong team")

    for weakness in weaknesses[:4]:
        chars = retrieval.find_characters_by_weakness(
            weakness,
            character_ids=roster_ids,
            limit=5,
        )
        result["recommended_characters"][weakness] = [
            plan_team_character_entry(c, roster) for c in chars
        ]

    result["coverage_gaps"] = [
        w for w in weaknesses[:4] if not result["recommended_characters"].get(w)
    ]

    for rr in boss.required_roles or []:
        role = rr.role.value
        chars = retrieval.find_characters_by_role_exact(
            role,
            character_ids=roster_ids,
            limit=5,
        )
        result["recommended_by_role"][role] = [plan_team_character_entry(c, roster) for c in chars]

    result["role_coverage_gaps"] = [
        rr.role.value
        for rr in (boss.required_roles or [])
        if rr.priority == RolePriority.REQUIRED
        and not result["recommended_by_role"].get(rr.role.value)
    ]

    if boss.general_strategy:
        result["general_strategy"] = boss.general_strategy

    return result


# =============================================================================
# EX FIGHT / ADVERSARY LOG TOOLS
# =============================================================================


@mcp.tool()
def get_ex_variants(boss_id: str) -> dict | str:
    """
    Get all EX variants for a base boss.

    Use this to find EX1, EX2, EX3 versions of an arena boss.

    Args:
        boss_id: The base boss ID (e.g., "arena-gertrude").

    Returns:
        Dictionary with base boss info and list of EX variants.
    """
    retrieval = get_retrieval()

    base_boss = retrieval.get_boss_by_id(boss_id)
    if base_boss is None:
        return f"Boss '{boss_id}' not found."

    # Find all bosses with this base_boss_id
    variants = []
    for boss in retrieval._bosses_cache.values():
        if hasattr(boss, "base_boss_id") and boss.base_boss_id == boss_id:
            variants.append(
                {
                    "id": boss.id,
                    "display_name": boss.display_name,
                    "ex_rank": boss.ex_rank.value if boss.ex_rank else None,
                    "shield_count": boss.shield_count,
                    "actions_per_turn": boss.actions_per_turn,
                    "provoke_immunity": boss.provoke_immunity,
                    "difficulty": boss.difficulty.value if boss.difficulty else None,
                }
            )

    # Sort by EX rank
    rank_order = {"ex1": 1, "ex2": 2, "ex3": 3}
    variants.sort(key=lambda v: rank_order.get(v.get("ex_rank", ""), 0))

    return {
        "base_boss": {
            "id": base_boss.id,
            "display_name": base_boss.display_name,
            "shield_count": base_boss.shield_count,
        },
        "ex_variants": variants,
        "total_variants": len(variants),
    }


@mcp.tool()
def find_tanks_by_type(
    tank_type: str,
    available_characters: list[str] | None = None,
) -> dict:
    """
    Find characters by curated tank type (provoke, dodge, cover, hp_barrier).

    Only curated characters carry tank_type; also try search_skill_effects with
    "taunt|provoke", "Sidestep|evade", "cover" to catch uncurated kits.

    Args:
        tank_type: provoke, dodge, cover, hp_barrier.
        available_characters: Optional ID filter. If omitted, the saved roster applies.

    Returns:
        roster_applied, recommendation_pool, characters with tank details.
    """
    retrieval, filter_ids, roster = resolve_pool(available_characters)
    matching = [
        char
        for char in retrieval.character_pool(filter_ids)
        if char.tank_type and char.tank_type.value == tank_type
    ]
    matching.sort(key=strength_sort_key)

    characters = []
    for char in matching:
        summary = character_summary(char, roster)
        summary["tank_type"] = char.tank_type.value
        summary["recommended_min_hp"] = char.recommended_min_hp
        summary["role_notes"] = char.role_notes
        characters.append(summary)
    return {**pool_meta(filter_ids), "characters": characters}


@mcp.tool()
def check_buff_coverage(character_ids: list[str]) -> dict:
    """
    Analyze which buff/debuff stacking categories a team covers.

    This helps optimize damage for EX fights by ensuring all 5
    multiplicative damage categories are covered.

    Args:
        character_ids: List of character IDs in the team.

    Returns:
        Dictionary showing coverage of each damage stacking category.
    """
    retrieval = get_retrieval()

    coverage = {
        "active_buffs": [],
        "active_debuffs": [],
        "passive_buffs": [],
        "ultimate_buffs": [],
        "ultimate_debuffs": [],
        "summary": {
            "has_active_atk_buff": False,
            "has_active_def_debuff": False,
            "has_passive_damage": False,
            "has_ultimate_potency": False,
            "categories_covered": 0,
        },
        "missing_categories": [],
    }

    for char_id in character_ids:
        char = retrieval.get_character_by_id(char_id)
        if not char:
            continue

        # Check buff categories
        if hasattr(char, "buff_categories") and char.buff_categories:
            if char.buff_categories.active:
                for entry in char.buff_categories.active:
                    coverage["active_buffs"].append(
                        {
                            "character": char_id,
                            "type": entry.type,
                            "value": entry.value,
                        }
                    )
                    if "atk" in entry.type.lower():
                        coverage["summary"]["has_active_atk_buff"] = True

            if char.buff_categories.passive:
                for entry in char.buff_categories.passive:
                    coverage["passive_buffs"].append(
                        {
                            "character": char_id,
                            "type": entry.type,
                            "value": entry.value,
                        }
                    )
                    coverage["summary"]["has_passive_damage"] = True

            if char.buff_categories.ultimate:
                for entry in char.buff_categories.ultimate:
                    coverage["ultimate_buffs"].append(
                        {
                            "character": char_id,
                            "type": entry.type,
                            "value": entry.value,
                        }
                    )
                    if "potency" in entry.type.lower():
                        coverage["summary"]["has_ultimate_potency"] = True

        # Check debuff categories
        if hasattr(char, "debuff_categories") and char.debuff_categories:
            if char.debuff_categories.active:
                for entry in char.debuff_categories.active:
                    coverage["active_debuffs"].append(
                        {
                            "character": char_id,
                            "type": entry.type,
                            "value": entry.value,
                        }
                    )
                    if "def" in entry.type.lower():
                        coverage["summary"]["has_active_def_debuff"] = True

            if char.debuff_categories.ultimate:
                for entry in char.debuff_categories.ultimate:
                    coverage["ultimate_debuffs"].append(
                        {
                            "character": char_id,
                            "type": entry.type,
                            "value": entry.value,
                        }
                    )

    # Count covered categories
    categories = [
        ("has_active_atk_buff", "Active ATK buffs (30% cap)"),
        ("has_active_def_debuff", "Active DEF debuffs (30% cap)"),
        ("has_passive_damage", "Passive damage bonuses (30% cap)"),
        ("has_ultimate_potency", "Ultimate potency (Solon = 100%)"),
    ]

    for key, desc in categories:
        if coverage["summary"][key]:
            coverage["summary"]["categories_covered"] += 1
        else:
            coverage["missing_categories"].append(desc)

    # Add pet/divine beast as note (not tracked in character data)
    coverage["missing_categories"].append("Pet damage bonus (check manually)")
    coverage["missing_categories"].append("Divine Beast bonus (check manually)")

    return coverage


# =============================================================================
# PLAYER ROSTER TOOLS
# =============================================================================


@mcp.tool()
def get_my_roster() -> dict:
    """
    Get the player's saved character roster (owned units + investment).

    Call before team planning. If not configured, returns configured=false —
    proceed with the full character pool and suggest `cotc-tactician roster-ui`.

    Returns:
        path, owned_count, characters dict, skipped_invalid_ids from lenient load.
    """
    retrieval = get_retrieval()
    known = known_character_ids(retrieval)
    return load_roster_with_meta(known_ids=known)


@mcp.tool()
def set_roster_characters(characters: dict[str, dict]) -> dict | str:
    """
    Upsert owned characters in the saved roster.

    Args:
        characters: Map of character_id → {awakening: 0-4, au: bool, ult_level: 0-20}.
                    Example: {"solon": {"awakening": 4, "au": true, "ult_level": 20}}

    Returns:
        Updated roster summary or error message.
    """
    retrieval = get_retrieval()
    known = known_character_ids(retrieval)
    try:
        updates = {cid: RosterEntry.model_validate(data) for cid, data in characters.items()}
        upsert_roster_characters(updates, known_ids=known)
    except ValueError as e:
        return str(e)
    return load_roster_with_meta(known_ids=known)


@mcp.tool()
def remove_roster_characters(character_ids: list[str]) -> dict:
    """
    Remove characters from the saved roster.

    Args:
        character_ids: Character IDs to remove from ownership.

    Returns:
        Updated roster summary.
    """
    retrieval = get_retrieval()
    remove_chars_from_roster(character_ids)
    return load_roster_with_meta(known_ids=known_character_ids(retrieval))


@mcp.tool()
def import_roster_yaml_content(yaml_content: str, merge: bool = False) -> dict | str:
    """
    Import roster from YAML text (replace or merge into saved roster).

    Args:
        yaml_content: Full or partial roster YAML (schema_version + characters map).
        merge: If true, merge into existing roster; if false, replace entirely.

    Returns:
        Updated roster summary or error message.
    """
    retrieval = get_retrieval()
    known = known_character_ids(retrieval)
    try:
        import_roster_yaml(yaml_content, merge=merge, known_ids=known)
    except (ValueError, ValidationError) as e:
        return str(e)
    return load_roster_with_meta(known_ids=known)


# =============================================================================
# TEAM BUILDING GUIDE TOOL
# =============================================================================


@mcp.tool()
def get_team_building_guide() -> dict:
    """
    Get essential COTC team building guidelines.

    CALL THIS FIRST before making team recommendations!

    Returns critical information:
    - Party structure (8 characters: 4 front + 4 back)
    - Skill slot limits (3-4 battle slots; ult/EX/TP separate)
    - Skill loadout rules (one skill per slot, no upgrade-line stacking)
    - Role definitions with top characters
    - EX fight scaling patterns for extrapolation
    - Common mistakes to avoid

    Returns:
        Dictionary with team building guidelines (loaded from reference YAML).
    """
    return load_team_building_guide(get_data_dir())


# =============================================================================
# SERVER ENTRY POINT
# =============================================================================


def run_mcp_server():
    """Run the MCP server with stdio transport."""
    # Note: No logging here - stdout is reserved for MCP protocol
    mcp.run(transport="stdio")


if __name__ == "__main__":
    run_mcp_server()
