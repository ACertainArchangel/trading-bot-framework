#!/usr/bin/env python3
"""
Backtest the Top 3 Winning Strategies

Tests the three best performing strategies from v2_5m analysis:
1. Spicy Mac: GreedyMACD(5/13/5, patience=720, margin=1.25%) @ 0.10% loss
2. Grumpy Mom: GreedyMomentum(p=14, patience=1440, margin=1.0%) @ 0.00% loss  
3. Sleepy Mac: GreedyMACD(5/13/5, patience=2880, margin=0.75%) @ 0.00% loss

Time periods tested (1-minute granularity):
- Past 3 months (0-3 months ago)
- 3-6 months ago
- Past 6 months (0-6 months ago)

Optimizations:
- Loads 6 months of data once, slices for each period
- Parallel execution of strategy tests
- tqdm progress bars for individual backtests
"""

import os
import multiprocessing as mp
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Tuple
from strategies.greedy_momentum import GreedyMomentumStrategy
from strategies.greedy_macd import GreedyMACDStrategy
from backtest_lib import load_historical_data
from trader_bot import Bot
from interfaces.PaperTradingInterface import PaperTradingInterface
import json

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False
    print("⚠️ tqdm not installed. Install with: pip install tqdm")

# Create results directory
RESULTS_DIR = 'backtest_results/winning_strategies_1m'
os.makedirs(RESULTS_DIR, exist_ok=True)

# Strategy definitions
STRATEGIES = [
    {
        'name': 'Spicy Mac',
        'description': 'GreedyMACD(5/13/5, patience=720, margin=1.25%) @ 0.10% loss',
        'strategy_class': GreedyMACDStrategy,
        'params': {
            'fast_period': 5,
            'slow_period': 13, 
            'signal_period': 5,
            'patience_candles': 720,
            'profit_margin': 1.25
        },
        'loss_tolerance': 0.0010
    },
    {
        'name': 'Grumpy Mom', 
        'description': 'GreedyMomentum(p=14, patience=1440, margin=1.0%) @ 0.00% loss',
        'strategy_class': GreedyMomentumStrategy,
        'params': {
            'period': 14,
            'patience_candles': 1440,
            'profit_margin': 1.0,
            'sell_threshold': -1.0,
            'buy_threshold': 1.0
        },
        'loss_tolerance': 0.0000
    },
    {
        'name': 'Sleepy Mac',
        'description': 'GreedyMACD(5/13/5, patience=2880, margin=0.75%) @ 0.00% loss', 
        'strategy_class': GreedyMACDStrategy,
        'params': {
            'fast_period': 5,
            'slow_period': 13,
            'signal_period': 5, 
            'patience_candles': 2880,
            'profit_margin': 0.75
        },
        'loss_tolerance': 0.0000
    }
]


