import unittest
from jarvis_unified.router import decide
from jarvis_unified.risk_execution import build_plan
from jarvis_unified.candidates import Candidate


def market(btc_ch4=0.02, btc_ch24=0.03, up=0.6, down=0.2):
    main={i:{"last":100.0,"change_4h":0.01,"change_24h":0.02,"ma20_1h":99,"ma99_1h":95,"atr_pct_15m":0.01,"funding":0} for i in ["BTC-USDT-SWAP","ETH-USDT-SWAP","SOL-USDT-SWAP","BNB-USDT-SWAP"]}
    main["BTC-USDT-SWAP"].update({"change_4h":btc_ch4,"change_24h":btc_ch24})
    return {"maincoin": main, "alt_universe": [], "breadth": {"count":80,"up_ratio":up,"down_ratio":down}}

class UnifiedCoreTests(unittest.TestCase):
    def test_router_impulse(self):
        d=decide(market(), {"freshness":"fresh","modifiers":{"total_risk_multiplier":1.0,"event_veto":False}})
        self.assertEqual(d.market_phase, "btc_impulse")
        self.assertEqual(d.maincoin_long_permission, "active")
        self.assertEqual(d.maincoin_permission, "active")

    def test_router_risk_off(self):
        d=decide(market(btc_ch4=-0.02, btc_ch24=-0.03, up=0.1, down=0.7), {"freshness":"fresh","modifiers":{"total_risk_multiplier":1.0,"event_veto":False}})
        self.assertEqual(d.market_phase, "risk_off_alt_decay")
        self.assertEqual(d.alt_short_permission, "active")

    def test_preliminary_candidate_blocked(self):
        class DummyClient: pass
        cand=Candidate("alt_short","ABC-USDT-SWAP","short",70,["seed"],1.0,0.018,preliminary=True)
        decision=type("D",(),{"max_positions":1,"total_risk_ceiling":0.30,"context_modifiers":{"total_risk_multiplier":1.0}})()
        plan=build_plan(DummyClient(), cand, {"code":"0","data":[{"totalEq":"100","details":[{"ccy":"USDT","eq":"100"}]}]}, {"code":"0","data":[]}, decision)
        self.assertFalse(plan.ok)
        self.assertIn("preliminary", plan.reason)

    def test_router_risk_ceiling_caps_margin(self):
        import jarvis_unified.risk_execution as r
        class DummyCache:
            def get(self, inst_id, client=None):
                return {"ctVal":"1", "lotSz":"0.01", "minSz":"0.01"}
        old_cache = r.InstrumentCache
        r.InstrumentCache = lambda: DummyCache()
        try:
            cand=Candidate("maincoin_long","BTC-USDT-SWAP","long",99,[],100,0.01)
            decision=type("D",(),{"max_positions":1,"total_risk_ceiling":0.01,"context_modifiers":{"total_risk_multiplier":1.0}})()
            plan=build_plan(object(), cand, {"code":"0","data":[{"totalEq":"100","details":[{"ccy":"USDT","eq":"100"}]}]}, {"code":"0","data":[]}, decision)
            self.assertTrue(plan.ok)
            self.assertLessEqual(plan.margin_usdt, 1.000001)
        finally:
            r.InstrumentCache = old_cache

    def test_daily_pnl_ignores_other_uid(self):
        import datetime as dt, json, tempfile
        from pathlib import Path
        import jarvis_unified.risk_execution as r
        tmp=Path(tempfile.mkdtemp())
        (tmp/"ledgers").mkdir()
        today=dt.datetime.now(dt.UTC).strftime("%Y-%m-%d")
        (tmp/"ledgers"/"fills.jsonl").write_text(json.dumps({"date":today,"uid":"OTHER","net_pnl":-99})+"\n"+json.dumps({"date":today,"uid":r.CFG.expected_uid,"net_pnl":-1.5})+"\n")
        old_cfg=r.CFG
        r.CFG=type("C",(),{"data_dir":tmp,"expected_uid":old_cfg.expected_uid})()
        try:
            self.assertEqual(r.daily_realized_pnl(), -1.5)
        finally:
            r.CFG=old_cfg

    def test_guardian_flags_unprotected_position(self):
        import tempfile
        from pathlib import Path
        import jarvis_unified.ledger_guardian as g
        tmp=Path(tempfile.mkdtemp())
        (tmp/"state").mkdir(parents=True)
        old_cfg=g.CFG
        g.CFG=type("C",(),{"data_dir":tmp})()
        class DummyClient:
            def assert_account(self):
                return {"uid":"851731612504386465","mainUid":"621655308511150593"}
            def positions(self):
                return {"code":"0","data":[{"instId":"BTC-USDT-SWAP","posSide":"long","pos":"1"}]}
            def algo_orders(self):
                return {"code":"0","data":[]}
        try:
            out=g.guardian_check(DummyClient())
            self.assertFalse(out["ok"])
            self.assertEqual(out["issues"][0]["type"], "unprotected_position")
        finally:
            g.CFG=old_cfg

    def test_guardian_evaluates_be_tp1_lock_and_full_close(self):
        import jarvis_unified.ledger_guardian as g
        p={"instId":"BTC-USDT-SWAP","posSide":"long","pos":"1.0","avgPx":"100","markPx":"121"}
        algos=[{"instId":"BTC-USDT-SWAP","posSide":"long","algoId":"sl1","slTriggerPx":"90"}]
        inst={"lotSz":"0.1","minSz":"0.1"}
        rec, ev = g.evaluate_guardian_actions(p, algos, {}, inst)
        self.assertAlmostEqual(ev["r_multiple"], 2.1)
        self.assertEqual([a["label"] for a in ev["actions"]], ["lock_0_5r", "tp1_50pct"])
        self.assertEqual(ev["actions"][0]["stop_px"], "105")
        self.assertEqual(ev["actions"][1]["sz"], "0.5")
        self.assertTrue(all(a.get("reduce_only", True) for a in ev["actions"] if a["type"] in {"partial_close", "full_close"}))
        p["markPx"]="131"
        rec, ev = g.evaluate_guardian_actions(p, algos, {}, inst)
        self.assertEqual([a["label"] for a in ev["actions"]], ["full_close_3r"])
        self.assertEqual(ev["actions"][0]["sz"], "1")

    def test_guardian_persists_tp1_once_after_live_success(self):
        import tempfile
        from pathlib import Path
        import jarvis_unified.ledger_guardian as g
        tmp=Path(tempfile.mkdtemp()); (tmp/"state").mkdir(parents=True)
        old_cfg=g.CFG
        g.CFG=type("C",(),{**old_cfg.__dict__,"data_dir":tmp,"guardian_tp_state_file":"guardian_tp_state.json"})()
        class DummyCache:
            def get(self, inst_id, client=None): return {"lotSz":"0.1", "minSz":"0.1"}
        old_cache=g.InstrumentCache; g.InstrumentCache=lambda: DummyCache()
        class DummyClient:
            def __init__(self): self.market_orders=[]; self.stops=[]; self.cancels=[]
            def assert_account(self): return {"uid":"851731612504386465","mainUid":"621655308511150593"}
            def positions(self): return {"code":"0","data":[{"instId":"BTC-USDT-SWAP","posSide":"long","pos":"1.0","avgPx":"100","markPx":"116"}]}
            def algo_orders(self): return {"code":"0","data":[{"instId":"BTC-USDT-SWAP","posSide":"long","algoId":"sl1","slTriggerPx":"90"}]}
            def cancel_algo_order(self, inst_id, algo_id): self.cancels.append((inst_id, algo_id)); return {"code":"0"}
            def place_stop_algo(self, inst_id, side, pos_side, sz, trigger_px): self.stops.append((inst_id, side, pos_side, sz, trigger_px)); return {"code":"0"}
            def place_reduce_only_market(self, inst_id, side, pos_side, sz): self.market_orders.append((inst_id, side, pos_side, sz)); return {"code":"0"}
        client=DummyClient()
        try:
            out1=g.guardian_check(client, dry_run=False)
            out2=g.guardian_check(client, dry_run=False)
            self.assertTrue(out1["ok"])
            self.assertEqual(len(client.market_orders), 1)
            self.assertEqual(client.market_orders[0], ("BTC-USDT-SWAP", "sell", "long", "0.5"))
            self.assertEqual([a["action"]["type"] for a in out2["action_results"] if a["action"].get("label") == "tp1_50pct"], [])
        finally:
            g.CFG=old_cfg; g.InstrumentCache=old_cache

    def test_guardian_dry_run_does_not_mark_tp1_done(self):
        import tempfile, json
        from pathlib import Path
        import jarvis_unified.ledger_guardian as g
        tmp=Path(tempfile.mkdtemp()); (tmp/"state").mkdir(parents=True)
        old_cfg=g.CFG
        g.CFG=type("C",(),{**old_cfg.__dict__,"data_dir":tmp,"guardian_tp_state_file":"guardian_tp_state.json"})()
        class DummyCache:
            def get(self, inst_id, client=None): return {"lotSz":"0.1", "minSz":"0.1"}
        old_cache=g.InstrumentCache; g.InstrumentCache=lambda: DummyCache()
        class DummyClient:
            def assert_account(self): return {}
            def positions(self): return {"code":"0","data":[{"instId":"BTC-USDT-SWAP","posSide":"long","pos":"1.0","avgPx":"100","markPx":"116"}]}
            def algo_orders(self): return {"code":"0","data":[{"instId":"BTC-USDT-SWAP","posSide":"long","algoId":"sl1","slTriggerPx":"90"}]}
        try:
            out=g.guardian_check(DummyClient(), dry_run=True)
            self.assertTrue(out["dry_run"])
            st=json.loads((tmp/"state"/"guardian_tp_state.json").read_text())
            self.assertFalse(st["positions"]["BTC-USDT-SWAP:long"].get("tp1_done", False))
        finally:
            g.CFG=old_cfg; g.InstrumentCache=old_cache


    def test_v030_router_range_allows_two_probe_slots(self):
        d=decide(market(btc_ch4=0.001, btc_ch24=0.002, up=0.42, down=0.44), {"freshness":"fresh","modifiers":{"total_risk_multiplier":1.0,"event_veto":False}})
        self.assertEqual(d.market_phase, "btc_range_alt_dispersion")
        self.assertEqual(d.max_positions, 5)
        self.assertGreaterEqual(d.total_risk_ceiling, 0.43)

    def test_v030_duplicate_symbol_position_blocks_new_entry(self):
        import jarvis_unified.risk_execution as r
        class DummyCache:
            def get(self, inst_id, client=None):
                return {"ctVal":"1", "lotSz":"0.01", "minSz":"0.01"}
        old_cache = r.InstrumentCache
        r.InstrumentCache = lambda: DummyCache()
        try:
            cand=Candidate("alt_long","H-USDT-SWAP","long",83,[],0.58,0.02)
            decision=type("D",(),{"max_positions":2,"total_risk_ceiling":0.30,"context_modifiers":{"total_risk_multiplier":1.0}})()
            positions={"code":"0","data":[{"instId":"H-USDT-SWAP","posSide":"long","pos":"0.1"}]}
            plan=build_plan(object(), cand, {"code":"0","data":[{"totalEq":"100","details":[{"ccy":"USDT","eq":"100"}]}]}, positions, decision)
            self.assertFalse(plan.ok)
            self.assertEqual(plan.reason, "duplicate_symbol_position")
        finally:
            r.InstrumentCache = old_cache

    def test_v030_healthcheck_flags_stale_context_and_missing_guardian(self):
        import tempfile, json, time
        from pathlib import Path
        from jarvis_unified.healthcheck import run_healthcheck
        tmp=Path(tempfile.mkdtemp()); (tmp/"snapshots").mkdir(); (tmp/"state").mkdir(); (tmp/"ledgers").mkdir()
        (tmp/"snapshots"/"cold_context_latest.json").write_text(json.dumps({"ts": time.time()-9*3600, "freshness":"fresh", "modifiers":{}}))
        (tmp/"state"/"live_cycle_latest.json").write_text(json.dumps({"ts": time.time(), "router":{"market_phase":"btc_range_alt_dispersion"}}))
        cfg=type("C",(),{"data_dir":tmp,"context_max_age_hours":6,"live_cycle_minutes":15,"guardian_minutes":5,"expected_uid":"851731612504386465","expected_main_uid":"621655308511150593","version":"0.3.0"})()
        class DummyClient:
            def assert_account(self): return {"uid":"851731612504386465","mainUid":"621655308511150593"}
            def positions(self): return {"code":"0","data":[]}
            def algo_orders(self): return {"code":"0","data":[]}
        out=run_healthcheck(DummyClient(), cfg=cfg)
        issue_types=[i["type"] for i in out["issues"]]
        self.assertIn("cold_context_stale", issue_types)
        self.assertIn("guardian_snapshot_missing", issue_types)
        self.assertFalse(out["ok"])


    def test_v030_per_sleeve_cap_blocks_second_alt_long_when_cap_one(self):
        import jarvis_unified.risk_execution as r
        class DummyCache:
            def get(self, inst_id, client=None):
                return {"ctVal":"1", "lotSz":"0.01", "minSz":"0.01"}
        old_cache, old_cfg = r.InstrumentCache, r.CFG
        r.InstrumentCache = lambda: DummyCache()
        r.CFG=type("C",(),{**old_cfg.__dict__,"max_total_positions":5,"max_positions_per_sleeve":1,"max_margin_usage_pct":0.65,"single_trade_risk_usdt":0.75,"daily_realized_loss_halt_usdt":4.5,"min_stop_pct":0.006,"max_stop_pct":0.025,"leverage_default":5,"leverage_hard_cap":10,"min_live_candidate_score":70.0})()
        try:
            cand=Candidate("alt_long","BABY-USDT-SWAP","long",78,[],0.015,0.02)
            decision=type("D",(),{"max_positions":3,"total_risk_ceiling":0.30,"context_modifiers":{"total_risk_multiplier":1.0}})()
            positions={"code":"0","data":[{"instId":"H-USDT-SWAP","posSide":"long","pos":"0.1"}]}
            plan=build_plan(object(), cand, {"code":"0","data":[{"totalEq":"100","details":[{"ccy":"USDT","eq":"100"}]}]}, positions, decision)
            self.assertFalse(plan.ok)
            self.assertEqual(plan.reason, "sleeve_position_cap_reached")
        finally:
            r.InstrumentCache = old_cache; r.CFG=old_cfg

    def test_v100_router_exposes_four_matrix_sleeves(self):
        d=decide(market(btc_ch4=-0.02, btc_ch24=-0.03, up=0.1, down=0.7), {"freshness":"fresh","modifiers":{"total_risk_multiplier":1.0,"event_veto":False}})
        self.assertIn("maincoin_long", d.sleeve_permissions)
        self.assertIn("maincoin_short", d.sleeve_permissions)
        self.assertIn("alt_long", d.sleeve_permissions)
        self.assertIn("alt_short", d.sleeve_permissions)
        self.assertEqual(d.maincoin_short_permission, "probe_only")
        self.assertEqual(d.alt_short_permission, "active")

    def test_v100_maincoin_short_counts_as_own_sleeve(self):
        import jarvis_unified.risk_execution as r
        positions={"code":"0","data":[{"instId":"BTC-USDT-SWAP","posSide":"short","pos":"0.1"}]}
        self.assertEqual(r.sleeve_positions_count(positions, "maincoin_short"), 1)
        self.assertEqual(r.sleeve_positions_count(positions, "maincoin_long"), 0)

    def test_v110_alt_universe_limit_uses_config_100(self):
        import jarvis_unified.market_data as m
        class DummyClient:
            def tickers(self):
                return {"code":"0","data":[{"instId":f"ALT{i}-USDT-SWAP","last":"2","open24h":"1","volCcy24h":str(1000+i)} for i in range(130)]}
        old_cfg=m.CFG
        m.CFG=type("C",(),{**old_cfg.__dict__,"alt_universe_limit":100,"allowed_maincoins":old_cfg.allowed_maincoins})()
        try:
            out=m.broad_swap_universe(DummyClient())
            self.assertEqual(len(out), 100)
        finally:
            m.CFG=old_cfg

    def test_v110_sync_fills_dedupes_by_uid_tradeid_and_sets_cooldown(self):
        import tempfile, json
        from pathlib import Path
        import jarvis_unified.ledger_guardian as g
        tmp=Path(tempfile.mkdtemp()); (tmp/"ledgers").mkdir(); (tmp/"state").mkdir()
        (tmp/"ledgers"/"fills.jsonl").write_text(json.dumps({"uid":"OTHER","tradeId":"T1","instId":"ABC-USDT-SWAP","date":"2026-01-01","net_pnl":0})+"\n")
        old_cfg=g.CFG
        g.CFG=type("C",(),{**old_cfg.__dict__,"data_dir":tmp,"version":"1.1.0","expected_uid":"U1","expected_main_uid":"M1","okx_profile":"test","strategy_tag":"test","stopout_cooldown_hours":6})()
        class DummyClient:
            def assert_account(self): return {"uid":"U1","mainUid":"M1"}
            def fills(self, limit): return {"code":"0","data":[{"tradeId":"T1","ts":"1781500000000","instId":"ABC-USDT-SWAP","side":"buy","posSide":"long","fillSz":"1","fillPx":"1","fee":"-0.01","fillPnl":"-0.5"}]}
        try:
            out=g.sync_fills(DummyClient())
            self.assertEqual(out["new"], 1)
            self.assertEqual(out["dedupe"], "uid_tradeId")
            rows=(tmp/"ledgers"/"fills.jsonl").read_text().splitlines()
            self.assertEqual(len(rows), 2)
            cooldown=json.loads((tmp/"state"/"stopout_cooldowns.json").read_text())
            self.assertIn("ABC-USDT-SWAP", cooldown["symbols"])
        finally:
            g.CFG=old_cfg

    def test_v110_stopout_cooldown_blocks_entry(self):
        import tempfile, json, time
        from pathlib import Path
        import jarvis_unified.risk_execution as r
        tmp=Path(tempfile.mkdtemp()); (tmp/"state").mkdir(); (tmp/"ledgers").mkdir()
        (tmp/"state"/"stopout_cooldowns.json").write_text(json.dumps({"version":"1.1.0","symbols":{"COOL-USDT-SWAP":{"until_ts":time.time()+3600}}}))
        old_cfg=r.CFG
        r.CFG=type("C",(),{**old_cfg.__dict__,"data_dir":tmp,"max_total_positions":5,"max_positions_per_sleeve":2,"daily_realized_loss_halt_usdt":4.5})()
        try:
            cand=Candidate("alt_long","COOL-USDT-SWAP","long",80,[],1.0,0.02)
            decision=type("D",(),{"max_positions":2,"total_risk_ceiling":0.30,"context_modifiers":{"total_risk_multiplier":1.0}})()
            plan=build_plan(object(), cand, {"code":"0","data":[{"totalEq":"100","details":[{"ccy":"USDT","eq":"100"}]}]}, {"code":"0","data":[]}, decision)
            self.assertFalse(plan.ok)
            self.assertIn("stopout_cooldown", plan.reason)
        finally:
            r.CFG=old_cfg

    def test_v110_report_pnl_summary_by_sleeve(self):
        import tempfile, json
        from pathlib import Path
        import jarvis_unified.reports as rep
        tmp=Path(tempfile.mkdtemp()); (tmp/"ledgers").mkdir(); (tmp/"state").mkdir(); (tmp/"snapshots").mkdir()
        from datetime import datetime, UTC
        today=datetime.now(UTC).strftime("%Y-%m-%d")
        rows=[
            {"date":today,"uid":rep.CFG.expected_uid,"instId":"BTC-USDT-SWAP","posSide":"long","fee":-0.01,"net_pnl":1.0},
            {"date":today,"uid":rep.CFG.expected_uid,"instId":"ABC-USDT-SWAP","posSide":"short","fee":-0.02,"net_pnl":-0.5},
            {"date":today,"uid":"OTHER","instId":"ABC-USDT-SWAP","posSide":"short","fee":-9,"net_pnl":-9},
        ]
        (tmp/"ledgers"/"fills.jsonl").write_text("\n".join(json.dumps(x) for x in rows)+"\n")
        old_cfg=rep.CFG
        rep.CFG=type("C",(),{**old_cfg.__dict__,"data_dir":tmp,"sleeve_names":old_cfg.sleeve_names,"allowed_maincoins":old_cfg.allowed_maincoins,"expected_uid":old_cfg.expected_uid})()
        try:
            out=rep._matrix_pnl_summary(7)
            self.assertEqual(out["raw_fills"], 2)
            self.assertEqual(out["sleeves"]["maincoin_long"]["net_pnl"], 1.0)
            self.assertEqual(out["sleeves"]["alt_short"]["net_pnl"], -0.5)
        finally:
            rep.CFG=old_cfg

    def test_v110_corrupt_cooldown_state_fails_closed(self):
        import tempfile
        from pathlib import Path
        import jarvis_unified.risk_execution as r
        tmp=Path(tempfile.mkdtemp()); (tmp/"state").mkdir(); (tmp/"ledgers").mkdir()
        (tmp/"state"/"stopout_cooldowns.json").write_text("not-json")
        old_cfg=r.CFG
        r.CFG=type("C",(),{**old_cfg.__dict__,"data_dir":tmp,"max_total_positions":5,"max_positions_per_sleeve":2,"daily_realized_loss_halt_usdt":4.5})()
        try:
            cand=Candidate("alt_long","SAFE-USDT-SWAP","long",80,[],1.0,0.02)
            decision=type("D",(),{"max_positions":2,"total_risk_ceiling":0.30,"context_modifiers":{"total_risk_multiplier":1.0}})()
            plan=build_plan(object(), cand, {"code":"0","data":[{"totalEq":"100","details":[{"ccy":"USDT","eq":"100"}]}]}, {"code":"0","data":[]}, decision)
            self.assertFalse(plan.ok)
            self.assertEqual(plan.reason, "stopout_cooldown_state_unreadable_fail_closed")
        finally:
            r.CFG=old_cfg

    def test_v110_missing_uid_ignored_for_daily_pnl_and_cooldown_rebuild(self):
        import tempfile, json, time
        from pathlib import Path
        import jarvis_unified.risk_execution as r
        import jarvis_unified.ledger_guardian as g
        tmp=Path(tempfile.mkdtemp()); (tmp/"ledgers").mkdir(); (tmp/"state").mkdir()
        import datetime as dt
        today=dt.datetime.now(dt.UTC).strftime("%Y-%m-%d")
        rows=[
            {"date":today,"tradeId":"NOUID","ts":int(time.time()*1000),"instId":"OLD-USDT-SWAP","fillPnl":-9,"net_pnl":-9},
            {"date":today,"uid":r.CFG.expected_uid,"tradeId":"UID","ts":int(time.time()*1000),"instId":"NEW-USDT-SWAP","fillPnl":-1,"net_pnl":-1},
        ]
        (tmp/"ledgers"/"fills.jsonl").write_text("\n".join(json.dumps(x) for x in rows)+"\n")
        old_r, old_g = r.CFG, g.CFG
        cfg=type("C",(),{**old_r.__dict__,"data_dir":tmp,"version":"1.1.0","expected_uid":old_r.expected_uid,"stopout_cooldown_hours":6})()
        r.CFG=cfg; g.CFG=cfg
        try:
            self.assertEqual(r.daily_realized_pnl(), -1.0)
            rebuild=g.rebuild_stopout_cooldowns_from_ledger()
            data=json.loads((tmp/"state"/"stopout_cooldowns.json").read_text())
            self.assertIn("NEW-USDT-SWAP", data["symbols"])
            self.assertNotIn("OLD-USDT-SWAP", data["symbols"])
        finally:
            r.CFG=old_r; g.CFG=old_g

    def test_v110_report_refresh_disables_fill_sync_and_decision_recording(self):
        import jarvis_unified.reports as rep
        calls=[]
        old_run = None
        # Import module then monkeypatch the live_cycle entry used by refresh_daily_state through module attr.
        import jarvis_unified.live_cycle as lc
        old_run = lc.run_live_cycle
        def fake_run_live_cycle(*args, **kwargs):
            calls.append(kwargs)
            return {"ok": True}
        lc.run_live_cycle = fake_run_live_cycle
        try:
            out=rep.refresh_daily_state()
            self.assertFalse(out["errors"][:1])
            self.assertEqual(calls[0].get("sync_fills_enabled"), False)
            self.assertEqual(calls[0].get("record_decisions"), False)
        finally:
            lc.run_live_cycle = old_run

    def test_v111_entry_stop_price_quantized_to_tick_without_8dp_rounding(self):
        import jarvis_unified.risk_execution as r
        class DummyCache:
            def get(self, inst_id, client=None):
                return {"ctVal":"1000000", "lotSz":"1", "minSz":"1", "tickSz":"0.000000001"}
        old_cache = r.InstrumentCache
        r.InstrumentCache = lambda: DummyCache()
        try:
            cand=Candidate("alt_long","SATS-USDT-SWAP","long",85,[],0.000000312,0.018,preliminary=False)
            decision=type("D",(),{"max_positions":1,"total_risk_ceiling":0.47,"context_modifiers":{"total_risk_multiplier":1.0}})()
            plan=build_plan(object(), cand, {"code":"0","data":[{"totalEq":"221","details":[{"ccy":"USDT","eq":"221"}]}]}, {"code":"0","data":[]}, decision)
            self.assertTrue(plan.ok, plan.reason)
            self.assertEqual(plan.stop_px_str, "0.000000306")
            self.assertNotEqual(plan.stop_px_str, str(round(plan.stop_px, 8)))
        finally:
            r.InstrumentCache = old_cache

    def test_v111_guardian_stop_price_quantized_to_tick(self):
        import jarvis_unified.ledger_guardian as g
        p={"instId":"MICRO-USDT-SWAP","posSide":"short","pos":"10","avgPx":"0.000000312","markPx":"0.000000120"}
        algos=[{"instId":"MICRO-USDT-SWAP","posSide":"short","algoId":"sl1","slTriggerPx":"0.000000400"}]
        inst={"lotSz":"1","minSz":"1","tickSz":"0.000000001"}
        rec, ev = g.evaluate_guardian_actions(p, algos, {}, inst)
        stop_actions=[a for a in ev["actions"] if a["type"] == "move_stop"]
        self.assertTrue(stop_actions)
        self.assertRegex(stop_actions[0]["stop_px"], r"^0\.000000\d{3}$")

    def test_v120_controlled_growth_config(self):
        import jarvis_unified.config as c
        self.assertEqual(c.CFG.version, "1.2.0")
        self.assertEqual(c.CFG.strategy_tag, "matrix_v1_2_0_controlled_growth")
        self.assertEqual(c.CFG.growth_mode, "controlled_growth")
        self.assertEqual(c.CFG.max_total_positions, 6)
        self.assertEqual(c.CFG.max_positions_per_sleeve, 3)
        self.assertEqual(c.CFG.single_trade_risk_usdt, 1.0)
        self.assertEqual(c.CFG.daily_realized_loss_halt_usdt, 6.0)
        self.assertEqual(c.CFG.alt_universe_limit, 120)

    def test_v120_alt_candidates_honor_configured_universe_width(self):
        import jarvis_unified.candidates as candmod
        old_cfg=candmod.CFG
        rows=[{"instId":f"ALT{i}-USDT-SWAP","chg24h":-0.05,"last":1.0,"vol":600000+i} for i in range(120)]
        candmod.CFG=type("C",(),{**old_cfg.__dict__,"alt_universe_limit":120,"allow_alt_short":True,"min_stop_pct":0.006,"max_stop_pct":0.025})()
        try:
            out=candmod.alt_candidates({"alt_universe":rows}, "wait", "active", short_delta=0)
            self.assertEqual(len(out), 120)
        finally:
            candmod.CFG=old_cfg

    def test_v120_place_stop_algo_uses_sl_trigger_payload(self):
        import os
        from jarvis_unified.okx_client import OKXClient
        old_env = os.environ.get("JARVIS_UNIFIED_LIVE_TRADING")
        os.environ["JARVIS_UNIFIED_LIVE_TRADING"] = "true"
        class DummyClient(OKXClient):
            def __init__(self): self._account_verified = True; self.body = None
            def req(self, method, path, body=None, auth=True):
                self.body = body
                return {"code":"0"}
        try:
            c=DummyClient()
            c.place_stop_algo("ABC-USDT-SWAP", "sell", "long", "1", "0.9")
            self.assertIn("slTriggerPx", c.body)
            self.assertIn("slOrdPx", c.body)
            self.assertNotIn("triggerPx", c.body)
            self.assertNotIn("orderPx", c.body)
        finally:
            if old_env is None: os.environ.pop("JARVIS_UNIFIED_LIVE_TRADING", None)
            else: os.environ["JARVIS_UNIFIED_LIVE_TRADING"] = old_env

    def test_v120_post_order_sl_confirmation_records_unconfirmed(self):
        import tempfile, os, json
        from pathlib import Path
        import jarvis_unified.risk_execution as r
        tmp=Path(tempfile.mkdtemp()); (tmp/"ledgers").mkdir(); (tmp/"state").mkdir()
        old_cfg=r.CFG
        r.CFG=type("C",(),{**old_cfg.__dict__,"data_dir":tmp,"post_order_sl_confirm_attempts":1,"post_order_sl_confirm_delay_sec":0.0})()
        old_env=os.environ.get("JARVIS_UNIFIED_LIVE_TRADING"); os.environ["JARVIS_UNIFIED_LIVE_TRADING"]="true"
        class DummyClient:
            def assert_account(self): return {"uid":r.CFG.expected_uid,"mainUid":r.CFG.expected_main_uid}
            def set_leverage(self, *a): return {"code":"0"}
            def place_market(self, *a, **kw): return {"code":"0", "data":[{"ordId":"O1"}]}
            def algo_orders(self): return {"code":"0", "data":[]}
        plan=r.ExecutionPlan(True,"ok",{},"ABC-USDT-SWAP","long","long","buy",1,0.9,0.1,10,2,"1",5,"0.9")
        try:
            out=r.execute_plan(DummyClient(), plan, dry_run=False)
            self.assertTrue(out["executed"])
            self.assertFalse(out["protection_confirmed"])
            self.assertEqual(out["reason"], "post_order_sl_confirm_failed")
            rows=(tmp/"ledgers"/"decisions.jsonl").read_text().splitlines()
            self.assertEqual(json.loads(rows[-1])["kind"], "live_order_unconfirmed_sl")
        finally:
            r.CFG=old_cfg
            if old_env is None: os.environ.pop("JARVIS_UNIFIED_LIVE_TRADING", None)
            else: os.environ["JARVIS_UNIFIED_LIVE_TRADING"] = old_env

    def test_v120_post_order_sl_confirmation_rejects_stale_wrong_stop(self):
        import jarvis_unified.risk_execution as r
        class DummyClient:
            def algo_orders(self): return {"code":"0", "data":[{"instId":"ABC-USDT-SWAP","posSide":"long","slTriggerPx":"0.70"}]}
        out=r.confirm_protective_stop(DummyClient(), "ABC-USDT-SWAP", "long", "0.90", attempts=1, delay_sec=0)
        self.assertFalse(out["ok"])
        self.assertEqual(len(out["matches"]), 1)

    def test_v120_post_order_sl_confirmation_accepts_close_normalized_stop(self):
        import jarvis_unified.risk_execution as r
        class DummyClient:
            def algo_orders(self): return {"code":"0", "data":[{"instId":"ABC-USDT-SWAP","posSide":"long","slTriggerPx":"0.899"}]}
        out=r.confirm_protective_stop(DummyClient(), "ABC-USDT-SWAP", "long", "0.90", attempts=1, delay_sec=0)
        self.assertTrue(out["ok"])

    def test_v120_opportunity_blocks_records_high_score_cap(self):
        import tempfile, json
        from pathlib import Path
        import jarvis_unified.live_cycle as lc
        tmp=Path(tempfile.mkdtemp()); (tmp/"ledgers").mkdir(); (tmp/"state").mkdir(); (tmp/"snapshots").mkdir()
        old_cfg=lc.CFG
        lc.CFG=type("C",(),{**old_cfg.__dict__,"data_dir":tmp,"version":"1.2.0","strategy_tag":"test","expected_uid":"U","opportunity_block_min_score":85.0})()
        decision=type("D",(),{"market_phase":"btc_range_alt_dispersion","sleeve_permissions":{"alt_short":"probe_only"}})()
        plans=[{"ok":False,"reason":"sleeve_position_cap_reached","candidate":{"inst_id":"ABC-USDT-SWAP","score":91,"sleeve":"alt_short"}}]
        try:
            out=lc._record_opportunity_blocks(plans, decision)
            self.assertEqual(out["recorded"], 1)
            row=json.loads((tmp/"ledgers"/"opportunity_blocks.jsonl").read_text().splitlines()[0])
            self.assertEqual(row["kind"], "opportunity_block")
            self.assertEqual(row["reason"], "sleeve_position_cap_reached")
        finally:
            lc.CFG=old_cfg

if __name__ == "__main__":
    unittest.main()
