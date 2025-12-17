#!/usr/bin/env python3
"""
Consolidated Strategy Backtester

Tests multiple trading strategies with various parameters and loss tolerance settings.
Define strategies once and test them with different loss tolerance values.

Results are saved to: backtest_results/
"""

import multiprocessing as mp
import os
import sys
from datetime import datetime
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


def main():
    """
    Run backtests across multiple strategies with various loss tolerance values.
    """
    print("=" * 80)
    print("CONSOLIDATED STRATEGY BACKTESTER")
    print("=" * 80)
    print()
    
    # Test parameters
    starting_currency = 1000.0
    months = 3
    
    # Define loss tolerance values to test for each strategy
    loss_tolerances = [
        0.000,  # 0.0% - never take a loss (baseline)
        0.001,  # 0.1%
        0.005,  # 0.5%
        0.010,  # 1.0%
        0.025,  # 2.5%
    ]
    
    # Define base strategy configurations (without loss tolerance)
    # Each will be tested with all loss tolerance values
    base_strategies = []
    
    # RSI Strategy configurations
    print("📊 RSI Strategy:")
    rsi_configs = [
        {'period': 14, 'oversold': 30, 'overbought': 70},  # Classic RSI
        {'period': 14, 'oversold': 20, 'overbought': 80},  # More extreme
        {'period': 9, 'oversold': 30, 'overbought': 70},   # Faster
    ]
    for config in rsi_configs:
        base_strategies.append({
            'strategy_class': RSIStrategy,
            'strategy_params': config,
            'name': f"RSI({config['period']}, {config['oversold']}/{config['overbought']})"
        })
        print(f"  • {base_strategies[-1]['name']}")
    print()
    
    # Bollinger Bands configurations
    print("📊 Bollinger Bands Strategy:")
    bb_configs = [
        {'period': 20, 'std_dev': 2.0},   # Classic
        {'period': 20, 'std_dev': 1.5},   # Tighter
        {'period': 10, 'std_dev': 2.0},   # Faster
    ]
    for config in bb_configs:
        base_strategies.append({
            'strategy_class': BollingerStrategy,
            'strategy_params': config,
            'name': f"Bollinger({config['period']}, {config['std_dev']}σ)"
        })
        print(f"  • {base_strategies[-1]['name']}")
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
        base_strategies.append({
            'strategy_class': EMACrossStrategy,
            'strategy_params': config,
            'name': f"EMA({config['fast']}/{config['slow']})"
        })
        print(f"  • {base_strategies[-1]['name']}")
    print()
    
    # Stochastic Oscillator configurations
    print("📊 Stochastic Strategy:")
    stoch_configs = [
        {'k_period': 14, 'd_period': 3, 'oversold': 20, 'overbought': 80},  # Classic
        {'k_period': 5, 'd_period': 3, 'oversold': 20, 'overbought': 80},   # Fast
    ]
    for config in stoch_configs:
        base_strategies.append({
            'strategy_class': StochasticStrategy,
            'strategy_params': config,
            'name': f"Stochastic({config['k_period']},{config['d_period']})"
        })
        print(f"  • {base_strategies[-1]['name']}")
    print()
    
    # Mean Reversion configurations
    print("📊 Mean Reversion Strategy:")
    mr_configs = [
        {'period': 20, 'buy_threshold': -1.5, 'sell_threshold': 1.5},  # Moderate
        {'period': 20, 'buy_threshold': -2.0, 'sell_threshold': 2.0},  # Wide
    ]
    for config in mr_configs:
        base_strategies.append({
            'strategy_class': MeanReversionStrategy,
            'strategy_params': config,
            'name': f"MeanRev({config['period']}, {config['buy_threshold']}σ)"
        })
        print(f"  • {base_strategies[-1]['name']}")
    print()
    
    # Momentum configurations
    print("📊 Momentum Strategy:")
    mom_configs = [
        {'period': 10, 'buy_threshold': 2.0, 'sell_threshold': -2.0},   # Moderate
        {'period': 10, 'buy_threshold': 1.0, 'sell_threshold': -1.0},   # Sensitive
    ]
    for config in mom_configs:
        base_strategies.append({
            'strategy_class': MomentumStrategy,
            'strategy_params': config,
            'name': f"Momentum({config['period']}, {config['buy_threshold']}%)"
        })
        print(f"  • {base_strategies[-1]['name']}")
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
        base_strategies.append({
            'strategy_class': MACDStrategy,
            'strategy_params': config,
            'name': f"MACD({config['fast_period']},{config['slow_period']},{config['signal_period']})"
        })
        print(f"  • {base_strategies[-1]['name']}")
    print()
    
    # Create test configurations by combining strategies with loss tolerances
    test_configs = []
    for base_strategy in base_strategies:
        for loss_tolerance in loss_tolerances:
            test_configs.append({
                'strategy_class': base_strategy['strategy_class'],
                'strategy_params': base_strategy['strategy_params'],
                'loss_tolerance': loss_tolerance,
                'strategy_name': base_strategy['name'],
                'loss_tolerance_pct': loss_tolerance * 100
            })
    
    print(f"📊 Base strategies: {len(base_strategies)}")
    print(f"🛡️  Loss tolerance values: {len(loss_tolerances)}")
    print(f"🔢 Total test configurations: {len(test_configs)}")
    print(f"💰 Starting capital: ${starting_currency:.2f}")
    print()
    
    # Load historical data once (shared across all tests)
    import time
    start_load = time.time()
    candles = load_historical_data(months=months)
    load_time = time.time() - start_load
    print(f"⏱️  Data loading took {load_time:.1f} seconds")
    print()
    
    # Run backtests in parallel
    results = parallel_backtest_runner(
        test_configs=test_configs,
        candles=candles,
        starting_currency=starting_currency,
        fee_rate=0.025,
        pair="BTC-USD",
        min_candles=50,  # Safe minimum for all strategies
        months=months
    )
    
    # Sort results by USD APY
    successful_results = [r for r in results if r['success']]
    failed_results = [r for r in results if not r['success']]
    successful_results.sort(key=lambda x: x['apy_usd'], reverse=True)
    
    # Print results table
    print("=" * 150)
    print("RESULTS - TOP 20 PERFORMERS")
    print("=" * 150)
    print()
    
    print(f"{'Rank':<6} {'Strategy':<30} {'Loss Tol':<10} {'APY_USD':<10} {'APY_BTC':<10} "
          f"{'Baseline%':<10} {'Trades':<8} {'Win%':<8} {'Avg$/Trade':<12} {'Final$':<12} {'Pos':<6}")
    print("-" * 158)
    
    for i, result in enumerate(successful_results[:20], 1):
        print(f"{i:<6} {result['strategy_name']:<30} {result['loss_tolerance_pct']:>6.2f}%   "
              f"{result['apy_usd']:>7.2f}%   {result['apy_btc']:>7.2f}%   "
              f"{result['baseline_return_pct']:>7.2f}%   "
              f"{result['trades']:>6}   {result['win_rate']:>6.1f}%  "
              f"${result['avg_profit_per_trade']:>9.2f}   ${result['current_value']:>10.2f}  "
              f"{result['final_position'].upper():<6}")
    
    print()
    
    if failed_results:
        print(f"❌ Failed tests: {len(failed_results)}")
        print()
    
    # Find best result
    if successful_results:
        best = successful_results[0]
        print("=" * 80)
        print("🏆 BEST PERFORMING CONFIGURATION")
        print("=" * 80)
        print(f"Strategy:           {best['strategy_name']}")
        print(f"Loss Tolerance:     {best['loss_tolerance_pct']:.2f}%")
        print(f"APY (USD):          {best['apy_usd']:.2f}%")
        print(f"APY (BTC):          {best['apy_btc']:.2f}%")
        print(f"Value Return:       {best['value_return_pct']:.2f}%")
        print(f"Baseline Return:    {best['baseline_return_pct']:.2f}%")
        print(f"Final Baseline:     ${best['final_baseline']:.2f}")
        print(f"Starting Value:     ${starting_currency:.2f}")
        print(f"Current Value:      ${best['current_value']:.2f}")
        print(f"Total Profit:       ${best['current_value'] - starting_currency:.2f}")
        print(f"Total Trades:       {best['trades']}")
        print(f"Win Rate:           {best['win_rate']:.1f}% ({best['wins']} wins, {best['losses']} losses)")
        print(f"Avg Profit/Trade:   ${best['avg_profit_per_trade']:.2f}")
        print(f"Final Position:     {best['final_position'].upper()}")
        print()
        
        # Save results to JSON
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        json_file = os.path.join(RESULTS_DIR, f"backtest_strategies_{timestamp}.json")
        with open(json_file, 'w') as f:
            json.dump({
                'test_config': {
                    'starting_currency': starting_currency,
                    'months': months,
                    'granularity': '5m',
                    'candles': len(candles),
                    'num_strategies': len(base_strategies),
                    'loss_tolerances': loss_tolerances,
                    'total_tests': len(test_configs),
                    'test_date': datetime.now().isoformat()
                },
                'results': successful_results,
                'failed': failed_results
            }, f, indent=2)
        
        # Save human-readable summary
        summary_file = os.path.join(RESULTS_DIR, f"backtest_strategies_{timestamp}.txt")
        with open(summary_file, 'w') as f:
            f.write("=" * 80 + "\n")
            f.write("CONSOLIDATED STRATEGY BACKTEST - SUMMARY\n")
            f.write("=" * 80 + "\n\n")
            
            f.write("TEST CONFIGURATION:\n")
            f.write(f"  Starting Capital:   ${starting_currency:,.2f}\n")
            f.write(f"  Test Period:        {months} months\n")
            f.write(f"  Granularity:        5m\n")
            f.write(f"  Total Candles:      {len(candles)}\n")
            f.write(f"  Base Strategies:    {len(base_strategies)}\n")
            f.write(f"  Loss Tolerances:    {len(loss_tolerances)}\n")
            f.write(f"  Total Tests:        {len(test_configs)}\n")
            f.write(f"  Test Date:          {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"  Successful Tests:   {len(successful_results)}\n")
            f.write(f"  Failed Tests:       {len(failed_results)}\n\n")
            
            f.write("LOSS TOLERANCE VALUES TESTED:\n")
            for lt in loss_tolerances:
                f.write(f"  • {lt * 100:.2f}%\n")
            f.write("\n")
            
            f.write("TOP 30 PERFORMING CONFIGURATIONS:\n")
            f.write("=" * 158 + "\n")
            f.write(f"{'Rank':<6} {'Strategy':<30} {'Loss Tol':<10} {'APY_USD':<10} {'APY_BTC':<10} "
                   f"{'Trades':<8} {'Win%':<8} {'Avg$/Trade':<12} {'Pos':<6}\n")
            f.write("-" * 158 + "\n")
            
            for i, result in enumerate(successful_results[:30], 1):
                f.write(f"{i:<6} {result['strategy_name']:<30} {result['loss_tolerance_pct']:>6.2f}%   "
                       f"{result['apy_usd']:>7.2f}%   {result['apy_btc']:>7.2f}%   "
                       f"{result['trades']:<8} {result['win_rate']:>6.1f}%  "
                       f"${result['avg_profit_per_trade']:>9.2f}  {result['final_position'].upper():<6}\n")
            
            f.write("\n" + "=" * 80 + "\n")
            f.write("BEST PERFORMING CONFIGURATION:\n")
            f.write("=" * 80 + "\n")
            f.write(f"Strategy:           {best['strategy_name']}\n")
            f.write(f"Loss Tolerance:     {best['loss_tolerance_pct']:.2f}%\n")
            f.write(f"APY (USD):          {best['apy_usd']:.2f}%\n")
            f.write(f"APY (BTC):          {best['apy_btc']:.2f}%\n")
            f.write(f"Value Return:       {best['value_return_pct']:.2f}%\n")
            f.write(f"Baseline Return:    {best['baseline_return_pct']:.2f}%\n")
            f.write(f"Final Baseline:     ${best['final_baseline']:,.2f}\n")
            f.write(f"Starting Value:     ${starting_currency:,.2f}\n")
            f.write(f"Current Value:      ${best['current_value']:,.2f}\n")
            f.write(f"Total Profit:       ${best['current_value'] - starting_currency:,.2f}\n")
            f.write(f"Total Trades:       {best['trades']}\n")
            f.write(f"Win Rate:           {best['win_rate']:.1f}% ({best['wins']} wins, {best['losses']} losses)\n")
            f.write(f"Avg Profit/Trade:   ${best['avg_profit_per_trade']:,.2f}\n")
            f.write(f"Final Position:     {best['final_position'].upper()}\n")
            
            # Add breakdown by strategy
            f.write("\n" + "=" * 80 + "\n")
            f.write("BEST CONFIGURATION PER STRATEGY:\n")
            f.write("=" * 80 + "\n")
            
            # Group results by base strategy name
            strategy_best = {}
            for result in successful_results:
                base_name = result['strategy_name']
                if base_name not in strategy_best:
                    strategy_best[base_name] = result
            
            for strategy_name in sorted(strategy_best.keys()):
                result = strategy_best[strategy_name]
                f.write(f"\n{strategy_name}:\n")
                f.write(f"  Best Loss Tolerance: {result['loss_tolerance_pct']:.2f}%\n")
                f.write(f"  APY (USD):          {result['apy_usd']:.2f}%\n")
                f.write(f"  APY (BTC):          {result['apy_btc']:.2f}%\n")
                f.write(f"  Trades:             {result['trades']}\n")
                f.write(f"  Win Rate:           {result['win_rate']:.1f}%\n")
        
        print(f"📁 Results saved to:")
        print(f"   JSON: {json_file}")
        print(f"   Summary: {summary_file}")
        print()


if __name__ == '__main__':
    # Required for multiprocessing on macOS/Windows
    mp.set_start_method('spawn', force=True)
    main()
