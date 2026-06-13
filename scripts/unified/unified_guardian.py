#!/usr/bin/env python3
import json
from jarvis_unified.ledger_guardian import guardian_check
if __name__ == "__main__": print(json.dumps(guardian_check(), ensure_ascii=False, indent=2))
