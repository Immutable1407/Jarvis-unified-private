#!/usr/bin/env python3
import json
from jarvis_unified.okx_client import OKXClient
from jarvis_unified.config import CFG, ensure_dirs

def main():
    ensure_dirs(); c=OKXClient(); cfg=c.assert_account(); bal=c.balance(); pos=c.positions(); maxavail=None
    # use CLI wrapper for max-avail until REST method is added
    import subprocess
    p=subprocess.run(["/usr/local/bin/okx-profile","--profile",CFG.okx_profile,"account","max-avail-size","--instId","BTC-USDT-SWAP","--tdMode","cross","--json"], text=True, capture_output=True, timeout=60)
    maxavail=json.loads(p.stdout) if p.returncode==0 and p.stdout.strip() else {"error": p.stderr or p.stdout}
    out={"ok": True, "account": {k: cfg.get(k) for k in ["uid","mainUid","label","acctLv","posMode","perm","type"]}, "balance": bal, "positions": pos, "btc_max_avail": maxavail}
    print(json.dumps(out, ensure_ascii=False, indent=2))
if __name__ == "__main__": main()
