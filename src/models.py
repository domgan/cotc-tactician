"""
Pydantic models for COTC game entities.

All models represent human-curated data. The LLM does NOT generate these values.
Fields are designed to be flexible for partial/incomplete data.
"""

from datetime import date
from enum import Enum

from pydantic import BaseModel, Field

# =============================================================================
# ENUMS
# =============================================================================


class Element(str, Enum):
    """Game elements (in weakness order)."""

    FIRE = "fire"
    ICE = "ice"
    LIGHTNING = "lightning"
    WIND = "wind"
    LIGHT = "light"  # Also called "Holy" in some contexts
    DARK = "dark"
    NONE = "none"


class Weapon(str, Enum):
    """Game weapon types (in weakness order)."""

    SWORD = "sword"
    POLEARM = "polearm"  # Also called "Spear" in some contexts
    DAGGER = "dagger"
    AXE = "axe"
    BOW = "bow"
    STAFF = "staff"
    TOME = "tome"
    FAN = "fan"


class Job(str, Enum):
    """Character job classes."""

    WARRIOR = "warrior"  # Primary weapon: Sword
    MERCHANT = "merchant"  # Primary weapon: Spear
    THIEF = "thief"  # Primary weapon: Dagger
    APOTHECARY = "apothecary"  # Primary weapon: Axe
    HUNTER = "hunter"  # Primary weapon: Bow
    CLERIC = "cleric"  # Primary weapon: Staff
    SCHOLAR = "scholar"  # Primary weapon: Tome (elemental attacks)
    DANCER = "dancer"  # Primary weapon: Fan (elemental attacks)


class Influence(str, Enum):
    """Character influence types (from game data)."""

    WEALTH = "wealth"
    POWER = "power"
    FAME = "fame"
    DOMINATION = "domination"
    OPULENCE = "opulence"
    APPROVAL = "approval"


class SkillCategory(str, Enum):
    """Skill category for team composition purposes."""

    ACTIVE = "active"  # Regular active skills (all available at max level)
    TP = "tp"  # TP skill (requires Blessing of the Lantern)
    EX = "ex"  # EX skill (conditional trigger, doesn't use equip slot)
    SPECIAL = "special"  # Special/Ultimate ability (separate gauge)


class PassiveCategory(str, Enum):
    """Passive category."""

    INNATE = "innate"  # Regular passives (all available at max level)
    TP = "tp"  # TP passive (from Blessing of the Lantern)
    BASIC = "basic"  # Basic/core passive (special innate passives)


class Role(str, Enum):
    """Abstract team roles."""

    TANK = "tank"
    HEALER = "healer"
    BUFFER = "buffer"
    DEBUFFER = "debuffer"
    BREAKER = "breaker"
    DPS = "dps"


class TeamRole(str, Enum):
    """Specific roles within a team composition."""

    TANK = "tank"
    HEALER = "healer"
    BUFFER = "buffer"
    DEBUFFER = "debuffer"
    BREAKER = "breaker"
    PRIMARY_DPS = "primary_dps"
    SECONDARY_DPS = "secondary_dps"
    UTILITY = "utility"


class SkillType(str, Enum):
    """Skill function types."""

    ATTACK = "attack"
    BUFF = "buff"
    DEBUFF = "debuff"
    HEAL = "heal"
    UTILITY = "utility"
    MIXED = "mixed"  # Attack + buff/debuff in one skill


class SkillTarget(str, Enum):
    """Skill targeting options."""

    SELF = "self"
    SINGLE_ALLY = "single_ally"
    PAIRED_ALLY = "paired_ally"  # Character in same row slot
    FRONT_ROW = "front_row"
    BACK_ROW = "back_row"
    ALL_ALLIES = "all_allies"
    SINGLE_ENEMY = "single_enemy"
    AOE = "aoe"  # All enemies
    RANDOM = "random"  # Random enemy targets


class MechanicType(str, Enum):
    """Boss mechanic types."""

    ATTACK = "attack"
    BUFF_SELF = "buff_self"
    DEBUFF_PARTY = "debuff_party"
    ULTIMATE = "ultimate"
    PASSIVE = "passive"
    PHASE_TRANSITION = "phase_transition"
    ENRAGE = "enrage"
    COUNTER = "counter"
    OTHER = "other"