def run_single_backtest_with_progress(args: Tuple) -> Dict[str, Any]:
    """
    Run a single backtest with progress tracking.
    Designed to be called from multiprocessing pool.
    """
    strategy_config, candles, starting_currency, granularity, months, period_name, process_position = args
    
    strategy_class = strategy_config['strategy_class']
    strategy_params = strategy_config['params']
    loss_tolerance = strategy_config['loss_tolerance']
    strategy_name = strategy_config['name']
    
    min_candles = 35
    fee_rate = 0.025
    
    try:
        # Create paper trading interface
        interface = PaperTradingInterface(
            starting_currency=starting_currency,
            starting_asset=0.0
        )
        
        # Get initial price for baselines
        initial_price = candles[0][4]
        
        # Create bot with strategy (no logger param - Bot uses global main_logger)
        bot = Bot(
            interface=interface,
            strategy=strategy_class,
            strategy_params=strategy_params,
            fee_rate=fee_rate,
            loss_tolerance=loss_tolerance,
            initial_price=initial_price
        )
        
        # Get initial baselines
        initial_usd_baseline = bot.initial_usd_baseline
        initial_crypto_baseline = bot.initial_crypto_baseline
        
        # Trading simulation
        trades = 0
        wins = 0
        losses = 0
        rejected_buys = 0
        rejected_sells = 0
        cycle_start_value = starting_currency
        
        # Create iterator with or without tqdm
        candle_range = range(min_candles, len(candles))
        desc_text = f"{strategy_name[:10]:10} | {period_name[:12]}"
        
        if HAS_TQDM:
            candle_range = tqdm(
                candle_range, 
                desc=desc_text,
                leave=False,
                ncols=100,
                position=process_position
            )
        
        # Simulate trading through all candles
        for i in candle_range:
            candle = candles[i]
            window = candles[:i+1]
            current_price = candle[4]
            
            # Update idle time tracking
            bot.candles_since_last_trade += 1
            if bot.candles_since_last_trade > bot.max_idle_candles:
                bot.max_idle_candles = bot.candles_since_last_trade
            
            # Check buy signal
            if bot.position == "short" and bot.buy_signal(window):
                cycle_start_value = bot.currency
                if bot.execute_buy(current_price):
                    trades += 1
                else:
                    rejected_buys += 1
            
            # Check sell signal
            elif bot.position == "long" and bot.sell_signal(window):
                pre_sell_asset = bot.asset
                if bot.execute_sell(current_price):
                    trades += 1
                    # Check if this was a winning trade
                    if bot.currency > cycle_start_value:
                        wins += 1
                    else:
                        losses += 1
                else:
                    rejected_sells += 1
        
        # Calculate final metrics
        current_price = candles[-1][4]
        if bot.position == "short":
            final_value = bot.currency
        else:
            final_value = bot.asset * current_price
        
        final_usd_baseline = bot.currency_baseline
        final_crypto_baseline = bot.asset_baseline
        
        # Calculate APY
        import math
        years = months / 12
        total_seconds = years * 365.25 * 24 * 3600
        
        apy_usd = 0.0
        apy_btc = 0.0
        
        if initial_usd_baseline > 0 and years > 0:
            try:
                ratio = final_usd_baseline / initial_usd_baseline
                if total_seconds < 86400:
                    return_pct = (ratio - 1) * 100
                    apy_usd = return_pct * (365.25 * 24 * 3600 / total_seconds)
                else:
                    if ratio > 0:
                        apy_usd = ((ratio ** (1 / years)) - 1) * 100
            except (OverflowError, ValueError):
                apy_usd = 0.0
        
        if initial_crypto_baseline > 0 and years > 0:
            try:
                ratio = final_crypto_baseline / initial_crypto_baseline
                if total_seconds < 86400:
                    return_pct = (ratio - 1) * 100
                    apy_btc = return_pct * (365.25 * 24 * 3600 / total_seconds)
                else:
                    if ratio > 0:
                        apy_btc = ((ratio ** (1 / years)) - 1) * 100
            except (OverflowError, ValueError):
                apy_btc = 0.0
        
        complete_cycles = wins + losses
        win_rate = (wins / complete_cycles * 100) if complete_cycles > 0 else 0
        
        return {
            'success': True,
            'strategy_name': strategy_name,
            'strategy_description': strategy_config['description'],
            'period_name': period_name,
            'granularity': granularity,
            'months': months,
            'starting_currency': starting_currency,
            'final_value': final_value,
            'apy_usd': apy_usd,
            'apy_btc': apy_btc,
            'trades': trades,
            'wins': wins,
            'losses': losses,
            'win_rate': win_rate,
            'rejected_buys': rejected_buys,
            'rejected_sells': rejected_sells,
            'final_position': bot.position,
            'candles_processed': len(candles)
        }
        
    except Exception as e:
        import traceback
        return {
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc(),
            'strategy_name': strategy_name,
            'period_name': period_name
        }


