# Trading Bot System

A modular algorithmic trading bot system with paper trading and live trading capabilities.

## Quick Start

### Paper Trading (Test Mode)
Test strategies on historical data with no risk:

```bash
# Test EMA(50/200) Golden Cross strategy
python test_bot.py ema_cross --fast 50 --slow 200 --days 10

# Test Momentum strategy  
python test_bot.py momentum --period 10 --buy_threshold 1.0 --sell_threshold -1.0

# Test with custom settings
python test_bot.py ema_cross --fast 9 --slow 26 --days 30 --granularity 15m --port 5004
```

### Live Trading (Real Money)
⚠️ **WARNING: Trades with REAL MONEY on Coinbase!**

```bash
# Live trade with EMA(50/200) strategy
python live_bot.py ema_cross --fast 50 --slow 200

# Live trade with Momentum strategy
python live_bot.py momentum --period 10 --buy_threshold 1.0 --sell_threshold -1.0
```

## Available Strategies

### 1. EMA Cross
Exponential Moving Average crossover strategy.

**Parameters:**
- `--fast N`: Fast EMA period (default: 9)
- `--slow N`: Slow EMA period (default: 21)

**Trading Logic:**
- **BUY**: When fast EMA crosses above slow EMA (Golden Cross)
- **SELL**: When fast EMA crosses below slow EMA (Death Cross)

**Best Configuration:**
- EMA(50/200): 48.55% APY, 127.49% BTC APY

```bash
python test_bot.py ema_cross --fast 50 --slow 200
```

### 2. Momentum
Rate of Change (ROC) momentum strategy.

**Parameters:**
- `--period N`: ROC lookback period (default: 10)
- `--buy_threshold N`: Buy when ROC > N% (default: 1.0)
- `--sell_threshold N`: Sell when ROC < N% (default: -1.0)

**Trading Logic:**
- **BUY**: When momentum crosses above buy threshold
- **SELL**: When momentum crosses below sell threshold

**Best Configuration:**
- Period 10, Buy +1.0%, Sell -1.0%: 53.70% APY

```bash
python test_bot.py momentum --period 10 --buy_threshold 1.0 --sell_threshold -1.0
```

### 3. MACD
Moving Average Convergence Divergence strategy.

**Parameters:**
- `--short_window N`: Short EMA period (default: 12)
- `--long_window N`: Long EMA period (default: 26)
- `--signal_window N`: Signal line period (default: 9)

### 4. RSI
Relative Strength Index strategy.

**Parameters:**
- `--period N`: RSI period (default: 14)
- `--oversold N`: Oversold threshold (default: 30)
- `--overbought N`: Overbought threshold (default: 70)

## Test Bot Options

```bash
python test_bot.py <strategy> [options]

Options:
  --days N              Number of days of historical data (default: 10)
  --granularity G       Candle size: 1m, 5m, 15m, 1h, 6h, 1d (default: 5m)
  --starting_currency N Starting USD balance (default: 1000.0)
  --fee_rate N          Fee rate as percentage (default: 0.025)
  --loss_tolerance N    Max acceptable loss % (default: 0.0)
  --playback_speed N    Replay speed multiplier (default: 0.05)
  --port N              Dashboard port (default: 5003)
```

## Live Bot Options

```bash
python live_bot.py <strategy> [options]

Options:
  --fee_rate N          Fee rate as decimal (default: 0.00025 = 0.025% VIP)
  --loss_tolerance N    Max acceptable loss as decimal (default: 0.0)
  --granularity G       Candle size: 1m, 5m, 15m, 1h (default: 1m)
  --port N              Dashboard port (default: 5003)
  --history_hours N     Hours of historical data to preload (default: 6)
```

## Live Trading Setup

1. **Get Coinbase API Credentials**
   - Go to https://www.coinbase.com/settings/api
   - Create a new API key with trading permissions
   - Download the private key

2. **Create secrets.json**
   ```json
   {
     "coinbase_api_key_name": "your_key_name",
     "coinbase_api_private_key": "-----BEGIN EC PRIVATE KEY-----\n...\n-----END EC PRIVATE KEY-----"
   }
   ```

3. **Run Live Bot**
   ```bash
   python live_bot.py ema_cross --fast 50 --slow 200
   ```

