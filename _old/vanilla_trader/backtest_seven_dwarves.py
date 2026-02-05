#!/usr/bin/env python3
"""
🧝 THE SEVEN DWARVES (+3 FORGOTTEN ONES) BACKTEST 🧝

Because it's 1:30am and why not.

The Famous Seven Dwarves of Trading:
1. Grumpy Mom      - The original, the legend (period=14, patience=1440, margin=1.0%)
2. Doc Mom         - The wise elder, more conservative (period=20, patience=2160, margin=1.5%)
3. Happy Mom       - The optimist, quick to buy (period=10, patience=1200, margin=0.75%)
4. Sleepy Mom      - Very patient, waits forever (period=14, patience=2880, margin=1.25%)
5. Bashful Mom     - Shy, needs bigger moves (period=14, patience=1440, margin=1.5%)
6. Sneezy Mom      - Twitchy, shorter period (period=9, patience=1080, margin=0.8%)
7. Dopey Mom       - Simple, lower thresholds (period=14, patience=1440, margin=0.5%)

The Forgotten Dwarves:
8. Cranky Mom      - Grumpy's cousin (period=12, patience=1320, margin=1.1%)
9. Stumpy Mom      - Short and stubby period (period=7, patience=960, margin=0.9%)
10. Dizzy Mom      - All over the place (period=18, patience=1800, margin=1.3%)

Testing: 1 year of 1m candles ending now
"""

import os
import sys
from datetime import datetime, timezone, timedelta
from multiprocessing import Pool, cpu_count

from CBData import CoinbaseDataFetcher
from trader_bot import Bot
from interfaces.PaperTradingInterface import PaperTradingInterface
from strategies.greedy_momentum import GreedyMomentumStrategy


# 🧝 THE LEGENDARY DWARVES 🧝
DWARVES = {
    # The Original 7 Dwarves
    '👿 Grumpy Mom': {
        'description': 'The original, the legend',
        'params': {
            'period': 14,
            'patience_candles': 1440,  # 1 day at 1m
            'profit_margin': 1.0,
            'buy_threshold': 1.0,
            'sell_threshold': -1.0
        }
    },
    '👨‍⚕️ Doc Mom': {
        'description': 'The wise elder, more conservative',
        'params': {
            'period': 20,
            'patience_candles': 2160,  # 1.5 days
            'profit_margin': 1.5,
            'buy_threshold': 1.2,
            'sell_threshold': -1.2
        }
    },
    '😄 Happy Mom': {
        'description': 'The optimist, quick to buy',
        'params': {
            'period': 10,
            'patience_candles': 1200,  # 20 hours
            'profit_margin': 0.75,
            'buy_threshold': 0.8,
            'sell_threshold': -0.8
        }
    },
    '😴 Sleepy Mom': {
        'description': 'Very patient, waits forever',
        'params': {
            'period': 14,
            'patience_candles': 2880,  # 2 days
            'profit_margin': 1.25,
            'buy_threshold': 1.0,
            'sell_threshold': -1.0
        }
    },
    '😳 Bashful Mom': {
        'description': 'Shy, needs bigger moves',
        'params': {
            'period': 14,
            'patience_candles': 1440,
            'profit_margin': 1.5,
            'buy_threshold': 1.3,
            'sell_threshold': -1.3
        }
    },
    '🤧 Sneezy Mom': {
        'description': 'Twitchy, shorter period',
        'params': {
            'period': 9,
            'patience_candles': 1080,  # 18 hours
            'profit_margin': 0.8,
            'buy_threshold': 0.9,
            'sell_threshold': -0.9
        }
    },
    '🥴 Dopey Mom': {
        'description': 'Simple, lower thresholds',
        'params': {
            'period': 14,
            'patience_candles': 1440,
            'profit_margin': 0.5,
            'buy_threshold': 0.6,
            'sell_threshold': -0.6
        }
    },
    
    # The 3 Forgotten Dwarves
    '😤 Cranky Mom': {
        'description': "Grumpy's lesser-known cousin",
        'params': {
            'period': 12,
            'patience_candles': 1320,  # 22 hours
            'profit_margin': 1.1,
            'buy_threshold': 1.0,
            'sell_threshold': -1.0
        }
    },
    '🦵 Stumpy Mom': {
        'description': 'Short and stubby period',
        'params': {
            'period': 7,
            'patience_candles': 960,  # 16 hours
            'profit_margin': 0.9,
            'buy_threshold': 0.85,
            'sell_threshold': -0.85
        }
    },
    '😵 Dizzy Mom': {
        'description': 'All over the place',
        'params': {
            'period': 18,
            'patience_candles': 1800,  # 30 hours
            'profit_margin': 1.3,
            'buy_threshold': 1.15,
            'sell_threshold': -1.15
        }
    }
}


