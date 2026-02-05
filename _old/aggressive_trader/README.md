# Aggressive Trader

A more active trading framework with stop-loss and take-profit orders.

## Key Differences from Vanilla Trader

| Feature | Vanilla Trader | Aggressive Trader |
|---------|---------------|-------------------|
| Order Check | 1x per minute | Configurable (1s-60s) |
| Orders at Once | 1 | Multiple (entry + SL + TP) |
| Stop Loss | None | Built-in |
| Take Profit | None | Built-in |
| Position Management | Simple buy/sell | Full bracket orders |

## Architecture

```
aggressive_trader/
├── bot.py              # Main trading bot
├── position.py         # Position tracking with SL/TP
├── order_manager.py    # Handles bracket orders (entry + SL + TP)
├── strategies/
│   ├── base.py         # Base class with SL/TP hooks
│   └── ...             # Strategy implementations
└── backtest/
    ├── engine.py       # Backtesting engine
    └── ...
```

## Position Types

### Bracket Order
When entering a position, we place three orders:
1. **Entry Order** - Limit order to enter the position
2. **Stop Loss** - Automatic exit if price moves against us
3. **Take Profit** - Automatic exit when target reached

```python
# Example: Long position with 2% stop loss, 5% take profit
position = Position(
    side="LONG",
    entry_price=50000,
    size=0.1,
    stop_loss_pct=0.02,    # Exit if price drops 2%
    take_profit_pct=0.05,  # Exit if price rises 5%
)
```

## Strategy Interface

```python
class AggressiveStrategy(ABC):
    @abstractmethod
    def should_enter(self, candles: List[Candle]) -> Optional[Signal]:
        '''Return entry signal with SL/TP levels, or None'''
        pass
    
    @abstractmethod
    def should_exit(self, position: Position, candles: List[Candle]) -> bool:
        '''Return True to exit early (before SL/TP hit)'''
        pass
```

## Risk Management

- **Max Position Size**: Configurable % of portfolio
- **Max Concurrent Positions**: Limit exposure
- **Daily Loss Limit**: Stop trading after X% loss
- **Trailing Stop**: Move SL as position profits
