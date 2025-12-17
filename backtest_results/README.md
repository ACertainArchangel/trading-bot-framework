# Trading Strategies

This directory contains modular trading strategies that can be plugged into the Bot class.

## Strategy System

All strategies inherit from the `Strategy` base class and must implement:
- `buy_signal(candles)` - Returns True when conditions are right to buy
- `sell_signal(candles)` - Returns True when conditions are right to sell
- `name` property - Returns a human-readable name for the strategy
- `explain()` method - Returns a list of strings describing the strategy

Strategies automatically check baseline profitability to avoid signaling trades that would be rejected.

## Available Strategies

### EMACrossStrategy

Exponential Moving Average crossover strategy (Golden Cross / Death Cross).

**Signals:**
- **BUY**: When fast EMA crosses above slow EMA (bullish crossover) AND trade would exceed asset baseline
- **SELL**: When fast EMA crosses below slow EMA (bearish crossover) AND trade would exceed currency baseline

**Parameters:**
- `fast`: Fast EMA period (default: 9)
- `slow`: Slow EMA period (default: 21)

**Best Performance:** EMA(50/200) - 48.55% APY, 127.49% BTC APY

**Usage:**
```python
from strategies.ema_cross import EMACrossStrategy

strategy = EMACrossStrategy(bot, fast=50, slow=200)
bot.set_strategy(strategy)
```

### MomentumStrategy

Rate of Change (ROC) momentum strategy.

**Signals:**
- **BUY**: When ROC crosses above buy threshold AND trade would exceed asset baseline
- **SELL**: When ROC crosses below sell threshold AND trade would exceed currency baseline

**Parameters:**
- `period`: ROC lookback period (default: 10)
- `buy_threshold`: Buy when ROC > threshold % (default: 1.0)
- `sell_threshold`: Sell when ROC < threshold % (default: -1.0)

**Best Performance:** Period 10, ±1.0% - 53.70% APY

**Usage:**
```python
from strategies.momentum import MomentumStrategy

strategy = MomentumStrategy(bot, period=10, buy_threshold=1.0, sell_threshold=-1.0)
bot.set_strategy(strategy)
```

### MACDStrategy

MACD (Moving Average Convergence Divergence) crossover strategy with trajectory prediction.

**Signals:**
- **BUY**: When MACD line crosses above signal line (bullish crossover) AND trade would exceed asset baseline
- **SELL**: When MACD line crosses below signal line (bearish crossover) AND trade would exceed currency baseline

**Parameters:**
- `fast_period`: Period for fast EMA (default: 12)
- `slow_period`: Period for slow EMA (default: 26)
- `signal_period`: Period for signal line EMA (default: 9)
- `min_slope_periods`: Slope consistency check (default: 3)
- `min_momentum_strength`: Acceleration threshold (default: 2.0)
- `trajectory_threshold`: Crossover prediction threshold (default: 0.7)
- `sharp_reversal_multiplier`: Sharp reversal detection (default: 3.0)

**Usage:**
```python
from strategies.macd import MACDStrategy

strategy = MACDStrategy(bot, fast_period=12, slow_period=26, signal_period=9)
bot.set_strategy(strategy)
```

### RSIStrategy

Relative Strength Index (RSI) oscillator strategy.

**Signals:**
- **BUY**: When RSI crosses below oversold level AND trade would exceed asset baseline
- **SELL**: When RSI crosses above overbought level AND trade would exceed currency baseline

**Parameters:**
- `period`: RSI period (default: 14)
- `oversold`: Oversold threshold (default: 30)
- `overbought`: Overbought threshold (default: 70)

**Usage:**
```python
from strategies.rsi import RSIStrategy

strategy = RSIStrategy(bot, period=14, oversold=30, overbought=70)
bot.set_strategy(strategy)
```

### BollingerStrategy

Bollinger Bands price channel strategy.

**Signals:**
- **BUY**: When price crosses below lower band AND trade would exceed asset baseline
- **SELL**: When price crosses above upper band AND trade would exceed currency baseline

**Parameters:**
- `period`: Moving average period (default: 20)
- `std_dev`: Standard deviation multiplier (default: 2.0)

**Usage:**
```python
from strategies.bollinger import BollingerStrategy

strategy = BollingerStrategy(bot, period=20, std_dev=2.0)
bot.set_strategy(strategy)
```

### StochasticStrategy

Stochastic Oscillator momentum strategy.

**Signals:**
- **BUY**: When %K crosses below oversold level AND trade would exceed asset baseline
- **SELL**: When %K crosses above overbought level AND trade would exceed currency baseline

**Parameters:**
- `k_period`: %K period (default: 14)
- `d_period`: %D smoothing period (default: 3)
- `oversold`: Oversold threshold (default: 20)
- `overbought`: Overbought threshold (default: 80)

**Usage:**
```python
from strategies.stochastic import StochasticStrategy

strategy = StochasticStrategy(bot, k_period=14, d_period=3, oversold=20, overbought=80)
bot.set_strategy(strategy)
```

