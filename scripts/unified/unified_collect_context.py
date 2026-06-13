#!/usr/bin/env python3
import json
from jarvis_unified.context import collect_cold_context
if __name__ == "__main__": print(json.dumps(collect_cold_context(), ensure_ascii=False, indent=2))
