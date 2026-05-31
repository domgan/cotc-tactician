"""Tests for RetrievalService weakness matching helpers."""

from pathlib import Path

from src.models import (
    Boss,
    Character,
    ContentType,
    Difficulty,
    Element,
    Enemy,
    Job,
    Role,
    Weaknesses,
    Weapon,
)
from src.retrieval import (
    RetrievalService,
    _character_covers_weakness,
    _normalize_role,
    _normalize_weakness,
)
from src.vector_store import VectorStore

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class _FakeEmbedding:
    def __call__(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * 8 for _ in texts]


def _char(char_id: str, display_name: str, coverage: list[str], roles: list[Role] | None = None) -> Character:
    return Character(
        id=char_id,
        display_name=display_name,
        rarity=5,
        job=Job.HUNTER,
        weakness_coverage=coverage,
        roles=roles or [],
    )


def _service(characters: list[Character]) -> RetrievalService:
    service = RetrievalService(
        DATA_DIR,
        vector_store=VectorStore(embedding_function=_FakeEmbedding()),
    )
    service._characters_cache = {c.id: c for c in characters}
    service._indexed = True
    return service


def test_normalize_weakness():
    assert _normalize_weakness(" Bow ") == "bow"
    assert _normalize_weakness("Light") == "light"


def test_character_covers_weakness_case_insensitive():
    char = _char("scarecrow", "Scarecrow", ["bow", "dark"])
    assert _character_covers_weakness(char, "Bow")
    assert _character_covers_weakness(char, "bow")
    assert not _character_covers_weakness(char, "light")


def test_get_boss_weaknesses_from_boss_level():
    boss = Boss(
        id="test-boss",
        display_name="Test Boss",
        content_type=ContentType.ARENA,
        difficulty=Difficulty.HARD,
        weaknesses=Weaknesses(elements=[Element.LIGHT], weapons=[Weapon.BOW]),
    )
    service = _service([])
    assert service.get_boss_weaknesses(boss) == ["light", "bow"]


def test_get_boss_weaknesses_from_main_enemy():
    boss = Boss(
        id="arena-tikilen",
        display_name="Tikilen",
        content_type=ContentType.ARENA,
        difficulty=Difficulty.EXTREME,
        enemies=[
            Enemy(
                name="Tikilen",
                is_main_target=True,
                weaknesses=Weaknesses(
                    elements=[Element.LIGHT],
                    weapons=[Weapon.BOW, Weapon.FAN],
                ),
            )
        ],
    )
    service = _service([])
    assert service.get_boss_weaknesses(boss) == ["light", "bow", "fan"]


def test_find_characters_by_weakness_global_pool():
    chars = [
        _char("scarecrow", "Scarecrow", ["bow", "dark"]),
        _char("solon", "Solon", ["fire", "polearm", "tome"]),
        _char("fiore-ex", "Fiore EX", ["fan"]),
    ]
    service = _service(chars)

    bow_chars = service.find_characters_by_weakness("bow")
    assert [c.id for c in bow_chars] == ["scarecrow"]


def test_find_characters_by_weakness_strict_roster():
    chars = [
        _char("scarecrow", "Scarecrow", ["bow", "dark"]),
        _char("solon", "Solon", ["fire", "polearm", "tome"]),
        _char("rinyuu-ex", "Rinyuu EX", ["axe", "fire", "ice", "light"]),
        _char("fiore-ex", "Fiore EX", ["fan"]),
    ]
    service = _service(chars)
    roster = ["solon", "scarecrow", "fiore-ex", "viola"]

    assert [c.id for c in service.find_characters_by_weakness("bow", character_ids=roster)] == [
        "scarecrow"
    ]
    assert service.find_characters_by_weakness("light", character_ids=roster) == []


def test_find_characters_by_weakness_roster_does_not_fallback_to_global():
    chars = [
        _char("scarecrow", "Scarecrow", ["bow", "dark"]),
        _char("ophilia", "Ophilia", ["light", "staff"]),
    ]
    service = _service(chars)
    roster = ["scarecrow"]

    light_matches = service.find_characters_by_weakness("light", character_ids=roster)
    assert light_matches == []


def test_find_characters_by_weakness_case_insensitive_query():
    char = _char("scarecrow", "Scarecrow", ["bow"])
    service = _service([char])
    assert service.find_characters_by_weakness("Bow")[0].id == "scarecrow"


def test_find_characters_by_weakness_respects_limit():
    chars = [
        _char("a-hunter", "A Hunter", ["bow"]),
        _char("b-hunter", "B Hunter", ["bow"]),
        _char("c-hunter", "C Hunter", ["bow"]),
    ]
    service = _service(chars)
    assert len(service.find_characters_by_weakness("bow", limit=2)) == 2


def test_normalize_role():
    assert _normalize_role("DPS") == Role.DPS
    assert _normalize_role(" Debuffer ") == Role.DEBUFFER
    assert _normalize_role("not-a-role") is None


def test_find_characters_by_role_exact():
    chars = [
        _char("signa", "Signa", ["fan"], roles=[Role.DEBUFFER, Role.BREAKER]),
        _char("viola", "Viola", ["dagger"], roles=[Role.DEBUFFER]),
        _char("solon", "Solon", ["fire"], roles=[Role.DPS]),
    ]
    service = _service(chars)

    debuffers = service.find_characters_by_role_exact("debuffer")
    assert {c.id for c in debuffers} == {"signa", "viola"}
    assert service.find_characters_by_role_exact("invalid") == []


def test_find_characters_by_role_exact_normalization():
    chars = [_char("signa", "Signa", ["fan"], roles=[Role.DEBUFFER])]
    service = _service(chars)
    assert service.find_characters_by_role_exact("DEBUFFER")[0].id == "signa"
    assert service.find_characters_by_role_exact("garbage") == []


def test_find_characters_by_role_exact_roster_strict():
    chars = [
        _char("signa", "Signa", ["fan"], roles=[Role.DEBUFFER]),
        _char("viola", "Viola", ["dagger"], roles=[Role.DEBUFFER]),
    ]
    service = _service(chars)
    roster = ["solon"]

    assert service.find_characters_by_role_exact("debuffer", character_ids=roster) == []


def test_list_boss_ids_and_character_ids():
    service = RetrievalService(
        DATA_DIR,
        vector_store=VectorStore(embedding_function=_FakeEmbedding()),
    )
    service._bosses_cache = {
        "b-boss": Boss(
            id="b-boss",
            display_name="B Boss",
            content_type=ContentType.ARENA,
            difficulty=Difficulty.HARD,
        ),
        "a-boss": Boss(
            id="a-boss",
            display_name="A Boss",
            content_type=ContentType.ARENA,
            difficulty=Difficulty.HARD,
        ),
    }
    service._characters_cache = {
        "z-char": _char("z-char", "Z Char", []),
        "a-char": _char("a-char", "A Char", []),
    }
    service._indexed = True

    assert service.list_boss_ids() == ["a-boss", "b-boss"]
    assert service.list_character_ids() == ["a-char", "z-char"]
