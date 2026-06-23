"""FastAPI app for roster management UI."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ..models import PlayerRoster, RosterEntry
from ..retrieval import RetrievalService
from ..roster import (
    import_roster_yaml,
    known_character_ids,
    load_roster_with_meta,
    roster_path,
    save_roster,
)
from ..vector_store import VectorStore

STATIC_DIR = Path(__file__).parent / "static"


class RosterPutBody(BaseModel):
    schema_version: str = "1.0"
    characters: dict[str, RosterEntry] = Field(default_factory=dict)


class RosterPatchBody(BaseModel):
    awakening: int = Field(default=0, ge=0, le=4)
    au: bool = False
    ult_level: int = Field(default=0, ge=0, le=20)


class ImportBody(BaseModel):
    content: str


def create_app(data_dir: Path, retrieval: RetrievalService | None = None) -> FastAPI:
    """Build FastAPI application bound to game data directory."""
    app = FastAPI(title="COTC Tactician Roster", docs_url=None, redoc_url=None)

    if retrieval is None:
        vector_dir = data_dir.parent / ".vectordb"
        vector_store = VectorStore(persist_directory=vector_dir)
        retrieval = RetrievalService(data_dir=data_dir, vector_store=vector_store)
        retrieval.initialize()
    known = known_character_ids(retrieval)

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/characters")
    def list_characters() -> list[dict]:
        chars = sorted(retrieval._characters_cache.values(), key=lambda c: c.display_name)
        return [
            {
                "id": c.id,
                "display_name": c.display_name,
                "job": c.job.value,
                "rarity": c.rarity,
                "gl_tier": c.gl_tier,
                "jp_tier": c.jp_tier,
            }
            for c in chars
        ]

    @app.get("/api/roster")
    def get_roster() -> dict:
        return load_roster_with_meta(known_ids=known)

    @app.put("/api/roster")
    def put_roster(body: RosterPutBody) -> dict:
        roster = PlayerRoster(
            schema_version=body.schema_version,
            characters=body.characters,
        )
        try:
            save_roster(roster, known_ids=known)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return load_roster_with_meta(known_ids=known)

    @app.patch("/api/roster/{character_id}")
    def patch_roster(character_id: str, body: RosterPatchBody) -> dict:
        if character_id not in known:
            raise HTTPException(status_code=400, detail=f"Unknown character '{character_id}'")
        meta = load_roster_with_meta(known_ids=known)
        characters = {
            cid: RosterEntry.model_validate(data)
            for cid, data in meta.get("characters", {}).items()
        }
        characters[character_id] = RosterEntry(
            awakening=body.awakening,
            au=body.au,
            ult_level=body.ult_level,
        )
        roster = PlayerRoster(characters=characters)
        save_roster(roster, known_ids=known)
        return load_roster_with_meta(known_ids=known)

    @app.delete("/api/roster/{character_id}")
    def delete_roster_character(character_id: str) -> dict:
        meta = load_roster_with_meta(known_ids=known)
        characters = {
            cid: RosterEntry.model_validate(data)
            for cid, data in meta.get("characters", {}).items()
            if cid != character_id
        }
        roster = PlayerRoster(characters=characters)
        save_roster(roster, known_ids=known)
        return load_roster_with_meta(known_ids=known)

    @app.post("/api/roster/import")
    def post_import(body: ImportBody, merge: bool = False) -> dict:
        try:
            import_roster_yaml(body.content, merge=merge, known_ids=known)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return load_roster_with_meta(known_ids=known)

    @app.get("/api/roster/export")
    def export_roster() -> dict:
        meta = load_roster_with_meta(known_ids=known)
        return {
            "path": str(roster_path()),
            "yaml": _roster_to_yaml(meta),
        }

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


def _roster_to_yaml(meta: dict) -> str:
    import yaml

    payload = {
        "schema_version": meta.get("schema_version", "1.0"),
        "last_updated": meta.get("last_updated"),
        "characters": meta.get("characters", {}),
    }
    return yaml.safe_dump(payload, default_flow_style=False, sort_keys=False)


def _default_data_dir() -> Path:
    if env_path := os.environ.get("COTC_DATA_DIR"):
        return Path(env_path)
    return Path(__file__).parent.parent.parent / "data"


def create_app_for_uvicorn() -> FastAPI:
    """Factory entrypoint for uvicorn --reload."""
    return create_app(_default_data_dir())