class MechanicTarget(str, Enum):
    """Boss mechanic targeting."""

    SELF = "self"  # Boss targets itself (buffs)
    SINGLE = "single"
    FRONT_ROW = "front_row"
    BACK_ROW = "back_row"
    ALL = "all"
    RANDOM = "random"
    HIGHEST_HP = "highest_hp"
    LOWEST_HP = "lowest_hp"
    PROVOKER = "provoker"


class ThreatLevel(str, Enum):
    """Mechanic threat assessment."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Difficulty(str, Enum):
    """Boss difficulty rating."""

    EASY = "easy"
    NORMAL = "normal"
    HARD = "hard"
    VERY_HARD = "very_hard"  # ★★★★☆
    EXPERT = "expert"
    EXTREME = "extreme"  # ★★★★★+


class ContentType(str, Enum):
    """Content category."""

    STORY = "story"
    STORY_BOSS = "story_boss"  # Major story boss
    SIDE_STORY = "side_story"
    NPC_BATTLE = "npc_battle"  # 100/120 NPC battles
    SUPERBOSS = "superboss"
    TOWER = "tower"
    ARENA = "arena"
    ADVERSARY_LOG = "adversary_log"  # EX fights (宿敵の写記)
    EVENT = "event"
    OTHER = "other"


class StrategyType(str, Enum):
    """Team strategy approach."""

    BURST = "burst"
    SUSTAIN = "sustain"
    SAFE = "safe"
    SPEED_CLEAR = "speed_clear"
    LOW_INVESTMENT = "low_investment"
    CHEESE = "cheese"


class InvestmentLevel(str, Enum):
    """Resource requirements."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    WHALE = "whale"


class DataConfidence(str, Enum):
    """Data reliability indicator."""

    VERIFIED = "verified"
    TESTED = "tested"
    THEORETICAL = "theoretical"
    INCOMPLETE = "incomplete"
    COMPLETE = "complete"


class SynergyType(str, Enum):
    """Types of character synergies."""

    BUFF_STACKING = "buff_stacking"
    ELEMENT_CHAIN = "element_chain"
    ROLE_COMPRESSION = "role_compression"
    SPEED_TUNING = "speed_tuning"
    DEBUFF_CHAIN = "debuff_chain"
    OTHER = "other"


class SpeedCategory(str, Enum):
    """Relative speed tiers."""

    VERY_FAST = "very_fast"
    FAST = "fast"
    MEDIUM = "medium"
    SLOW = "slow"
    VERY_SLOW = "very_slow"


class RolePriority(str, Enum):
    """How important a role is for a boss."""

    REQUIRED = "required"
    STRONGLY_RECOMMENDED = "strongly_recommended"
    RECOMMENDED = "recommended"
    OPTIONAL = "optional"


class BattlePhase(str, Enum):
    """Phases of a battle for turn planning."""

    SETUP = "setup"
    BREAK_PUSH = "break_push"
    BREAK_WINDOW = "break_window"
    SUSTAIN = "sustain"
    BURST = "burst"
    RECOVERY = "recovery"


class ExRank(str, Enum):
    """EX difficulty rank for Adversary Log bosses."""

    BASE = "base"  # Standard arena/story version
    EX1 = "ex1"  # First EX rematch (~2x HP)
    EX2 = "ex2"  # Second EX rematch (~3x HP)
    EX3 = "ex3"  # Third EX rematch (~5x HP)


class TankType(str, Enum):
    """Tank archetype for character classification."""

    PROVOKE = "provoke"  # Draw attacks via Provoke (Gilderoy, Serenoa)
    DODGE = "dodge"  # Evade via Sidestep (H'aanit EX, Canary)
    COVER = "cover"  # Intercept for allies (Fiore EX only)
    HP_BARRIER = "hp_barrier"  # Create HP shields (Sazantos, Temenos)
    NONE = "none"  # Not a tank