def run_single_backtest(args):
    """Run a single backtest for a dwarf."""
    dwarf_name, dwarf_config, candles = args
    
    try:
        # Suppress print output
        import io
        import contextlib
        
        # Create paper trading interface with $10000 starting balance
        interface = PaperTradingInterface(starting_currency=10000.0, starting_asset=0.0)
        
        # Get initial price for baselines
        initial_price = candles[0][4]
        
        # Create bot with strategy
        with contextlib.redirect_stdout(io.StringIO()):
            bot = Bot(
                interface=interface,
                strategy=GreedyMomentumStrategy,
                strategy_params=dwarf_config['params'],
                fee_rate=0.025,  # 0.025%
                loss_tolerance=0.0,
                initial_price=initial_price
            )
        
        # Minimum candles needed
        min_candles = 35
        
        # Run backtest
        trades = 0
        wins = 0
        losses = 0
        rejected_sells = 0
        rejected_buys = 0
        cycle_start_value = bot.currency
        
        for i in range(min_candles, len(candles)):
            candle = candles[i]
            window = candles[:i+1]
            current_price = candle[4]
            
            # Update idle tracking
            bot.candles_since_last_trade += 1
            if bot.candles_since_last_trade > bot.max_idle_candles:
                bot.max_idle_candles = bot.candles_since_last_trade
            
            # Check buy signal (when holding USD)
            if bot.position == "short" and bot.buy_signal(window):
                cycle_start_value = bot.currency
                if bot.execute_buy(current_price):
                    pass  # Buy executed
                else:
                    rejected_buys += 1
            
            # Check sell signal (when holding BTC)
            elif bot.position == "long" and bot.sell_signal(window):
                pre_sell_value = cycle_start_value
                if bot.execute_sell(current_price):
                    trades += 1
                    if bot.currency > pre_sell_value:
                        wins += 1
                    else:
                        losses += 1
                else:
                    rejected_sells += 1
        
        # Calculate final value
        final_price = candles[-1][4]
        if bot.position == "short":
            current_portfolio_usd = bot.currency
            current_portfolio_btc = bot.currency / final_price if final_price > 0 else 0
        else:
            current_portfolio_usd = bot.asset * final_price
            current_portfolio_btc = bot.asset
        
        initial_usd = 10000.0
        initial_btc = initial_usd / initial_price
        
        # Calculate returns
        usd_return_pct = ((current_portfolio_usd - initial_usd) / initial_usd) * 100
        btc_return_pct = ((current_portfolio_btc - initial_btc) / initial_btc) * 100
        
        # APY calculation (1 year = 525600 minutes at 1m candles)
        total_minutes = len(candles)
        days = total_minutes / (60 * 24)
        years = days / 365.0
        
        if years > 0 and current_portfolio_usd > 0:
            real_apy = ((current_portfolio_usd / initial_usd) ** (1 / years) - 1) * 100
            btc_apy = ((current_portfolio_btc / initial_btc) ** (1 / years) - 1) * 100
        else:
            real_apy = 0.0
            btc_apy = 0.0
        
        win_rate = (wins / trades * 100) if trades > 0 else 0
        
        # Idle time calculation
        max_idle_hours = bot.max_idle_candles / 60
        max_idle_days = max_idle_hours / 24
        
        return {
            'dwarf': dwarf_name,
            'description': dwarf_config['description'],
            'params': dwarf_config['params'],
            'real_apy': real_apy,
            'btc_apy': btc_apy,
            'usd_return_pct': usd_return_pct,
            'btc_return_pct': btc_return_pct,
            'trades': trades,
            'wins': wins,
            'losses': losses,
            'rejected_buys': rejected_buys,
            'rejected_sells': rejected_sells,
            'win_rate': win_rate,
            'current_portfolio_usd': current_portfolio_usd,
            'current_portfolio_btc': current_portfolio_btc,
            'candles': len(candles),
            'days': days,
            'max_idle_hours': max_idle_hours,
            'max_idle_days': max_idle_days,
            'final_position': bot.position,
            'success': True
        }
        
    except Exception as e:
        import traceback
        return {
            'dwarf': dwarf_name,
            'error': str(e),
            'traceback': traceback.format_exc(),
            'success': False
        }


