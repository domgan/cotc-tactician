"""
Run repo-defined MCP scenarios against a real `mcp_server` subprocess over stdio.

Each tests/mcp_scenarios/<id>.yaml holds deterministic `steps` (checked here against
the fixture roster) plus `agent_prompt` / `agent_checks` for agent-driven runs
against the live MCP in Cursor. See AGENTS.md "MCP scenario tests".
"""

import json
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent.parent
SCENARIO_DIR = Path(__file__).resolve().parent / "mcp_scenarios"
FIXTURE_ROSTER = SCENARIO_DIR / "roster.yaml"
VECTOR_DIR = ROOT / ".pytest_cache" / "mcp-vectordb"

SCENARIOS = sorted(p for p in SCENARIO_DIR.glob("*.yaml") if p != FIXTURE_ROSTER)
OWNED_IDS = set(yaml.safe_load(FIXTURE_ROSTER.read_text(encoding="utf-8"))["characters"])


def select(data: Any, path: str) -> list[Any]:
    """Dotted path lookup; `*` fans out over dict values / list items."""
    nodes = [data]
    for part in path.split("."):
        next_nodes: list[Any] = []
        for node in nodes:
            if part == "*":
                values = node.values() if isinstance(node, dict) else node
                for value in values:
                    next_nodes.extend(value if isinstance(value, list) else [value])
            elif isinstance(node, dict) and part in node:
                next_nodes.append(node[part])
        nodes = next_nodes
    return nodes


def items(data: Any, path: str) -> list[Any]:
    flat: list[Any] = []
    for node in select(data, path):
        flat.extend(node if isinstance(node, list) else [node])
    return flat


def ids(data: Any, path: str) -> list[str]:
    return [item["id"] for item in items(data, path) if isinstance(item, dict) and "id" in item]


def check_expectations(data: Any, expect: dict) -> list[str]:
    """Return human-readable failures for one step's `expect` block."""
    failures = []
    text = json.dumps(data, ensure_ascii=False)

    for path, expected in (expect.get("equals") or {}).items():
        actual = select(data, path)
        if actual != [expected]:
            failures.append(f"equals {path}: expected {expected!r}, got {actual!r}")
    for path, wanted in (expect.get("includes_ids") or {}).items():
        missing = set(wanted) - set(ids(data, path))
        if missing:
            failures.append(f"includes_ids {path}: missing {sorted(missing)}")
    for path, unwanted in (expect.get("excludes_ids") or {}).items():
        present = set(unwanted) & set(ids(data, path))
        if present:
            failures.append(f"excludes_ids {path}: unexpected {sorted(present)}")
    for path in expect.get("ids_owned") or []:
        unowned = set(ids(data, path)) - OWNED_IDS
        if unowned:
            failures.append(f"ids_owned {path}: not in roster {sorted(unowned)}")
    for path, minimum in (expect.get("min_items") or {}).items():
        count = len(items(data, path))
        if count < minimum:
            failures.append(f"min_items {path}: expected >= {minimum}, got {count}")
    for needle in expect.get("contains_text") or []:
        if needle not in text:
            failures.append(f"contains_text: {needle!r} not found")
    for needle in expect.get("not_contains_text") or []:
        if needle in text:
            failures.append(f"not_contains_text: {needle!r} found")
    return failures


def tool_payload(result: Any) -> Any:
    """Decode a call_tool result into the JSON value the tool returned."""
    if result.structuredContent is not None:
        payload = result.structuredContent
        return payload["result"] if set(payload) == {"result"} else payload
    return json.loads(result.content[0].text)


def server_params(roster_mode: str, tmp_path: Path) -> StdioServerParameters:
    roster_file = FIXTURE_ROSTER if roster_mode == "fixture" else tmp_path / "no-roster.yaml"
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "src.mcp_server"],
        cwd=str(ROOT),
        env={"COTC_ROSTER_FILE": str(roster_file), "COTC_VECTOR_DIR": str(VECTOR_DIR)},
    )


@pytest.mark.parametrize("scenario_path", SCENARIOS, ids=lambda p: p.stem)
async def test_mcp_scenario(scenario_path: Path, tmp_path: Path):
    scenario = yaml.safe_load(scenario_path.read_text(encoding="utf-8"))
    assert scenario["id"] == scenario_path.stem
    assert scenario.get("agent_prompt") and scenario.get("agent_checks")

    failures = []
    async with stdio_client(server_params(scenario["roster"], tmp_path)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            for index, step in enumerate(scenario["steps"]):
                result = await session.call_tool(step["tool"], step.get("args") or {})
                assert not result.isError, f"step {index} {step['tool']} errored: {result.content}"
                for failure in check_expectations(tool_payload(result), step.get("expect") or {}):
                    failures.append(f"step {index} {step['tool']}: {failure}")

    assert not failures, "\n".join(failures)
