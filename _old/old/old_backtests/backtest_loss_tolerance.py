#!/usr/bin/env python3
"""
Backtest loss tolerance parameter across multiple values.
Tests different loss tolerance settings on the same historical data to find optimal value.
"""

import multiprocessing as mp
from datetime import datetime, timezone, timedelta
from trader_bot import Bot
from interfaces.PaperTradingInterface import PaperTradingInterface
from strategies.macd import MACDStrategy
from CBData import CoinbaseDataFetcher
import json
import time
import os

# Create results directory if it doesn't exist
RESULTS_DIR = 'backtest_results'
os.makedirs(RESULTS_DIR, exist_ok=True)

def load_historical_data(months=3):
    """
    Load historical data once to be shared across all tests.
    Returns list of candles.
    """
    now = datetime.now(timezone.utc)
    start_date = now - timedelta(days=30 * months)
    
    print(f"📦 Loading {months} months of 5-minute candles...")
    print(f"📅 Date range: {start_date.strftime('%Y-%m-%d')} to {now.strftime('%Y-%m-%d')}")
    
    api = CoinbaseDataFetcher(product_id='BTC-USD')
    candles = api.fetch_candles(
        granularity='5m',
        start=start_date,
        end=now
    )
    
    print(f"✅ Loaded {len(candles)} candles")
    return candles


def run_backtest(args):
    """
    Run a single backtest with given loss tolerance.
    This runs in a separate process.
    """
    loss_tolerance, candles, starting_currency = args
    
    try:
        # Create interface and bot (disable logging for speed)
        import sys
        from io import StringIO
        old_stdout = sys.stdout
        sys.stdout = StringIO()  # Suppress all print output
        
        interface = PaperTradingInterface()
        bot = Bot(
            interface=interface,
            strategy=MACDStrategy,
            pair="BTC-USD",
            starting_currency=starting_currency,
            starting_asset=0.0,
            fee_rate=0.025,
            fee_in_percent=True,
            loss_tolerance=loss_tolerance
        )
        
        sys.stdout = old_stdout  # Restore stdout
        
        # Verify loss tolerance is set
        if bot.loss_tolerance != loss_tolerance:
            raise ValueError(f"Bot loss_tolerance mismatch: expected {loss_tolerance}, got {bot.loss_tolerance}")
        
        # Track metrics
        trades = 0
        wins = 0
        losses = 0
        rejected_buys = 0
        rejected_sells = 0
        cycle_start_value = starting_currency  # Track USD value at start of each cycle
        initial_usd = starting_currency  # First USD amount (at start)
        last_usd_held = starting_currency  # Last USD amount before we went LONG
        initial_btc = None  # First BTC amount (after first buy)
        
        # Suppress logging output during backtest
        sys.stdout = StringIO()
        
        # Simulate trading through all candles
        for i, candle in enumerate(candles):
            if i < 35:  # Need 35 candles for MACD
                continue
            
            # Get historical window
            window = candles[:i+1]
            current_price = candle[4]  # Close price
            
            # Check signals
            if bot.position == "short" and bot.buy_signal(window):
                # Store the USD value before buying (for cycle profit tracking)
                cycle_start_value = bot.currency
                last_usd_held = bot.currency  # Track last USD amount before going LONG
                if bot.execute_buy(current_price):
                    trades += 1
                    # Track the first BTC amount ever held
                    if initial_btc is None:
                        initial_btc = bot.asset
                else:
                    rejected_buys += 1
                    
            elif bot.position == "long" and bot.sell_signal(window):
                if bot.execute_sell(current_price):
                    trades += 1
                    # Calculate profit for this complete cycle (short->long->short)
                    # Compare final USD to starting USD for this cycle
                    profit = bot.currency - cycle_start_value
                    if profit > 0:
                        wins += 1
                    else:
                        losses += 1
                else:
                    rejected_sells += 1
        
        # Restore stdout
        sys.stdout = old_stdout
        
        # Calculate APY - always use USD values for consistent comparison
        # APY = (final_USD / initial_USD) ^ (1/years) - 1
        months = 3
        years = months / 12
        current_price = candles[-1][4]
        
        # If we never bought BTC, use theoretical initial BTC
        if initial_btc is None:
            initial_btc = starting_currency / candles[35][4]  # Approximate based on first trading candle
        
        if bot.position == "short":
            # Ending in USD: use actual USD
            final_usd = bot.currency
            final_baseline_usd = bot.currency_baseline
            current_value = bot.currency
            final_btc = bot.asset_baseline  # Last BTC baseline (from when we held BTC)
        else:
            # Ending in BTC: use the LAST USD amount we held (before buying BTC)
            final_usd = last_usd_held
            final_baseline_usd = bot.asset_baseline * current_price
            current_value = bot.asset * current_price
            final_btc = bot.asset  # Current BTC holdings
        
        # Always compare USD to USD for APY_USD and BTC to BTC for APY_BTC
        apy_usd = ((final_usd / initial_usd) ** (1 / years) - 1) * 100
        apy_btc = ((final_btc / initial_btc) ** (1 / years) - 1) * 100 if initial_btc > 0 else 0.0

        
        # Calculate return percentage
        starting_baseline_usd = starting_currency
        value_return = ((current_value - starting_baseline_usd) / starting_baseline_usd) * 100
        baseline_return = ((final_baseline_usd - starting_baseline_usd) / starting_baseline_usd) * 100
        
        # Calculate win rate based on complete cycles (buy+sell = 1 cycle)
        complete_cycles = wins + losses
        win_rate = (wins / complete_cycles * 100) if complete_cycles > 0 else 0
        
        # Calculate average profit per complete cycle
        total_profit = current_value - starting_baseline_usd
        avg_profit = total_profit / complete_cycles if complete_cycles > 0 else 0
        
        return {
            'loss_tolerance': loss_tolerance,
            'loss_tolerance_pct': loss_tolerance * 100,
            'final_baseline': final_baseline_usd,
            'current_value': current_value,
            'baseline_return_pct': baseline_return,
            'apy_usd': apy_usd,
            'apy_btc': apy_btc,
            'trades': trades,
            'wins': wins,
            'losses': losses,
            'rejected_buys': rejected_buys,
            'rejected_sells': rejected_sells,
            'win_rate': win_rate,
            'avg_profit_per_trade': avg_profit,
            'final_position': bot.position,
            'success': True
        }
        
    except Exception as e:
        return {
            'loss_tolerance': loss_tolerance,
            'loss_tolerance_pct': loss_tolerance * 100,
            'error': str(e),
            'success': False
        }


