# Registro de implementación — candado de supervivencia (2026-10-13)

Ledger de la ejecución por subagentes: decisiones tomadas (Ruling R1–R16), menores diferidos por tarea y residuos de la revisión final. Fuente de verdad para revisar lo que quedó pendiente.

# SDD ledger — plan: docs/superpowers/plans/2026-10-13-candado-supervivencia.md
Spec: docs/superpowers/specs/2026-10-13-candado-supervivencia-design.md
Branch: experimento-2-rediseno (same folder by user decision; no worktree). Start HEAD a83a953.

## Preflight scan
| Rows | Produces -> Consumes | Finding |
|---|---|---|
| T1->T3,T5,T7,T8 | SurvivalGuard.fit/s_now/n_max/s_with_delta/s_after_close | consistent |
| T1 vs existing tests | SurvivalGuard needs Broker.account_margin/contract_size; FakeBroker in tests/test_m5_and_budget.py lacks them | CONFLICT -> Ruling R1 |
| T2->T3,T4,T5,T7,T8,T9 | ROLE_LOCK, lock_legs, meta keys | consistent |
| T3->T4 | meta ref_lot | consistent |
| T3->T5 | meta rescue_opened | consistent |
| T3->T6 | dead gate inside _open_additive | consistent |
| T3/T7/T8 tests | engine cfg_provider merges strategy DEFAULTS (equity_weight 0.8); T8 expects 0.14 which needs weight 1.0 | CONFLICT -> Ruling R2 |
| T4 vs existing M15 tests | _move_money calls broker.contract_size() in on_tick | covered by R1 |
| T6 vs FakeBroker | account_dead calls trade_allowed(); base FakeBroker lacks it | CONFLICT -> Ruling R3 |
| T7 vs FakeBroker | order_check missing in FakeBroker | CONFLICT -> Ruling R4 |
| T8->T9 | T8 resets lock_since to None when all LOCK closed; T9 "both sides" case measures 24h from last lock | CONFLICT -> Ruling R5 |
| T5 vs test_m5_and_budget [16] | L3 news exception test must flip | plan says so; consistent |
| T10 | migration/schema only | consistent |
| Each task self-consistency | tests vs code checked: T1 numbers (n_max 0.20, 0.15/0.19/0.20/0, share 0.16/0.04, s_after_close 500, UTC 13/13/1), T3 0.15, T4 levels 1/2/3 & 29.97, T5 S=166, T7 S=147/166, T8 0.14 (with R2), T9 0.10 | consistent |

