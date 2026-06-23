"""
Player roster load/save and team feasibility scoring.

Roster file is optional — missing file means no filtering (backward compatible).
"""

from __future__ import annotations

import difflib
import logging
import os
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from pydantic import ValidationError

from .models import InvestmentLevel, PlayerRoster, RosterEntry, Team

if TYPE_CHECKING:
    from .retrieval import RetrievalService

logger = logging.getLogger(__name__)

FEASIBILITY_ORDER = {"full": 0, "partial": 1, "unavailable": 2}
INVESTMENT_LEVEL_ORDER = {
    InvestmentLevel.LOW.value: 0,
    InvestmentLevel.MEDIUM.value: 1,
    InvestmentLevel.HIGH.value: 2,
    InvestmentLevel.WHALE.value: 3,
}


def roster_path() -> Path:
    """Canonical roster file path (override with COTC_ROSTER_FILE)."""
    if env_path := os.environ.get("COTC_ROSTER_FILE"):
        return Path(env_path).expanduser()
    return Path.home() / ".cotc-tactician" / "roster.yaml"


def owned_character_ids(roster: PlayerRoster | None) -> list[str]:
    """Character IDs the user owns."""
    if roster is None:
        return []
    return sorted(roster.characters.keys())


def resolve_roster(
    available_characters: list[str] | None = None,
    path: Path | None = None,
    known_ids: set[str] | None = None,
) -> tuple[list[str] | None, PlayerRoster | None]:
    """
    Resolve roster for tool calls in a single disk read.

    Returns (filter_ids, roster). filter_ids None means no roster filter.
    Explicit available_characters wins for filtering; roster is still loaded
    for investment metadata when a file exists.
    """
    roster = load_roster(path, known_ids=known_ids)
    if available_characters is not None:
        return available_characters, roster
    if roster is None or not roster.characters:
        return None, None
    return owned_character_ids(roster), roster


def resolve_roster_character_ids(
    available_characters: list[str] | None,
    path: Path | None = None,
    known_ids: set[str] | None = None,
) -> list[str] | None:
    """
    Resolve roster filter IDs for tool calls.

    Explicit available_characters wins; else load from disk; missing file → None.
    Always reads from disk (no in-memory cache).
    """
    ids, _ = resolve_roster(available_characters, path, known_ids)
    return ids


def sanitize_roster_entries(
    roster: PlayerRoster,
    known_ids: set[str],
) -> tuple[PlayerRoster, list[str]]:
    """Drop unknown character IDs (lenient load). Returns cleaned roster + skipped IDs."""
    skipped: list[str] = []
    cleaned: dict[str, RosterEntry] = {}
    for char_id, entry in roster.characters.items():
        if char_id in known_ids:
            cleaned[char_id] = entry
        else:
            skipped.append(char_id)
            logger.warning("Roster: dropping unknown character id %r", char_id)
    roster.characters = cleaned
    return roster, skipped


def validate_character_ids_strict(
    ids: list[str],
    known_ids: set[str],
) -> tuple[list[str], list[str]]:
    """
    Strict validation for writes. Returns (valid_ids, errors).
    Each error may include a 'did you mean' suggestion.
    """
    valid: list[str] = []
    errors: list[str] = []
    known_list = sorted(known_ids)
    for char_id in ids:
        if char_id in known_ids:
            valid.append(char_id)
            continue
        matches = difflib.get_close_matches(char_id, known_list, n=1, cutoff=0.6)
        if matches:
            errors.append(f"Unknown character '{char_id}'. Did you mean '{matches[0]}'?")
        else:
            errors.append(f"Unknown character '{char_id}'.")
    return valid, errors


def _parse_roster_file(file_path: Path) -> PlayerRoster | None:
    """Parse roster YAML from disk. Returns None if missing or invalid."""
    if not file_path.is_file():
        return None

    try:
        with file_path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        logger.error("Failed to parse roster YAML %s: %s", file_path, e)
        return None

    if not data:
        return None

    try:
        return PlayerRoster.model_validate(data)
    except ValidationError as e:
        logger.error("Roster validation error in %s:\n%s", file_path, e)
        return None


def load_roster(path: Path | None = None, known_ids: set[str] | None = None) -> PlayerRoster | None:
    """
    Load roster from disk. Missing file → None (not an error).

    When known_ids is provided, unknown character IDs are dropped with warnings.
    """
    roster = _parse_roster_file(path or roster_path())
    if roster is None:
        return None
    if known_ids is not None:
        roster, _ = sanitize_roster_entries(roster, known_ids)
    return roster