def main():
    """
    Run backtests across multiple loss tolerance values.
    """
    print("=" * 80)
    print("MACD STRATEGY - LOSS TOLERANCE OPTIMIZATION")
    print("=" * 80)
    print()
    
    # Test parameters
    starting_currency = 1000.0
    loss_tolerances = [
        0.000,  # 0.0% - never take a loss (baseline behavior)
        0.001,  # 0.1%
        0.005,  # 0.5%
        0.010,  # 1.0%
        0.025,  # 2.5%
        0.050,  # 5.0%
        0.100,  # 10.0%
        0.250,  # 25.0% - aggressive loss cutting
    ]
    
    print(f"📊 Testing {len(loss_tolerances)} different loss tolerance values")
    print(f"💰 Starting capital: ${starting_currency:.2f}")
    print()
    
    # Load data once (shared across all tests)
    start_load = time.time()
    candles = load_historical_data(months=3)
    load_time = time.time() - start_load
    print(f"⏱️  Data loading took {load_time:.1f} seconds")
    print()
    
    # Prepare arguments for parallel processing
    args_list = [(lt, candles, starting_currency) for lt in loss_tolerances]
    
    # Run backtests in parallel using multiprocessing
    print(f"🚀 Running {len(loss_tolerances)} backtests in parallel...")
    print()
    
    start_time = time.time()
    
    # Use multiprocessing Pool to run tests in parallel
    with mp.Pool(processes=mp.cpu_count()) as pool:
        results = pool.map(run_backtest, args_list)
    
    elapsed_time = time.time() - start_time
    
    # Print individual results
    print()
    print("✅ All tests complete!")
    print()
    for i, result in enumerate(results, 1):
        if result['success']:
            print(f"  [{i}/{len(results)}] {result['loss_tolerance_pct']:.2f}% → Baseline: ${result['final_baseline']:.2f}, Trades: {result['trades']}, Rejected: {result['rejected_buys']}B/{result['rejected_sells']}S, APY_USD: {result['apy_usd']:.1f}%, APY_BTC: {result['apy_btc']:.1f}%")
    print()
    
    # Sort results by USD APY (primary metric)
    successful_results = [r for r in results if r['success']]
    failed_results = [r for r in results if not r['success']]
    successful_results.sort(key=lambda x: x['apy_usd'], reverse=True)
    
    # Print results
    print("=" * 80)
    print("RESULTS")
    print("=" * 80)
    print()
    
    print(f"{'Loss Tol':<10} {'APY_USD':<10} {'APY_BTC':<10} {'Baseline':<10} {'Trades':<8} {'W/L':<10} {'Win%':<8} {'Avg $/Trade':<12} {'Current $':<12}")
    print("-" * 120)
    
    for result in successful_results:
        print(f"{result['loss_tolerance_pct']:>6.2f}%   "
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
            print(f"   Loss tolerance {result['loss_tolerance_pct']:.2f}%: {result['error']}")
    
    print()
    print(f"⏱️  Total backtest time: {elapsed_time:.1f} seconds")
    print(f"⚡ Average time per test: {elapsed_time/len(loss_tolerances):.1f} seconds")
    print()
    
    # Find best result
    if successful_results:
        best = successful_results[0]
        print("=" * 80)
        print("🏆 BEST PERFORMING CONFIGURATION")
        print("=" * 80)
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
        json_file = os.path.join(RESULTS_DIR, f"backtest_loss_tolerance_{timestamp}.json")
        with open(json_file, 'w') as f:
            json.dump({
                'test_config': {
                    'starting_currency': starting_currency,
                    'months': 3,
                    'granularity': '5m',
                    'candles': len(candles),
                    'test_date': datetime.now().isoformat()
                },
                'results': successful_results,
                'failed': failed_results
            }, f, indent=2)
        
        # Save human-readable summary
        summary_file = os.path.join(RESULTS_DIR, f"backtest_loss_tolerance_{timestamp}.txt")
        with open(summary_file, 'w') as f:
            f.write("=" * 80 + "\n")
            f.write("LOSS TOLERANCE PARAMETER - BACKTEST SUMMARY\n")
            f.write("=" * 80 + "\n\n")
            
            f.write("TEST CONFIGURATION:\n")
            f.write(f"  Starting Capital:  ${starting_currency:,.2f}\n")
            f.write(f"  Test Period:       3 months\n")
            f.write(f"  Granularity:       5m\n")
            f.write(f"  Total Candles:     {len(candles)}\n")
            f.write(f"  Test Date:         {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"  Successful Tests:  {len(successful_results)}\n")
            f.write(f"  Failed Tests:      {len(failed_results)}\n\n")
            
            f.write("TOP 10 PERFORMING CONFIGURATIONS:\n")
            f.write("=" * 80 + "\n")
            f.write(f"{'Rank':<6} {'Loss Tol':<10} {'APY_USD':<10} {'APY_BTC':<10} {'Trades':<8} {'Win Rate':<10} {'Avg/Trade':<12}\n")
            f.write("-" * 80 + "\n")
            
            for i, result in enumerate(successful_results[:10], 1):
                f.write(f"{i:<6} {result['loss_tolerance_pct']:<9.2f}% "
                       f"{result['apy_usd']:<9.2f}% {result['apy_btc']:<9.2f}% "
                       f"{result['trades']:<8} {result['win_rate']:<9.1f}% "
                       f"${result['avg_profit_per_trade']:<11,.2f}\n")
            
            f.write("\n" + "=" * 80 + "\n")
            f.write("BEST PERFORMING CONFIGURATION:\n")
            f.write("=" * 80 + "\n")
            f.write(f"Loss Tolerance:     {best['loss_tolerance']:.4f}\n")
            f.write(f"Total Profit:       ${best['profit']:,.2f}\n")
            f.write(f"ROI:                {best['roi']:.2f}%\n")
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