class SurvivalStrategy(str, Enum):
    """Team survival strategy for EX fights."""

    DODGE_TANK = "dodge_tank"  # Evade attacks (H'aanit EX, Canary)
    PROVOKE_TANK = "provoke_tank"  # Draw single-target attacks
    COVER_TANK = "cover_tank"  # Intercept with Fiore EX
    HP_BARRIER = "hp_barrier"  # HP shields (Sazantos)
    TURTLE = "turtle"  # Max DEF buffs + ATK debuffs
    SPEEDRUN = "speedrun"  # Kill before dangerous mechanics
    NONE = "none"  # No specific survival strategy


# =============================================================================
# CHARACTER MODELS
# =============================================================================


class Skill(BaseModel):
    """Character skill definition."""

    name: str | None = None  # Some skills are unnamed
    skill_category: SkillCategory  # active, tp, ex, or special
    sp_cost: int | None = None
    skill_type: SkillType
    damage_types: list[str] = Field(default_factory=list)  # Weapons/elements this skill can hit
    target: SkillTarget
    hit_count: str | None = None  # Can be range like "4-6x"
    power: str | None = None  # Power range like "170~350"
    effects: list[str] = Field(default_factory=list)  # Effect descriptions
    conditions: list[str] = Field(default_factory=list)  # Conditional modifiers
    priority: bool = False  # Has [Priority]?
    ex_trigger: str | None = None  # For EX skills
    limit_break_upgrade: str | None = None  # 6★ upgrade (shown as "6*" in spreadsheet)
    notes: str | None = None


class Passive(BaseModel):
    """Character passive ability."""

    passive_category: PassiveCategory  # innate, tp, or basic
    effect: str  # What the passive does
    trigger: str | None = None  # When it activates
    limit_break_upgrade: str | None = None  # 6★ upgrade (shown as "6*" in spreadsheet)


class A4Accessory(BaseModel):
    """A4 exclusive accessory."""

    name: str
    passive_effect: str


class UniqueMechanic(BaseModel):
    """Character-specific mechanic (stances, stacks, etc.)."""

    name: str
    description: str


class Synergy(BaseModel):
    """Synergy with another character."""

    character_id: str
    synergy_type: SynergyType
    description: str


class BuffCategoryEntry(BaseModel):
    """A single buff/debuff contribution to a stacking category."""

    type: str  # e.g., "phys_atk_up", "sword_damage_up"
    value: int  # Percentage value
    source_skill: str | None = None  # Which skill provides this


class BuffCategories(BaseModel):
    """Character's buff contributions organized by stacking category."""

    active: list[BuffCategoryEntry] = Field(default_factory=list)  # Active skill buffs
    passive: list[BuffCategoryEntry] = Field(default_factory=list)  # Passive buffs
    ultimate: list[BuffCategoryEntry] = Field(default_factory=list)  # Ultimate buffs


class DebuffCategories(BaseModel):
    """Character's debuff contributions organized by stacking category."""

    active: list[BuffCategoryEntry] = Field(default_factory=list)  # Active skill debuffs
    ultimate: list[BuffCategoryEntry] = Field(default_factory=list)  # Ultimate debuffs


