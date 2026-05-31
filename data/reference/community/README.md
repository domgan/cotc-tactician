# Reddit community data intake

When Reddit MCP is configured, community threads are collected into `resources/reddit-intake/` (gitignored alongside `resources/`).

## MCP options

| Server | Auth | Best for |
|--------|------|----------|
| `reddit-rss` | None (RSS) | Search, browse, flat comments (~25/post) |
| `reddit` (OAuth) | Client ID + secret | Scores, nested comment trees, write actions |

Prefer **`reddit-rss`** for intake when OAuth credentials are unavailable.

## OAuth environment variables

Configure the `user-reddit` MCP server in `~/.cursor/mcp.json`:

| Variable | Purpose |
|----------|---------|
| `REDDIT_USER_AGENT` | Required format: `platform:app-id:version (by u/username)` |
| `REDDIT_CLIENT_ID` | Reddit app client ID |
| `REDDIT_CLIENT_SECRET` | Reddit app secret |

If searches return HTTP 403, fix `REDDIT_USER_AGENT` first, then verify credentials via the MCP `test_reddit_mcp_server` tool.

## Freshness rule

Prefer newer posts when a topic has multiple threads. Mark older guides as `superseded_by` when a newer thread covers the same character/boss.

## Promotion policy

- **Teams** → `data/teams/` only when a full 8-character comp is documented with source URL
- **Boss tips** → boss `general_strategy` append with attribution
- **Meta claims** → `data/reference/community/` only if corroborated

All Reddit-sourced entries use `data_confidence: community_unverified`.

## Promoted files (2026-05-31)

### Teams
- `data/teams/adversary-universal-ex3-turtle.yaml`
- `data/teams/adversary-ex3-crickari-f2p.yaml`
- `data/teams/adversary-divine-beast-lutiya-kaine-clear.yaml`
- `data/teams/adversary-dk-universal-vivi.yaml`
- `data/teams/adversary-ex3-hybrid-rainbow-3t.yaml`
- `data/teams/adversary-sazantos-ex3-rainbow-dolphin.yaml`
- `data/teams/general-premium-rainbow-roster.yaml`

### Community reference
- `data/reference/community/reddit_rainbow_and_ice_meta.yaml`
- `data/reference/community/reddit_endgame_mechanics.yaml`
- `data/reference/community/reddit_gacha_planning.yaml`
- `data/reference/community/reddit_side_solistia_final_boss.yaml`

### Boss updates
- `data/bosses/adversary-sazantos-ex3.yaml`
- `data/bosses/adversary-lucian-the-glorious-ex3.yaml`
- `data/bosses/arena-kagemune-ex3.yaml`
- `data/bosses/arena-gertrude-ex3.yaml`
- `data/bosses/arena-mirgardi-ex3.yaml`
- `data/bosses/adversary-hammy-bladesman-petra-whirlwind-miluca-ex3.yaml`
- `data/bosses/arena-tikilen-ex3.yaml`

### Reference updates
- `data/reference/meta_strategies.yaml`
- `data/reference/llm_guidelines.yaml`
- `data/reference/damage_mechanics.yaml`
- `data/reference/damage_stacking.yaml`

See `resources/reddit-intake/2026-05-31-STATUS.md` for items not promoted (partial rosters, missing boss YAML).
