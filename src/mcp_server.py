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

from .retrieval import RetrievalService
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
    import os
    if env_path := os.environ.get("COTC_DATA_DIR"):
        return Path(env_path)
    # Default to ./data relative to project root
    return Path(__file__).parent.parent / "data"


def get_vector_store_dir() -> Path:
    """Get the vector store directory path."""
    import os
    if env_path := os.environ.get("COTC_VECTOR_DIR"):
        return Path(env_path)
    return Path(__file__).parent.parent / ".vectordb"


def get_retrieval() -> RetrievalService:
    """Get or create the retrieval service (lazy initialization)."""
    global _retrieval
    if _retrieval is None:
        data_dir = get_data_dir()
        vector_dir = get_vector_store_dir()
        
        vector_store = VectorStore(persist_directory=vector_dir)
        _retrieval = RetrievalService(
            data_dir=data_dir,
            vector_store=vector_store,
        )
        _retrieval.initialize()
    
    return _retrieval


def character_to_dict(char: Any) -> dict:
    """Convert a Character model to a clean dictionary for JSON output."""
    skills_summary = []
    for skill in char.skills[:8]:  # Limit to 8 most important skills
        skill_info = {
            "name": skill.name or "(unnamed)",
            "category": skill.skill_category.value,
            "type": skill.skill_type.value,
            "target": skill.target.value,
        }
        if skill.damage_types:
            skill_info["damage_types"] = skill.damage_types
        if skill.sp_cost:
            skill_info["sp_cost"] = skill.sp_cost
        if skill.hit_count:
            skill_info["hit_count"] = skill.hit_count
        if skill.power:
            skill_info["power"] = skill.power
        if skill.effects:
            skill_info["effects"] = skill.effects[:2]  # First 2 effects
        skills_summary.append(skill_info)
    
    passives_summary = []
    for passive in char.passives[:5]:  # Limit to 5 passives
        passives_summary.append({
            "category": passive.passive_category.value,
            "effect": passive.effect[:150] + "..." if len(passive.effect) > 150 else passive.effect,
        })
    
    result = {
        "id": char.id,
        "display_name": char.display_name,
        "job": char.job.value,
        "rarity": char.rarity,
        "weakness_coverage": char.weakness_coverage,
        "roles": [r.value for r in char.roles] if char.roles else [],
        "role_notes": char.role_notes,
        "gl_tier": char.gl_tier,
        "jp_tier": char.jp_tier,
        "stats": {
            "hp": char.hp,
            "p_atk": char.p_atk,
            "e_atk": char.e_atk,
            "speed": char.speed,
        },
        "skills": skills_summary,
        "passives": passives_summary,
        "data_confidence": char.data_confidence.value,
    }
    
    if char.a4_accessory:
        result["a4_accessory"] = {
            "name": char.a4_accessory.name,
            "effect": char.a4_accessory.passive_effect,
        }
    
    return result


def character_summary(char: Any) -> dict:
    """Create a brief summary of a character for list results."""
    return {
        "id": char.id,
        "display_name": char.display_name,
        "job": char.job.value,
        "weakness_coverage": char.weakness_coverage,
        "roles": [r.value for r in char.roles] if char.roles else [],
        "gl_tier": char.gl_tier,
        "jp_tier": char.jp_tier,
    }


# =============================================================================
# MCP TOOLS
# =============================================================================

@mcp.tool()
def search_characters(query: str, limit: int = 8) -> list[dict]:
    """
    Search for characters using semantic search.
    
    Use this to find characters matching a description like:
    - "fire damage dealers"
    - "sword buffer"
    - "healer with regen"
    - "high shield break"
    
    Args:
        query: Natural language description of what you're looking for.
        limit: Maximum number of results to return (default: 8, max party size).
    
    Returns:
        List of matching characters with basic info (id, name, job, weaknesses, roles, tier).
    """
    retrieval = get_retrieval()
    
    results = retrieval.vector_store.search_characters(
        query=query,
        n_results=limit,
    )
    
    characters = []
    for result in results:
        char = retrieval.get_character_by_id(result["id"])
        if char:
            characters.append(character_summary(char))
    
    return characters