class Character(BaseModel):
    """
    COTC Character definition.

    All data in this model is [HUMAN-REQUIRED].
    The LLM cannot generate or invent any of these values.
    """

    # Identity
    id: str
    display_name: str
    rarity: int = Field(ge=3, le=5)

    # Core attributes
    job: Job
    influence: Influence | None = None
    origin: str | None = None  # Continent/world (Orsterra, Solistia, crossovers)

    # Weakness coverage - what enemy weaknesses can this character hit?
    # Combines weapons and elements into a single list (matches CSV "Weakness to hit")
    weakness_coverage: list[str] = Field(default_factory=list)  # e.g. ["sword", "fire", "polearm"]

    # Roles
    roles: list[Role] = Field(default_factory=list)  # May be empty until manually assigned
    role_notes: str | None = None
    tank_type: TankType | None = None  # Tank archetype if this character tanks

    # Buff/Debuff categories for damage stacking
    buff_categories: BuffCategories | None = None
    debuff_categories: DebuffCategories | None = None

    # EX fight recommendations
    recommended_min_hp: int | None = None  # Minimum HP for EX fights

    # Skills
    skills: list[Skill] = Field(default_factory=list)

    # Passives
    passives: list[Passive] = Field(default_factory=list)

    # Unique mechanics (stances, stacks, etc.)
    unique_mechanics: list[UniqueMechanic] = Field(default_factory=list)

    # A4 Accessory
    a4_accessory: A4Accessory | None = None

    # Synergies
    synergies: list[Synergy] = Field(default_factory=list)

    # Speed
    base_speed: int | None = None
    speed_category: SpeedCategory | None = None
    speed_notes: str | None = None

    # Limitations & Use Cases
    weaknesses: list[str] = Field(default_factory=list)
    best_use_cases: list[str] = Field(default_factory=list)

    # Investment / Progression
    awakening_stage: int = Field(default=4, ge=0, le=4)  # Stages I-IV (0-4)
    has_limit_break: bool = False  # 6★ Limit Break (Lv120, skill upgrades)
    has_blessing_of_lantern: bool = False  # Blessing of the Lantern (TP passive/skill)

    # Base stats (at max level for base rarity)
    hp: int | None = None
    p_atk: int | None = None
    p_def: int | None = None
    e_atk: int | None = None
    e_def: int | None = None
    speed: int | None = None
    crit: int | None = None
    sp: int | None = None

    # Lv120 stats (after Limit Break)
    hp_120: int | None = None
    p_atk_120: int | None = None
    p_def_120: int | None = None
    e_atk_120: int | None = None
    e_def_120: int | None = None
    speed_120: int | None = None
    crit_120: int | None = None
    sp_120: int | None = None

    # Tier ratings from community
    gl_tier: str | None = None
    jp_tier: str | None = None

    # Metadata
    data_confidence: DataConfidence = DataConfidence.INCOMPLETE
    data_notes: str | None = None
    data_source: str | None = None
    last_updated: date | None = None

    @property
    def primary_weapon(self) -> Weapon:
        """Derive primary weapon from job."""
        job_to_weapon = {
            Job.WARRIOR: Weapon.SWORD,
            Job.MERCHANT: Weapon.POLEARM,
            Job.THIEF: Weapon.DAGGER,
            Job.APOTHECARY: Weapon.AXE,
            Job.HUNTER: Weapon.BOW,
            Job.CLERIC: Weapon.STAFF,
            Job.SCHOLAR: Weapon.TOME,
            Job.DANCER: Weapon.FAN,
        }
        return job_to_weapon.get(self.job, Weapon.SWORD)

    def get_embedding_text(self) -> str:
        """Generate text for vector embedding."""
        parts = [
            self.display_name,
            f"Job: {self.job.value}",
        ]

        if self.roles:
            parts.append(f"Roles: {', '.join(r.value for r in self.roles)}")

        if self.role_notes:
            parts.append(self.role_notes)

        if self.weakness_coverage:
            parts.append(f"Weakness coverage: {', '.join(self.weakness_coverage)}")

        if self.origin:
            parts.append(f"Origin: {self.origin}")

        if self.best_use_cases:
            parts.append(f"Best for: {'; '.join(self.best_use_cases)}")

        if self.weaknesses:
            parts.append(f"Limitations: {'; '.join(self.weaknesses)}")

        return " ".join(parts)

    def get_metadata(self) -> dict:
        """Generate metadata for vector store."""
        return {
            "id": self.id,
            "job": self.job.value,
            "weakness_coverage": self.weakness_coverage,
            "roles": [r.value for r in self.roles],
            "rarity": self.rarity,
            "origin": self.origin,
            "gl_tier": self.gl_tier,
            "jp_tier": self.jp_tier,
            "data_confidence": self.data_confidence.value,
        }


# =============================================================================
# BOSS MODELS
# =============================================================================


class Weaknesses(BaseModel):
    """Boss weakness definition."""

    elements: list[Element] = Field(default_factory=list)
    weapons: list[Weapon] = Field(default_factory=list)


class ShieldPhase(BaseModel):
    """Shield count per phase."""

    phase: int
    shield_count: int
    trigger: str


class Mechanic(BaseModel):
    """Boss mechanic/ability."""

    name: str
    mechanic_type: MechanicType
    trigger: str | None = None
    target: MechanicTarget
    damage_type: str | None = None  # physical, elemental, true, none
    element: Element | None = None
    effects: list[str] = Field(default_factory=list)
    threat_level: ThreatLevel
    counter_strategy: str


