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
            bosses.append({
                "id": boss.id,
                "display_name": boss.display_name,
                "content_type": boss.content_type,
                "difficulty": boss.difficulty.value if boss.difficulty else None,
                "shield_count": boss.shield_count,
                "weaknesses": {
                    "elements": [e.value for e in boss.weaknesses.elements] if boss.weaknesses.elements else [],
                    "weapons": [w.value for w in boss.weaknesses.weapons] if boss.weaknesses.weapons else [],
                },
                "data_confidence": boss.data_confidence.value,
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
        "weaknesses": {
            "elements": [e.value for e in boss.weaknesses.elements] if boss.weaknesses.elements else [],
            "weapons": [w.value for w in boss.weaknesses.weapons] if boss.weaknesses.weapons else [],
        },
        "required_roles": [
            {"role": rr.role.value, "priority": rr.priority, "reason": rr.reason}
            for rr in (boss.required_roles or [])
        ],
        "required_capabilities": boss.required_capabilities,
        "general_strategy": boss.general_strategy,
        "data_confidence": boss.data_confidence.value,
    }
    
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
    
    This analyzes boss weaknesses and requirements, then suggests
    characters from the available roster that match.
    
    Args:
        boss_id: The boss to plan for.
        available_characters: Optional list of character IDs the user owns.
                             If not provided, suggests from all characters.
    
    Returns:
        Dictionary with boss analysis and character recommendations.
    """
    retrieval = get_retrieval()
    
    boss = retrieval.get_boss_by_id(boss_id)
    if boss is None:
        return {"error": f"Boss '{boss_id}' not found."}
    
    # Build the analysis
    weaknesses = []
    if boss.weaknesses.elements:
        weaknesses.extend([e.value for e in boss.weaknesses.elements])
    if boss.weaknesses.weapons:
        weaknesses.extend([w.value for w in boss.weaknesses.weapons])
    
    result = {
        "boss": {
            "id": boss.id,
            "display_name": boss.display_name,
            "shield_count": boss.shield_count,
            "weaknesses": weaknesses,
            "difficulty": boss.difficulty.value if boss.difficulty else None,
        },
        "required_roles": [
            {"role": rr.role.value, "priority": rr.priority, "reason": rr.reason}
            for rr in (boss.required_roles or [])
        ],
        "recommended_characters": {},
        "tactical_notes": [],
    }
    
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
# SERVER ENTRY POINT
# =============================================================================

def run_mcp_server():
    """Run the MCP server with stdio transport."""
    # Note: No logging here - stdout is reserved for MCP protocol
    mcp.run(transport="stdio")


if __name__ == "__main__":
    run_mcp_server()