@mcp.tool()
def get_character(character_id: str) -> dict | str:
    """
    Get full details for a specific character.
    
    Use this after search_characters to get complete information including
    skills, passives, stats, and A4 accessory.
    
    Args:
        character_id: The character's unique ID (e.g., "richard", "primrose-ex").
    
    Returns:
        Full character details or error message if not found.
    """
    retrieval = get_retrieval()
    
    char = retrieval.get_character_by_id(character_id)
    if char is None:
        return f"Character '{character_id}' not found."
    
    return character_to_dict(char)


@mcp.tool()
def find_by_weakness(weakness_types: list[str], limit: int = 8) -> list[dict]:
    """
    Find characters that can hit specific enemy weaknesses.
    
    Use this when you know what weaknesses a boss has and want to find
    characters that can exploit them.
    
    Args:
        weakness_types: List of weakness types to search for.
                       Valid values: sword, polearm, dagger, axe, bow, staff,
                                    fire, ice, lightning, wind, light, dark
        limit: Maximum number of results (default: 8, max party size).
    
    Returns:
        List of characters that cover at least one of the specified weaknesses.
    """
    retrieval = get_retrieval()
    
    # Build a query from the weakness types
    query = f"Character with weakness coverage: {', '.join(weakness_types)}"
    
    results = retrieval.vector_store.search_characters(
        query=query,
        n_results=limit * 2,  # Get extra to filter
    )
    
    # Filter to characters that actually cover the weaknesses
    characters = []
    for result in results:
        char = retrieval.get_character_by_id(result["id"])
        if char:
            # Check if character covers at least one weakness
            coverage = set(char.weakness_coverage)
            requested = set(weakness_types)
            if coverage & requested:  # Intersection
                summary = character_summary(char)
                summary["matching_weaknesses"] = list(coverage & requested)
                characters.append(summary)
        
        if len(characters) >= limit:
            break
    
    return characters


@mcp.tool()
def list_by_tier(tier: str = "S", server: str = "jp", limit: int = 20) -> list[dict]:
    """
    List characters by their tier rating.
    
    Tier ratings come from community sources and indicate general strength.
    JP tiers are more up-to-date; GL tiers reflect Global server meta.
    
    Args:
        tier: Tier to filter by. Common values: "S+", "S", "A", "B", "C", "D", "H".
        server: Which tier rating to use - "jp" or "gl" (default: "jp").
        limit: Maximum number of results (default: 20).
    
    Returns:
        List of characters at the specified tier.
    """
    retrieval = get_retrieval()
    
    # Get all characters and filter by tier
    if not retrieval._characters_cache:
        retrieval.initialize()
    
    matching = []
    for char in retrieval._characters_cache.values():
        tier_value = char.jp_tier if server == "jp" else char.gl_tier
        if tier_value and tier.upper() in tier_value.upper():
            matching.append(character_summary(char))
        
        if len(matching) >= limit:
            break
    
    return matching


@mcp.tool()
def get_team_suggestions(
    weaknesses: list[str],
    roles_needed: list[str] | None = None,
    limit: int = 8,
) -> dict:
    """
    Get character suggestions for building a team against a boss.
    
    Provide the boss's weaknesses and optionally the roles you need,
    and this will suggest characters that fit.
    
    COTC teams have 8 slots: 4 front row (active) + 4 back row (swap in).
    
    Args:
        weaknesses: Boss weaknesses to exploit (e.g., ["fire", "sword"]).
        roles_needed: Optional roles you need (e.g., ["healer", "buffer", "dps"]).
                     Valid roles: tank, healer, buffer, debuffer, breaker, dps
                     From meowdb: PDPS, EDPS, Tankiness, Healer, Buffer, Debuffer, Breaker
        limit: Max characters per category (default: 8, full party).
    
    Returns:
        Dictionary with character suggestions organized by weakness coverage
        and optionally by role.
    """
    retrieval = get_retrieval()
    
    result = {
        "by_weakness": {},
        "summary": {
            "total_weaknesses": weaknesses,
            "roles_requested": roles_needed or [],
        },
    }
    
    # Find characters for each weakness
    for weakness in weaknesses:
        query = f"Character with {weakness} coverage"
        search_results = retrieval.vector_store.search_characters(
            query=query,
            n_results=limit * 2,
        )
        
        chars_for_weakness = []
        for sr in search_results:
            char = retrieval.get_character_by_id(sr["id"])
            if char and weakness in char.weakness_coverage:
                chars_for_weakness.append(character_summary(char))
            if len(chars_for_weakness) >= limit:
                break
        
        result["by_weakness"][weakness] = chars_for_weakness
    
    # If roles requested, add role-based suggestions
    if roles_needed:
        result["by_role"] = {}
        for role in roles_needed:
            query = f"Character with {role} role"
            search_results = retrieval.vector_store.search_characters(
                query=query,
                n_results=limit,
            )
            
            chars_for_role = []
            for sr in search_results:
                char = retrieval.get_character_by_id(sr["id"])
                if char:
                    chars_for_role.append(character_summary(char))
                if len(chars_for_role) >= limit // 2:
                    break
            
            result["by_role"][role] = chars_for_role
    
    return result


