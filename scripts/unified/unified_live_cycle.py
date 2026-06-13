#!/usr/bin/env python3
import json, os
from jarvis_unified.live_cycle import run_live_cycle
if __name__ == "__main__":
    dry = os.environ.get("JARVIS_UNIFIED_DRY_RUN", "0") in {"1","true","yes"}
    print(json.dumps(run_live_cycle(dry_run=dry), ensure_ascii=False, indent=2))
