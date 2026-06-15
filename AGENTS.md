# AGENTS.md — Unified Jarvis

Project root: `/root/jarvis-unified`. Address the user as Sir.

## Status

- Matrix Account / Unified Jarvis v1.1.1 is the current live system on the dedicated OKX subaccount, now funded with about 220U after Mi and v4 balances were transferred in. Release notes: `docs/V1_0_0_MATRIX_RELEASE.md`, `docs/V1_1_0_MATRIX_HYGIENE_RELEASE.md`, `docs/V1_1_1_TICK_SAFE_STOPS_RELEASE.md`.
- The system is no longer framed as 100U survival-only. Its purpose is to validate the 2×2 full-market matrix: `maincoin_long`, `maincoin_short`, `alt_long`, `alt_short`.
- v1.1.1 keeps v1.1.0 sampling parameters/hygiene and adds tick-safe stop quantization for entry attached SL and guardian stop moves.
- GitHub private archive: `git@github.com-jarvis:Immutable1407/Jarvis-unified-private.git`.
- Primary skill: `jarvis-matrix-trading`. Historical Mi/v4 skills are archive-only unless Sir requests rollback.
- Sanitized export repo: `/root/jarvis-unified-github-export`.
- Remote verification clone: `/root/jarvis-unified-github-verify-clone`.

## Hard rules

- Do not commit or push runtime state: `data/`, `reports/`, fills, ledgers, snapshots, account JSON, or `.jsonl` files.
- Do not commit OKX secrets, Hermes `.env`, Feishu webhook URLs, model keys, SSH keys, or config files.
- All OKX access must use profile isolation; production CLI profile is `jarvis-unified-100u`.
- Live write paths require UID/mainUid guard and `JARVIS_UNIFIED_LIVE_TRADING=true`.
- No LLM in hot order path. Cold context can adjust score/risk/permission only; it cannot directly trigger orders.
- Alt seed candidates are preliminary until candle-rescore confirms them.

## Verification commands

```bash
cd /root/jarvis-unified
export PYTHONPATH=/root/jarvis-unified
python3 -m compileall -q jarvis_unified scripts/unified tests
python3 -m unittest discover -s tests -v
python3 scripts/unified/unified_account_check.py
python3 scripts/unified/unified_collect_context.py
JARVIS_UNIFIED_DRY_RUN=1 python3 scripts/unified/unified_live_cycle.py
python3 scripts/unified/unified_guardian.py
python3 scripts/unified/unified_healthcheck.py
```

Only run live cycle with `JARVIS_UNIFIED_LIVE_TRADING=true` deliberately; it can place real OKX orders.

## GitHub sync workflow

1. Export safe source/docs/tests to `/root/jarvis-unified-github-export`.
2. Run compile/tests on export.
3. Run `python3 scripts/secret_scan.py .` and require `path_findings=0`, `content_findings=0`.
4. Commit and push to `git@github.com-jarvis:Immutable1407/Jarvis-unified-private.git`.
5. Fresh clone to `/root/jarvis-unified-github-verify-clone` and run the same scan.
