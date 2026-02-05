# Backtest Results

This directory contains output files from strategy backtests.

## File Types

### JSON Files (`backtest_strategies_*.json`)
Raw backtest results data for programmatic analysis:
- Strategy configurations
- Trade history
- Performance metrics
- Portfolio values over time

### Text Files (`backtest_strategies_*.txt`)
Human-readable summaries:
- APY calculations
- BTC-denominated returns
- Win rates
- Trade counts
- Best/worst performers

## Usage

Run backtests from the vanilla_trader directory:

```bash
cd vanilla_trader
python backtest_main.py
```

Results will be automatically saved here with timestamps.

## Example Output

```
Strategy: EMA(50/200)
Days: 365, Loss Tolerance: 0.0%
---------------------------------
Final Value: $1,485.50
APY: 48.55%
BTC APY: 127.49%
Trades: 24 (58% winners)
Max Drawdown: 8.2%
```