@mcp.tool()
def list_all_character_ids() -> list[str]:
    """
    List all available character IDs in the database.
    
    Use this to see what characters are available, then use get_character
    to get details on specific ones.
    
    Returns:
        List of all character IDs (sorted alphabetically).
    """
    retrieval = get_retrieval()
    
    if not retrieval._characters_cache:
        retrieval.initialize()
    
    return sorted(retrieval._characters_cache.keys())


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
                    "elements": [e.value for e in boss.weaknesses.elements] if boss.weaknesses.elements else [],
                    "weapons": [w.value for w in boss.weaknesses.weapons] if boss.weaknesses.weapons else [],
                }
            elif boss.enemies:
                # Extract from first enemy for multi-enemy encounters
                first_enemy = boss.enemies[0] if boss.enemies else None
                if first_enemy and first_enemy.weaknesses:
                    weaknesses = {
                        "elements": [e.value for e in first_enemy.weaknesses.elements] if first_enemy.weaknesses.elements else [],
                        "weapons": [w.value for w in first_enemy.weaknesses.weapons] if first_enemy.weaknesses.weapons else [],
                    }
                else:
                    weaknesses = {"elements": [], "weapons": []}
            else:
                weaknesses = {"elements": [], "weapons": []}
            
            bosses.append({
                "id": boss.id,
                "display_name": boss.display_name,
                "content_type": boss.content_type.value if boss.content_type else None,
                "difficulty": boss.difficulty.value if boss.difficulty else None,
                "shield_count": boss.shield_count,
                "weaknesses": weaknesses,
                "ex_rank": boss.ex_rank.value if boss.ex_rank else None,
                "data_confidence": boss.data_confidence.value if boss.data_confidence else None,
            })
    
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
            "elements": [e.value for e in boss.weaknesses.elements] if boss.weaknesses.elements else [],
            "weapons": [w.value for w in boss.weaknesses.weapons] if boss.weaknesses.weapons else [],
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
                    "elements": [el.value for el in e.weaknesses.elements] if e.weaknesses and e.weaknesses.elements else [],
                    "weapons": [w.value for w in e.weaknesses.weapons] if e.weaknesses and e.weaknesses.weapons else [],
                } if e.weaknesses else None,
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
    retrieval = get_retrieval()
    
    if not retrieval._bosses_cache:
        retrieval.initialize()
    
    return sorted(retrieval._bosses_cache.keys())


