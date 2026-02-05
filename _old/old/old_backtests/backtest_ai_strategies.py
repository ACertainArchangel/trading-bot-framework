#!/usr/bin/env python3
"""
Backtest AI-Generated Trading Strategies

Tests 6 different trading strategies with multiple parameter configurations each:
1. RSI (Relative Strength Index)
2. Bollinger Bands
3. EMA Crossover
4. Stochastic Oscillator
5. Mean Reversion
6. Momentum (Rate of Change)

Each strategy is tested with multiple parameter variations to find optimal settings.
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
from backtest_lib import load_historical_data, parallel_backtest_runner
import json

# Create backtest results directory if it doesn't exist
RESULTS_DIR = 'backtest_results'
os.makedirs(RESULTS_DIR, exist_ok=True)


def main():
    """
    Run backtests across 6 different strategies with multiple parameters each.
    """
    print("=" * 80)
    print("AI TRADING STRATEGIES - COMPREHENSIVE BACKTEST")
    print("=" * 80)
    print()
    
    # Test parameters
    starting_currency = 1000.0
    months = 3
    loss_tolerance = 0.0  # Use optimal loss tolerance from MACD tests
    
    # Define test configurations for each strategy
    test_configs = []
    
    # 1. RSI Strategy - 5 configurations
    print("📊 RSI Strategy Configurations:")
    rsi_configs = [
        #{'period': 14, 'oversold': 30, 'overbought': 70},  # Classic RSI
        #{'period': 14, 'oversold': 20, 'overbought': 80},  # More extreme levels
        #{'period': 9, 'oversold': 30, 'overbought': 70},   # Faster RSI
        #{'period': 21, 'oversold': 30, 'overbought': 70},  # Slower RSI
        #{'period': 14, 'oversold': 40, 'overbought': 60},  # Tighter range
    ]
    for config in rsi_configs:
        test_configs.append({
            'strategy_class': RSIStrategy,
            'strategy_params': config,
            'loss_tolerance': loss_tolerance
        })
        print(f"  • RSI({config['period']}, {config['oversold']}/{config['overbought']})")
    print()
    
    # 2. Bollinger Bands - 5 configurations
    print("📊 Bollinger Bands Strategy Configurations:")
    bb_configs = [
        #{'period': 20, 'std_dev': 2.0},   # Classic Bollinger
        #{'period': 20, 'std_dev': 1.5},   # Tighter bands
        #{'period': 20, 'std_dev': 2.5},   # Wider bands
        #{'period': 10, 'std_dev': 2.0},   # Faster bands
        #{'period': 30, 'std_dev': 2.0},   # Slower bands
    ]
    for config in bb_configs:
        test_configs.append({
            'strategy_class': BollingerStrategy,
            'strategy_params': config,
            'loss_tolerance': loss_tolerance
        })
        print(f"  • Bollinger({config['period']}, {config['std_dev']}σ)")
    print()
    
    # 3. EMA Crossover - 5 configurations
    print("📊 EMA Crossover Strategy Configurations:")
    ema_configs = [
        {'fast': 9, 'slow': 21},    # Classic short-term
        {'fast': 12, 'slow': 26},   # MACD-like
        #{'fast': 5, 'slow': 13},    # Very fast
        #{'fast': 20, 'slow': 50},   # Medium-term
        #{'fast': 50, 'slow': 200},  # Long-term (golden cross)
    ]
    for config in ema_configs:
        test_configs.append({
            'strategy_class': EMACrossStrategy,
            'strategy_params': config,
            'loss_tolerance': loss_tolerance
        })
        print(f"  • EMA_Cross({config['fast']}/{config['slow']})")
    
    # Add EMA 9-26 with multiple risk tolerances
    print("  Testing EMA(9/26) with multiple risk tolerances:")
    for lt in [0.0, 0.00025, 0.001]:
        test_configs.append({
            'strategy_class': EMACrossStrategy,
            'strategy_params': {'fast': 9, 'slow': 26},
            'loss_tolerance': lt
        })
        print(f"  • EMA_Cross(9/26) @ {lt * 100:.3f}% loss tolerance")
    print()
    
    # 4. Stochastic Oscillator - 5 configurations
    print("📊 Stochastic Strategy Configurations:")
    stoch_configs = [
        #{'k_period': 14, 'd_period': 3, 'oversold': 20, 'overbought': 80},  # Classic
        #{'k_period': 14, 'd_period': 3, 'oversold': 30, 'overbought': 70},  # Less extreme
        #{'k_period': 5, 'd_period': 3, 'oversold': 20, 'overbought': 80},   # Fast
        #{'k_period': 21, 'd_period': 5, 'oversold': 20, 'overbought': 80},  # Slow
        #{'k_period': 14, 'd_period': 3, 'oversold': 10, 'overbought': 90},  # Very extreme
    ]
    for config in stoch_configs:
        test_configs.append({
            'strategy_class': StochasticStrategy,
            'strategy_params': config,
            'loss_tolerance': loss_tolerance
        })
        print(f"  • Stochastic({config['k_period']},{config['d_period']})")
    print()
    
    # 5. Mean Reversion - 5 configurations
    print("📊 Mean Reversion Strategy Configurations:")
    mr_configs = [
        #{'period': 20, 'buy_threshold': -1.5, 'sell_threshold': 1.5},  # Moderate
        #{'period': 20, 'buy_threshold': -2.0, 'sell_threshold': 2.0},  # Wide range
        #{'period': 20, 'buy_threshold': -1.0, 'sell_threshold': 1.0},  # Tight range
        #{'period': 10, 'buy_threshold': -1.5, 'sell_threshold': 1.5},  # Fast
        #{'period': 30, 'buy_threshold': -1.5, 'sell_threshold': 1.5},  # Slow
    ]
    for config in mr_configs:
        test_configs.append({
            'strategy_class': MeanReversionStrategy,
            'strategy_params': config,
            'loss_tolerance': loss_tolerance
        })
        print(f"  • MeanReversion({config['period']}, {config['buy_threshold']}σ/{config['sell_threshold']}σ)")
    print()
    
    # 6. Momentum - 5 configurations
    print("📊 Momentum Strategy Configurations:")
    mom_configs = [
        {'period': 10, 'buy_threshold': 2.0, 'sell_threshold': -2.0},   # Moderate
        {'period': 10, 'buy_threshold': 3.0, 'sell_threshold': -3.0},   # Strong signals
        {'period': 10, 'buy_threshold': 1.0, 'sell_threshold': -1.0},   # Weak signals
        {'period': 5, 'buy_threshold': 2.0, 'sell_threshold': -2.0},    # Fast
        {'period': 20, 'buy_threshold': 2.0, 'sell_threshold': -2.0},   # Slow
    ]
    for config in mom_configs:
        test_configs.append({
            'strategy_class': MomentumStrategy,
            'strategy_params': config,
            'loss_tolerance': loss_tolerance
        })
        print(f"  • Momentum({config['period']}, {config['buy_threshold']}%/{config['sell_threshold']}%)")
    print()
    
    print(f"📊 Total configurations to test: {len(test_configs)}")
    print(f"💰 Starting capital: ${starting_currency:.2f}")
    print(f"🛡️  Loss tolerance: {loss_tolerance * 100:.2f}%")
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
    print("=" * 140)
    print("RESULTS - TOP 10 PERFORMERS")
    print("=" * 140)
    print()
    
    print(f"{'Rank':<6} {'Strategy':<30} {'APY_USD':<10} {'APY_BTC':<10} {'Trades':<8} "
          f"{'W/L':<10} {'Win%':<8} {'Avg $/Trade':<14} {'Final $':<12}")
    print("-" * 140)
    
    # Show top 10
    for i, result in enumerate(successful_results[:10], 1):
        strategy_name = result['strategy']
        params = result['strategy_params']
        
        # Format parameters based on strategy
        if strategy_name == 'RSIStrategy':
            params_str = f"RSI({params['period']},{params['oversold']}/{params['overbought']})"
        elif strategy_name == 'BollingerStrategy':
            params_str = f"BB({params['period']},{params['std_dev']}σ)"
        elif strategy_name == 'EMACrossStrategy':
            params_str = f"EMA({params['fast']}/{params['slow']})"
        elif strategy_name == 'StochasticStrategy':
            params_str = f"Stoch({params['k_period']},{params['d_period']})"
        elif strategy_name == 'MeanReversionStrategy':
            params_str = f"MR({params['period']},{params['buy_threshold']}σ)"
        elif strategy_name == 'MomentumStrategy':
            params_str = f"Mom({params['period']},{params['buy_threshold']}%)"
        else:
            params_str = str(params)
        
        print(f"#{i:<5} {params_str:<30} "
              f"{result['apy_usd']:>7.2f}%   "
              f"{result['apy_btc']:>7.2f}%   "
              f"{result['trades']:>6}   "
              f"{result['wins']:>3}/{result['losses']:<3}   "
              f"{result['win_rate']:>6.1f}%  "
              f"${result['avg_profit_per_trade']:>11.2f}   "
              f"${result['current_value']:>10.2f}")
    
    print()
    
    # Show strategy performance summary
    print("=" * 80)
    print("STRATEGY PERFORMANCE SUMMARY")
    print("=" * 80)
    print()
    
    strategy_names = ['RSIStrategy', 'BollingerStrategy', 'EMACrossStrategy', 
                     'StochasticStrategy', 'MeanReversionStrategy', 'MomentumStrategy']
    
    for strat_name in strategy_names:
        strat_results = [r for r in successful_results if r['strategy'] == strat_name]
        if strat_results:
            best = max(strat_results, key=lambda x: x['apy_usd'])
            avg_apy = sum(r['apy_usd'] for r in strat_results) / len(strat_results)
            print(f"{strat_name:25} | Best: {best['apy_usd']:>7.2f}% | Avg: {avg_apy:>7.2f}% | Configs: {len(strat_results)}")
    
    print()
    
    if failed_results:
        print(f"⚠️  {len(failed_results)} configurations failed")
        print()
    
    # Find and display best overall result
    if successful_results:
        best = successful_results[0]
        best_params = best['strategy_params']
        
        print("=" * 80)
        print("🏆 BEST PERFORMING CONFIGURATION")
        print("=" * 80)
        print(f"Strategy:           {best['strategy']}")
        print(f"Parameters:         {best_params}")
        print(f"Loss Tolerance:     {best['loss_tolerance_pct']:.2f}%")
        print(f"APY (USD):          {best['apy_usd']:.2f}%")
        print(f"APY (BTC):          {best['apy_btc']:.2f}%")
        print(f"Baseline Return:    {best['baseline_return_pct']:.2f}%")
        print(f"Final Baseline:     ${best['final_baseline']:.2f}")
        print(f"Current Value:      ${best['current_value']:.2f}")
        print(f"Total Trades:       {best['trades']}")
        print(f"Win Rate:           {best['win_rate']:.1f}% ({best['wins']} wins, {best['losses']} losses)")
        print(f"Avg Profit/Trade:   ${best['avg_profit_per_trade']:.2f}")
        print(f"Final Position:     {best['final_position'].upper()}")
        print()
        
        # Save results to backtest_results directory
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Save JSON results
        json_file = os.path.join(RESULTS_DIR, f"backtest_ai_{timestamp}.json")
        with open(json_file, 'w') as f:
            json.dump({
                'test_config': {
                    'starting_currency': starting_currency,
                    'months': months,
                    'loss_tolerance': loss_tolerance,
                    'granularity': '5m',
                    'candles': len(candles),
                    'test_date': datetime.now().isoformat(),
                    'strategies_tested': len(test_configs)
                },
                'results': successful_results,
                'failed': failed_results
            }, f, indent=2)
        
        # Save human-readable summary
        summary_file = os.path.join(RESULTS_DIR, f"backtest_ai_{timestamp}.txt")
        with open(summary_file, 'w') as f:
            f.write("=" * 80 + "\n")
            f.write("AI TRADING STRATEGIES - BACKTEST SUMMARY\n")
            f.write("=" * 80 + "\n")
            f.write(f"Test Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Period: {months} months of historical data\n")
            f.write(f"Starting Capital: ${starting_currency:.2f}\n")
            f.write(f"Loss Tolerance: {loss_tolerance * 100:.2f}%\n")
            f.write(f"Total Configurations: {len(test_configs)}\n")
            f.write(f"Successful: {len(successful_results)}\n")
            f.write(f"Failed: {len(failed_results)}\n")
            f.write("\n")
            
            f.write("=" * 140 + "\n")
            f.write("TOP 10 PERFORMERS\n")
            f.write("=" * 140 + "\n")
            f.write(f"{'Rank':<6} {'Strategy':<30} {'APY_USD':<10} {'APY_BTC':<10} {'Trades':<8} "
                   f"{'W/L':<10} {'Win%':<8} {'Avg $/Trade':<14} {'Final $':<12}\n")
            f.write("-" * 140 + "\n")
            
            for i, result in enumerate(successful_results[:10], 1):
                strategy_name = result['strategy']
                params = result['strategy_params']
                
                if strategy_name == 'RSIStrategy':
                    params_str = f"RSI({params['period']},{params['oversold']}/{params['overbought']})"
                elif strategy_name == 'BollingerStrategy':
                    params_str = f"BB({params['period']},{params['std_dev']}σ)"
                elif strategy_name == 'EMACrossStrategy':
                    params_str = f"EMA({params['fast']}/{params['slow']})"
                elif strategy_name == 'StochasticStrategy':
                    params_str = f"Stoch({params['k_period']},{params['d_period']})"
                elif strategy_name == 'MeanReversionStrategy':
                    params_str = f"MR({params['period']},{params['buy_threshold']}σ)"
                elif strategy_name == 'MomentumStrategy':
                    params_str = f"Mom({params['period']},{params['buy_threshold']}%)"
                else:
                    params_str = str(params)
                
                f.write(f"#{i:<5} {params_str:<30} "
                       f"{result['apy_usd']:>7.2f}%   "
                       f"{result['apy_btc']:>7.2f}%   "
                       f"{result['trades']:>6}   "
                       f"{result['wins']:>3}/{result['losses']:<3}   "
                       f"{result['win_rate']:>6.1f}%  "
                       f"${result['avg_profit_per_trade']:>11.2f}   "
                       f"${result['current_value']:>10.2f}\n")
            
            f.write("\n")
            f.write("=" * 80 + "\n")
            f.write("BEST PERFORMING CONFIGURATION\n")
            f.write("=" * 80 + "\n")
            f.write(f"Strategy:           {best['strategy']}\n")
            f.write(f"Parameters:         {best_params}\n")
            f.write(f"Loss Tolerance:     {best['loss_tolerance_pct']:.2f}%\n")
            f.write(f"APY (USD):          {best['apy_usd']:.2f}%\n")
            f.write(f"APY (BTC):          {best['apy_btc']:.2f}%\n")
            f.write(f"Baseline Return:    {best['baseline_return_pct']:.2f}%\n")
            f.write(f"Final Baseline:     ${best['final_baseline']:.2f}\n")
            f.write(f"Current Value:      ${best['current_value']:.2f}\n")
            f.write(f"Total Trades:       {best['trades']}\n")
            f.write(f"Win Rate:           {best['win_rate']:.1f}% ({best['wins']} wins, {best['losses']} losses)\n")
            f.write(f"Avg Profit/Trade:   ${best['avg_profit_per_trade']:.2f}\n")
            f.write(f"Final Position:     {best['final_position'].upper()}\n")
        
        print(f"📁 Results saved to:")
        print(f"   JSON: {json_file}")
        print(f"   Summary: {summary_file}")
        print()


if __name__ == '__main__':
    # Required for multiprocessing on macOS/Windows
    mp.set_start_method('spawn', force=True)
    main()
