# Data curation guide

What is still missing, what to fill first, and how to fill it without breaking source rules.
Every game fact lives in `data/`; the MCP only reasons over what is written there.

Live numbers: `uv run python scripts/audit_data.py --list` (also ranks your own roster).

## Snapshot (2026-10-31)

| Area | Gap | Count | Fillable from |
|---|---|---|---|
| Characters | `roles` empty | 187 / 277 | Kit text (`get_character`, `search_skill_effects`), NiaDB page |
| Characters | Your **invested** units without roles | 67 | same; do these first |
| Characters | No `buff_categories` / `debuff_categories` | 260 | Kit text |
| Characters | No `tank_type` | 250 | Kit text (taunt, Sidestep, cover, HP barrier) |
| Characters | No `gl_tier` | 109 | Community spreadsheet CSV re-export |
| Characters | Not in repo at all | FFX collab (Rikku, Auron, Yuna, Tidus, Jecht), Delitia, Bargello EX2, Sonia EX | New Notion/CSV export after GL release |
| Bosses | No weaknesses | 23 | In-game, NiaDB boss page (no CSV has them) |
| Bosses | `general_strategy` is TODO | 39 | Fight Notes CSV (only 11 fights covered), community guides |
| Bosses | EX3 whose base fight file is missing | 14 | Sheet only has EX3 rows for these |
| Bosses | 120 NPC EX3 files with no base | 5 | 120 NPC sheet has no ranks |
| Bosses | EX/arena without HP | 6 | Not in sources at that rank |
| Bosses | **EX4 ranks** (live in GL) | 0 files | New Adversary Log export; `ex_rank: ex4` is supported |
| Bosses | No file at all | Al the Servant, Dreadwrought Endbringer, Bestower of All, Cascade Log, Garrison, job towers | New exports |
| Teams | Names that match no character | 4 teams | Rewatch the source video, then fix `unresolved_character_ids` |
| Teams | EX3 fights without a boss-specific team | 79 | Reddit/YouTube clears with full 8-unit rosters |

Known source conflicts, deliberately left unchanged (verify in game before editing):
`adversary-sazantos*` (matches the Lv. 50 Sazantos rows, not a different Lv. 75 "Sazantos"),
King Pardis III EX3 shields 31 vs sheet 28, Cursed Princess Elrica EX3 shields 40 vs 52,
Adventurer & Fox EX level 100 vs 120, Kagemune EX3 speed/P.Def. Kainé's weaknesses are unverified.

## Priority order

1. **Your invested units without roles.** These unblock `list_by_role` / `find_tanks_by_type`
   for your real roster. `search_skill_effects` already works without them.
2. **New GL releases** (kit + roles + buff/debuff categories) as they land.
3. **EX4 boss files** for fights you are attempting.
4. **Boss weaknesses** for anything you plan against.
5. Team promotions from community clears.

## How to curate

### Character roles, tank type, stacking categories

1. Read the kit: `get_character <id>` (or the YAML). For effect lookups across the roster use
   `search_skill_effects`, e.g. `lower.*Elem\. Def`, `Damage Limit`, `taunt|provoke`.
2. Edit **above** the `# Skills - parsed from markdown` marker only: `roles`, `role_notes`,
   `tank_type`, `buff_categories`, `debuff_categories`. Values must be quoted from kit text
   (percentages and conditions exactly as written).
3. Set `data_source` (add the NiaDB page URL if you used it), `data_confidence: complete`,
   and `last_updated`.
4. If you hand-edit skills/passives, delete the marker line so the importer skips the file.

Worked examples: `rocbouquet.yaml`, `noel.yaml`, `final-emperor.yaml`, `final-empress.yaml`.

### Kits from a new Notion export

```bash
uv run python scripts/import_characters_from_csv.py            # stubs for new units
uv run python scripts/merge_character_stats_from_csv.py        # stats/tiers, keeps curation
uv run python scripts/import_skills_from_markdown.py --dry-run
uv run python scripts/import_skills_from_markdown.py
uv run python scripts/audit_data.py
```

### Bosses from Adversary Log CSVs

```bash
uv run python scripts/import_adversary_log_from_csv.py --fill-missing --dry-run
uv run python scripts/import_adversary_log_from_csv.py --fill-missing
```

`--fill-missing` only fills empty fields, never overwrites curated values, skips files whose HP
or shields disagree with the sheet, and reports values that sit in the wrong column of their
own row ("Column shift (not changed)"). Fix flagged conflicts by hand and write why in `data_notes`.
Each EX rank is its own file (`base_boss_id`, `ex_rank`, real `hp`/`shield_count`/`speed`).

### Teams

- **Boss-specific team:** `boss_id` must exist in `data/bosses/`.
- **Universal team** (works across content): `boss_id: null` + `applies_to: [adversary_log]`.
  These appear in `plan_team_for_boss` / `get_proven_teams` with `scope: universal`.
- All 8 slots need real character IDs. Names you cannot match go in
  `unresolved_character_ids` (the integrity test enforces this).
- Mark sourcing honestly: `verified: false` + `data_confidence: theoretical` for templates,
  `community_unverified` for reported clears, `verified` only for clears you reproduced.
- Empty skeletons belong in `_draft-*.yaml` (the loader skips `_` files).

### Community notes

Raw Reddit intake goes to `resources/reddit-intake/YYYY-MM-DD-*.md` (gitignored). Promote
condensed, attributed findings to `data/reference/community/*.yaml`; agents read them through
`search_community_notes`. Never copy community claims into character kit fields.

## Sources and their limits

| Source | Use for | Limits |
|---|---|---|
| Notion Character Index export (`resources/Character List/`) | Kits (skills, passives, EX, ultimate, A4) | Newest exports lack skill names; parser keeps `unlock_tier` instead |
| Community spreadsheet CSV | Stats, tiers, progression flags | Tiers are opinions; GL tier lags new units |
| Adversary Log CSVs (`resources/Adversary Log*/`) | Boss HP, shields, speed, defenses | New export dropped weakness icons; no 120 NPC ranks; EX4 absent |
| [NiaDB](https://meowdb.com/db/octopath-traveler-cotc) | Single-unit facts and role curation | Excerpts/facts only, with the exact page URL in `data_source`. **No crawling or bulk import** without emailing contact@meowdb.com (then max 1 request / 10 s). Its Community Teams page is sourced from this repo, so it is not an independent team source |
| Reddit (`reddit-rss` MCP) | Meta, clears, mechanics discussion | Curation only, attribute URLs, no redistribution or model training (Reddit Responsible Builder Policy). RSS truncates bodies/comments and rate-limits (~1 call/min) |
| YouTube transcripts (`MCP_DOCKER`) | Creator guides | Auto-captions garble names; verify every ID |
| In-game | Final authority | Manual |

## Checks before committing

```bash
uv run pytest                 # incl. data integrity + MCP scenarios over stdio
uv run ruff check . && uv run ruff format --check .
uv run python scripts/audit_data.py
```
