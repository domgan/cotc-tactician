"""Smoke tests for roster web UI API."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.roster_ui.app import create_app

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("COTC_ROSTER_FILE", str(tmp_path / "roster.yaml"))
    return TestClient(create_app(DATA_DIR))


def test_index(client: TestClient) -> None:
    res = client.get("/")
    assert res.status_code == 200
    assert "COTC Tactician" in res.text
    assert res.headers["cache-control"] == "no-cache"


def test_list_characters(client: TestClient) -> None:
    res = client.get("/api/characters")
    assert res.status_code == 200
    chars = res.json()
    assert len(chars) > 200
    assert "id" in chars[0]
    assert "display_name" in chars[0]


def test_roster_get_empty(client: TestClient) -> None:
    res = client.get("/api/roster")
    assert res.status_code == 200
    data = res.json()
    assert data["configured"] is False
    assert data["owned_count"] == 0


def test_roster_put_and_patch(client: TestClient) -> None:
    put = client.put(
        "/api/roster",
        json={
            "schema_version": "1.0",
            "characters": {
                "solon": {"awakening": 4, "au": True, "ult_level": 20},
            },
        },
    )
    assert put.status_code == 200
    assert put.json()["owned_count"] == 1

    patch = client.patch(
        "/api/roster/solon",
        json={"awakening": 3, "au": False, "ult_level": 10},
    )
    assert patch.status_code == 200
    assert patch.json()["characters"]["solon"]["awakening"] == 3

    delete = client.delete("/api/roster/solon")
    assert delete.status_code == 200
    assert delete.json()["owned_count"] == 0


def test_roster_put_rejects_unknown(client: TestClient) -> None:
    res = client.put(
        "/api/roster",
        json={
            "characters": {"not-real-char": {"awakening": 0, "au": False, "ult_level": 0}},
        },
    )
    assert res.status_code == 400


def test_roster_import_export(client: TestClient) -> None:
    yaml_text = """
schema_version: "1.0"
characters:
  phenn:
    awakening: 1
    au: false
    ult_level: 0
"""
    imp = client.post("/api/roster/import?merge=false", json={"content": yaml_text})
    assert imp.status_code == 200
    assert imp.json()["owned_count"] == 1

    exp = client.get("/api/roster/export")
    assert exp.status_code == 200
    assert "phenn" in exp.json()["yaml"]
