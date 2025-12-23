"""
YAML Data Loader for COTC game data.

Loads human-curated YAML files and parses them into Pydantic models.
Handles validation and provides helpful error messages for malformed data.
"""

import logging
from pathlib import Path
from typing import TypeVar

import yaml
from pydantic import ValidationError

from .models import Boss, Character, Team

logger = logging.getLogger(__name__)

T = TypeVar("T", Character, Boss, Team)


class DataLoader:
    """
    Loads game data from YAML files.

    All loaded data is human-curated. This loader does NOT generate
    any game knowledge - it only reads what humans have provided.
    """

    def __init__(self, data_dir: str | Path):
        """
        Initialize the data loader.

        Args:
            data_dir: Path to the data directory containing
                      characters/, bosses/, teams/ subdirectories.
        """
        self.data_dir = Path(data_dir)
        self._validate_data_dir()

    def _validate_data_dir(self) -> None:
        """Validate that the data directory structure exists."""
        if not self.data_dir.exists():
            raise FileNotFoundError(f"Data directory not found: {self.data_dir}")

        required_dirs = ["characters", "bosses", "teams"]
        for subdir in required_dirs:
            path = self.data_dir / subdir
            if not path.exists():
                logger.warning(f"Expected subdirectory not found: {path}")

    def _load_yaml_file(self, file_path: Path) -> dict:
        """Load a single YAML file."""
        with open(file_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _is_data_file(self, file_path: Path) -> bool:
        """Check if a file is a data file (not schema/template/example)."""
        name = file_path.stem
        # Skip schema, template, and example files
        if name.startswith("_"):
            return False
        return file_path.suffix in (".yaml", ".yml")

    def _load_entity(
        self,
        file_path: Path,
        model_class: type[T],
    ) -> T | None:
        """
        Load a single entity from a YAML file.

        Args:
            file_path: Path to the YAML file.
            model_class: Pydantic model class to parse into.

        Returns:
            Parsed model instance, or None if validation fails.
        """
        try:
            data = self._load_yaml_file(file_path)
            if not data:
                logger.warning(f"Empty file: {file_path}")
                return None

            return model_class.model_validate(data)

        except ValidationError as e:
            logger.error(f"Validation error in {file_path}:\n{e}")
            return None
        except yaml.YAMLError as e:
            logger.error(f"YAML parse error in {file_path}:\n{e}")
            return None
        except Exception as e:
            logger.error(f"Error loading {file_path}: {e}")
            return None

    def load_characters(self) -> list[Character]:
        """
        Load all character files from the characters/ directory.

        Returns:
            List of parsed Character models.
        """
        characters_dir = self.data_dir / "characters"
        characters = []

        if not characters_dir.exists():
            logger.warning("Characters directory not found")
            return characters

        for file_path in characters_dir.glob("*.yaml"):
            if not self._is_data_file(file_path):
                continue

            character = self._load_entity(file_path, Character)
            if character:
                characters.append(character)
                logger.debug(f"Loaded character: {character.id}")

        for file_path in characters_dir.glob("*.yml"):
            if not self._is_data_file(file_path):
                continue

            character = self._load_entity(file_path, Character)
            if character:
                characters.append(character)
                logger.debug(f"Loaded character: {character.id}")

        logger.info(f"Loaded {len(characters)} characters")
        return characters

    def load_bosses(self) -> list[Boss]:
        """
        Load all boss files from the bosses/ directory.

        Returns:
            List of parsed Boss models.
        """
        bosses_dir = self.data_dir / "bosses"
        bosses = []

        if not bosses_dir.exists():
            logger.warning("Bosses directory not found")
            return bosses

        for file_path in bosses_dir.glob("*.yaml"):
            if not self._is_data_file(file_path):
                continue

            boss = self._load_entity(file_path, Boss)
            if boss:
                bosses.append(boss)
                logger.debug(f"Loaded boss: {boss.id}")

        for file_path in bosses_dir.glob("*.yml"):
            if not self._is_data_file(file_path):
                continue

            boss = self._load_entity(file_path, Boss)
            if boss:
                bosses.append(boss)
                logger.debug(f"Loaded boss: {boss.id}")

        logger.info(f"Loaded {len(bosses)} bosses")
        return bosses

    def load_teams(self) -> list[Team]:
        """
        Load all team files from the teams/ directory.

        Returns:
            List of parsed Team models.
        """
        teams_dir = self.data_dir / "teams"
        teams = []

        if not teams_dir.exists():
            logger.warning("Teams directory not found")
            return teams

        for file_path in teams_dir.glob("*.yaml"):
            if not self._is_data_file(file_path):
                continue

            team = self._load_entity(file_path, Team)
            if team:
                teams.append(team)
                logger.debug(f"Loaded team: {team.id}")

        for file_path in teams_dir.glob("*.yml"):
            if not self._is_data_file(file_path):
                continue

            team = self._load_entity(file_path, Team)
            if team:
                teams.append(team)
                logger.debug(f"Loaded team: {team.id}")

        logger.info(f"Loaded {len(teams)} teams")
        return teams

    def load_all(self) -> tuple[list[Character], list[Boss], list[Team]]:
        """
        Load all game data.

        Returns:
            Tuple of (characters, bosses, teams).
        """
        return (
            self.load_characters(),
            self.load_bosses(),
            self.load_teams(),
        )

    def load_character_by_id(self, character_id: str) -> Character | None:
        """
        Load a specific character by ID.

        Args:
            character_id: The character's unique ID.

        Returns:
            Character model if found, None otherwise.
        """
        characters_dir = self.data_dir / "characters"

        # Try exact filename match
        for ext in (".yaml", ".yml"):
            file_path = characters_dir / f"{character_id}{ext}"
            if file_path.exists():
                return self._load_entity(file_path, Character)

        # Fall back to searching all files
        for character in self.load_characters():
            if character.id == character_id:
                return character

        return None

    def load_boss_by_id(self, boss_id: str) -> Boss | None:
        """
        Load a specific boss by ID.

        Args:
            boss_id: The boss's unique ID.

        Returns:
            Boss model if found, None otherwise.
        """
        bosses_dir = self.data_dir / "bosses"

        # Try exact filename match
        for ext in (".yaml", ".yml"):
            file_path = bosses_dir / f"{boss_id}{ext}"
            if file_path.exists():
                return self._load_entity(file_path, Boss)

        # Fall back to searching all files
        for boss in self.load_bosses():
            if boss.id == boss_id:
                return boss

        return None

    def load_teams_for_boss(self, boss_id: str) -> list[Team]:
        """
        Load all teams designed for a specific boss.

        Args:
            boss_id: The boss's unique ID.

        Returns:
            List of Team models for this boss.
        """
        all_teams = self.load_teams()
        return [team for team in all_teams if team.boss_id == boss_id]


def get_embedding_texts(entities: list[Character | Boss | Team]) -> list[str]:
    """
    Extract embedding text from a list of entities.

    Args:
        entities: List of Character, Boss, or Team models.

    Returns:
        List of text strings suitable for embedding.
    """
    return [entity.get_embedding_text() for entity in entities]


def get_metadata_list(entities: list[Character | Boss | Team]) -> list[dict]:
    """
    Extract metadata from a list of entities.

    Args:
        entities: List of Character, Boss, or Team models.

    Returns:
        List of metadata dictionaries.
    """
    return [entity.get_metadata() for entity in entities]
