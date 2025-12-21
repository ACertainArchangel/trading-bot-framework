# Market Making - DEPRECATED

⚠️ **This folder is deprecated and no longer maintained.**

## Why?

After extensive testing, we found that market making on Coinbase's retail API is not viable:

1. **Tokens with good spreads** (TROLL, SHPING) → No liquidity, orders sit unfilled for minutes
2. **Tokens with liquidity** (GST, DOGINME) → Activity is one-sided or inconsistent  
3. **The profitable gap** is being arbitraged by faster/better-positioned traders with co-located servers

### Key Findings

- Need sub-millisecond execution to capture spreads consistently
- Need co-located servers near the exchange
- Need significantly larger capital
- Our 0.025% maker fee means we need >0.05% spread to profit
- Even when spread exists, market orders don't flow through our price levels consistently

## What Worked

The vanilla trader bot consistently achieves **27% APY** in year-long backtests (up to 47% in good conditions). It uses simple limit orders once per minute and doesn't try to compete on speed.

See the `vanilla_trader/` folder for the active trading system.
