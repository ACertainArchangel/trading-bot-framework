# 🤖 Algorithmic Trading Bot System

A modular, production-ready algorithmic trading system with paper trading, live trading, and comprehensive backtesting capabilities for cryptocurrency trading on Coinbase.

## 🌟 Features

- **Multiple Trading Strategies**: EMA Cross, Momentum, MACD, RSI, Bollinger Bands, Stochastic, Mean Reversion
- **Paper Trading**: Test strategies risk-free on historical data
- **Live Trading**: Execute real trades on Coinbase Advanced Trade API
- **Baseline Protection**: Never take a loss below your starting position
- **Real-time Dashboard**: Web-based monitoring with interactive charts and technical indicators
- **Comprehensive Backtesting**: Test strategies with multiple parameter configurations and loss tolerances
- **Modular Architecture**: Easily add new strategies and exchange interfaces

## 📋 Table of Contents

- [Quick Start](#-quick-start)
- [Installation](#-installation)
- [Paper Trading](#-paper-trading)
- [Live Trading](#-live-trading)
- [Backtesting](#-backtesting)
- [Available Strategies](#-available-strategies)
- [Web Dashboard](#-web-dashboard)
- [Project Structure](#-project-structure)
- [Creating Custom Strategies](#-creating-custom-strategies)

## 🚀 Quick Start

### Paper Trading (Test Mode)
```bash
# Test EMA(50/200) Golden Cross strategy on 10 days of historical data
python test_bot.py ema_cross --fast 50 --slow 200 --days 10

# Test Momentum strategy with custom parameters
python test_bot.py momentum --period 10 --buy_threshold 1.0 --sell_threshold -1.0
```

### Live Trading (Real Money)
⚠️ **WARNING: This trades with REAL MONEY on Coinbase!**

```bash
# Live trade with EMA(50/200) strategy
python live_bot.py ema_cross --fast 50 --slow 200
```

### Backtesting
```bash
# Test multiple strategies with various loss tolerance levels
python backtest_strategies.py
```

## 💾 Installation

1. **Clone the repository**
```bash
git clone <repository-url>
cd "Algorithmic Trading"
```

2. **Create virtual environment**
```bash
python -m venv venv
source venv/bin/activate  # On macOS/Linux
# or
venv\Scripts\activate  # On Windows
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

## 📊 Paper Trading

Paper trading lets you test strategies on historical data with zero risk.

### Basic Usage
```bash
python test_bot.py <strategy> [options]
```

### Options
- `--instance N` - Bot instance number for parallel bots (default: 1)
- `--days N` - Number of days of historical data (default: 10)
- `--granularity G` - Candle size: 1m, 5m, 15m, 1h, 6h, 1d (default: 5m)
- `--starting_currency N` - Starting USD balance (default: 1000.0)
- `--fee_rate N` - Fee rate as percentage (default: 0.025)
- `--loss_tolerance N` - Max acceptable loss % (default: 0.0)
- `--playback_speed N` - Replay speed multiplier (default: 0.05)
- `--port N` - Dashboard port (default: 5003)

### Examples
```bash
# Test EMA(9/26) with 30 days of data
python test_bot.py ema_cross --fast 9 --slow 26 --days 30

# Fast replay with 1-hour candles
python test_bot.py ema_cross --fast 50 --slow 200 --days 90 --granularity 1h --playback_speed 0.01

# Test with higher loss tolerance (2.5%)
python test_bot.py momentum --period 10 --loss_tolerance 2.5
```

## 💰 Live Trading

Live trading executes real trades on Coinbase using your API credentials.

### Setup

1. **Get Coinbase API Credentials**
   - Go to https://www.coinbase.com/settings/api
   - Create a new API key with trading permissions
   - Download the private key JSON file

2. **Create `secrets/secrets1.json`**
```json
{
  "coinbase_api_key_name": "organizations/xxx/apiKeys/xxx",
  "coinbase_api_private_key": "-----BEGIN EC PRIVATE KEY-----\n...\n-----END EC PRIVATE KEY-----"
}
```

**Note:** For multiple parallel bots, create `secrets/secrets2.json`, `secrets/secrets3.json`, etc.

3. **Run Live Bot**
```bash
python live_bot.py <strategy> [options]
```

### Live Bot Options
- `--instance N` - Bot instance number for parallel bots (default: 1)
- `--fee_rate N` - Fee rate as decimal (default: 0.00025 = 0.025%)
- `--loss_tolerance N` - Max acceptable loss as decimal (default: 0.0)
- `--granularity G` - Candle size: 1m, 5m, 15m, 1h (default: 1m)
- `--port N` - Dashboard port (default: 5003)
- `--history_hours N` - Hours of historical data to preload (default: 6)

### Safety Features
- **Confirmation Required**: Must type 'YES' to start trading
- **Baseline Protection**: Never takes a loss below starting position
- **Balance Sync**: Verifies bot state matches exchange balances
- **Order Timeout**: Cancels unfilled orders after 5 minutes
- **Graceful Shutdown**: Ctrl+C stops monitoring safely (keeps positions)

### Examples
```bash
# Conservative EMA(50/200) with no loss tolerance
python live_bot.py ema_cross --fast 50 --slow 200 --loss_tolerance 0.0

# Aggressive Momentum with 0.5% loss tolerance
python live_bot.py momentum --period 10 --loss_tolerance 0.005

# Run on custom port
python live_bot.py ema_cross --fast 50 --slow 200 --port 8080

# Run multiple parallel bots (requires secrets/secrets2.json)
python live_bot.py ema_cross --fast 50 --slow 200 --instance 2 --port 5004
```

## 🔬 Backtesting

Backtest strategies with multiple parameter configurations and loss tolerance levels.

### Consolidated Backtester
```bash
python backtest_strategies.py
```

This tests:
- **19 base strategy configurations** across 7 strategy types
- **5 loss tolerance levels** (0%, 0.1%, 0.5%, 1.0%, 2.5%)
- **95 total test configurations** run in parallel
- Results saved to `backtest_results/` with timestamps

### Output
- **JSON file**: Machine-readable results with all metrics
- **TXT file**: Human-readable summary with:
  - Top 30 performing configurations
  - Best configuration per strategy type
  - Complete test parameters and metrics

### Legacy Backtests (in `old_backtests/`)
- `backtest_ai_strategies.py` - Test multiple strategies
- `backtest_loss_tolerance.py` - Test loss tolerance parameter
- `backtest_macd_params.py` - Test MACD parameter variations

## 📈 Available Strategies

### 1. EMA Cross
Exponential Moving Average crossover strategy.

**Best Configuration**: EMA(50/200) - 48.55% APY, 127.49% BTC APY

```bash
python test_bot.py ema_cross --fast 50 --slow 200
```

**Parameters:**
- `--fast N` - Fast EMA period (default: 9)
- `--slow N` - Slow EMA period (default: 21)

### 2. Momentum
Rate of Change (ROC) momentum strategy.

**Best Configuration**: Period 10, ±1.0% thresholds - 53.70% APY

```bash
python test_bot.py momentum --period 10 --buy_threshold 1.0 --sell_threshold -1.0
```

**Parameters:**
- `--period N` - ROC lookback period (default: 10)
- `--buy_threshold N` - Buy when ROC > N% (default: 1.0)
- `--sell_threshold N` - Sell when ROC < N% (default: -1.0)

### 3. MACD
Moving Average Convergence Divergence strategy with trajectory prediction.

```bash
python test_bot.py macd --fast_period 12 --slow_period 26 --signal_period 9
```

**Parameters:**
- `--fast_period N` - Fast EMA (default: 12)
- `--slow_period N` - Slow EMA (default: 26)
- `--signal_period N` - Signal line EMA (default: 9)
- `--min_slope_periods N` - Slope consistency check (default: 3)
- `--min_momentum_strength N` - Acceleration threshold (default: 2.0)

### 4. RSI
Relative Strength Index strategy.

```bash
python test_bot.py rsi --period 14 --oversold 30 --overbought 70
```

**Parameters:**
- `--period N` - RSI period (default: 14)
- `--oversold N` - Oversold threshold (default: 30)
- `--overbought N` - Overbought threshold (default: 70)

### 5. Bollinger Bands
Price channel breakout strategy.

```bash
python test_bot.py bollinger --period 20 --std_dev 2.0
```

**Parameters:**
- `--period N` - Moving average period (default: 20)
- `--std_dev N` - Standard deviation multiplier (default: 2.0)

### 6. Stochastic Oscillator
Momentum-based oscillator strategy.

```bash
python test_bot.py stochastic --k_period 14 --d_period 3 --oversold 20 --overbought 80
```

**Parameters:**
- `--k_period N` - %K period (default: 14)
- `--d_period N` - %D period (default: 3)
- `--oversold N` - Oversold level (default: 20)
- `--overbought N` - Overbought level (default: 80)

### 7. Mean Reversion
Statistical mean reversion strategy.

```bash
python test_bot.py mean_reversion --period 20 --buy_threshold -1.5 --sell_threshold 1.5
```

**Parameters:**
- `--period N` - Lookback period (default: 20)
- `--buy_threshold N` - Buy when price < mean + N*std (default: -1.5)
- `--sell_threshold N` - Sell when price > mean + N*std (default: 1.5)

## 📊 Web Dashboard

All bots (test and live) include a real-time web dashboard at **http://localhost:5003** (or custom `--port`).

### Features

#### Main Chart
- **Candlestick Chart**: Real-time price action with zoom/pan
- **Trade Markers**: Green triangles (buy), Red triangles (sell)
- **Configurable Indicators**:
  - Moving Averages: EMA (9, 12, 20, 26, 50, 100, 200), SMA (20, 50, 100, 200)
  - Bollinger Bands (20, 2)
  - Oscillators: RSI (14), Stochastic (14, 3)

#### MACD Subplot
- MACD line, Signal line, and Histogram
- Color-coded for trend direction

#### Bot State Sidebar
- **Current Position**: LONG (holding BTC) or SHORT (holding USD)
- **Live Balances**: USD and BTC holdings
- **Baseline Values**: Minimum acceptable amounts (never go below)
- **Current Price**: Latest candle close
- **Profit Zones**: Min profitable buy/sell prices

#### Trade History
- Chronological list of all executed trades
- Color-coded borders (green=buy, red=sell)
- Timestamps and prices

#### Log Windows
- Main application log
- Stream/exchange log
- Real-time updates

### Indicator Dropdown
Click "📊 Indicators" to enable/disable:
- EMA lines (multiple periods)
- SMA lines
- Bollinger Bands
- RSI
- Stochastic oscillator

Indicators auto-update every 10 candles and persist across chart interactions.

## 🏗️ Project Structure

```
.
├── README.md                          # This file
├── BOT_USAGE.md                       # Detailed bot usage guide
├── test_bot.py                        # Generic paper trading bot
├── live_bot.py                        # Generic live trading bot
├── backtest_strategies.py             # Consolidated backtester
├── trader_bot.py                      # Core Bot class
├── web_dashboard.py                   # Flask + SocketIO dashboard
├── backtest_lib.py                    # Backtesting framework
├── CBData.py                          # Coinbase data fetcher
├── secrets/                           # API credentials (not in git)
│   ├── secrets1.json                  # Instance 1 credentials
│   ├── secrets2.json                  # Instance 2 credentials (optional)
│   └── ...
├── logs/                              # Bot logs (not in git)
│   ├── bot_1_main.log                 # Instance 1 main log
│   ├── bot_1_stream.log               # Instance 1 stream log
│   └── ...
│
├── strategies/                        # Trading strategies
│   ├── README.md                      # Strategy documentation
│   ├── base.py                        # Abstract Strategy class
│   ├── ema_cross.py                   # EMA crossover
│   ├── momentum.py                    # ROC momentum
│   ├── macd.py                        # MACD with trajectory
│   ├── rsi.py                         # RSI
│   ├── bollinger.py                   # Bollinger Bands
│   ├── stochastic.py                  # Stochastic Oscillator
│   └── mean_reversion.py              # Mean Reversion
│
├── interfaces/                        # Exchange interfaces
│   ├── PaperTradingInterface.py       # Simulated trading
│   └── CoinbaseAdvancedTradeInterface.py  # Coinbase API
│
├── templates/                         # Dashboard HTML
│   └── dashboard.html
│
├── backtest_results/                  # Backtest output files
│   ├── backtest_strategies_*.json     # Results data
│   └── backtest_strategies_*.txt      # Human-readable summaries
│
└── old_bots/                          # Legacy bot scripts
    └── old_backtests/                 # Legacy backtest scripts
```

## 🔧 Creating Custom Strategies

See `strategies/README.md` for detailed instructions.

### Quick Example

1. Create file in `strategies/` directory:

```python
from typing import List, Tuple
from .base import Strategy

class MyStrategy(Strategy):
    def __init__(self, bot, my_param: int = 10):
        super().__init__(bot)
        self.my_param = my_param
    
    @property
    def name(self):
        return f"MyStrategy({self.my_param})"
    
    def buy_signal(self, candles: List[Tuple]) -> bool:
        current_price = candles[-1][4]
        
        # Always check baseline first
        if not self.check_baseline_for_buy(current_price):
            return False
        
        # Your technical analysis logic here
        # Return True to trigger buy, False otherwise
        return False
    
    def sell_signal(self, candles: List[Tuple]) -> bool:
        current_price = candles[-1][4]
        
        # Always check baseline first
        if not self.check_baseline_for_sell(current_price):
            return False
        
        # Your technical analysis logic here
        # Return True to trigger sell, False otherwise
        return False
    
    def explain(self) -> List[str]:
        return [
            f"🎯 {self.name}",
            "   • Your strategy description here",
            "   • Buy when: ...",
            "   • Sell when: ...",
        ]
```

2. Add to `strategies/__init__.py`:
```python
from .my_strategy import MyStrategy
__all__ = ['Strategy', 'MyStrategy', ...]
```

3. Register in bot scripts:
```python
# In test_bot.py and live_bot.py
STRATEGIES = {
    'my_strategy': MyStrategy,
    # ... other strategies
}
```

4. Test it:
```bash
python test_bot.py my_strategy --my_param 20
```

## 📝 Troubleshooting

### Port Already in Use
```bash
# Kill process on port 5003
lsof -ti:5003 | xargs kill -9

# Or use a different port
python test_bot.py ema_cross --fast 50 --slow 200 --port 5004
```

### API Rate Limits
Historical data fetching may take 20-30 seconds for large date ranges due to Coinbase API rate limits. The system automatically handles this with delays.

### Balance Sync Errors
If bot balances don't match exchange:
- Check for pending orders on Coinbase
- Verify you're starting with either USD or BTC, not both
- Check `asset_tolerance` in the interface configuration

## ⚠️ Disclaimer

This software is for **educational purposes only**. Use at your own risk.

- **Not Financial Advice**: This is not investment advice. Cryptocurrency trading carries significant risk.
- **No Warranty**: The software is provided "as is" without warranty of any kind.
- **Real Money**: Live trading uses real money. Always test thoroughly in paper trading mode first.
- **Losses Possible**: Despite baseline protection, market conditions can change rapidly.

## 📄 License

Educational purposes only. See LICENSE file for details.

## 🤝 Contributing

Contributions welcome! To add a new strategy:

1. Create strategy file in `strategies/`
2. Implement `buy_signal()`, `sell_signal()`, `name`, and `explain()`
3. Add to `strategies/__init__.py`
4. Register in `STRATEGIES` dict in bot scripts
5. Test thoroughly
6. Submit pull request

## 📚 Additional Documentation

- **`BOT_USAGE.md`**: Comprehensive bot usage guide with examples
- **`strategies/README.md`**: Detailed strategy development guide
- **`backtest_lib.py`**: Backtesting framework documentation (inline)

---

**Happy Trading! 🚀**

*Remember: Past performance does not guarantee future results.*