class BossAction(BaseModel):
    """A boss/enemy action/skill."""

    name: str
    name_jp: str | None = None
    effect: str
    trigger: str | None = None  # When this action is used
    threat_level: str | None = None  # low, medium, high, extreme


class Enemy(BaseModel):
    """
    Individual enemy in an encounter.
    Used for multi-enemy boss fights (up to 4 enemies).
    """

    name: str
    name_jp: str | None = None
    is_main_target: bool = False  # Is this the primary target?

    # Stats
    hp: int | None = None
    speed: int | None = None
    p_def: int | None = None
    e_def: int | None = None

    # Weaknesses & Shields
    shield_count: int | None = None
    weaknesses: Weaknesses | None = None

    # Actions
    actions: list[BossAction] = Field(default_factory=list)

    # Notes
    notes: str | None = None


class Phase(BaseModel):
    """Boss battle phase - flexible structure for various boss types."""

    # Core identification
    phase_number: int | None = None  # Phase number (1, 2, 3...)
    phase: int | None = None  # Alternative name for phase_number

    # Phase details
    description: str | None = None
    trigger: str | None = None  # What triggers this phase
    behavior_changes: str | None = None
    priority_actions: str | None = None
    notes: str | None = None

    # Phase-specific stats (for bosses that change mid-fight)
    shield_count: int | None = None
    speed: int | None = None

    # For multi-enemy phases
    enemies: list[dict] | None = None  # List of enemy data


class WeaknessChange(BaseModel):
    """Weakness changes during an aura."""

    locked: list[str] = Field(default_factory=list)  # Weaknesses that become locked
    unlocked: list[str] = Field(default_factory=list)  # Weaknesses that remain open


class Aura(BaseModel):
    """
    Aura/stance mechanic for EX fights.

    Auras are visible effects (flames/glows) indicating special boss states.
    Common in EX fights where they lock weaknesses and trigger counters.
    """

    name: str  # e.g., "Counter Stance", "Strong Guard EX"
    trigger: str  # When this aura activates (e.g., "Break recovery", "HP < 50%")
    active_indicator: str | None = None  # Visual indicator (e.g., "Purple flame")
    weakness_changes: WeaknessChange | None = None  # How weaknesses change
    counter_trigger: str | None = None  # What triggers counter attack
    counter_effect: str | None = None  # What happens when counter triggers
    removal_condition: str | None = None  # How to remove this aura


class HpThreshold(BaseModel):
    """
    HP-based phase trigger for EX fights.

    More structured than generic Phase for precise planning.
    """

    hp_percent: int  # HP percentage that triggers this (e.g., 75)
    event: str  # What happens at this threshold
    behavior_changes: str  # Detailed behavior changes
    actions_per_turn: int | None = None  # New actions per turn
    new_weaknesses: list[str] = Field(default_factory=list)  # Weaknesses that open
    locked_weaknesses: list[str] = Field(default_factory=list)  # Weaknesses that lock


class RoleRequirement(BaseModel):
    """Required role for a boss."""

    role: Role
    priority: RolePriority
    reason: str


class CriticalTurn(BaseModel):
    """Critical turn timing."""

    turn: int
    event: str
    required_action: str