@mcp.tool()
def plan_team_for_boss(
    boss_id: str,
    available_characters: list[str] | None = None,
) -> dict:
    """
    Get strategic team planning advice for a specific boss.

    IMPORTANT: COTC parties have 8 characters (4 front + 4 back).
    Use get_team_building_guide() first for full context.

    This analyzes boss weaknesses and requirements, then suggests
    characters from the available roster that match.

    Args:
        boss_id: The boss to plan for.
        available_characters: Optional list of character IDs the user owns.
                             If not provided, suggests from all characters.

    Returns:
        Dictionary with boss analysis and character recommendations.
        Note: Recommended characters are grouped by weakness - pick 8 total
        (4 front row + 4 back row) covering multiple weaknesses.
    """
    retrieval = get_retrieval()
    
    boss = retrieval.get_boss_by_id(boss_id)
    if boss is None:
        return {"error": f"Boss '{boss_id}' not found."}
    
    # Build the analysis
    weaknesses = []
    if boss.weaknesses:
        if boss.weaknesses.elements:
            weaknesses.extend([e.value for e in boss.weaknesses.elements])
        if boss.weaknesses.weapons:
            weaknesses.extend([w.value for w in boss.weaknesses.weapons])
    elif boss.enemies:
        # For multi-enemy encounters, get weaknesses from main target
        main_enemy = next((e for e in boss.enemies if e.is_main_target), boss.enemies[0] if boss.enemies else None)
        if main_enemy and main_enemy.weaknesses:
            if main_enemy.weaknesses.elements:
                weaknesses.extend([e.value for e in main_enemy.weaknesses.elements])
            if main_enemy.weaknesses.weapons:
                weaknesses.extend([w.value for w in main_enemy.weaknesses.weapons])
    
    result = {
        "party_structure": {
            "note": "COTC parties have 8 characters: 4 FRONT ROW + 4 BACK ROW",
            "front_row": 4,
            "back_row": 4,
            "instruction": "Pick 8 total from recommended characters below"
        },
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
        "recommended_characters": {},
        "tactical_notes": [],
    }
    
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
            result["tactical_notes"].append(
                "Plan for 2+ break cycles unless very strong team"
            )
    
    # Find recommended characters for each weakness
    for weakness in weaknesses[:4]:  # Top 4 weaknesses
        query = f"Character with {weakness} coverage"
        search_results = retrieval.vector_store.search_characters(
            query=query,
            n_results=10,
        )
        
        chars = []
        for sr in search_results:
            char_id = sr["id"]
            
            # Filter by available if specified
            if available_characters and char_id not in available_characters:
                continue
            
            char = retrieval.get_character_by_id(char_id)
            if char and weakness in char.weakness_coverage:
                chars.append({
                    "id": char.id,
                    "display_name": char.display_name,
                    "job": char.job.value,
                    "roles": [r.value for r in char.roles] if char.roles else [],
                    "jp_tier": char.jp_tier,
                })
            
            if len(chars) >= 5:
                break
        
        result["recommended_characters"][weakness] = chars
    
    # Add strategy if available
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
        if hasattr(boss, 'base_boss_id') and boss.base_boss_id == boss_id:
            variants.append({
                "id": boss.id,
                "display_name": boss.display_name,
                "ex_rank": boss.ex_rank.value if boss.ex_rank else None,
                "shield_count": boss.shield_count,
                "actions_per_turn": boss.actions_per_turn,
                "provoke_immunity": boss.provoke_immunity,
                "difficulty": boss.difficulty.value if boss.difficulty else None,
            })
    
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
def find_tanks_by_type(tank_type: str) -> list[dict]:
    """
    Find characters by tank type (provoke, dodge, cover, hp_barrier).
    
    Use this when building teams for EX fights to find appropriate tanks.
    
    Args:
        tank_type: Type of tank to find.
                  Valid values: provoke, dodge, cover, hp_barrier
    
    Returns:
        List of characters with the specified tank type.
    """
    retrieval = get_retrieval()
    
    if not retrieval._characters_cache:
        retrieval.initialize()
    
    matching = []
    for char in retrieval._characters_cache.values():
        if hasattr(char, 'tank_type') and char.tank_type:
            if char.tank_type.value == tank_type:
                summary = character_summary(char)
                summary["tank_type"] = char.tank_type.value
                summary["recommended_min_hp"] = getattr(char, 'recommended_min_hp', None)
                summary["role_notes"] = char.role_notes
                matching.append(summary)
    
    return matching


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
        if hasattr(char, 'buff_categories') and char.buff_categories:
            if char.buff_categories.active:
                for entry in char.buff_categories.active:
                    coverage["active_buffs"].append({
                        "character": char_id,
                        "type": entry.type,
                        "value": entry.value,
                    })
                    if "atk" in entry.type.lower():
                        coverage["summary"]["has_active_atk_buff"] = True
            
            if char.buff_categories.passive:
                for entry in char.buff_categories.passive:
                    coverage["passive_buffs"].append({
                        "character": char_id,
                        "type": entry.type,
                        "value": entry.value,
                    })
                    coverage["summary"]["has_passive_damage"] = True
            
            if char.buff_categories.ultimate:
                for entry in char.buff_categories.ultimate:
                    coverage["ultimate_buffs"].append({
                        "character": char_id,
                        "type": entry.type,
                        "value": entry.value,
                    })
                    if "potency" in entry.type.lower():
                        coverage["summary"]["has_ultimate_potency"] = True
        
        # Check debuff categories
        if hasattr(char, 'debuff_categories') and char.debuff_categories:
            if char.debuff_categories.active:
                for entry in char.debuff_categories.active:
                    coverage["active_debuffs"].append({
                        "character": char_id,
                        "type": entry.type,
                        "value": entry.value,
                    })
                    if "def" in entry.type.lower():
                        coverage["summary"]["has_active_def_debuff"] = True
            
            if char.debuff_categories.ultimate:
                for entry in char.debuff_categories.ultimate:
                    coverage["ultimate_debuffs"].append({
                        "character": char_id,
                        "type": entry.type,
                        "value": entry.value,
                    })
    
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
# TEAM BUILDING GUIDE TOOL
# =============================================================================

