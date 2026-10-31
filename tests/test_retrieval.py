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
    Passive,
    PassiveCategory,
    Role,
    Skill,
    SkillCategory,
    SkillTarget,
    SkillType,
    Weaknesses,
    Weapon,
)
from src.retrieval import (
    RetrievalService,
    _character_covers_weakness,
    _normalize_role,
    _normalize_weakness,
    tier_score,
)
from src.vector_store import VectorStore

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class _FakeEmbedding:
    def __call__(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * 8 for _ in texts]


def _char(
    char_id: str, display_name: str, coverage: list[str], roles: list[Role] | None = None
) -> Character:
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


def test_weakness_matches_rank_by_jp_tier_score():
    weak = _char("a-weak", "A Weak", ["bow"])
    weak.jp_tier = "F | 8.0"
    strong = _char("z-strong", "Z Strong", ["bow"])
    strong.jp_tier = "S+ | 9.9"
    unrated = _char("m-unrated", "M Unrated", ["bow"])
    service = _service([weak, strong, unrated])

    assert [c.id for c in service.find_characters_by_weakness("bow")] == [
        "z-strong",
        "a-weak",
        "m-unrated",
    ]
    assert tier_score(strong) == 9.9
    assert tier_score(unrated) == 0.0


def _kit_char(char_id: str, effects: list[str], passive: str) -> Character:
    char = _char(char_id, char_id.title(), [])
    char.skills = [
        Skill(
            skill_category=SkillCategory.ACTIVE,
            unlock_tier="2★",
            sp_cost=60,
            skill_type=SkillType.DEBUFF,
            target=SkillTarget.AOE,
            effects=effects,
        )
    ]
    char.passives = [Passive(passive_category=PassiveCategory.TP, effect=passive)]
    return char


def test_search_kit_effects_returns_only_matching_sentences():
    rocbouquet = _kit_char(
        "rocbouquet",
        [
            "Deal Elem. Wind damage to All Foes.",
            "Also lower their Phys. Def. and Elem. Def. by 15%.",
        ],
        "Raise Damage Limit of All Allies by 15,000.",
    )
    other = _kit_char("other", ["Deal Phys. Sword damage."], "Raise own Fire Res. by 10%.")
    service = _service([rocbouquet, other])

    results = service.search_kit_effects([r"lower.*Elem\. Def"])
    assert [(c.id, m) for c, m in results] == [
        (
            "rocbouquet",
            [
                {
                    "source": "active",
                    "unlock_tier": "2★",
                    "sp_cost": 60,
                    "matched": ["Also lower their Phys. Def. and Elem. Def. by 15%."],
                }
            ],
        )
    ]


def test_search_kit_effects_sources_match_all_and_roster():
    rocbouquet = _kit_char(
        "rocbouquet",
        ["Also lower their Phys. Def. by 15%."],
        "Raise Damage Limit of All Allies by 15,000.",
    )
    service = _service([rocbouquet])

    assert service.search_kit_effects(["damage limit"], sources=["active"]) == []
    assert (
        service.search_kit_effects(["damage limit"], sources=["passive"])[0][0].id == "rocbouquet"
    )
    assert service.search_kit_effects(["lower", "Damage Limit"], match_all=True) == []
    assert service.search_kit_effects(["Phys. Def"], character_ids=["someone-else"]) == []
    assert service.search_kit_effects(["(unclosed"]) == []


def test_initialize_reloads_when_data_changes(tmp_path):
    for sub in ("characters", "bosses", "teams"):
        (tmp_path / sub).mkdir()
    char_file = tmp_path / "characters" / "alpha.yaml"
    char_file.write_text(
        "id: alpha\ndisplay_name: Alpha\nrarity: 5\njob: hunter\n", encoding="utf-8"
    )
    store = VectorStore(embedding_function=_FakeEmbedding())
    service = RetrievalService(tmp_path, vector_store=store)

    service.initialize()
    assert service.list_character_ids() == ["alpha"]

    (tmp_path / "characters" / "beta.yaml").write_text(
        "id: beta\ndisplay_name: Beta\nrarity: 5\njob: cleric\n", encoding="utf-8"
    )
    char_file.unlink()
    service.initialize()

    assert service.list_character_ids() == ["beta"]
    assert store.get_collection_stats()["characters"] == 1