class Boss(BaseModel):
    """
    COTC Boss definition.

    All data in this model is [HUMAN-REQUIRED].
    The LLM cannot generate or invent any of these values.
    """

    # Identity
    id: str
    display_name: str
    display_name_jp: str | None = None  # Japanese name
    content_type: ContentType
    difficulty: Difficulty
    location: str | None = None  # Where the boss is found
    level: int | None = None  # Boss level (100, 120, etc.)

    # EX Fight / Adversary Log fields
    base_boss_id: str | None = None  # For EX variants, references base boss
    ex_rank: ExRank | None = None  # EX difficulty rank
    actions_per_turn: int = 1  # How many actions boss takes per turn
    provoke_immunity: bool = False  # If true, boss cannot be provoked

    # Auras/Stances (common in EX fights)
    auras: list[Aura] = Field(default_factory=list)

    # HP Thresholds (structured phase triggers)
    hp_thresholds: list[HpThreshold] = Field(default_factory=list)

    # Stats (for NPCs with known values)
    hp: int | None = None
    speed: int | None = None
    p_def: int | None = None
    e_def: int | None = None

    # Weaknesses & Resistances (optional for multi-phase bosses)
    weaknesses: Weaknesses | None = None  # Optional for bosses with phase-based weaknesses
    resistances: Weaknesses | None = None
    immunities: Weaknesses | None = None
    status_immunity: str | None = None  # e.g., "20%", "100%", "none"

    # Shield (optional for multi-phase bosses)
    shield_count: int | None = None  # Optional for bosses with variable shields
    shield_phases: list[ShieldPhase] = Field(default_factory=list)
    shield_scaling: str | None = None  # e.g., "38 → 99"

    # Weakness cycling (for complex bosses)
    weakness_sets: list[dict] | None = None  # Multiple weakness sets
    weakness_change_trigger: str | None = None  # When weaknesses change

    # Multi-enemy encounters (up to 4 enemies in COTC)
    enemies: list[Enemy] = Field(default_factory=list)  # All enemies in the encounter

    # Actions (for single-enemy or simplified encounters)
    actions: list[BossAction] = Field(default_factory=list)

    # Mechanics
    mechanics: list[Mechanic] = Field(default_factory=list)
    special_mechanics: list[dict] | None = None  # Free-form mechanics

    # Phases
    phases: list[Phase] = Field(default_factory=list)

    # Team Requirements
    required_roles: list[RoleRequirement] = Field(default_factory=list)
    required_capabilities: list[str] = Field(default_factory=list)
    recommended_weakness_coverage: list[str] = Field(default_factory=list)

    # Timing
    turn_limit: int | None = None  # Soft turn limit
    enrage_turn: int | None = None  # Turn when boss enrages (instant death)
    enrage_description: str | None = None  # What happens on enrage
    critical_turns: list[CriticalTurn] = Field(default_factory=list)

    # Strategy
    general_strategy: str | None = None  # Made optional
    common_mistakes: list[str] = Field(default_factory=list)

    # Metadata
    data_confidence: DataConfidence = DataConfidence.INCOMPLETE
    data_source: str | None = None
    last_updated: date | None = None

    def get_embedding_text(self) -> str:
        """Generate text for vector embedding."""
        parts = [self.display_name]

        if self.general_strategy:
            parts.append(self.general_strategy)

        if self.location:
            parts.append(f"Location: {self.location}")

        # Add weakness info
        if self.weaknesses:
            if self.weaknesses.elements:
                parts.append(f"Weak to: {', '.join(e.value for e in self.weaknesses.elements)}")
            if self.weaknesses.weapons:
                parts.append(f"Weak to: {', '.join(w.value for w in self.weaknesses.weapons)}")

        # Add mechanic summaries
        for mech in self.mechanics:
            parts.append(f"{mech.name}: {mech.counter_strategy}")

        return " ".join(p for p in parts if p)

    def get_metadata(self) -> dict:
        """Generate metadata for vector store."""
        # Handle optional weaknesses
        elements = []
        weapons = []
        if self.weaknesses:
            elements = (
                [e.value for e in self.weaknesses.elements] if self.weaknesses.elements else []
            )
            weapons = [w.value for w in self.weaknesses.weapons] if self.weaknesses.weapons else []

        return {
            "id": self.id,
            "difficulty": self.difficulty.value,
            "content_type": self.content_type.value,
            "weaknesses_elements": elements,
            "weaknesses_weapons": weapons,
            "required_roles": [rr.role.value for rr in self.required_roles],
            "data_confidence": self.data_confidence.value,
        }


# =============================================================================
# TEAM MODELS
# =============================================================================


class TeamSlot(BaseModel):
    """Character slot in a team composition."""

    position: int = Field(ge=1, le=8)
    character_id: str
    role_in_team: TeamRole
    is_required: bool
    substitutes: list[str] = Field(default_factory=list)
    substitute_notes: str | None = None
    key_skills_used: list[str] = Field(default_factory=list)
    accessory_requirements: list[str] = Field(default_factory=list)
    awakening_required: int = Field(default=0, ge=0, le=4)


class TurnPlan(BaseModel):
    """Turn-by-turn action plan."""

    turn_range: str  # "1", "2-6", "7+"
    phase: BattlePhase | None = None
    actions: list[str]
    notes: str | None = None