Ruling R1: Task 1 also adds account_margin() (returns self._margin, default 0.0) and contract_size() (100.0) to FakeBroker in tests/test_m5_and_budget.py so existing M15 tests keep running — why: SurvivalGuard/_move_money call them — cost if wrong: none, test-only.
Ruling R2: all engine-level tests in tests/test_supervivencia.py set cfg {"equity_weight": 1.0} unless the test is about the bot share — why: plan numbers (0.15, 0.14) assume weight 1.0 — cost if wrong: test-only.
Ruling R3: Task 6 adds trade_allowed() -> (True, "") to FakeBroker (test_m5_and_budget) and SurvBroker — cost: none.
Ruling R4: Task 7 adds order_check() -> (True, 0) to FakeBroker/SurvBroker — cost: none.
Ruling R5: Task 9 measures the 24h from max(lock_since or 0, last_unlock_ts or 0); if both absent the "both sides" case does not run — why: lock_since is cleared on full unlock but last_unlock_ts persists until meta reset at core_count==0 — cost if wrong: both-sides dissolution never runs after a lock that was never unlocked but fully dissolved (rare; basket then ends via normal trail).
Task 1: ⚠️ Logger.write balance kwarg — verified: real signature write(log_type, message, price, lots, balance, ticket=0) (logging-taxonomy memory) — OK.
Task 1: minor (deferred): S=inf logged as "S=0 $" in fit block message (survival.py:202).
Task 1: minor (deferred): fit linear scan does MT5 reads per step (~500 iters for 5 lots); hoist reads / bisect.
Task 1: minor (deferred): parse_hours isdigit()/int edge; survival_move_usd=0 ZeroDivision; None cfg -> float() raises.
Task 1: minor (deferred): SurvBroker redundant overrides; test gaps (_mpl margin path, other-bot S branch, dedupe relog, < volume_min); sign logic duplicated net_lots vs s_after_close.
Task 1: minor (deferred): survival.DEFAULTS includes §5.9 move keys early (unused).
Task 1: complete (commits a83a953..2030530, review clean)
Ruling R6: a LOCK leg alive with no ENTRY/RECOVERY/RESCUE alive degrades to ORPHAN in ledger.sync (then existing pairing/watchdog/promotion rules apply) — why: a lone lock is naked directional exposure; spec silent; consistent with "huérfano descubierto -> ENTRY" + OP2 freezes — cost if wrong: a leftover lock leg becomes an OP1 that the hedge monitor may cover at hedge_dist.
Task 2: minor (deferred): set_meta writes file on every call; meta dict reference goes stale after reset_meta.
Task 2: fix round 1/5 (2 addressed, 0 open — lg3 role pin; R6 lone LOCK degrade; commits 69db536..cc9576c)
Task 2: minor (deferred): LOCK->ORPHAN degrade is one-way; degrade log not asserted in test.
Task 2: complete (commits 2030530..cc9576c, review clean)
Ruling R7: rescue cooldown (last_rescue_time) starts only when an order was actually sent to the broker (confirmed or rejected), not when blocked by survival/gov — why: preserves pre-change anti-spam on broker rejections while not delaying L3 retries blocked by transient survival — cost if wrong: a survival-blocked rescue re-evaluates every tick (cheap, BUDGET log deduped).
Task 3: minor (deferred): no test of M5 surv.fit call site, reset_meta on core_count==0, on_tick integration; add positive "rescue blocked by survival" case for fixture [16]; loose >1.0 asserts in test_no_fixed_lot_caps.
Task 3: fix round 1/5 (2 addressed, 0 open — rescue cooldown only when sent; stale comment; commits 10c5512..985a07c)
Task 3: minor (deferred): blocked-by-survival branch of test_rescue_cooldown_only_when_sent could pass vacuously (assert BUDGET event); fixture [16] survival_move_usd=1.0 for final review glance.
Task 3: complete (commits cc9576c..985a07c, review clean)
Task 4: ⚠️ default values — controller verified in bot/survival.py DEFAULTS.
Task 4: minor (deferred): _move_money recomputes ref_lot/contract_size 3x per tick in trail; no test that trail arm/retrace clamp/min_green use new thresholds; long lines 1090-1091; _ref_lot fallback untested.
Task 4: complete (commits 985a07c..e0383db, review clean)
Ruling R8: plan's Unwind variant (BUY 0.30 green/SELL 0.20 red) actually increases |net| (0.10->0.20); implementer's BUY 0.30/SELL 0.10 variant accepted — why: plan arithmetic error, intent is 'reducing close is banked' — cost: none.
Task 5: minor (deferred): recovery-branch risk-hour gate (strategy.py:1199) untested; garbled _news_note docstring ("solo no deberia"); stale comment strategy.py:1005 "news_enforce=False (default)" (+ maybe :496); churn test relies on FakePos identity.
Task 5: complete (commits e0383db..1c60c3e, review clean)
Task 6: minor (deferred): failed send consumes cooldown (undocumented); datetime.now wall clock for history window; no M5 dead-gate test; transient equity 0 may send one spurious CRITICA.
Task 6: fix round 1/5 (2 addressed, 2 open — stop-out window in future (new Critical), idle window 24h not 72h; commits dcd9945..a708873)
Ruling R9: history windows for stop-out/idle use server-time base like _check_healing: to=utcfromtimestamp(now)+5min; from=to-1d (stop-out) / to-72h (idle) — why: deal times are server time; consistent with existing code — cost if wrong: alert timing off by tz offset hours.
Task 6: fix round 2/5 (2 addressed, 0 open — server-time windows; commits a708873..1c33d24)
Task 6: minor (deferred, pre-existing): strategy.py:160 wall-clock 7-day window; strategy_m5.py:255 utcnow() vs self.now.
Task 6: complete (commits 1c60c3e..1c33d24, review clean)
Task 7: ⚠️ margin_hedged startup log — controller verified implemented in bot/main.py by Task 6.
Ruling R10: while any LOCK leg is alive (CONGELADO or AFLOJADO), the ENTRY hedge monitor and the orphan watchdog do NOT open hedges; protection in AFLOJADO is the re-lock at S<150 — why: a full-volume Hedge Lock stacked on residual LOCK flips the net (anti-objective) — cost if wrong: in AFLOJADO an ENTRY is not OP2-frozen at hedge_dist; covered by survival cap + re-lock.
Ruling R11: Healer depth gate (healer_min_core) counts own positions excluding LOCK legs — why: constraint "Healer solo con core>=3" refers to cycle depth — cost: none.
Ruling R12: throttle pre-existing "Hedge Lock FALLIDO" ERROR to once per 600 s per ticket (self.now) — why: spec anti-objective (12,970 10019 errors) and reviewer showed the flood path remains when lock fails on margin — cost: fewer error lines.
Task 7: minor (deferred): failure throttle time-only (different retcode within 600s not logged); partial IOC fill overstates lock_initial_volume; lock_state cached per tick (doc); no test for order_check-ok-but-send-rejected or volume_max split; vmax<=0 guard.
Task 7: fix round 1/5 (5 addressed, 0 open — per-tick SL clear; R10 no hedges with LOCK alive; R11 healer gate; R12 hedge-fail throttle; vmax<=0; commits a209e11..b52db8e)
Task 7: minor (deferred): SL-clear error throttle global not per ticket; modify_sl None treated as success; SL clear placement vs early returns not checked; _hedge_fail_next never pruned.
Task 7: complete (commits 1c33d24..b52db8e, review clean)
Ruling R13: on every confirmed lock leg, meta unlock_ref_price = that leg's price, so after a re-lock the rebound is measured from the new lock price — why: spec §5.4 "medido desde el precio medio de apertura de las patas LOCK"; the previous unlock price would demand an outsized rebound — cost if wrong: unlocks sooner after a re-lock (still bounded by S>=350).
Task 8: minor (deferred): mixed close result moves ref and defers shortfall to a new rebound; DONE_PARTIAL realized P&L not added to cycle_realized; ERROR and SHADOW share _unlock_err_next throttle.
Task 8: fix round 1/5 (3 addressed, 0 open — BUY mirror test; R13 ref on relock; bisect; commits 3ed2889..524c34b)
Task 8: minor (deferred): binary search assumes non-lock net not opposing dir_orig (lock over-hedge) — add comment.
Task 8: complete (commits b52db8e..524c34b, review clean)
Ruling R14: dissolution persists a pending debt (meta dissolve_pending) when the second close of a pair fails; until repaid only that member is retried (60 s backoff, gates except VCB ignored), no new pairs; CRITICA alert — why: reviewer reproduced net 0 -> -0.30 compounding naked exposure — cost if wrong: a stuck pending debt blocks further dissolution until its tickets close.
Task 9: ⚠️ both-sides dissolution can also pair Op3/Op4 opened after the lock ended in the same cycle (last_unlock_ts persists) — accepted as spec intent ("si quedan Op3/Op4 de ambos lados"); flag to user.
Task 9: minor (deferred): lock_initial_volume fallback untested; _utc_day relies on positive offset (helper survival.utc_ts_from_server would be clearer).
Ruling R15: accept implementer's extra guard — a pending-debt retry never pushes the net past its pre-pair value; if net already back there (e.g. re-lock covered it) the debt is dropped — why: prevents overshoot after a new lock — cost if wrong: a debt may be dropped while the lock covers the gap (net-correct either way).
Task 9: fix round 1/5 (4 addressed, 0 open — persistent dissolve debt, backoff, texts, minors; commits a02f962..79ccfb4)
Task 9: minor (deferred): R15 capped-retry path logs wrong reason and skips _dissolve_done (no last_dissolve_day, no lock-meta cleanup) — net correct; debt-drop/PARCIAL leave last_dissolve_day unset (extra same-day pair possible); first-close backoff not persisted.
Task 9: complete (commits 524c34b..79ccfb4, review clean)
Ruling R16: migration grep count 20 (not plan's 17) accepted — 3 extra ADD COLUMN IF NOT EXISTS for drift columns already created by 002 (no-op) — cost: none.
Task 10: fix round 1/5 (3 addressed, 0 open — rollback per-row filters, comment, note; commits 810a9a3..d30847f)
Task 10: minor (deferred): commented rollback block mixes prose lines that would be syntax errors if uncommented verbatim.
Task 10: complete (commits 79ccfb4..d30847f, review clean)
Final review: 1 Critical, 2 Important, 7 minors selected for the single fix wave (see final-findings.md). Deferred-only (can wait): unlock delta_margin 0; R6 orphan-promotion edge; [so magic filter to verify on demo; healer budget counting dissolved lock profits (conscious: de-risks); rollback prose.
Final fix wave: complete (commits d30847f..35cbd39, re-review: all 10 addressed, no new Critical/Important)
Residual (surface to user): M5 margin_level()=0.0 on failed account_info + code default ml_flatten 250 -> one bad read could flatten M5 scalps; migration 010 sets m5 ml_flatten=0 in DB, so neutralized once migration is applied. sim_broker.py (backtest harness) lacks new broker methods (pre-existing).
