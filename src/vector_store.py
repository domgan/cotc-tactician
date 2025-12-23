"""
Vector Store implementation using ChromaDB.

Provides semantic search capabilities for game entities.
Designed with abstraction layer for easy swapping to other vector DBs.
"""

import json
import logging
from pathlib import Path
from typing import Protocol

import chromadb
from chromadb.config import Settings

from .models import Boss, Character, Team

logger = logging.getLogger(__name__)


class EmbeddingFunction(Protocol):
    """Protocol for embedding functions."""

    def __call__(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a list of texts."""
        ...


class SentenceTransformerEmbedding:
    """Embedding function using sentence-transformers."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        """
        Initialize the embedding function.

        Args:
            model_name: Name of the sentence-transformer model.
        """
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model_name)
        self.model_name = model_name

    def __call__(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for texts."""
        embeddings = self.model.encode(texts, convert_to_numpy=True)
        return embeddings.tolist()


class VectorStore:
    """
    Vector store for semantic search of game entities.

    Uses ChromaDB for storage and retrieval.
    Supports characters, bosses, and teams as separate collections.
    """

    COLLECTION_CHARACTERS = "characters"
    COLLECTION_BOSSES = "bosses"
    COLLECTION_TEAMS = "teams"

    def __init__(
        self,
        persist_directory: str | Path | None = None,
        embedding_function: EmbeddingFunction | None = None,
    ):
        """
        Initialize the vector store.

        Args:
            persist_directory: Directory to persist the database.
                               If None, uses in-memory storage.
            embedding_function: Function to generate embeddings.
                                If None, uses sentence-transformers.
        """
        self.persist_directory = Path(persist_directory) if persist_directory else None

        # Initialize ChromaDB client
        if self.persist_directory:
            self.persist_directory.mkdir(parents=True, exist_ok=True)
            self.client = chromadb.PersistentClient(
                path=str(self.persist_directory),
                settings=Settings(anonymized_telemetry=False),
            )
        else:
            self.client = chromadb.Client(
                settings=Settings(anonymized_telemetry=False),
            )

        # Initialize embedding function
        if embedding_function is None:
            self._embedding_fn = SentenceTransformerEmbedding()
        else:
            self._embedding_fn = embedding_function

        # Get or create collections
        self._characters_collection = self.client.get_or_create_collection(
            name=self.COLLECTION_CHARACTERS,
            metadata={"description": "COTC character data"},
        )
        self._bosses_collection = self.client.get_or_create_collection(
            name=self.COLLECTION_BOSSES,
            metadata={"description": "COTC boss data"},
        )
        self._teams_collection = self.client.get_or_create_collection(
            name=self.COLLECTION_TEAMS,
            metadata={"description": "COTC team compositions"},
        )

    def _serialize_metadata(self, metadata: dict) -> dict:
        """
        Serialize metadata for ChromaDB storage.

        ChromaDB only supports string, int, float, bool values.
        Lists must be JSON serialized.
        """
        result = {}
        for key, value in metadata.items():
            if isinstance(value, list):
                result[key] = json.dumps(value)
            elif value is None:
                result[key] = ""
            else:
                result[key] = value
        return result

    def _deserialize_metadata(self, metadata: dict) -> dict:
        """Deserialize metadata from ChromaDB storage."""
        result = {}
        for key, value in metadata.items():
            if isinstance(value, str) and value.startswith("["):
                try:
                    result[key] = json.loads(value)
                except json.JSONDecodeError:
                    result[key] = value
            else:
                result[key] = value
        return result

    # =========================================================================
    # INDEXING
    # =========================================================================

    def index_characters(self, characters: list[Character]) -> int:
        """
        Index characters into the vector store.

        Args:
            characters: List of Character models to index.

        Returns:
            Number of characters indexed.
        """
        if not characters:
            return 0

        ids = [c.id for c in characters]
        texts = [c.get_embedding_text() for c in characters]
        metadatas = [self._serialize_metadata(c.get_metadata()) for c in characters]
        embeddings = self._embedding_fn(texts)

        # Upsert to handle updates
        self._characters_collection.upsert(
            ids=ids,
            embeddings=embeddings,
            metadatas=metadatas,
            documents=texts,
        )

        logger.info(f"Indexed {len(characters)} characters")
        return len(characters)

    def index_bosses(self, bosses: list[Boss]) -> int:
        """
        Index bosses into the vector store.

        Args:
            bosses: List of Boss models to index.

        Returns:
            Number of bosses indexed.
        """
        if not bosses:
            return 0

        ids = [b.id for b in bosses]
        texts = [b.get_embedding_text() for b in bosses]
        metadatas = [self._serialize_metadata(b.get_metadata()) for b in bosses]
        embeddings = self._embedding_fn(texts)

        self._bosses_collection.upsert(
            ids=ids,
            embeddings=embeddings,
            metadatas=metadatas,
            documents=texts,
        )

        logger.info(f"Indexed {len(bosses)} bosses")
        return len(bosses)

    def index_teams(self, teams: list[Team]) -> int:
        """
        Index teams into the vector store.

        Args:
            teams: List of Team models to index.

        Returns:
            Number of teams indexed.
        """
        if not teams:
            return 0

        ids = [t.id for t in teams]
        texts = [t.get_embedding_text() for t in teams]
        metadatas = [self._serialize_metadata(t.get_metadata()) for t in teams]
        embeddings = self._embedding_fn(texts)

        self._teams_collection.upsert(
            ids=ids,
            embeddings=embeddings,
            metadatas=metadatas,
            documents=texts,
        )

        logger.info(f"Indexed {len(teams)} teams")
        return len(teams)

    def index_all(
        self,
        characters: list[Character],
        bosses: list[Boss],
        teams: list[Team],
    ) -> dict[str, int]:
        """
        Index all game data.

        Args:
            characters: Characters to index.
            bosses: Bosses to index.
            teams: Teams to index.

        Returns:
            Dictionary with counts per entity type.
        """
        return {
            "characters": self.index_characters(characters),
            "bosses": self.index_bosses(bosses),
            "teams": self.index_teams(teams),
        }

    # =========================================================================
    # SEARCH - CHARACTERS
    # =========================================================================

    def search_characters(
        self,
        query: str,
        n_results: int = 10,
        where: dict | None = None,
    ) -> list[dict]:
        """
        Semantic search for characters.

        Args:
            query: Search query text.
            n_results: Maximum number of results.
            where: Optional metadata filter.

        Returns:
            List of results with id, document, metadata, distance.
        """
        query_embedding = self._embedding_fn([query])[0]

        results = self._characters_collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        return self._format_results(results)

    def search_characters_by_role(
        self,
        roles: list[str],
        weakness_type: str | None = None,
        n_results: int = 10,
    ) -> list[dict]:
        """
        Search characters by role with optional weakness coverage filter.

        Note: ChromaDB has limited filtering, so this does a semantic
        search with role keywords and post-filters.

        Args:
            roles: List of roles to search for.
            weakness_type: Optional element/weapon filter (e.g., 'fire', 'sword').
            n_results: Maximum number of results.

        Returns:
            List of matching characters.
        """
        # Build query from roles
        query = f"Character with roles: {', '.join(roles)}"
        if weakness_type:
            query += f" with {weakness_type} coverage"

        results = self.search_characters(query, n_results=n_results * 2)

        # Post-filter by metadata
        filtered = []
        for result in results:
            metadata = self._deserialize_metadata(result.get("metadata", {}))

            # Check weakness coverage (combined elements and weapons)
            if weakness_type:
                weakness_coverage = metadata.get("weakness_coverage", [])
                if isinstance(weakness_coverage, str):
                    weakness_coverage = json.loads(weakness_coverage)
                if weakness_type not in weakness_coverage:
                    continue

            # Check roles (at least one match)
            char_roles = metadata.get("roles", [])
            if isinstance(char_roles, str):
                char_roles = json.loads(char_roles)
            if char_roles and not any(r in char_roles for r in roles):
                continue

            filtered.append(result)
            if len(filtered) >= n_results:
                break

        return filtered

    # =========================================================================
    # SEARCH - BOSSES
    # =========================================================================

    def search_bosses(
        self,
        query: str,
        n_results: int = 5,
        where: dict | None = None,
    ) -> list[dict]:
        """
        Semantic search for bosses.

        Args:
            query: Search query text.
            n_results: Maximum number of results.
            where: Optional metadata filter.

        Returns:
            List of results with id, document, metadata, distance.
        """
        query_embedding = self._embedding_fn([query])[0]

        results = self._bosses_collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        return self._format_results(results)

    def get_boss_by_id(self, boss_id: str) -> dict | None:
        """
        Get a boss by exact ID.

        Args:
            boss_id: The boss's unique ID.

        Returns:
            Boss data if found, None otherwise.
        """
        results = self._bosses_collection.get(
            ids=[boss_id],
            include=["documents", "metadatas"],
        )

        if results["ids"]:
            return {
                "id": results["ids"][0],
                "document": results["documents"][0] if results["documents"] else None,
                "metadata": self._deserialize_metadata(
                    results["metadatas"][0] if results["metadatas"] else {}
                ),
            }
        return None

    # =========================================================================
    # SEARCH - TEAMS
    # =========================================================================

    def search_teams(
        self,
        query: str,
        n_results: int = 5,
        where: dict | None = None,
    ) -> list[dict]:
        """
        Semantic search for teams.

        Args:
            query: Search query text.
            n_results: Maximum number of results.
            where: Optional metadata filter.

        Returns:
            List of results with id, document, metadata, distance.
        """
        query_embedding = self._embedding_fn([query])[0]

        results = self._teams_collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        return self._format_results(results)

    def get_teams_for_boss(self, boss_id: str) -> list[dict]:
        """
        Get all teams designed for a specific boss.

        Args:
            boss_id: The boss's unique ID.

        Returns:
            List of team data.
        """
        results = self._teams_collection.get(
            where={"boss_id": boss_id},
            include=["documents", "metadatas"],
        )

        teams = []
        for i, id_ in enumerate(results["ids"]):
            teams.append(
                {
                    "id": id_,
                    "document": results["documents"][i] if results["documents"] else None,
                    "metadata": self._deserialize_metadata(
                        results["metadatas"][i] if results["metadatas"] else {}
                    ),
                }
            )
        return teams

    # =========================================================================
    # UTILITIES
    # =========================================================================

    def _format_results(self, results: dict) -> list[dict]:
        """Format ChromaDB results into a cleaner structure."""
        formatted = []

        if not results["ids"] or not results["ids"][0]:
            return formatted

        for i, id_ in enumerate(results["ids"][0]):
            item = {"id": id_}

            if results.get("documents") and results["documents"][0]:
                item["document"] = results["documents"][0][i]

            if results.get("metadatas") and results["metadatas"][0]:
                item["metadata"] = self._deserialize_metadata(results["metadatas"][0][i])

            if results.get("distances") and results["distances"][0]:
                item["distance"] = results["distances"][0][i]

            formatted.append(item)

        return formatted

    def get_collection_stats(self) -> dict:
        """Get statistics about the indexed data."""
        return {
            "characters": self._characters_collection.count(),
            "bosses": self._bosses_collection.count(),
            "teams": self._teams_collection.count(),
        }

    def clear_all(self) -> None:
        """Clear all collections (for testing/reset)."""
        self.client.delete_collection(self.COLLECTION_CHARACTERS)
        self.client.delete_collection(self.COLLECTION_BOSSES)
        self.client.delete_collection(self.COLLECTION_TEAMS)

        # Recreate empty collections
        self._characters_collection = self.client.get_or_create_collection(
            name=self.COLLECTION_CHARACTERS,
        )
        self._bosses_collection = self.client.get_or_create_collection(
            name=self.COLLECTION_BOSSES,
        )
        self._teams_collection = self.client.get_or_create_collection(
            name=self.COLLECTION_TEAMS,
        )

        logger.info("Cleared all collections")