### MeanReversionStrategy

Statistical mean reversion strategy.

**Signals:**
- **BUY**: When price is below mean + buy_threshold * std_dev AND trade would exceed asset baseline
- **SELL**: When price is above mean + sell_threshold * std_dev AND trade would exceed currency baseline

**Parameters:**
- `period`: Lookback period for mean/std calculation (default: 20)
- `buy_threshold`: Buy when price < mean + threshold*std (default: -1.5)
- `sell_threshold`: Sell when price > mean + threshold*std (default: 1.5)

**Usage:**
```python
from strategies.mean_reversion import MeanReversionStrategy

strategy = MeanReversionStrategy(bot, period=20, buy_threshold=-1.5, sell_threshold=1.5)
bot.set_strategy(strategy)
```

## Quick Usage with Bots

All strategies work with both test and live bots:

```bash
# Paper trading
python test_bot.py ema_cross --fast 50 --slow 200 --days 10

# Live trading
python live_bot.py momentum --period 10 --buy_threshold 1.0 --sell_threshold -1.0
```

## Creating New Strategies

1. Create a new file in `strategies/` directory
2. Inherit from `Strategy` base class
3. Implement required methods: `buy_signal()`, `sell_signal()`, `name`, `explain()`
4. Use `check_baseline_for_buy()` and `check_baseline_for_sell()` to avoid unprofitable trades
5. Add to `__init__.py` exports
6. Register in bot scripts (`test_bot.py` and `live_bot.py`)

**Example:**
```python
from typing import List, Tuple
from .base import Strategy

class MyStrategy(Strategy):
    def __init__(self, bot, my_param: int = 10):
        super().__init__(bot)
        self.my_param = my_param
    
    @property
    def name(self):
        """Return human-readable strategy name"""
        return f"MyStrategy({self.my_param})"
    
    def buy_signal(self, candles: List[Tuple]) -> bool:
        """Determine if conditions are right to buy"""
        current_price = candles[-1][4]
        
        # Always check baseline before signaling
        if not self.check_baseline_for_buy(current_price):
            return False
        
        # Your technical analysis here
        # Example: Buy if price dropped 5% in last my_param candles
        if len(candles) < self.my_param:
            return False
        
        old_price = candles[-self.my_param][4]
        price_change = ((current_price - old_price) / old_price) * 100
        
        return price_change < -5.0  # Buy on 5% dip
    
    def sell_signal(self, candles: List[Tuple]) -> bool:
        """Determine if conditions are right to sell"""
        current_price = candles[-1][4]
        
        # Always check baseline before signaling
        if not self.check_baseline_for_sell(current_price):
            return False
        
        # Your technical analysis here
        # Example: Sell if price rose 5% in last my_param candles
        if len(candles) < self.my_param:
            return False
        
        old_price = candles[-self.my_param][4]
        price_change = ((current_price - old_price) / old_price) * 100
        
        return price_change > 5.0  # Sell on 5% gain
    
    def explain(self) -> List[str]:
        """Provide human-readable explanation of strategy"""
        return [
            f"🎯 {self.name}",
            f"   • Buys when price drops 5% over {self.my_param} candles",
            f"   • Sells when price rises 5% over {self.my_param} candles",
            "   • Uses baseline protection to avoid losses",
        ]
```

Then register it:

1. **Add to `strategies/__init__.py`:**
```python
from .my_strategy import MyStrategy
__all__ = ['Strategy', 'MyStrategy', ...]
```

2. **Add to bot scripts (`test_bot.py` and `live_bot.py`):**
```python
STRATEGIES = {
    'my_strategy': MyStrategy,
    # ... other strategies
}
```

3. **Test it:**
```bash
python test_bot.py my_strategy --my_param 20 --days 10
```

## Strategy Ideas

Additional strategies you could implement:

1. **Volume Profile** - Support/resistance from volume
2. **Trend Following** - ADX/DMI for trend strength
3. **Multi-timeframe** - Combine signals from different granularities
4. **Machine Learning** - Train models on historical patterns
5. **Order Book Analysis** - Trade based on bid/ask imbalances
4. **Stochastic Oscillator** - Momentum-based signals
5. **Volume Profile** - Support/resistance from volume
6. **Mean Reversion** - Trade when price deviates from mean
7. **Trend Following** - ADX/DMI for trend strength
8. **Multi-timeframe** - Combine signals from different granularities

## Baseline Protection

All strategies should use baseline checks to implement the "never take a loss" algorithm:

```python
# For buy signals
if not self.check_baseline_for_buy(current_price):
    return False

# For sell signals  
if not self.check_baseline_for_sell(current_price):
    return False
```

This prevents the strategy from signaling trades that would:
- Buy for less asset than the best previous long position
- Sell for less currency than the best previous short position

The bot's `execute_buy()` and `execute_sell()` methods also enforce this, but checking in the strategy prevents wasting computation on rejected trades.