def load_roster_with_meta(
    path: Path | None = None,
    known_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Load roster and return metadata for API/MCP (includes skipped_invalid_ids)."""
    file_path = path or roster_path()
    roster = _parse_roster_file(file_path)
    if roster is None:
        return {
            "configured": False,
            "path": str(file_path),
            "owned_count": 0,
            "characters": {},
            "skipped_invalid_ids": [],
        }

    skipped: list[str] = []
    if known_ids is not None:
        roster, skipped = sanitize_roster_entries(roster, known_ids)

    return {
        "configured": bool(roster.characters),
        "path": str(file_path),
        "owned_count": len(roster.characters),
        "schema_version": roster.schema_version,
        "last_updated": roster.last_updated.isoformat() if roster.last_updated else None,
        "characters": {
            cid: entry.model_dump() for cid, entry in roster.characters.items()
        },
        "skipped_invalid_ids": skipped,
    }


def save_roster(
    roster: PlayerRoster,
    path: Path | None = None,
    known_ids: set[str] | None = None,
) -> Path:
    """Persist roster to disk. Strict: raises ValueError on unknown IDs if known_ids set."""
    file_path = path or roster_path()
    roster.last_updated = date.today()

    if known_ids is not None:
        unknown = set(roster.characters.keys()) - known_ids
        if unknown:
            _, errors = validate_character_ids_strict(list(unknown), known_ids)
            raise ValueError("; ".join(errors))

    file_path.parent.mkdir(parents=True, exist_ok=True)
    payload = roster.model_dump(mode="json")
    with file_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(payload, f, default_flow_style=False, sort_keys=False)

    return file_path


def battle_skill_slot_count(awakening: int) -> int:
    """
    Equippable active skill slots from awakening stage.

    Slot 4 unlocks at Awakening Stage II (awakening >= 2).
    """
    return 4 if awakening >= 2 else 3


def roster_entry_for_character(roster: PlayerRoster | None, char_id: str) -> dict | None:
    """Investment dict for MCP character entries, or None."""
    if roster is None or char_id not in roster.characters:
        return None
    entry = roster.characters[char_id]
    return {
        "awakening": entry.awakening,
        "au": entry.au,
        "ult_level": entry.ult_level,
        "battle_skill_slots": battle_skill_slot_count(entry.awakening),
    }


def _team_slots(team: Team) -> list:
    return list(team.front_line) + list(team.back_line)


def score_team_feasibility(team: Team, roster: PlayerRoster) -> dict[str, Any]:
    """Score how runnable a proven team is with the player's roster."""
    owned = set(roster.characters.keys())
    missing_characters: list[dict[str, Any]] = []
    investment_gaps: list[dict[str, Any]] = []
    suggested_substitutions: list[dict[str, Any]] = []
    owned_count = 0
    has_owned_substitutes = False

    for slot in _team_slots(team):
        primary = slot.character_id
        primary_owned = primary in owned
        owned_subs = [s for s in slot.substitutes if s in owned]

        if primary_owned:
            owned_count += 1
            entry = roster.characters[primary]
            if slot.awakening_required and entry.awakening < slot.awakening_required:
                investment_gaps.append(
                    {
                        "position": slot.position,
                        "character_id": primary,
                        "required_awakening": slot.awakening_required,
                        "actual_awakening": entry.awakening,
                    }
                )
        elif owned_subs:
            owned_count += 1
            has_owned_substitutes = True
            sub_id = owned_subs[0]
            suggested_substitutions.append(
                {
                    "position": slot.position,
                    "missing": primary,
                    "use_instead": sub_id,
                    "all_owned_subs": owned_subs,
                }
            )
            entry = roster.characters[sub_id]
            if slot.awakening_required and entry.awakening < slot.awakening_required:
                investment_gaps.append(
                    {
                        "position": slot.position,
                        "character_id": sub_id,
                        "required_awakening": slot.awakening_required,
                        "actual_awakening": entry.awakening,
                    }
                )
        else:
            missing_characters.append(
                {
                    "position": slot.position,
                    "character_id": primary,
                    "substitutes": slot.substitutes,
                    "is_required": slot.is_required,
                }
            )

    total_slots = len(_team_slots(team)) or 8
    investment_gap_count = len(investment_gaps)

    if owned_count == 0:
        feasibility = "unavailable"
    elif owned_count == total_slots and investment_gap_count == 0:
        feasibility = "full"
    else:
        feasibility = "partial"

    return {
        "team_id": team.id,
        "team_name": team.name,
        "feasibility": feasibility,
        "owned_count": owned_count,
        "total_slots": total_slots,
        "investment_gap_count": investment_gap_count,
        "has_owned_substitutes": has_owned_substitutes,
        "missing_characters": missing_characters,
        "investment_gaps": investment_gaps,
        "suggested_substitutions": suggested_substitutions,
        "investment_level": team.investment_level.value,
    }


def sort_teams_by_roster_feasibility(scored: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort feasibility scores per plan: tier → owned ↓ → gaps ↑ → subs ↓ → investment."""
    return sorted(
        scored,
        key=lambda s: (
            FEASIBILITY_ORDER.get(s["feasibility"], 99),
            -s["owned_count"],
            s["investment_gap_count"],
            -int(s["has_owned_substitutes"]),
            INVESTMENT_LEVEL_ORDER.get(s.get("investment_level", "medium"), 1),
            s["team_id"],
        ),
    )


def teams_for_roster(
    teams: list[Team],
    roster: PlayerRoster | None,
    team_to_dict_fn,
) -> dict[str, Any]:
    """Build roster-aware proven team payload for MCP."""
    if roster is None or not roster.characters:
        return {
            "roster_applied": False,
            "teams": [team_to_dict_fn(t) for t in teams],
            "teams_for_my_roster": [],
        }

    scored = [score_team_feasibility(t, roster) for t in teams]
    sorted_scores = sort_teams_by_roster_feasibility(scored)
    team_by_id = {t.id: t for t in teams}

    enriched = []
    for score in sorted_scores:
        team = team_by_id[score["team_id"]]
        entry = team_to_dict_fn(team)
        entry["roster_feasibility"] = score
        enriched.append(entry)

    feasible = [e for e in enriched if e["roster_feasibility"]["feasibility"] == "full"]
    partial = [e for e in enriched if e["roster_feasibility"]["feasibility"] == "partial"]

    return {
        "roster_applied": True,
        "teams": [team_to_dict_fn(t) for t in teams],
        "teams_for_my_roster": enriched,
        "feasible_proven_teams": feasible,
        "partial_proven_teams": partial,
    }


def upsert_roster_characters(
    updates: dict[str, RosterEntry | dict],
    path: Path | None = None,
    known_ids: set[str] | None = None,
) -> PlayerRoster:
    """Merge character entries into saved roster."""
    file_path = path or roster_path()
    roster = load_roster(file_path) or PlayerRoster()

    if known_ids is not None:
        ids = list(updates.keys())
        _, errors = validate_character_ids_strict(ids, known_ids)
        if errors:
            raise ValueError("; ".join(errors))

    for char_id, raw in updates.items():
        entry = raw if isinstance(raw, RosterEntry) else RosterEntry.model_validate(raw)
        roster.characters[char_id] = entry

    save_roster(roster, file_path, known_ids=known_ids)
    return roster


def remove_roster_characters(
    character_ids: list[str],
    path: Path | None = None,
) -> PlayerRoster:
    """Remove characters from saved roster."""
    file_path = path or roster_path()
    roster = load_roster(file_path) or PlayerRoster()
    for char_id in character_ids:
        roster.characters.pop(char_id, None)
    save_roster(roster, file_path)
    return roster


def import_roster_yaml(
    yaml_content: str,
    merge: bool = False,
    path: Path | None = None,
    known_ids: set[str] | None = None,
) -> PlayerRoster:
    """Import roster from YAML string (replace or merge)."""
    data = yaml.safe_load(yaml_content)
    if not data:
        raise ValueError("Empty YAML content.")
    incoming = PlayerRoster.model_validate(data)

    file_path = path or roster_path()
    if merge:
        existing = load_roster(file_path) or PlayerRoster()
        existing.characters.update(incoming.characters)
        if incoming.last_updated:
            existing.last_updated = incoming.last_updated
        roster = existing
    else:
        roster = incoming

    save_roster(roster, file_path, known_ids=known_ids)
    return roster


def known_character_ids(retrieval: RetrievalService) -> set[str]:
    """All valid character IDs from the data loader."""
    if not retrieval._characters_cache:
        retrieval.initialize()
    return set(retrieval._characters_cache.keys())
