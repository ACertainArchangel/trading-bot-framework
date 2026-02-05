# Trading Framework

> **A Python framework for rapid prototyping, testing, visualization, and deployment of algorithmic trading strategies.**

---

## Features

- ** Simple Strategy Development** - Just implement `buy_signal()` and `sell_signal()`
- ** Built-in Indicators** - EMA, SMA, RSI, MACD, Bollinger Bands, and more
- ** Fast Backtesting** - Test strategies on months of historical data in seconds
- ** Paper Trading** - Validate with fake money and real market data
- ** Live Trading** - Deploy to Coinbase with one function call
- ** Web Dashboard** - Real-time charts and monitoring

---

## 📚 Documentation

Full documentation is in [framework/README.md](framework/README.md).

### Core Concepts

| Module | Purpose |
|--------|---------|
| `framework.Strategy` | Base class for all trading strategies |
| `framework.Candle` | OHLCV candlestick data structure |
| `framework.backtest()` | Run strategy on historical data |
| `framework.paper_trade()` | Test with fake money, real data |
| `framework.live_trade()` | Deploy with real money |
| `framework.indicators` | Technical indicators (EMA, RSI, etc.) |

---

## 🗂️ Project Structure

```
trading-framework/
├── framework/           # THE FRAMEWORK
│   ├── __init__.py      # Main exports
│   ├── README.md        # Full documentation
│   ├── core/            # Candle, signals
│   ├── strategies/      # Strategy base + examples
│   ├── indicators/      # Technical indicators
│   ├── data/            # Data fetching & streaming
│   ├── interfaces/      # Paper & live trading
│   ├── runners/         # Backtest, paper, live
│   └── dashboard/       # Web visualization
│
├── quickstart/          #   Ready-to-run examples
│   ├── custom_strategy.py      # Create your own strategy
│   ├── simulation.py           # Visual backtest with dashboard
│   ├── dynamic_allocation.py   # Advanced position sizing
│   ├── compare_strategies.py   # Compare multiple strategies
│   ├── inspect_real_account.py # Coinbase account inspector
│   └── trade_real_money.py     # Live trading with Coinbase
│
├── secrets/             # API credentials (gitignored)
│
└── _old/                # Legacy code (reference only)
```

---

## 🔧 Workflow

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  1. DEVELOP     │ ──▶ │  2. BACKTEST    │ ──▶ │  3. PAPER TRADE │
│  Create your    │     │  Test on        │     │  Validate with  │
│  Strategy class │     │  historical     │     │  real market    │
└─────────────────┘     │  data           │     │  fake money     │
                        └─────────────────┘     └────────┬────────┘
                                                         │
                                                         ▼
                                                ┌─────────────────┐
                                                │  4. LIVE TRADE  │
                                                │  Deploy with    │
                                                │  real money     │
                                                |  after checking |
                                                | your accounts   |
                                                └─────────────────┘
```

---

## ⚠️ Disclaimer

This framework is for **educational purposes only**. Trading cryptocurrencies involves significant risk. Never trade with money you can't afford to lose. Past performance does not guarantee future results. Again, this software is provided AS IS with NO WARRENTY of ANY KIND. PERIOD. PLEASE DO NOT COMPLAIN TO ME IF YOU LOST YOUR LIFE SAVINGS USING THIS.

---

## 📄 License

MIT License
