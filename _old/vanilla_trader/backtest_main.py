#!/usr/bin/env python3
"""
Main Backtest Script - All Strategies

Tests multiple trading strategies including:
1. Best Greedy Strategies from previous backtests
2. New Greedy MACD variations
3. All non-greedy strategies (RSI, Bollinger, EMA, MACD, etc.)

Results are saved to: backtest_results/
"""

import multiprocessing as mp
import os
from datetime import datetime
from strategies.greedy_momentum import GreedyMomentumStrategy
from strategies.greedy_ema_cross import GreedyEMACrossStrategy
from strategies.greedy_macd import GreedyMACDStrategy
from strategies.rsi import RSIStrategy
from strategies.bollinger import BollingerStrategy
from strategies.ema_cross import EMACrossStrategy
from strategies.stochastic import StochasticStrategy
from strategies.mean_reversion import MeanReversionStrategy
from strategies.momentum import MomentumStrategy
from strategies.macd import MACDStrategy
from backtest_lib import load_historical_data, parallel_backtest_runner
import json

# Create backtest results directory if it doesn't exist
RESULTS_DIR = 'backtest_results'
os.makedirs(RESULTS_DIR, exist_ok=True)

# How many days in the past the test period should END
# 0 = end now, 90 = end 90 days ago (so 3-month test would be 6-3 months ago)
AGE_DAYS = 180
DAYS = 180

GRANULARITY = '1m'

