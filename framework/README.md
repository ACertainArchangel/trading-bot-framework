# Trading Framework

This is another pet project of mine that I turned into a reusable, documented, and user friendly framework. Copilot was a great help in documentation and organisation of the files, which were essentially a bunch of messy ad-hoc scripts with 20x the boilerplate needed (see _old and you'll see what I mean). I made this to develop, backtest, and deploy stratagies fast, but I have been unable to make one that:
1. Consistently gets returns that beat out the coinbase fees whilst
2. Not getting stuck if it is programmed to 'resuse to take a loss' (see the "7+3 CPU dwarves"... I mean, if you want to...)

For a project in the future I will try deep learning strategies to integrate here.

Note: Never take a loss strats actually worked great... Until they get stuck for 200 days but oh well. Maybe I can try a grumpy strat where the threshold the price has to come above before a sell gradually lowers over time. Prevents volatility jitter, busts out of those long 200 day periods. Maybe... Anyway, the framework works, so if you like it, maybe submit a pull request with your cool strats and additions.

## Quick Start

```python
from framework import Strategy, Candle, backtest, paper_trade, live_trade

class MyStrategy(Strategy):
    def buy_signal(self, candles: list[Candle]) -> bool:
        """Buy on 2% drop."""
        if len(candles) < 2:
            return False
        change = (candles[-1].close - candles[-2].close) / candles[-2].close
        return change < -0.02
    
    def sell_signal(self, candles: list[Candle]) -> bool:
        """Sell on 3% gain."""
        if not self.entry_price:
            return False
        gain = (candles[-1].close - self.entry_price) / self.entry_price
        return gain > 0.03

# Backtest → Paper trade → Live trade
result = backtest(MyStrategy, months=6)
paper_trade(MyStrategy, starting_balance=1000)
live_trade(MyStrategy, secrets_file="secrets/coinbase.json")
```

## Installation

```bash
cd trading-framework/framework
pip install -r requirements.txt
```

## Examples

See the `quickstart/` folder for complete examples:

- **simulation.py** - Backtest with visual dashboard
- **paper_trading.py** - Paper trade with real-time data
- **trade_real_money.py** - Live trading with Coinbase
- **compare_strategies.py** - Batch test multiple strategies
- **custom_strategy.py** - Build your own strategy
- **inspect_real_account.py** - View Coinbase account safely

## Creating Strategies

Implement two methods: `buy_signal()` and `sell_signal()`:

```python
from framework import Strategy
from framework.indicators import ema, rsi, macd

class MyStrategy(Strategy):
    def buy_signal(self, candles):
        fast, slow = ema(candles, 12), ema(candles, 26)
        return fast[-1] > slow[-1] and fast[-2] <= slow[-2]
    
    def sell_signal(self, candles):
        rsi_val = rsi(candles)[-1]
        return rsi_val > 70
```

### Built-in Strategies

```python
from framework.strategies.examples import (
    EMACrossover,     # EMA crossover
    RSIStrategy,      # RSI overbought/oversold
    MACDStrategy,     # MACD histogram
    BollingerStrategy # Bollinger bands
)

backtest(EMACrossover, months=6)
```

## Indicators

```python
from framework.indicators import (
    ema, sma,          # Moving averages
    rsi,               # Relative Strength Index
    macd,              # MACD + signal + histogram
    bollinger_bands,   # Upper/middle/lower bands
    stochastic,        # Stochastic oscillator
    atr,               # Average True Range
    vwap               # Volume-Weighted Average Price
)
```

## Backtesting

```python
from framework import backtest, visualize_backtest

# Basic backtest
result = backtest(MyStrategy, months=6)

# Custom parameters
result = backtest(
    MyStrategy,
    starting_balance=5000,
    fee_rate=0.001,
    product_id="ETH-USD",
    granularity="5m",
    strategy_params={"fast": 9, "slow": 21}
)

# Visual dashboard
visualize_backtest(MyStrategy, months=6)  # Opens browser
```

Output:
```
🟢 MyStrategy Backtest
Period: 6 months (182 days)
Starting: $1,000  →  Ending: $1,234
Return: +23.4% (APY: +52.1%)
Trades: 48 (62.5% win rate)
Max Drawdown: -8.3%
```

## Paper Trading

Test with fake money and real market data:

```python
from framework import paper_trade

paper_trade(MyStrategy, starting_balance=1000)
# Ctrl+C to stop
```

## Live Trading

**⚠️ Use real money carefully!**

```python
from framework import live_trade

live_trade(MyStrategy, secrets_file="secrets/coinbase.json")
```

Secrets file format (`secrets/coinbase.json`):
```json
{
    "name": "organizations/xxx/apiKeys/xxx",
    "privateKey": "-----BEGIN EC PRIVATE KEY-----\n...\n-----END EC PRIVATE KEY-----"
}
```

## Dashboard

```python
from framework import simulate, launch_dashboard

# Simulate with dashboard (backtest + visualization)
simulate(MyStrategy, months=6)  # Opens localhost:5001

# Standalone dashboard
launch_dashboard(product_id="BTC-USD")  # Opens localhost:5000
```

## Risk Management

```python
# Economics-aware trading
class SmartStrategy(Strategy):
    def buy_signal(self, candles):
        if my_condition(candles):
            # Only buy if profitable after fees
            return self.would_be_profitable_buy(candles[-1].close)
        return False

# Loss tolerance
backtest(MyStrategy, loss_tolerance=0.01)  # Max 1% loss per trade
```

### Built-in Protections

- **Data validation**: Automatically pauses trading if candle gaps detected
- **Position clarity**: Always fully in cash OR fully in asset
- **Dust handling**: Manages small leftover amounts automatically

## Project Structure

```
framework/
├── core/          # Candle, Signal types
├── strategies/    # Strategy base + examples
├── indicators/    # Technical indicators
├── data/          # Historical fetch + live stream
├── interfaces/    # Paper + Coinbase trading
├── runners/       # Backtest, paper, live, simulate
└── dashboard/     # Flask visualization
```

## Requirements

Core dependencies (see `requirements.txt`):
- `coinbase-advanced-py` - Coinbase API
- `flask`, `flask-socketio`, `flask-cors` - Dashboard
- `requests`, `websockets` - Data fetching

## Disclaimer

**Educational purposes only.** Trading involves significant risk. Never trade money you can't afford to lose.

## License

MIT
