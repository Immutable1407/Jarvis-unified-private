# Matrix Strategy — Plain-Language Operating Logic

This note explains how the Matrix Account is supposed to make money without relying on trading jargon.

## One-sentence version

The system tries to recognize the current market weather, choose the right sleeve for that weather, pay small controlled losses while searching for real trends, and let the rare large winners pay for many failed probes.

In plain language:

> Strong market: buy strength. Weak market: short weakness. Noisy market: do less. Lose small while searching; when the real move appears, let it become big enough to matter.

## What the Matrix is

The Matrix is not one fixed strategy that always buys or always shorts. It has four sleeves:

1. **Maincoin long** — BTC/ETH/SOL/BNB style large coins when the market is genuinely strong.
2. **Maincoin short** — large coins when the market is clearly breaking down.
3. **Alt long** — high-beta altcoins when risk appetite is strong.
4. **Alt short** — weak altcoins when risk appetite is falling.

The Router is the traffic light. It does not place orders by itself; it only says which sleeves may look for opportunities.

## Where profit should come from

### 1. Trend capture

Most trades are probes. They ask: “Is this a real move?”

If the answer is no, the system exits with a small loss. If the answer is yes, the system should stay long enough for the winner to become larger than several small losses.

The expected shape is not many tiny wins. The expected shape is many small controlled losses plus a smaller number of large winners.

### 2. Relative strength and weakness

Markets do not move evenly. Some coins lead, some lag, and some collapse faster than the index.

The Matrix tries to find:

- the strongest names during strong markets;
- the weakest names during weak markets;
- no-trade or small probes when the market has no clean edge.

### 3. Risk mismatch

The system also looks for situations where the market is positioned the wrong way: for example, weak price action while traders are still leaning bullish, or strong price action while the broader market allows risk-taking.

These setups can fail often. They only matter if losses stay small and winners are allowed to run.

## Why 1U losses can be normal now

The account is no longer a 50U experiment. Around 200–220U equity, a 1U loss is roughly the same account percentage as a 0.23–0.25U loss on a 50U account.

So the key question is not “did it lose 1U?” The key question is:

> Are these 1U probes buying enough chances to catch 2U, 3U, or larger right-tail winners?

If the answer becomes yes, the system can work. If the answer stays no, the structure needs repair.

## What v1.3.1–v1.3.2 changes about this logic

v1.3.1 does not try to remove all losses. That would destroy the trend-following logic.

Instead, it makes the exploration safer and easier to judge:

- **rolling 24h loss halt**: if the recent loss window is too large, stop opening new trades;
- **fill/lane attribution**: record which sleeve and lane a trade came from;
- **post-candle-rescore reselection**: after fresh candle confirmation, evaluate candidates in the correct order;
- **tight-stop notional cap**: if a stop is very tight, do not let position size become too large;
- **maincoin starvation diagnostics**: report whether maincoin sleeves are absent because of Router permissions or candidate failure;
- **fill-sync fail-closed**: if recent fills cannot be synced, do not place new trades from stale loss data.

v1.3.2 keeps those strategy rules but repairs execution: live entry and guardian reduce-only close orders use OKX-safe metadata and retry without tag on `51000 Parameter tag error`. This matters because the whole right-tail logic fails if floating multi-R profit cannot be converted into realized profit.

## How to judge the next phase

Do not judge Matrix by one losing trade. Judge it by the distribution of outcomes:

1. Are losses staying small and bounded?
2. Are winners sometimes reaching multiple-loss size?
3. Are losses concentrated in one sleeve or one market condition?
4. Are existing winners protected before they turn back into losers?
5. Are maincoin sleeves producing samples, or is the system degenerating into alt-only trading?

## Failure modes to watch

The Matrix is failing if:

- it keeps producing small losses but never produces large winners;
- all losses come from the same sleeve or the same type of altcoin noise;
- alt shorts are just chasing already-oversold moves;
- floating profit repeatedly appears but is not converted into realized profit;
- maincoin sleeves never produce candidates or trades;
- recent-loss guards do not pause new entries when the loss window is already too large.

The Matrix is working if:

- small losses remain controlled;
- a few winners become large enough to cover many probes;
- Router permissions match actual market weather;
- the system can identify which sleeves are helping and which are hurting;
- risk controls stop the system from revenge-trading after a bad window.