@mcp.tool()
def get_team_building_guide() -> dict:
    """
    Get essential COTC team building guidelines.
    
    CALL THIS FIRST before making team recommendations!
    
    Returns critical information:
    - Party structure (8 characters: 4 front + 4 back)
    - Skill slot limits (3-4 per character)
    - Role definitions with top characters
    - EX fight scaling patterns for extrapolation
    - Common mistakes to avoid
    
    Returns:
        Dictionary with team building guidelines.
    """
    return {
        "party_structure": {
            "total_characters": 8,
            "front_row": 4,
            "back_row": 4,
            "notes": "ALWAYS recommend 8 characters. Front row is active, back row swaps in."
        },
        "skill_slots": {
            "awakening_0_1": 3,
            "awakening_2_plus": 4,
            "notes": "Recommend specific skills to equip for each character."
        },
        "ex_scaling_patterns": {
            "ex1": {
                "hp_multiplier": "~2x base",
                "speed_bonus": "+50-100",
                "actions_per_turn": 2,
                "shield_bonus": "+3-5",
                "provoke_immunity": True,
                "recommended_hp": 3000
            },
            "ex2": {
                "hp_multiplier": "~3x base",
                "speed_bonus": "+100-150",
                "actions_per_turn": "2-3",
                "shield_bonus": "+5-7",
                "provoke_immunity": True,
                "recommended_hp": 3500
            },
            "ex3": {
                "hp_multiplier": "~5x base",
                "speed_bonus": "+150-250",
                "actions_per_turn": 3,
                "shield_bonus": "+8-12",
                "provoke_immunity": True,
                "recommended_hp": 4000,
                "notes": "Extreme difficulty. Requires speedkill (Solon+Primrose EX) or full turtle strategy."
            }
        },
        "role_priorities": {
            "tank": {
                "subtypes": ["provoke", "dodge", "cover", "hp_barrier"],
                "ex_notes": "Most EX bosses are provoke immune! Use dodge (Canary, H'aanit EX) or cover (Fiore EX only).",
                "top_picks": ["fiore-ex", "canary", "h-aanit-ex"]
            },
            "healer": {
                "key_skills": ["Rehabilitate (status cleanse)", "Instant healing", "HP barriers"],
                "top_picks": ["rinyuu-ex", "therese-ex", "temenos", "ophilia-ex"]
            },
            "debuffer": {
                "cap": "30% per category",
                "priority": "E.ATK Down (reduces enemy damage)",
                "top_picks": ["viola", "canary", "signa-ex", "therion"]
            },
            "breaker": {
                "notes": "High hit count essential. Breaking is the core mechanic.",
                "top_picks": ["canary", "nephti", "primrose-ex", "kouren"]
            },
            "dps": {
                "damage_formula": "Weakness (2.5x) + Break (2x) = 5x damage window",
                "buff_categories": ["Active skills (30%)", "Passives (30%)", "Ultimate (varies)", "Pet", "Divine Beast"],
                "top_picks": ["solon", "primrose-ex", "richard", "leon"]
            }
        },
        "recommendation_format": {
            "sections": [
                "1. Boss Summary (weaknesses, mechanics, EX notes)",
                "2. Full 8-Character Team (4 front + 4 back with roles)",
                "3. Skill Loadouts (3-4 skills per key character)",
                "4. Turn-by-Turn Tactics (early game, break windows, phases)",
                "5. Alternative Teams (budget options, replacements)"
            ]
        },
        "common_mistakes": [
            "Recommending only 6 characters (must be 8)",
            "Ignoring skill slot limits (3-4 per character)",
            "Using provoke tank on provoke-immune EX boss",
            "Stacking redundant buffs past 30% cap",
            "Not covering all boss weaknesses",
            "Inventing EX stats instead of using scaling patterns"
        ]
    }


# =============================================================================
# SERVER ENTRY POINT
# =============================================================================

def run_mcp_server():
    """Run the MCP server with stdio transport."""
    # Note: No logging here - stdout is reserved for MCP protocol
    mcp.run(transport="stdio")


if __name__ == "__main__":
    run_mcp_server()
