#!/usr/bin/env python3
import json, os
from jarvis_unified.ledger_guardian import guardian_check

if __name__ == "__main__":
    # Default safe: read/audit/evaluate only. Set JARVIS_UNIFIED_GUARDIAN_LIVE=1
    # plus the global live-trading env to permit protective reduce-only writes.
    live = os.environ.get("JARVIS_UNIFIED_GUARDIAN_LIVE", "0").lower() in {"1", "true", "yes"}
    print(json.dumps(guardian_check(dry_run=not live), ensure_ascii=False, indent=2))
