#!/usr/bin/env python3
from __future__ import annotations
import json, sys
from jarvis_unified.healthcheck import run_healthcheck

if __name__ == "__main__":
    out = run_healthcheck()
    if not out.get("ok"):
        print(json.dumps(out, ensure_ascii=False, indent=2))
        sys.exit(1)
    print(json.dumps(out, ensure_ascii=False, indent=2))
