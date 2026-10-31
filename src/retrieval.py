"""
Retrieval service for COTC game data.

Combines data loader and vector store to provide unified retrieval patterns.
All retrieved data is human-curated - the LLM does NOT participate in retrieval.
"""

import logging
import re
from collections.abc import Iterator
from pathlib import Path

from .data_loader import DataLoader
from .models import Boss, Character, Role, Team
from .vector_store import VectorStore

logger = logging.getLogger(__name__)


def _normalize_weakness(value: str) -> str:
    return value.lower().strip()


def _normalize_role(value: str) -> Role | None:
    normalized = value.lower().strip()
    try:
        return Role(normalized)
    except ValueError:
        return None


def _character_covers_weakness(character: Character, weakness: str) -> bool:
    target = _normalize_weakness(weakness)
    return any(_normalize_weakness(w) == target for w in character.weakness_coverage)


def tier_score(character: Character) -> float:
    """Numeric community score from jp_tier (e.g. 'S+ | 9.9' -> 9.9); 0 when unrated."""
    match = re.search(r"\d+(?:\.\d+)?", (character.jp_tier or "").split("|")[-1])
    return float(match.group()) if match else 0.0


def strength_sort_key(character: Character) -> tuple[float, str]:
    """Sort key: highest JP tier score first, then name."""
    return (-tier_score(character), character.display_name)


def _compile_term(term: str) -> re.Pattern[str]:
    try:
        return re.compile(term, re.IGNORECASE)
    except re.error:
        return re.compile(re.escape(term), re.IGNORECASE)


def _kit_entries(character: Character) -> Iterator[dict]:
    """Flatten a kit into searchable entries: identity fields + list of texts."""
    for skill in character.skills:
        yield _without_none(
            {
                "source": skill.skill_category.value,
                "name": skill.name,
                "unlock_tier": skill.unlock_tier,
                "sp_cost": skill.sp_cost,
                "texts": [*skill.effects, *skill.upgrades, skill.limit_break_upgrade],
            }
        )
    for passive in character.passives:
        yield _without_none(
            {
                "source": "passive",
                "name": passive.name,
                "unlock_tier": passive.unlock_tier,
                "texts": [passive.effect, *passive.upgrades, passive.limit_break_upgrade],
            }
        )
    if character.a4_accessory:
        yield {
            "source": "a4",
            "name": character.a4_accessory.name,
            "texts": [character.a4_accessory.passive_effect],
        }


def _without_none(entry: dict) -> dict:
    entry["texts"] = [t for t in entry["texts"] if t]
    return {k: v for k, v in entry.items() if v is not None}


