#!/usr/bin/env python3
"""
Compare Grumpy Mom vs Greedy Trend Mom at 1m and 5m granularity

Greedy Trend Mom = Grumpy Mom + Trend Filter:
- Greedy BUY only when price > SMA (uptrend)
- Greedy SELL only when price < SMA (downtrend)
- Don't fight the trend with greedy trades

Tests across 3 periods:
- Past 3 months (3-0 months ago)
- 3-6 months ago
- Past 6 months (full period)

At 2 granularities: 1m and 5m
"""

import os
import sys
import json
from datetime import datetime, timezone, timedelta
from multiprocessing import Pool, cpu_count
from tqdm import tqdm

from CBData import CoinbaseDataFetcher
from trader_bot import Bot
from interfaces.PaperTradingInterface import PaperTradingInterface
from strategies.greedy_momentum import GreedyMomentumStrategy
from strategies.experimental_momentum import ExperimentalMomentumStrategy


# Strategy configurations
STRATEGIES = {
    'Grumpy Mom': {
        'class': GreedyMomentumStrategy,
        'params_1m': {
            'period': 14,
            'patience_candles': 1440,
            'profit_margin': 1.0,
            'buy_threshold': 1.0,
            'sell_threshold': -1.0
        },
        'params_5m': {
            'period': 14,
            'patience_candles': 288,
            'profit_margin': 1.0,
            'buy_threshold': 1.0,
            'sell_threshold': -1.0
        }
    },
    'Greedy Trend Mom': {
        'class': ExperimentalMomentumStrategy,
        'params_1m': {
            'period': 14,
            'patience_candles': 1440,
            'profit_margin': 1.0,
            'buy_threshold': 1.0,
            'sell_threshold': -1.0,
            'trend_period': 200,
            'require_trend_alignment': True
        },
        'params_5m': {
            'period': 14,
            'patience_candles': 288,
            'profit_margin': 1.0,
            'buy_threshold': 1.0,
            'sell_threshold': -1.0,
            'trend_period': 200,
            'require_trend_alignment': True
        }
    }
}

# Time periods
PERIODS = {
    'Past 3 Months': {'start_days': 90, 'end_days': 0},
    '3-6 Months Ago': {'start_days': 180, 'end_days': 90},
    'Past 6 Months': {'start_days': 180, 'end_days': 0}
}


def run_single_backtest(args):
    """Run a single backtest - designed to be called in parallel."""
    strategy_name, strategy_class, strategy_params, granularity, period_name, candles = args
    
    try:
        # Create paper trading interface with $10000 starting balance
        interface = PaperTradingInterface(starting_currency=10000.0, starting_asset=0.0)
        
        # Get initial price for baselines
        initial_price = candles[0][4]
        
        # Create bot with strategy
        bot = Bot(
            interface=interface,
            strategy=strategy_class,
            strategy_params=strategy_params,
            fee_rate=0.025,  # 0.025%
            loss_tolerance=0.0,
            initial_price=initial_price
        )
        
        # Minimum candles needed
        min_candles = max(35, strategy_params.get('volatility_baseline', 200) + 10)
        
        # Run backtest using correct API
        trades = 0
        wins = 0
        losses = 0
        rejected_sells = 0
        cycle_start_value = bot.currency
        
        for i in range(min_candles, len(candles)):
            candle = candles[i]
            window = candles[:i+1]
            current_price = candle[4]
            
            # Check buy signal (when holding USD)
            if bot.position == "short" and bot.buy_signal(window):
                cycle_start_value = bot.currency
                bot.execute_buy(current_price)  # Will be rejected if would result in loss
            
            # Check sell signal (when holding BTC)
            elif bot.position == "long" and bot.sell_signal(window):
                pre_sell_value = cycle_start_value
                if bot.execute_sell(current_price):
                    # Trade was executed (not rejected by loss_tolerance)
                    trades += 1
                    # With loss_tolerance=0, this should always be a win
                    if bot.currency > pre_sell_value:
                        wins += 1
                    else:
                        losses += 1
                else:
                    # Trade was rejected due to loss_tolerance
                    rejected_sells += 1
        
        # Calculate final value
        final_price = candles[-1][4]
        if bot.position == "short":
            final_value = bot.currency
        else:
            final_value = bot.asset * final_price
        
        initial_value = 10000.0
        profit_pct = ((final_value - initial_value) / initial_value) * 100
        
        # APY calculation
        minutes_per_candle = 1 if granularity == '1m' else 5
        total_minutes = len(candles) * minutes_per_candle
        days = total_minutes / (60 * 24)
        
        if days > 1:
            years = days / 365.0
            if final_value > 0:
                apy = ((final_value / initial_value) ** (1 / years) - 1) * 100
            else:
                apy = -100.0
        else:
            apy = profit_pct * 365
        
        win_rate = (wins / trades * 100) if trades > 0 else 0
        
        return {
            'strategy': strategy_name,
            'granularity': granularity,
            'period': period_name,
            'apy': apy,
            'profit_pct': profit_pct,
            'trades': trades,
            'wins': wins,
            'losses': losses,
            'rejected_sells': rejected_sells,
            'win_rate': win_rate,
            'final_value': final_value,
            'candles': len(candles),
            'days': days,
            'success': True
        }
        
    except Exception as e:
        import traceback
        return {
            'strategy': strategy_name,
            'granularity': granularity,
            'period': period_name,
            'error': str(e),
            'traceback': traceback.format_exc(),
            'success': False
        }