## Web Dashboard

All bots (test and live) include a real-time web dashboard:

- **URL**: http://localhost:5003 (or custom port with `--port`)
- **Features**:
  - Real-time candlestick chart with indicators
  - MACD subplot
  - Live bot state (position, balance, baselines)
  - Trade history with markers
  - Log windows (main + stream)
  - Configurable technical indicators (EMA, SMA, BB, RSI, Stochastic)

## Technical Indicators

The dashboard includes a comprehensive indicator system:

### Moving Averages
- EMA: 9, 12, 20, 26, 50, 100, 200 periods
- SMA: 20, 50, 100, 200 periods

### Bands
- Bollinger Bands (20, 2)

### Oscillators
- RSI (14)
- Stochastic (14, 3)

Use the dropdown menu in the dashboard to enable/disable indicators.

## Architecture

```
.
├── test_bot.py              # Generic paper trading bot
├── live_bot.py              # Generic live trading bot
├── trader_bot.py            # Core Bot class
├── strategies/              # Trading strategies
│   ├── base.py             # Base Strategy class
│   ├── ema_cross.py        # EMA crossover
│   ├── momentum.py         # ROC momentum
│   ├── macd.py             # MACD
│   └── rsi.py              # RSI
├── interfaces/              # Exchange interfaces
│   ├── PaperTradingInterface.py
│   └── CoinbaseAdvancedTradeInterface.py
├── web_dashboard.py         # Flask + SocketIO dashboard
└── old_bots/               # Legacy bot scripts
```

## Safety Features

1. **Baseline Protection**: Never takes a loss below starting baseline
2. **Loss Tolerance**: Configurable acceptable loss percentage
3. **Fee Validation**: Verifies exchange fees match expectations
4. **Order Timeout**: Cancels unfilled orders after 5 minutes
5. **Balance Sync**: Validates bot state matches exchange balances

## Examples

### Test Multiple Strategies
```bash
# Test EMA(9/26) with 30 days of data
python test_bot.py ema_cross --fast 9 --slow 26 --days 30

# Test Momentum with aggressive thresholds
python test_bot.py momentum --period 5 --buy_threshold 2.0 --sell_threshold -2.0

# Test with high loss tolerance (risky!)
python test_bot.py ema_cross --fast 50 --slow 200 --loss_tolerance 1.0
```

### Live Trading Scenarios
```bash
# Conservative EMA(50/200) with no loss tolerance
python live_bot.py ema_cross --fast 50 --slow 200 --loss_tolerance 0.0

# Aggressive Momentum with 0.5% loss tolerance
python live_bot.py momentum --period 10 --buy_threshold 1.0 --sell_threshold -1.0 --loss_tolerance 0.005

# Run on custom port if 5003 is busy
python live_bot.py ema_cross --fast 50 --slow 200 --port 8080
```

## Troubleshooting

### Port Already in Use
```bash
# Kill process on port 5003
lsof -ti:5003 | xargs kill -9

# Or use a different port
python test_bot.py ema_cross --fast 50 --slow 200 --port 5004
```

### API Rate Limits
The bots automatically handle Coinbase API rate limits with delays. Historical data fetching may take 20-30 seconds for large date ranges.

### Balance Sync Errors
If bot balances don't match exchange:
- Check for pending orders on Coinbase
- Verify you're starting with either USD or BTC, not both
- Adjust tolerance with `asset_tolerance` in the interface

## Performance Notes

- **EMA(50/200)**: Best for catching major trends, few trades (13 in 3 months)
- **Momentum**: Best overall returns (53.70% APY), more trades
- **Lower granularity** (1m, 5m) = faster signals, more trades, higher fees
- **Higher granularity** (1h, 6h) = slower signals, fewer trades, catches bigger moves

## Contributing

To add a new strategy:

1. Create file in `strategies/` inheriting from `Strategy`
2. Implement `buy_signal()` and `sell_signal()` methods
3. Add `name` property and `explain()` method
4. Register in `strategies/__init__.py`
5. Add to `STRATEGIES` dict in `test_bot.py` and `live_bot.py`

## License

Educational purposes only. Use at your own risk. Not financial advice.
