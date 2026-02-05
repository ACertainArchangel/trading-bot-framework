#!/usr/bin/env python3
"""
Backtest MACD strategy with different parameter configurations.
Tests 8 different MACD parameter combinations to find the optimal configuration.
"""

import multiprocessing as mp
from datetime import datetime
from strategies.macd import MACDStrategy
from backtest_lib import load_historical_data, parallel_backtest_runner
import json
import os

# Create results directory if it doesn't exist
RESULTS_DIR = 'backtest_results'
os.makedirs(RESULTS_DIR, exist_ok=True)


def main():
    """
    Run backtests across multiple MACD parameter configurations.
    """
    print("=" * 80)
    print("MACD STRATEGY - PARAMETER OPTIMIZATION")
    print("=" * 80)
    print()
    
    # Test parameters
    starting_currency = 1000.0
    months = 3
    loss_tolerance = 0.0  # Use optimal loss tolerance
    
    # Define 8 different MACD parameter configurations to test
    # Format: (fast_period, slow_period, signal_period)
    macd_configs = [
        {'fast': 12, 'slow': 26, 'signal': 9},   # Classic MACD (default)
        {'fast': 8, 'slow': 17, 'signal': 9},    # Faster, more sensitive
        {'fast': 5, 'slow': 13, 'signal': 5},    # Very fast, aggressive
        {'fast': 12, 'slow': 26, 'signal': 5},   # Classic with faster signal
        {'fast': 12, 'slow': 26, 'signal': 15},  # Classic with slower signal
        {'fast': 19, 'slow': 39, 'signal': 9},   # Slower, more conservative
        {'fast': 24, 'slow': 52, 'signal': 18},  # Very slow, very conservative
        {'fast': 10, 'slow': 20, 'signal': 7},   # Balanced medium-term
    ]
    
    print(f"📊 Testing {len(macd_configs)} different MACD parameter configurations")
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
    
    # Create test configurations
    test_configs = []
    for config in macd_configs:
        test_configs.append({
            'strategy_class': MACDStrategy,
            'strategy_params': config,
            'loss_tolerance': loss_tolerance
        })
    
    # Run backtests in parallel
    results = parallel_backtest_runner(
        test_configs=test_configs,
        candles=candles,
        starting_currency=starting_currency,
        fee_rate=0.025,
        pair="BTC-USD",
        min_candles=max(config['slow'] + config['signal'] for config in macd_configs),  # Need enough for slowest MACD
        months=months
    )
    
    # Sort results by USD APY
    successful_results = [r for r in results if r['success']]
    failed_results = [r for r in results if not r['success']]
    successful_results.sort(key=lambda x: x['apy_usd'], reverse=True)
    
    # Print results table
    print("=" * 120)
    print("RESULTS")
    print("=" * 120)
    print()
    
    print(f"{'Fast':<6} {'Slow':<6} {'Signal':<8} {'APY_USD':<10} {'APY_BTC':<10} {'Baseline':<10} "
          f"{'Trades':<8} {'W/L':<10} {'Win%':<8} {'Avg $/Trade':<12} {'Current $':<12}")
    print("-" * 120)
    
    for result in successful_results:
        params = result['strategy_params']
        print(f"{params['fast']:<6} {params['slow']:<6} {params['signal']:<8} "
              f"{result['apy_usd']:>7.2f}%   "
              f"{result['apy_btc']:>7.2f}%   "
              f"{result['baseline_return_pct']:>7.2f}%   "
              f"{result['trades']:>6}   "
              f"{result['wins']:>3}/{result['losses']:<3}   "
              f"{result['win_rate']:>6.1f}%  "
              f"${result['avg_profit_per_trade']:>9.2f}   "
              f"${result['current_value']:>10.2f}")
    
    if failed_results:
        print()
        print("❌ FAILED TESTS:")
        for result in failed_results:
            params = result['strategy_params']
            print(f"   MACD({params['fast']}/{params['slow']}/{params['signal']}): {result['error']}")
    
    print()
    
    # Find and display best result
    if successful_results:
        best = successful_results[0]
        best_params = best['strategy_params']
        
        print("=" * 80)
        print("🏆 BEST PERFORMING CONFIGURATION")
        print("=" * 80)
        print(f"MACD Parameters:    Fast={best_params['fast']}, Slow={best_params['slow']}, Signal={best_params['signal']}")
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
        
        # Save results to JSON
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        json_file = os.path.join(RESULTS_DIR, f"backtest_macd_params_{timestamp}.json")
        with open(json_file, 'w') as f:
            json.dump({
                'test_config': {
                    'starting_currency': starting_currency,
                    'months': months,
                    'loss_tolerance': loss_tolerance,
                    'granularity': '5m',
                    'candles': len(candles),
                    'test_date': datetime.now().isoformat()
                },
                'results': successful_results,
                'failed': failed_results
            }, f, indent=2)
        
        # Save human-readable summary
        summary_file = os.path.join(RESULTS_DIR, f"backtest_macd_params_{timestamp}.txt")
        with open(summary_file, 'w') as f:
            f.write("=" * 80 + "\n")
            f.write("MACD STRATEGY - PARAMETER OPTIMIZATION SUMMARY\n")
            f.write("=" * 80 + "\n\n")
            
            f.write("TEST CONFIGURATION:\n")
            f.write(f"  Starting Capital:  ${starting_currency:,.2f}\n")
            f.write(f"  Test Period:       {months} months\n")
            f.write(f"  Loss Tolerance:    {loss_tolerance:.4f}\n")
            f.write(f"  Granularity:       5m\n")
            f.write(f"  Total Candles:     {len(candles)}\n")
            f.write(f"  Test Date:         {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"  Successful Tests:  {len(successful_results)}\n")
            f.write(f"  Failed Tests:      {len(failed_results)}\n\n")
            
            f.write("ALL TESTED CONFIGURATIONS:\n")
            f.write("=" * 80 + "\n")
            f.write(f"{'Rank':<6} {'Fast':<6} {'Slow':<6} {'Signal':<8} {'Profit':<12} {'ROI %':<8} {'Trades':<8} {'Win Rate':<10}\n")
            f.write("-" * 80 + "\n")
            
            for i, result in enumerate(sorted_results, 1):
                f.write(f"{i:<6} {result['fast_period']:<6} {result['slow_period']:<6} "
                       f"{result['signal_period']:<8} ${result['profit']:<11,.2f} {result['roi']:<7.2f}% "
                       f"{result['trades']:<8} {result['win_rate']:<9.1f}%\n")
            
            f.write("\n" + "=" * 80 + "\n")
            f.write("BEST PERFORMING CONFIGURATION:\n")
            f.write("=" * 80 + "\n")
            f.write(f"MACD Parameters:    Fast={best['fast_period']}, Slow={best['slow_period']}, Signal={best['signal_period']}\n")
            f.write(f"Total Profit:       ${best['profit']:,.2f}\n")
            f.write(f"ROI:                {best['roi']:.2f}%\n")
            f.write(f"APY (USD):          {best['apy_usd']:.2f}%\n")
            f.write(f"APY (BTC):          {best['apy_btc']:.2f}%\n")
            f.write(f"Baseline Return:    {best['baseline_return_pct']:.2f}%\n")
            f.write(f"Final Baseline:     ${best['final_baseline']:,.2f}\n")
            f.write(f"Starting Value:     ${best['starting_value']:,.2f}\n")
            f.write(f"Current Value:      ${best['current_value']:,.2f}\n")
            f.write(f"Total Trades:       {best['trades']}\n")
            f.write(f"Win Rate:           {best['win_rate']:.1f}% ({best['wins']} wins, {best['losses']} losses)\n")
            f.write(f"Avg Profit/Trade:   ${best['avg_profit_per_trade']:,.2f}\n")
            f.write(f"Final Position:     {best['final_position'].upper()}\n")
        
        print(f"📁 Results saved to:")
        print(f"   JSON: {json_file}")
        print(f"   Summary: {summary_file}")
        print()


if __name__ == '__main__':
    # Required for multiprocessing on macOS/Windows
    mp.set_start_method('spawn', force=True)
    main()
