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
        self.assertEqual(d.maincoin_permission, "active")

    def test_router_risk_off(self):
        d=decide(market(btc_ch4=-0.02, btc_ch24=-0.03, up=0.1, down=0.7), {"freshness":"fresh","modifiers":{"total_risk_multiplier":1.0,"event_veto":False}})
        self.assertEqual(d.market_phase, "risk_off_alt_decay")
        self.assertEqual(d.alt_short_permission, "active")

    def test_preliminary_candidate_blocked(self):
        class DummyClient: pass
        cand=Candidate("alt_short","ABC-USDT-SWAP","short",70,["seed"],1.0,0.018,preliminary=True)
        decision=type("D",(),{"max_positions":1,"context_modifiers":{"total_risk_multiplier":1.0}})()
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
            cand=Candidate("maincoin","BTC-USDT-SWAP","long",99,[],100,0.01)
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

if __name__ == "__main__":
    unittest.main()