def main():
    print("=" * 80)
    print("🧪 MAIN BACKTEST - ALL STRATEGIES")
    print("=" * 80)
    print()
    
    # Test parameters
    starting_currency = 1000.0
    months = DAYS // 30  # Approximate number of months
    
    # Define loss tolerance values to test for each strategy
    loss_tolerances = [
        0.000,  # 0.0% - never take a loss (baseline)
        0.001,  # 0.1%
        0.005,  # 0.5%
        0.010,  # 1.0%
        0.025,  # 2.5%
    ]
    
    # Load historical data once (shared across all tests)
    import time
    start_load = time.time()
    candles = load_historical_data(months=months, granularity=GRANULARITY, age_days=AGE_DAYS)
    load_time = time.time() - start_load
    print(f"⏱️  Data loading took {load_time:.1f} seconds")
    print()
    
    # Define parameter combinations to test
    base_configs = []
    
    # ============================================================================
    # NON-GREEDY STRATEGIES
    # ============================================================================
    
    # RSI Strategy configurations
    print("📊 RSI Strategy:")
    rsi_configs = [
        {'period': 14, 'oversold': 30, 'overbought': 70},  # Classic RSI
        {'period': 14, 'oversold': 20, 'overbought': 80},  # More extreme
        {'period': 9, 'oversold': 30, 'overbought': 70},   # Faster
    ]
    for config in rsi_configs:
        base_configs.append({
            'strategy_class': RSIStrategy,
            'strategy_params': config,
            'name': f"RSI({config['period']}, {config['oversold']}/{config['overbought']})"
        })
        print(f"  • {base_configs[-1]['name']}")
    print()
    
    # Bollinger Bands configurations
    print("📊 Bollinger Bands Strategy:")
    bb_configs = [
        {'period': 20, 'std_dev': 2.0},   # Classic
        {'period': 20, 'std_dev': 1.5},   # Tighter
        {'period': 10, 'std_dev': 2.0},   # Faster
    ]
    for config in bb_configs:
        base_configs.append({
            'strategy_class': BollingerStrategy,
            'strategy_params': config,
            'name': f"Bollinger({config['period']}, {config['std_dev']}σ)"
        })
        print(f"  • {base_configs[-1]['name']}")
    print()
    
    # EMA Crossover configurations
    print("📊 EMA Crossover Strategy:")
    ema_configs = [
        {'fast': 9, 'slow': 21},    # Short-term
        {'fast': 9, 'slow': 26},    # Default on coinbase
        {'fast': 12, 'slow': 26},   # MACD-like
        {'fast': 50, 'slow': 200},  # Golden cross
    ]
    for config in ema_configs:
        base_configs.append({
            'strategy_class': EMACrossStrategy,
            'strategy_params': config,
            'name': f"EMA({config['fast']}/{config['slow']})"
        })
        print(f"  • {base_configs[-1]['name']}")
    print()
    
    # Stochastic Oscillator configurations
    print("📊 Stochastic Strategy:")
    stoch_configs = [
        {'k_period': 14, 'd_period': 3, 'oversold': 20, 'overbought': 80},  # Classic
        {'k_period': 5, 'd_period': 3, 'oversold': 20, 'overbought': 80},   # Fast
    ]
    for config in stoch_configs:
        base_configs.append({
            'strategy_class': StochasticStrategy,
            'strategy_params': config,
            'name': f"Stochastic({config['k_period']},{config['d_period']})"
        })
        print(f"  • {base_configs[-1]['name']}")
    print()
    
    # Mean Reversion configurations
    print("📊 Mean Reversion Strategy:")
    mr_configs = [
        {'period': 20, 'buy_threshold': -1.5, 'sell_threshold': 1.5},  # Moderate
        {'period': 20, 'buy_threshold': -2.0, 'sell_threshold': 2.0},  # Wide
    ]
    for config in mr_configs:
        base_configs.append({
            'strategy_class': MeanReversionStrategy,
            'strategy_params': config,
            'name': f"MeanRev({config['period']}, {config['buy_threshold']}σ)"
        })
        print(f"  • {base_configs[-1]['name']}")
    print()
    
    # Momentum configurations
    print("📊 Momentum Strategy:")
    mom_configs = [
        {'period': 10, 'buy_threshold': 2.0, 'sell_threshold': -2.0},   # Moderate
        {'period': 10, 'buy_threshold': 1.0, 'sell_threshold': -1.0},   # Sensitive
    ]
    for config in mom_configs:
        base_configs.append({
            'strategy_class': MomentumStrategy,
            'strategy_params': config,
            'name': f"Momentum({config['period']}, {config['buy_threshold']}%)"
        })
        print(f"  • {base_configs[-1]['name']}")
    print()
    
    # MACD configurations
    print("📊 MACD Strategy:")
    macd_configs = [
        {'fast_period': 12, 'slow_period': 26, 'signal_period': 9,
         'min_slope_periods': 3, 'min_momentum_strength': 2.0,
         'trajectory_threshold': 0.7, 'sharp_reversal_multiplier': 3.0},  # Default
        {'fast_period': 8, 'slow_period': 17, 'signal_period': 9,
         'min_slope_periods': 3, 'min_momentum_strength': 2.0,
         'trajectory_threshold': 0.7, 'sharp_reversal_multiplier': 3.0},  # Faster
    ]
    for config in macd_configs:
        base_configs.append({
            'strategy_class': MACDStrategy,
            'strategy_params': config,
            'name': f"MACD({config['fast_period']},{config['slow_period']},{config['signal_period']})"
        })
        print(f"  • {base_configs[-1]['name']}")
    print()
    
    # ============================================================================
    # GREEDY STRATEGIES
    # ============================================================================
    
    # Best Greedy Momentum (from previous results)
    print("📊 Best Greedy Momentum (59.3% APY from previous backtest):")
    base_configs.append({
        'strategy_class': GreedyMomentumStrategy,
        'strategy_params': {
            'period': 14,
            'buy_threshold': 2.0,
            'sell_threshold': -2.0,
            'profit_margin': 1.0,
            'patience_candles': 288
        },
        'name': "GreedyMom(p=14, patience=288, margin=1.0%)"
    })
    print(f"  • {base_configs[-1]['name']}")
    print()
    
    # Best Greedy EMA Cross (from previous results)
    print("📊 Best Greedy EMA Cross:")
    # Top EMA 9/21: 30.3% APY with 0.10% loss tolerance
    base_configs.append({
        'strategy_class': GreedyEMACrossStrategy,
        'strategy_params': {
            'fast': 9,
            'slow': 21,
            'profit_margin': 1.0,
            'patience_candles': 144
        },
        'name': "GreedyEMA(9/21, patience=144, margin=1.0%)"
    })
    print(f"  • {base_configs[-1]['name']} (30.3% APY from previous)")
    
    # Top EMA 12/26: 29.4% APY
    base_configs.append({
        'strategy_class': GreedyEMACrossStrategy,
        'strategy_params': {
            'fast': 12,
            'slow': 26,
            'profit_margin': 1.0,
            'patience_candles': 144
        },
        'name': "GreedyEMA(12/26, patience=144, margin=1.0%)"
    })
    print(f"  • {base_configs[-1]['name']} (29.4% APY from previous)")
    print()
    
    # Greedy MACD Variations
    print("📊 Greedy MACD Strategy:")
    # Test different MACD configurations
    greedy_macd_configs = [
        (12, 26, 9),   # Standard MACD
        (8, 17, 9),    # Faster MACD
        (5, 13, 5),    # Very fast MACD
    ]
    
    # Different patience levels for MACD
    # 144 = 12 hours, 288 = 1 day, 576 = 2 days
    greedy_macd_patience = [144, 288, 576]
    
    # Different profit margins for greedy MACD
    greedy_macd_margins = [0.5, 0.75, 1.0, 1.25]
    
    # Generate all MACD combinations
    for fast, slow, signal in greedy_macd_configs:
        for patience in greedy_macd_patience:
            for margin in greedy_macd_margins:
                base_configs.append({
                    'strategy_class': GreedyMACDStrategy,
                    'strategy_params': {
                        'fast_period': fast,
                        'slow_period': slow,
                        'signal_period': signal,
                        'profit_margin': margin,
                        'patience_candles': patience
                    },
                    'name': f"GreedyMACD({fast}/{slow}/{signal}, patience={patience}, margin={margin}%)"
                })
    greedy_macd_count = len(greedy_macd_configs) * len(greedy_macd_patience) * len(greedy_macd_margins)
    print(f"  • {greedy_macd_count} Greedy MACD variations")
    print()
    
    # Create full test configurations (base configs × loss tolerances)
    test_configs = []
    for base in base_configs:
        for loss_tol in loss_tolerances:
            test_configs.append({
                'strategy_class': base['strategy_class'],
                'strategy_params': base['strategy_params'],
                'loss_tolerance': loss_tol,
                'strategy_name': base['name'],
                'loss_tolerance_pct': loss_tol * 100
            })
    
    print(f"📊 Total Summary:")
    print(f"   • Base strategies: {len(base_configs)}")
    print(f"   • Loss tolerance values: {len(loss_tolerances)}")
    print(f"   • Total test configurations: {len(test_configs)}")
    print(f"   • Starting capital: ${starting_currency:.2f}")
    print()
    
    # Run backtests in parallel with progress bar
    print(f"🚀 Running {len(test_configs)} backtests in parallel...")
    print()
    
    start_time = time.time()
    results = parallel_backtest_runner(
        candles=candles,
        test_configs=test_configs,
        starting_currency=starting_currency,
        fee_rate=0.006,
        pair="BTC-USD",
        min_candles=50,
        months=months
    )
    elapsed_time = time.time() - start_time
    
    print()
    print("✅ All tests complete!")
    print()
    print(f"⏱️  Total backtest time: {elapsed_time:.1f} seconds")
    print(f"⚡ Average time per test: {elapsed_time/len(test_configs):.1f} seconds")
    print()
    
    # Sort results by Real APY
    successful_results = [r for r in results if r.get('success', False)]
    failed_results = [r for r in results if not r.get('success', False)]
    successful_results.sort(key=lambda x: x.get('real_apy', 0), reverse=True)
    
    if not successful_results:
        print("❌ No successful backtests completed")
        return
    
    # Print results table
    print("=" * 180)
    print("📈 TOP 30 PERFORMERS")
    print("=" * 180)
    print()
    
    print(f"{'Rank':<6} {'Strategy':<40} {'Loss Tol':<10} {'Real_APY':<10} {'BTC_APY':<10} "
          f"{'Trades':<8} {'Win%':<8} {'Avg$/Trade':<12} {'Final$':<12} {'Idle':<12} {'Pos':<6}")
    print("-" * 180)
    
    for i, result in enumerate(successful_results[:30], 1):
        print(f"{i:<6} {result.get('strategy_name', 'Unknown'):<40} {result.get('loss_tolerance_pct', 0):>6.2f}%   "
              f"{result.get('real_apy', 0):>7.2f}%   {result.get('apy_btc', 0):>7.2f}%   "
              f"{result.get('trades', 0):>6}   {result.get('win_rate', 0):>6.1f}%  "
              f"${result.get('avg_profit_per_trade', 0):>9.2f}   ${result.get('current_portfolio_usd', 0):>10.2f}  "
              f"{result.get('final_position', 'unknown').upper():<6}")
    
    print()
    
    if failed_results:
        print(f"❌ Failed tests: {len(failed_results)}")
        print()
    
    # Find best result
    best = successful_results[0]
    print("=" * 80)
    print("🏆 BEST PERFORMING CONFIGURATION")
    print("=" * 80)
    print(f"Strategy:                {best.get('strategy_name', 'Unknown')}")
    print(f"Loss Tolerance:          {best.get('loss_tolerance_pct', 0):.2f}%")
    print()
    print(f"Real APY (USD):          {best.get('real_apy', 0):.2f}%")
    print(f"BTC APY:                 {best.get('apy_btc', 0):.2f}%")
    print(f"Value Return:            {best.get('value_return_pct', 0):.2f}%")
    print(f"BTC Return:              {best.get('btc_return_pct', 0):.2f}%")
    print()
    print(f"Initial USD Baseline:    ${best.get('initial_usd_baseline', 0):.2f}")
    print(f"Final USD Baseline:      ${best.get('final_usd_baseline', 0):.2f}")
    print(f"Initial BTC Baseline:    {best.get('initial_crypto_baseline', 0):.8f} BTC")
    print(f"Final BTC Baseline:      {best.get('final_crypto_baseline', 0):.8f} BTC")
    print()
    print(f"Starting Value:          ${starting_currency:.2f}")
    print(f"Current Value:           ${best.get('current_portfolio_usd', 0):.2f}")
    print(f"Total Profit:            ${best.get('current_portfolio_usd', 0) - starting_currency:.2f}")
    print(f"Total Trades:            {best.get('trades', 0)}")
    print(f"Win Rate:                {best.get('win_rate', 0):.1f}% ({best.get('wins', 0)} wins, {best.get('losses', 0)} losses)")
    print(f"Avg Profit/Trade:        ${best.get('avg_profit_per_trade', 0):.2f}")
    print(f"Longest Idle Time:       {best.get('longest_idle_time', 'N/A')}")
    print(f"Final Position:          {best.get('final_position', 'unknown').upper()}")
    print()
    
    # Save results to JSON
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    json_file = os.path.join(RESULTS_DIR, f"backtest_main_{timestamp}.json")
    with open(json_file, 'w') as f:
        json.dump({
            'test_config': {
                'starting_currency': starting_currency,
                'months': months,
                'granularity': GRANULARITY,
                'candles': len(candles),
                'num_strategies': len(base_configs),
                'loss_tolerances': loss_tolerances,
                'total_tests': len(test_configs),
                'test_date': datetime.now().isoformat(),
                'elapsed_time': elapsed_time
            },
            'results': successful_results,
            'failed': failed_results
        }, f, indent=2)
    
    # Save human-readable summary
    summary_file = os.path.join(RESULTS_DIR, f"backtest_main_{timestamp}.txt")
    with open(summary_file, 'w') as f:
        f.write("=" * 80 + "\n")
        f.write("MAIN BACKTEST - ALL STRATEGIES SUMMARY\n")
        f.write("=" * 80 + "\n\n")
        
        f.write("TEST CONFIGURATION:\n")
        f.write(f"  Starting Capital:   ${starting_currency:,.2f}\n")
        f.write(f"  Test Period:        {months} months\n")
        f.write(f"  Granularity:        {GRANULARITY}\n")
        f.write(f"  Total Candles:      {len(candles)}\n")
        f.write(f"  Base Strategies:    {len(base_configs)}\n")
        f.write(f"  Loss Tolerances:    {len(loss_tolerances)}\n")
        f.write(f"  Total Tests:        {len(test_configs)}\n")
        f.write(f"  Test Date:          {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"  Elapsed Time:       {elapsed_time:.1f} seconds\n")
        f.write(f"  Successful Tests:   {len(successful_results)}\n")
        f.write(f"  Failed Tests:       {len(failed_results)}\n\n")
        
        f.write("LOSS TOLERANCE VALUES TESTED:\n")
        for lt in loss_tolerances:
            f.write(f"  • {lt * 100:.2f}%\n")
        f.write("\n")
        
        f.write("TOP 50 PERFORMING CONFIGURATIONS:\n")
        f.write("=" * 180 + "\n")
        f.write(f"{'Rank':<6} {'Strategy':<40} {'Loss Tol':<10} {'Real_APY':<10} {'BTC_APY':<10} "
               f"{'Trades':<8} {'Win%':<8} {'Avg$/Trade':<12} {'Idle':<12} {'Pos':<6}\n")
        f.write("-" * 180 + "\n")
        
        for i, result in enumerate(successful_results[:50], 1):
            f.write(f"{i:<6} {result.get('strategy_name', 'Unknown'):<40} {result.get('loss_tolerance_pct', 0):>6.2f}%   "
                   f"{result.get('real_apy', 0):>7.2f}%   {result.get('apy_btc', 0):>7.2f}%   "
                   f"{result.get('trades', 0):<8} {result.get('win_rate', 0):>6.1f}%  "
                   f"${result.get('avg_profit_per_trade', 0):>9.2f}  {result.get('longest_idle_time', 'N/A'):<12} "
                   f"{result.get('final_position', 'unknown').upper():<6}\n")
        f.write("\n" + "=" * 80 + "\n")
        f.write("BEST PERFORMING CONFIGURATION:\n")
        f.write("=" * 80 + "\n")
        f.write(f"Strategy:                {best.get('strategy_name', 'Unknown')}\n")
        f.write(f"Loss Tolerance:          {best.get('loss_tolerance_pct', 0):.2f}%\n\n")
        f.write(f"Real APY (USD):          {best.get('real_apy', 0):.2f}%\n")
        f.write(f"BTC APY:                 {best.get('apy_btc', 0):.2f}%\n")
        f.write(f"Value Return:            {best.get('value_return_pct', 0):.2f}%\n")
        f.write(f"BTC Return:              {best.get('btc_return_pct', 0):.2f}%\n\n")
        f.write(f"Initial USD Baseline:    ${best.get('initial_usd_baseline', 0):,.2f}\n")
        f.write(f"Final USD Baseline:      ${best.get('final_usd_baseline', 0):,.2f}\n")
        f.write(f"Initial BTC Baseline:    {best.get('initial_crypto_baseline', 0):.8f} BTC\n")
        f.write(f"Final BTC Baseline:      {best.get('final_crypto_baseline', 0):.8f} BTC\n\n")
        f.write(f"Starting Value:          ${starting_currency:,.2f}\n")
        f.write(f"Current Value:           ${best.get('current_portfolio_usd', 0):,.2f}\n")
        f.write(f"Total Profit:            ${best.get('current_portfolio_usd', 0) - starting_currency:,.2f}\n")
        f.write(f"Total Trades:            {best.get('trades', 0)}\n")
        f.write(f"Win Rate:                {best.get('win_rate', 0):.1f}% ({best.get('wins', 0)} wins, {best.get('losses', 0)} losses)\n")
        f.write(f"Avg Profit/Trade:        ${best.get('avg_profit_per_trade', 0):,.2f}\n")
        f.write(f"Longest Idle Time:       {best.get('longest_idle_time', 'N/A')}\n")
        f.write(f"Final Position:          {best.get('final_position', 'unknown').upper()}\n")
        
        # Add breakdown by strategy type
        f.write("\n" + "=" * 80 + "\n")
        f.write("BEST CONFIGURATION PER STRATEGY:\n")
        f.write("=" * 80 + "\n")
        
        # Group results by base strategy name (without loss tolerance)
        strategy_best = {}
        for strategy_name in sorted(strategy_best.keys()):
            result = strategy_best[strategy_name]
            f.write(f"\n{strategy_name}:\n")
            f.write(f"  Best Loss Tolerance: {result.get('loss_tolerance_pct', 0):.2f}%\n")
            f.write(f"  Real APY (USD):     {result.get('real_apy', 0):.2f}%\n")
            f.write(f"  BTC APY:            {result.get('apy_btc', 0):.2f}%\n")
            f.write(f"  Trades:             {result.get('trades', 0)}\n")
            f.write(f"  Win Rate:           {result.get('win_rate', 0):.1f}%\n")
            f.write(f"  Longest Idle:       {result.get('longest_idle_time', 'N/A')}\n")
    
    print(f"📁 Results saved to:")
    print(f"   JSON: {json_file}")
    print(f"   Summary: {summary_file}")
    print()


if __name__ == '__main__':
    # Set start method for multiprocessing (required on macOS)
    mp.set_start_method('spawn', force=True)
    main()