class RetrievalService:
    """
    Unified retrieval service for game data.

    Provides both exact-match lookups and semantic search capabilities.
    All returned data is human-curated.
    """

    def __init__(
        self,
        data_dir: str | Path,
        vector_store: VectorStore | None = None,
    ):
        """
        Initialize the retrieval service.

        Args:
            data_dir: Path to the data directory.
            vector_store: Optional pre-configured vector store.
                         If None, creates one with in-memory storage.
        """
        self.data_loader = DataLoader(data_dir)
        self.vector_store = vector_store or VectorStore()

        # Cache for exact lookups
        self._characters_cache: dict[str, Character] = {}
        self._bosses_cache: dict[str, Boss] = {}
        self._teams_cache: dict[str, Team] = {}

        self._indexed = False
        self._fingerprint: str | None = None

    def initialize(self, force_reindex: bool = False) -> dict[str, int]:
        """
        Load data and index into vector store; reload when data files changed.

        Re-embeds only when the persisted index was built from different data,
        so a long-running MCP server picks up YAML edits without a restart.

        Args:
            force_reindex: If True, rebuild the index even if data is unchanged.

        Returns:
            Dictionary with counts of indexed entities.
        """
        fingerprint = self.data_loader.fingerprint()
        if self._indexed and not force_reindex and fingerprint == self._fingerprint:
            return self.vector_store.get_collection_stats()

        characters, bosses, teams = self.data_loader.load_all()
        self._characters_cache = {c.id: c for c in characters}
        self._bosses_cache = {b.id: b for b in bosses}
        self._teams_cache = {t.id: t for t in teams}

        if force_reindex or self.vector_store.get_data_fingerprint() != fingerprint:
            self.vector_store.clear_all()
            self.vector_store.index_all(characters, bosses, teams)
            self.vector_store.set_data_fingerprint(fingerprint)

        self._fingerprint = fingerprint
        self._indexed = True
        stats = self.vector_store.get_collection_stats()
        logger.info(f"Initialized retrieval service: {stats}")
        return stats

    # =========================================================================
    # BOSS RETRIEVAL
    # =========================================================================

    def get_boss_by_id(self, boss_id: str) -> Boss | None:
        """
        Get a boss by exact ID.

        THIS MUST COME FROM DATA, NOT THE MODEL.

        Args:
            boss_id: The boss's unique ID.

        Returns:
            Boss model if found, None otherwise.
        """
        # Check cache first
        if boss_id in self._bosses_cache:
            return self._bosses_cache[boss_id]

        # Try loading directly
        boss = self.data_loader.load_boss_by_id(boss_id)
        if boss:
            self._bosses_cache[boss_id] = boss
        return boss

    def find_similar_bosses(
        self,
        description: str,
        n_results: int = 3,
    ) -> list[Boss]:
        """
        Find bosses with similar mechanics based on description.

        Used when user describes an unknown boss to find patterns.

        Args:
            description: Free-text description of boss mechanics.
            n_results: Number of similar bosses to return.

        Returns:
            List of similar Boss models.
        """
        results = self.vector_store.search_bosses(
            query=description,
            n_results=n_results,
        )

        bosses = []
        for result in results:
            boss_id = result["id"]
            boss = self.get_boss_by_id(boss_id)
            if boss:
                bosses.append(boss)

        return bosses

    # =========================================================================
    # CHARACTER RETRIEVAL
    # =========================================================================

    def get_character_by_id(self, character_id: str) -> Character | None:
        """
        Get a character by exact ID.

        THIS MUST COME FROM DATA, NOT THE MODEL.

        Args:
            character_id: The character's unique ID.

        Returns:
            Character model if found, None otherwise.
        """
        # Check cache first
        if character_id in self._characters_cache:
            return self._characters_cache[character_id]

        # Try loading directly
        character = self.data_loader.load_character_by_id(character_id)
        if character:
            self._characters_cache[character_id] = character
        return character

    def get_characters_by_ids(self, character_ids: list[str]) -> list[Character]:
        """
        Get multiple characters by their IDs.

        Args:
            character_ids: List of character IDs.

        Returns:
            List of found Character models (missing IDs are skipped).
        """
        characters = []
        for char_id in character_ids:
            char = self.get_character_by_id(char_id)
            if char:
                characters.append(char)
        return characters

    def find_characters_for_boss(
        self,
        boss: Boss,
        available_character_ids: list[str] | None = None,
        n_results: int = 20,
    ) -> list[Character]:
        """
        Find characters suitable for a specific boss.

        THIS LOGIC COMES FROM DATA (boss fields), NOT THE MODEL.

        Filters by:
        - Element matching boss weaknesses
        - Weapons matching boss weaknesses
        - Roles matching boss required roles

        Args:
            boss: The target boss.
            available_character_ids: Optional list of characters the user has.
                                    If None, searches all characters.
            n_results: Maximum number of results.

        Returns:
            List of suitable Character models.
        """
        # Build search query from boss requirements
        query_parts = []

        # Add weakness elements
        if boss.weaknesses and boss.weaknesses.elements:
            elements = [e.value for e in boss.weaknesses.elements]
            query_parts.append(f"Element: {', '.join(elements)}")

        # Add weakness weapons
        if boss.weaknesses and boss.weaknesses.weapons:
            weapons = [w.value for w in boss.weaknesses.weapons]
            query_parts.append(f"Weapons: {', '.join(weapons)}")

        # Add required roles
        if boss.required_roles:
            roles = [rr.role.value for rr in boss.required_roles]
            query_parts.append(f"Roles: {', '.join(roles)}")

        query = " ".join(query_parts) if query_parts else "DPS character"

        # Semantic search
        results = self.vector_store.search_characters(
            query=query,
            n_results=n_results * 2,  # Get extra to filter
        )

        # Filter by availability if specified
        candidates = []
        for result in results:
            char_id = result["id"]

            # Skip if not in available list
            if available_character_ids and char_id not in available_character_ids:
                continue

            char = self.get_character_by_id(char_id)
            if char:
                candidates.append(char)

            if len(candidates) >= n_results:
                break

        return candidates

    def find_characters_by_role(
        self,
        roles: list[Role],
        weakness_type: str | None = None,
        n_results: int = 10,
    ) -> list[Character]:
        """
        Find characters matching specific roles.

        Args:
            roles: List of roles to search for.
            weakness_type: Optional element/weapon coverage filter (e.g., 'fire', 'sword').
            n_results: Maximum number of results.

        Returns:
            List of matching Character models.
        """
        role_strings = [r.value for r in roles]

        results = self.vector_store.search_characters_by_role(
            roles=role_strings,
            weakness_type=weakness_type,
            n_results=n_results,
        )

        characters = []
        for result in results:
            char_id = result["id"]
            char = self.get_character_by_id(char_id)
            if char:
                characters.append(char)

        return characters

    def get_all_characters(self) -> list[Character]:
        """Get all loaded characters."""
        if not self._characters_cache:
            self.initialize()
        return list(self._characters_cache.values())

    def list_boss_ids(self) -> list[str]:
        """Return sorted boss IDs from the loaded cache."""
        if not self._bosses_cache:
            self.initialize()
        return sorted(self._bosses_cache.keys())

    def list_character_ids(self) -> list[str]:
        """Return sorted character IDs from the loaded cache."""
        if not self._characters_cache:
            self.initialize()
        return sorted(self._characters_cache.keys())

    def list_team_ids(self) -> list[str]:
        """Return sorted team IDs from the loaded cache."""
        if not self._teams_cache:
            self.initialize()
        return sorted(self._teams_cache.keys())

    def get_boss_weaknesses(self, boss: Boss) -> list[str]:
        """
        Extract flat weakness list from a boss (boss-level or main-target enemy).

        Returns lowercased element/weapon strings, e.g. ["bow", "light", "fan"].
        """
        weaknesses: list[str] = []
        if boss.weaknesses:
            if boss.weaknesses.elements:
                weaknesses.extend(e.value for e in boss.weaknesses.elements)
            if boss.weaknesses.weapons:
                weaknesses.extend(w.value for w in boss.weaknesses.weapons)
        elif boss.enemies:
            main_enemy = next(
                (e for e in boss.enemies if e.is_main_target),
                boss.enemies[0] if boss.enemies else None,
            )
            if main_enemy and main_enemy.weaknesses:
                if main_enemy.weaknesses.elements:
                    weaknesses.extend(e.value for e in main_enemy.weaknesses.elements)
                if main_enemy.weaknesses.weapons:
                    weaknesses.extend(w.value for w in main_enemy.weaknesses.weapons)
        return [_normalize_weakness(w) for w in weaknesses]

    def find_characters_by_weakness(
        self,
        weakness: str,
        *,
        character_ids: list[str] | None = None,
        limit: int = 5,
    ) -> list[Character]:
        """
        Find characters that cover a weakness via exact cache lookup.

        When character_ids is set (roster mode), only those characters are searched.
        No fallback to the global pool when roster mode yields zero matches.
        """
        target = _normalize_weakness(weakness)
        matching = [
            char
            for char in self.character_pool(character_ids)
            if _character_covers_weakness(char, target)
        ]
        matching.sort(key=strength_sort_key)
        return matching[:limit]

    def find_characters_by_weakness_any(
        self,
        weaknesses: set[str],
        *,
        character_ids: list[str] | None = None,
    ) -> list[Character]:
        """Characters covering at least one of the weaknesses, strongest first."""
        matching = [
            char
            for char in self.character_pool(character_ids)
            if any(_character_covers_weakness(char, w) for w in weaknesses)
        ]
        matching.sort(key=strength_sort_key)
        return matching

    def find_characters_by_role_exact(
        self,
        role: str,
        *,
        character_ids: list[str] | None = None,
        limit: int = 8,
    ) -> list[Character]:
        """
        Find characters with a role via exact cache lookup on char.roles.

        When character_ids is set (roster mode), only those characters are searched.
        No fallback to the global pool when roster mode yields zero matches.
        """
        target_role = _normalize_role(role)
        if target_role is None:
            return []

        matching = [
            char for char in self.character_pool(character_ids) if target_role in char.roles
        ]
        matching.sort(key=strength_sort_key)
        return matching[:limit]

    def character_pool(self, character_ids: list[str] | None = None) -> list[Character]:
        """
        Characters to search: the given IDs (roster mode) or the whole database.

        Roster mode never falls back to the global pool when it yields no matches.
        """
        if not self._characters_cache:
            self.initialize()
        if character_ids is None:
            return list(self._characters_cache.values())
        return [
            self._characters_cache[cid] for cid in character_ids if cid in self._characters_cache
        ]

    def search_kit_effects(
        self,
        terms: list[str],
        *,
        character_ids: list[str] | None = None,
        sources: list[str] | None = None,
        match_all: bool = False,
    ) -> list[tuple[Character, list[dict]]]:
        """
        Exact search over kit text (skills, passives, EX, ultimate, A4 accessory).

        Terms are case-insensitive regexes (invalid patterns match literally).
        An entry matches when any term (or every term with match_all) hits its text.
        Returns (character, matching entries) sorted strongest first.
        """
        patterns = [_compile_term(t) for t in terms if t.strip()]
        if not patterns:
            return []
        wanted = {s.lower() for s in sources} if sources else None

        results = []
        for char in self.character_pool(character_ids):
            matches = []
            for entry in _kit_entries(char):
                if wanted and entry["source"] not in wanted:
                    continue
                hit_texts = [t for t in entry.pop("texts") if any(p.search(t) for p in patterns)]
                if not hit_texts:
                    continue
                if match_all and not all(any(p.search(t) for t in hit_texts) for p in patterns):
                    continue
                matches.append({**entry, "matched": hit_texts})
            if matches:
                results.append((char, matches))
        results.sort(key=lambda item: strength_sort_key(item[0]))
        return results

    # =========================================================================
    # TEAM RETRIEVAL
    # =========================================================================

    def get_team_by_id(self, team_id: str) -> Team | None:
        """
        Get a team by exact ID.

        Args:
            team_id: The team's unique ID.

        Returns:
            Team model if found, None otherwise.
        """
        if team_id in self._teams_cache:
            return self._teams_cache[team_id]

        # Teams don't have direct file lookup, search cache
        return None

    def get_teams_for_boss(self, boss_id: str) -> list[Team]:
        """
        Get all proven teams for a specific boss.

        THIS MUST COME FROM DATA, NOT THE MODEL.

        Args:
            boss_id: The boss's unique ID.

        Returns:
            List of Team models for this boss.
        """
        # Check cache
        teams = [t for t in self._teams_cache.values() if t.boss_id == boss_id]

        if not teams:
            # Try loading from disk
            teams = self.data_loader.load_teams_for_boss(boss_id)
            for team in teams:
                self._teams_cache[team.id] = team

        return teams

    def get_universal_teams(self, boss: Boss) -> list[Team]:
        """
        Universal teams (no boss_id) whose applies_to covers this boss's content type.

        Teams targeting the boss's EX rank come first.
        """
        if not self._teams_cache:
            self.initialize()
        teams = [
            t
            for t in self._teams_cache.values()
            if t.boss_id is None and boss.content_type in t.applies_to
        ]
        teams.sort(key=lambda t: (t.target_ex_rank != boss.ex_rank, t.name))
        return teams

    def get_teams_for_planning(self, boss: Boss) -> list[Team]:
        """Boss-specific proven teams followed by matching universal teams."""
        return self.get_teams_for_boss(boss.id) + self.get_universal_teams(boss)

    def find_similar_teams(
        self,
        query: str,
        n_results: int = 5,
    ) -> list[Team]:
        """
        Find teams with similar strategies.

        Used when no exact boss match exists.

        Args:
            query: Description of desired strategy or boss mechanics.
            n_results: Number of results to return.

        Returns:
            List of similar Team models.
        """
        results = self.vector_store.search_teams(
            query=query,
            n_results=n_results,
        )

        teams = []
        for result in results:
            team_id = result["id"]
            team = self.get_team_by_id(team_id)
            if team:
                teams.append(team)

        return teams

    # =========================================================================
    # COMPOSITE RETRIEVAL
    # =========================================================================

    def retrieve_context_for_boss(
        self,
        boss_id: str | None = None,
        boss_description: str | None = None,
        available_character_ids: list[str] | None = None,
    ) -> dict:
        """
        Retrieve all relevant context for team composition.

        This is the main entry point for the reasoning pipeline.
        All returned data is human-curated.

        Args:
            boss_id: ID of a known boss.
            boss_description: Free-text description for unknown boss.
            available_character_ids: Characters the user has available.

        Returns:
            Dictionary with all retrieved context.
        """
        context = {
            "boss": None,
            "similar_bosses": [],
            "proven_teams": [],
            "candidate_characters": [],
            "data_completeness": {
                "boss_data": "minimal",
                "character_data": "minimal",
                "proven_teams_available": False,
            },
        }

        # Get boss data
        if boss_id:
            boss = self.get_boss_by_id(boss_id)
            if boss:
                context["boss"] = boss
                context["data_completeness"]["boss_data"] = (
                    "complete" if boss.data_confidence.value == "verified" else "partial"
                )

                # Get proven teams for this boss (plus matching universal teams)
                teams = self.get_teams_for_planning(boss)
                context["proven_teams"] = teams
                context["data_completeness"]["proven_teams_available"] = len(teams) > 0

                # Get candidate characters based on boss requirements
                characters = self.find_characters_for_boss(
                    boss,
                    available_character_ids,
                )
                context["candidate_characters"] = characters

        elif boss_description:
            # Find similar bosses for pattern matching
            similar = self.find_similar_bosses(boss_description, n_results=3)
            context["similar_bosses"] = similar

            # Find teams for similar bosses
            teams_by_id = {
                team.id: team for boss in similar for team in self.get_teams_for_planning(boss)
            }
            context["proven_teams"].extend(teams_by_id.values())

            context["data_completeness"]["proven_teams_available"] = (
                len(context["proven_teams"]) > 0
            )

            # Get characters based on available list or general search
            if available_character_ids:
                context["candidate_characters"] = self.get_characters_by_ids(
                    available_character_ids
                )
            else:
                # Search based on description
                results = self.vector_store.search_characters(
                    query=boss_description,
                    n_results=15,
                )
                for result in results:
                    char = self.get_character_by_id(result["id"])
                    if char:
                        context["candidate_characters"].append(char)

        # Update character data completeness
        if context["candidate_characters"]:
            verified_count = sum(
                1 for c in context["candidate_characters"] if c.data_confidence.value == "verified"
            )
            ratio = verified_count / len(context["candidate_characters"])
            if ratio > 0.8:
                context["data_completeness"]["character_data"] = "complete"
            elif ratio > 0.5:
                context["data_completeness"]["character_data"] = "partial"

        return context
