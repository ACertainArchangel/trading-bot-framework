# Vanilla Trader

The original simple trading bot that consistently achieves **~27% APY** in year-long backtests.

## How It Works

- Checks market conditions once per minute
- Places one limit order at a time
- Uses dual baseline system to track performance
- Strategies signal BUY/SELL based on technical indicators

## Key Files

| File | Purpose |
|------|---------|
| `trader_bot.py` | Main Bot class |
| `live_bot.py` | Live trading entry point |
| `backtest_main.py` | Backtesting entry point |
| `backtest_lib.py` | Backtesting infrastructure |
| `strategies/` | Trading strategies |
| `interfaces/` | Exchange interfaces (Coinbase, Paper) |

## Best Performing Strategies

From extensive backtesting:

1. **Grumpy Mom** - Consistently profitable across market conditions
2. **EMA Cross** - Good in trending markets
3. **MACD** - Reliable signals

## Running

### Backtest
```bash
python vanilla_trader/backtest_main.py
```

### Live Trading
```bash
python vanilla_trader/live_bot.py
```

## Performance

- **Average APY**: 27%
- **Best Year**: 47% APY
- **Worst Year**: ~10% APY
- **Win Rate**: ~55-60%

## Limitations

- Only checks once per minute (misses intraday moves)
- No stop-loss/take-profit orders
- One position at a time
- Can't react quickly to sudden moves

See `aggressive_trader/` for a more active approach.