def main():
    print()
    print("=" * 90)
    print("🧝✨ THE SEVEN DWARVES (+3 FORGOTTEN ONES) BACKTEST ✨🧝")
    print("=" * 90)
    print()
    print("Because it's 1:30am and why not.")
    print()
    print("📜 THE LEGENDARY DWARVES:")
    print("-" * 90)
    for name, config in DWARVES.items():
        params = config['params']
        print(f"  {name:20} - {config['description']}")
        print(f"                       period={params['period']}, patience={params['patience_candles']}, "
              f"margin={params['profit_margin']}%, thresholds=±{params['buy_threshold']}")
    print()
    
    # Load 1 year of 1m candles
    print("=" * 90)
    print("📦 LOADING DATA: 1 Year of 1-minute candles")
    print("=" * 90)
    
    now = datetime.now(timezone.utc)
    end_date = now
    start_date = end_date - timedelta(days=365)
    
    print(f"📅 Date range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    print()
    
    api = CoinbaseDataFetcher(product_id='BTC-USD')
    candles = api.fetch_candles(
        granularity='1m',
        start=start_date,
        end=end_date
    )
    
    print(f"✅ Loaded {len(candles):,} candles ({len(candles)/60/24:.1f} days)")
    print()
    
    # Prepare test configurations
    test_configs = [
        (name, config, candles) for name, config in DWARVES.items()
    ]
    
    print("=" * 90)
    print(f"🏃 RUNNING {len(test_configs)} BACKTESTS IN PARALLEL")
    print("=" * 90)
    print()
    
    start_time = datetime.now()
    
    # Run in parallel
    num_workers = min(len(test_configs), cpu_count())
    print(f"⚡ Using {num_workers} parallel workers...")
    print()
    
    with Pool(num_workers) as pool:
        results = pool.map(run_single_backtest, test_configs)
    
    elapsed = (datetime.now() - start_time).total_seconds()
    print(f"⏱️  Completed in {elapsed:.1f} seconds")
    print()
    
    # Sort by Real APY
    successful = [r for r in results if r.get('success')]
    failed = [r for r in results if not r.get('success')]
    successful.sort(key=lambda x: x['real_apy'], reverse=True)
    
    # Print results table
    print("=" * 90)
    print("🏆 RESULTS - SORTED BY REAL APY")
    print("=" * 90)
    print()
    print(f"{'Rank':<5} {'Dwarf':<22} {'Real APY':>10} {'BTC APY':>10} {'Trades':>8} {'Win%':>7} {'Final$':>12} {'Idle':>10}")
    print("-" * 90)
    
    for i, r in enumerate(successful, 1):
        idle_str = f"{r['max_idle_days']:.1f}d" if r['max_idle_days'] >= 1 else f"{r['max_idle_hours']:.1f}h"
        print(f"{i:<5} {r['dwarf']:<22} {r['real_apy']:>9.2f}% {r['btc_apy']:>9.2f}% "
              f"{r['trades']:>8} {r['win_rate']:>6.1f}% ${r['current_portfolio_usd']:>10.2f} {idle_str:>10}")
    
    print()
    
    if failed:
        print("❌ FAILED:")
        for r in failed:
            print(f"  {r['dwarf']}: {r.get('error', 'Unknown error')}")
        print()
    
    # Winner announcement
    if successful:
        winner = successful[0]
        print("=" * 90)
        print("👑 AND THE WINNER IS...")
        print("=" * 90)
        print()
        print(f"  🏆 {winner['dwarf']} 🏆")
        print(f"     \"{winner['description']}\"")
        print()
        print(f"     Real APY:     {winner['real_apy']:.2f}%")
        print(f"     BTC APY:      {winner['btc_apy']:.2f}%")
        print(f"     Final Value:  ${winner['current_portfolio_usd']:.2f}")
        print(f"     Trades:       {winner['trades']} ({winner['wins']} wins, {winner['losses']} losses)")
        print(f"     Win Rate:     {winner['win_rate']:.1f}%")
        print(f"     Max Idle:     {winner['max_idle_days']:.1f} days")
        print()
        
        params = winner['params']
        print(f"     Configuration:")
        print(f"       period={params['period']}, patience={params['patience_candles']}, "
              f"margin={params['profit_margin']}%, thresholds=±{params['buy_threshold']}")
        print()
    
    # Compare to just holding BTC
    btc_start = candles[0][4]
    btc_end = candles[-1][4]
    btc_return = ((btc_end - btc_start) / btc_start) * 100
    
    print("=" * 90)
    print("📊 COMPARISON TO HODL")
    print("=" * 90)
    print(f"   BTC Price Start:  ${btc_start:,.2f}")
    print(f"   BTC Price End:    ${btc_end:,.2f}")
    print(f"   HODL Return:      {btc_return:.2f}%")
    print()
    
    # Count how many dwarves beat HODL
    beat_hodl = [r for r in successful if r['real_apy'] > btc_return]
    print(f"   Dwarves beating HODL: {len(beat_hodl)}/{len(successful)}")
    
    if beat_hodl:
        print(f"   Winners: {', '.join([r['dwarf'].split(' ')[1] for r in beat_hodl])}")
    print()
    
    print("=" * 90)
    print("✨ May the best dwarf win! ✨")
    print("=" * 90)


if __name__ == '__main__':
    main()