class BuffPlan(BaseModel):
    """Buff stacking plan."""

    buff_type: str
    sources: list[str]  # character IDs
    target_cap: str | None = None
    timing: str


class BuffCategoryCoverage(BaseModel):
    """
    Which damage stacking categories a team covers.

    See damage_stacking.yaml for full explanation of the 5 categories.
    All values are percentages.
    """

    active_atk_up: int | None = None  # Cap 30%
    active_def_down: int | None = None  # Cap 30%
    passive_damage_up: int | None = None  # Cap 30%
    ultimate_potency: int | None = None  # Solon = 100%
    pet_damage_up: int | None = None  # Varies
    divine_beast: int | None = None  # Varies


class Team(BaseModel):
    """
    COTC Team composition.

    All data in this model is [HUMAN-REQUIRED].
    The LLM cannot generate or invent any of these values.
    """

    # Identity
    id: str
    name: str
    boss_id: str

    # Classification
    strategy_type: StrategyType
    investment_level: InvestmentLevel

    # EX Fight Classification
    target_ex_rank: ExRank | None = None  # What EX difficulty this team targets
    survival_strategy: SurvivalStrategy | None = None  # Primary survival approach
    minimum_hp_recommended: int | None = None  # Minimum HP per character

    # Buff/Debuff Category Coverage
    buff_category_coverage: BuffCategoryCoverage | None = None

    # Composition
    front_line: list[TeamSlot]
    back_line: list[TeamSlot] = Field(default_factory=list)

    # Speed
    speed_order: list[str] = Field(default_factory=list)  # character IDs
    speed_tuning_notes: str | None = None

    # Turn Plan
    turn_plan: list[TurnPlan] = Field(default_factory=list)

    # Buff Plan
    buff_stacking: list[BuffPlan] = Field(default_factory=list)

    # Explanation
    why_it_works: str
    key_synergies: list[str]
    risks_and_recovery: list[str] = Field(default_factory=list)

    # Verification
    verified: bool = False
    clear_time: str | None = None
    success_rate: str | None = None

    # Metadata
    author: str | None = None
    source_url: str | None = None
    data_confidence: DataConfidence = DataConfidence.INCOMPLETE
    last_verified: date | None = None
    last_updated: date | None = None

    def get_embedding_text(self) -> str:
        """Generate text for vector embedding."""
        parts = [
            self.name,
            f"Strategy: {self.strategy_type.value}",
            self.why_it_works,
        ]

        if self.key_synergies:
            parts.append(f"Synergies: {'; '.join(self.key_synergies)}")

        return " ".join(parts)

    def get_metadata(self) -> dict:
        """Generate metadata for vector store."""
        all_character_ids = [slot.character_id for slot in self.front_line]
        all_character_ids.extend(slot.character_id for slot in self.back_line)

        return {
            "id": self.id,
            "boss_id": self.boss_id,
            "character_ids": all_character_ids,
            "strategy_type": self.strategy_type.value,
            "investment_level": self.investment_level.value,
            "verified": self.verified,
            "data_confidence": self.data_confidence.value,
        }


# =============================================================================
# QUERY/OUTPUT MODELS
# =============================================================================


class BossQuery(BaseModel):
    """User query for team composition."""

    boss_id: str | None = None  # Known boss
    description: str | None = None  # Free-text for unknown boss
    available_characters: list[str] = Field(default_factory=list)  # Character IDs user has
    constraints: str | None = None  # Any specific constraints


class MechanicAnalysis(BaseModel):
    """Analysis of a single mechanic."""

    mechanic_name: str
    threat_level: ThreatLevel
    counter_needed: str
    source: str  # Where this info came from


class TeamProposal(BaseModel):
    """A proposed team composition."""

    name: str
    confidence: DataConfidence
    confidence_reason: str
    strategy_type: StrategyType
    composition: list[dict]  # Simplified for output
    key_synergies: list[str]
    risks: list[str]
    source: str  # "proven_team: {id}" or "inferred"


class CompositionOutput(BaseModel):
    """Output from the reasoning pipeline."""

    data_completeness: dict
    boss_analysis: dict
    proposed_teams: list[TeamProposal]
    characters_not_recommended: list[dict]
    additional_notes: list[str]
    data_gaps: list[str]