def main():
    print("=" * 80)
    print("📊 GRUMPY MOM vs GREEDY TREND MOM COMPARISON")
    print("=" * 80)
    print()
    print("Greedy Trend Mom = Grumpy Mom + TREND FILTER:")
    print("  • Same greedy parameters (period=14, margin=1.0%, thresholds=±1.0)")
    print("  • Greedy BUY only when price > SMA (uptrend)")
    print("  • Greedy SELL only when price < SMA (downtrend)")
    print("  • Trade with the trend, not against it")
    print()
    
    # Fetch all data upfront
    fetcher = CoinbaseDataFetcher(product_id='BTC-USD')
    now = datetime.now(timezone.utc)
    
    print("📦 Loading candle data...")
    
    # Load 6 months of data for both granularities
    start_6m = now - timedelta(days=180)
    start_3m = now - timedelta(days=90)
    
    print("   Fetching 6 months of 1m candles...")
    candles_1m_6m = fetcher.fetch_candles(start_6m, now, '1m')
    print(f"   ✅ {len(candles_1m_6m):,} 1m candles loaded")
    
    print("   Fetching 6 months of 5m candles...")
    candles_5m_6m = fetcher.fetch_candles(start_6m, now, '5m')
    print(f"   ✅ {len(candles_5m_6m):,} 5m candles loaded")
    
    # Slice candles for different periods
    # Find the split point for 3 months
    split_timestamp = (now - timedelta(days=90)).timestamp()
    
    # 1m slices
    split_idx_1m = next((i for i, c in enumerate(candles_1m_6m) if c[0] >= split_timestamp), len(candles_1m_6m) // 2)
    candles_1m_3_6 = candles_1m_6m[:split_idx_1m]  # Older half
    candles_1m_0_3 = candles_1m_6m[split_idx_1m:]  # Recent half
    
    # 5m slices
    split_idx_5m = next((i for i, c in enumerate(candles_5m_6m) if c[0] >= split_timestamp), len(candles_5m_6m) // 2)
    candles_5m_3_6 = candles_5m_6m[:split_idx_5m]
    candles_5m_0_3 = candles_5m_6m[split_idx_5m:]
    
    print(f"\n   1m splits: 3-6mo={len(candles_1m_3_6):,}, 0-3mo={len(candles_1m_0_3):,}, 6mo={len(candles_1m_6m):,}")
    print(f"   5m splits: 3-6mo={len(candles_5m_3_6):,}, 0-3mo={len(candles_5m_0_3):,}, 6mo={len(candles_5m_6m):,}")
    
    # Build test configurations
    candle_map = {
        ('1m', 'Past 3 Months'): candles_1m_0_3,
        ('1m', '3-6 Months Ago'): candles_1m_3_6,
        ('1m', 'Past 6 Months'): candles_1m_6m,
        ('5m', 'Past 3 Months'): candles_5m_0_3,
        ('5m', '3-6 Months Ago'): candles_5m_3_6,
        ('5m', 'Past 6 Months'): candles_5m_6m,
    }
    
    # Build all test cases
    test_cases = []
    for strategy_name, config in STRATEGIES.items():
        for granularity in ['1m', '5m']:
            params = config[f'params_{granularity}']
            for period_name in ['Past 3 Months', '3-6 Months Ago', 'Past 6 Months']:
                candles = candle_map[(granularity, period_name)]
                test_cases.append((
                    strategy_name,
                    config['class'],
                    params,
                    granularity,
                    period_name,
                    candles
                ))
    
    print(f"\n🔄 Running {len(test_cases)} backtests in parallel...")
    print()
    
    # Run in parallel
    num_workers = min(cpu_count(), len(test_cases))
    with Pool(processes=num_workers) as pool:
        results = list(tqdm(
            pool.imap(run_single_backtest, test_cases),
            total=len(test_cases),
            desc="Overall Progress"
        ))
    
    # Organize results
    results_by_strat = {}
    for r in results:
        if r['success']:
            key = (r['strategy'], r['granularity'])
            if key not in results_by_strat:
                results_by_strat[key] = {}
            results_by_strat[key][r['period']] = r
    
    # Print results
    print("\n" + "=" * 100)
    print("📊 RESULTS COMPARISON")
    print("=" * 100)
    
    for granularity in ['1m', '5m']:
        print(f"\n{'─' * 100}")
        print(f"⏱️  GRANULARITY: {granularity}")
        print(f"{'─' * 100}")
        
        for strategy_name in STRATEGIES.keys():
            key = (strategy_name, granularity)
            if key not in results_by_strat:
                continue
            
            print(f"\n🏆 {strategy_name}")
            strat_config = STRATEGIES[strategy_name]
            params = strat_config[f'params_{granularity}']
            if 'trend_period' in params:
                print(f"   margin={params['profit_margin']}%, trend_sma={params['trend_period']}, patience={params['patience_candles']}")
            else:
                print(f"   margin={params['profit_margin']}%, patience={params['patience_candles']}")
            
            for period_name in ['Past 3 Months', '3-6 Months Ago', 'Past 6 Months']:
                r = results_by_strat[key].get(period_name)
                if r:
                    rejected = r.get('rejected_sells', 0)
                    print(f"   📅 {period_name:<15} | APY: {r['apy']:>7.1f}% | Trades: {r['trades']:>3} | Win: {r['win_rate']:>5.1f}% | Rejected: {rejected:>3} | Final: ${r['final_value']:>8.2f}")
    
    # Summary comparison
    print("\n" + "=" * 100)
    print("🏁 HEAD-TO-HEAD COMPARISON")
    print("=" * 100)
    
    for granularity in ['1m', '5m']:
        print(f"\n⏱️  {granularity} Granularity:")
        print(f"   {'Period':<18} {'Grumpy Mom APY':>15} {'Greedy Trend APY':>18} {'Winner':>15}")
        print(f"   {'-' * 70}")
        
        grumpy_key = ('Grumpy Mom', granularity)
        exp_key = ('Greedy Trend Mom', granularity)
        
        for period_name in ['Past 3 Months', '3-6 Months Ago', 'Past 6 Months']:
            grumpy = results_by_strat.get(grumpy_key, {}).get(period_name)
            exp = results_by_strat.get(exp_key, {}).get(period_name)
            
            if grumpy and exp:
                g_apy = grumpy['apy']
                e_apy = exp['apy']
                if g_apy > e_apy:
                    winner = f"Grumpy (+{g_apy - e_apy:.1f}%)"
                else:
                    winner = f"Greedy (+{e_apy - g_apy:.1f}%)"
                print(f"   {period_name:<18} {g_apy:>14.1f}% {e_apy:>17.1f}% {winner:>15}")
    
    # Save results
    output_dir = 'backtest_results/mom_comparison'
    os.makedirs(output_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M')
    output_file = f'{output_dir}/results_{timestamp}.json'
    
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n💾 Results saved to: {output_file}")
    print("\n✅ Comparison complete!")


if __name__ == '__main__':
    main()