def main():
    print("=" * 80)
    print("🏆 BACKTEST - TOP 3 WINNING STRATEGIES (1-MINUTE GRANULARITY)")
    print("=" * 80)
    print()
    
    starting_currency = 1000.0
    granularity = '1m'
    
    # Step 1: Load ALL 6 months of data once
    print("📦 STEP 1: Loading 6 months of 1-minute data (this takes a while)...")
    print("   This data will be cached and sliced for each test period.")
    print()
    
    all_candles = load_historical_data(
        months=6,
        granularity=granularity,
        age_days=0
    )
    
    total_candles = len(all_candles)
    print(f"✅ Loaded {total_candles:,} total candles")
    print()
    
    # Get timestamps to find proper slice points
    first_ts = all_candles[0][0]
    last_ts = all_candles[-1][0]
    first_date = datetime.fromtimestamp(first_ts, tz=timezone.utc)
    last_date = datetime.fromtimestamp(last_ts, tz=timezone.utc)
    
    print(f"📅 Data range: {first_date.strftime('%Y-%m-%d')} to {last_date.strftime('%Y-%m-%d')}")
    print()
    
    # Calculate midpoint (3 months ago)
    three_months_ago = last_date - timedelta(days=90)
    midpoint_ts = int(three_months_ago.timestamp())
    
    # Find the index closest to 3 months ago
    midpoint_idx = None
    for i, candle in enumerate(all_candles):
        if candle[0] >= midpoint_ts:
            midpoint_idx = i
            break
    
    if midpoint_idx is None:
        midpoint_idx = len(all_candles) // 2
    
    # Define test periods with their candle slices
    # Convert to lists to make them picklable for multiprocessing
    test_periods = [
        {
            'name': 'Past 3 Months',
            'candles': list(all_candles[midpoint_idx:]),  # Most recent 3 months
            'months': 3
        },
        {
            'name': '3-6 Months Ago',
            'candles': list(all_candles[:midpoint_idx]),  # Older 3 months
            'months': 3
        },
        {
            'name': 'Past 6 Months',
            'candles': list(all_candles),  # All data
            'months': 6
        }
    ]
    
    print("📊 Test periods:")
    for period in test_periods:
        candles = period['candles']
        start_date = datetime.fromtimestamp(candles[0][0], tz=timezone.utc)
        end_date = datetime.fromtimestamp(candles[-1][0], tz=timezone.utc)
        print(f"   {period['name']:15} | {len(candles):,} candles | {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    print()
    
    # Step 2: Build all test configurations
    print("📋 STEP 2: Building test configurations...")
    test_configs = []
    
    position_counter = 0
    for period in test_periods:
        for strategy in STRATEGIES:
            test_configs.append((
                strategy,
                period['candles'],
                starting_currency,
                granularity,
                period['months'],
                period['name'],
                position_counter
            ))
            position_counter += 1
    
    print(f"   Total tests to run: {len(test_configs)} (3 strategies × 3 periods)")
    print()
    
    # Step 3: Run tests in parallel
    print("🚀 STEP 3: Running backtests in parallel...")
    print()
    
    # Use fewer processes to avoid overwhelming the system
    num_processes = min(mp.cpu_count(), len(test_configs))
    print(f"   Using {num_processes} parallel processes")
    print()
    
    with mp.Pool(processes=num_processes) as pool:
        if HAS_TQDM:
            results = list(tqdm(
                pool.imap(run_single_backtest_with_progress, test_configs),
                total=len(test_configs),
                desc="Overall Progress",
                position=len(test_configs) + 1
            ))
        else:
            results = pool.map(run_single_backtest_with_progress, test_configs)
    
    print()
    print("✅ All backtests complete!")
    print()
    
    # Step 4: Save results
    results_file = f"{RESULTS_DIR}/results_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"💾 Results saved to: {results_file}")
    print()
    
    # Step 5: Print summary
    print("=" * 80)
    print("📊 SUMMARY REPORT")
    print("=" * 80)
    print()
    
    # Group by strategy
    for strategy in STRATEGIES:
        print(f"🏆 {strategy['name']}")
        print(f"   {strategy['description']}")
        print()
        
        strategy_results = [r for r in results if r.get('strategy_name') == strategy['name']]
        
        for result in strategy_results:
            if result.get('success'):
                period = result['period_name']
                apy = result['apy_usd']
                trades = result['trades']
                win_rate = result['win_rate']
                final = result['final_value']
                candles = result['candles_processed']
                
                print(f"   📅 {period:15} | APY: {apy:7.1f}% | Trades: {trades:3d} | Win: {win_rate:5.1f}% | Final: ${final:8.2f} | {candles:,} candles")
            else:
                print(f"   📅 {result['period_name']:15} | ❌ ERROR: {result.get('error', 'Unknown')}")
        
        print()
    
    # Best performers
    successful = [r for r in results if r.get('success') and r.get('apy_usd') is not None]
    if successful:
        best_apy = max(successful, key=lambda x: x['apy_usd'])
        best_trades = max(successful, key=lambda x: x['trades'])
        best_win = max(successful, key=lambda x: x['win_rate'])
        
        print("=" * 80)
        print("🥇 BEST PERFORMERS")
        print("=" * 80)
        print(f"   Highest APY:    {best_apy['strategy_name']} ({best_apy['period_name']}) → {best_apy['apy_usd']:.1f}%")
        print(f"   Most Trades:    {best_trades['strategy_name']} ({best_trades['period_name']}) → {best_trades['trades']} trades")
        print(f"   Best Win Rate:  {best_win['strategy_name']} ({best_win['period_name']}) → {best_win['win_rate']:.1f}%")
        print()
    
    print("✅ Analysis complete!")


if __name__ == '__main__':
    # Required for multiprocessing on macOS
    mp.set_start_method('spawn', force=True)
    main()
