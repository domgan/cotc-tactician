"""
Reasoning Pipeline for COTC team composition.

Linear pipeline that:
1. Parses user input
2. Retrieves relevant context from data
3. Assembles structured prompt
4. Calls LLM for reasoning
5. Returns structured output

The LLM is treated as ignorant - all game knowledge comes from data.
"""

import json
import logging
from pathlib import Path
from typing import Protocol

from .prompts import SYSTEM_PROMPT, build_prompt
from .retrieval import RetrievalService
from .vector_store import VectorStore

logger = logging.getLogger(__name__)


class LLMClient(Protocol):
    """Protocol for LLM clients."""
    
    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        """Send a chat completion request."""
        ...


class OpenAIClient:
    """OpenAI API client."""
    
    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4-turbo-preview",
    ):
        """
        Initialize OpenAI client.
        
        Args:
            api_key: OpenAI API key. If None, uses OPENAI_API_KEY env var.
            model: Model to use for completions.
        """
        import openai
        
        self.client = openai.OpenAI(api_key=api_key)
        self.model = model
    
    def chat(self, system_prompt: str, user_prompt: str) -> str:
        """Send a chat completion request."""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,  # Lower temperature for more consistent reasoning
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content


class OllamaClient:
    """Ollama local LLM client."""
    
    def __init__(
        self,
        model: str = "llama3.1",
        host: str = "http://localhost:11434",
    ):
        """
        Initialize Ollama client.
        
        Args:
            model: Model name to use.
            host: Ollama server host.
        """
        import ollama
        
        self.client = ollama.Client(host=host)
        self.model = model
    
    def chat(self, system_prompt: str, user_prompt: str) -> str:
        """Send a chat completion request."""
        response = self.client.chat(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            options={"temperature": 0.3},
            format="json",
        )
        return response["message"]["content"]


class ReasoningPipeline:
    """
    Main reasoning pipeline for team composition.
    
    Flow:
    1. Parse input (boss_id or description)
    2. Retrieve context from data
    3. Build prompt with context
    4. Call LLM for analysis
    5. Parse and return structured output
    """
    
    def __init__(
        self,
        data_dir: str | Path,
        llm_client: LLMClient | None = None,
        vector_store: VectorStore | None = None,
    ):
        """
        Initialize the reasoning pipeline.
        
        Args:
            data_dir: Path to the data directory.
            llm_client: LLM client for reasoning. If None, must be set later.
            vector_store: Vector store for semantic search.
        """
        self.retrieval = RetrievalService(
            data_dir=data_dir,
            vector_store=vector_store,
        )
        self.llm_client = llm_client
        self._initialized = False
    
    def initialize(self, force_reindex: bool = False) -> dict[str, int]:
        """
        Initialize the pipeline by loading and indexing data.
        
        Args:
            force_reindex: If True, reindex even if already done.
            
        Returns:
            Statistics about indexed data.
        """
        stats = self.retrieval.initialize(force_reindex=force_reindex)
        self._initialized = True
        return stats
    
    def set_llm_client(self, client: LLMClient) -> None:
        """Set the LLM client."""
        self.llm_client = client
    
    def compose_team(
        self,
        boss_id: str | None = None,
        boss_description: str | None = None,
        available_character_ids: list[str] | None = None,
    ) -> dict:
        """
        Main entry point for team composition.
        
        Args:
            boss_id: ID of a known boss (exact match).
            boss_description: Free-text description for unknown boss.
            available_character_ids: List of character IDs the user has.
            
        Returns:
            Structured team composition recommendations.
        """
        if not self._initialized:
            self.initialize()
        
        if self.llm_client is None:
            raise RuntimeError("LLM client not configured. Call set_llm_client() first.")
        
        # Step 1: Validate input
        if not boss_id and not boss_description:
            return {
                "error": "Either boss_id or boss_description must be provided.",
                "data_completeness": {"boss_data": "minimal"},
            }
        
        # Step 2: Retrieve context
        logger.info(f"Retrieving context for boss_id={boss_id}, description={boss_description[:50] if boss_description else None}")
        
        context = self.retrieval.retrieve_context_for_boss(
            boss_id=boss_id,
            boss_description=boss_description,
            available_character_ids=available_character_ids,
        )
        
        # Check if we have any data
        if not context["boss"] and not context["similar_bosses"]:
            logger.warning("No boss data found in context")
        
        if not context["candidate_characters"]:
            logger.warning("No candidate characters found")
            return {
                "error": "No character data available for team composition.",
                "data_completeness": context["data_completeness"],
            }
        
        # Step 3: Build prompt
        user_prompt = build_prompt(context)
        
        logger.info(f"Built prompt with {len(context['candidate_characters'])} characters, "
                   f"{len(context['proven_teams'])} teams")
        
        # Step 4: Call LLM
        logger.info("Calling LLM for team composition reasoning")
        
        try:
            response = self.llm_client.chat(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=user_prompt,
            )
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return {
                "error": f"LLM call failed: {str(e)}",
                "data_completeness": context["data_completeness"],
            }
        
        # Step 5: Parse response
        try:
            result = json.loads(response)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            return {
                "error": "LLM returned invalid JSON",
                "raw_response": response,
                "data_completeness": context["data_completeness"],
            }
        
        # Add metadata
        result["_metadata"] = {
            "boss_id": boss_id,
            "boss_description": boss_description[:100] if boss_description else None,
            "characters_considered": [c.id for c in context["candidate_characters"]],
            "proven_teams_found": [t.id for t in context["proven_teams"]],
        }
        
        return result
    
    def get_boss_info(self, boss_id: str) -> dict | None:
        """
        Get information about a specific boss.
        
        This is a helper method for exploration, not for team composition.
        
        Args:
            boss_id: The boss's unique ID.
            
        Returns:
            Boss data as dictionary, or None if not found.
        """
        if not self._initialized:
            self.initialize()
        
        boss = self.retrieval.get_boss_by_id(boss_id)
        if boss:
            return boss.model_dump()
        return None
    
    def get_character_info(self, character_id: str) -> dict | None:
        """
        Get information about a specific character.
        
        Args:
            character_id: The character's unique ID.
            
        Returns:
            Character data as dictionary, or None if not found.
        """
        if not self._initialized:
            self.initialize()
        
        character = self.retrieval.get_character_by_id(character_id)
        if character:
            return character.model_dump()
        return None
    
    def list_bosses(self) -> list[str]:
        """List all indexed boss IDs."""
        if not self._initialized:
            self.initialize()
        
        return list(self.retrieval._bosses_cache.keys())
    
    def list_characters(self) -> list[str]:
        """List all indexed character IDs."""
        if not self._initialized:
            self.initialize()
        
        return list(self.retrieval._characters_cache.keys())
    
    def list_teams(self) -> list[str]:
        """List all indexed team IDs."""
        if not self._initialized:
            self.initialize()
        
        return list(self.retrieval._teams_cache.keys())

