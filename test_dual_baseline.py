#!/usr/bin/env python3
"""
Quick test script to verify dual baseline system works correctly.
Runs a single backtest with momentum strategy.
"""

import sys
from datetime import datetime, timedelta
from backtest_lib import load_historical_data, run_single_backtest
from strategies.momentum import MomentumStrategy

def main():
    print("=" * 80)
    print("🧪 TESTING DUAL BASELINE SYSTEM")
    print("=" * 80)
    print()
    
    # Load 1 month of data
    print("📊 Loading 1 month of historical data...")
    months = 1
    candles = load_historical_data(months=months, granularity='5m')
    print(f"✅ Loaded {len(candles)} candles")
    print()
    
    # Run single backtest with momentum strategy
    print("🚀 Running backtest with Momentum Strategy...")
    print("   Parameters: lookback=10, threshold=0.02")
    print("   Starting capital: $10,000")
    print("   Loss tolerance: 1.0%")
    print()
    
    result = run_single_backtest(
        strategy_class=MomentumStrategy,
        strategy_params={'period': 10, 'buy_threshold': 2.0, 'sell_threshold': -2.0},
        candles=candles,
        starting_currency=10000.0,
        loss_tolerance=0.01,
        fee_rate=0.025,
        pair='BTC-USD',
        min_candles=35,
        months=1,
        granularity='5m'
    )
    
    if not result.get('success', False):
        print(f"❌ Test failed: {result.get('error', 'Unknown error')}")
        return 1
    
    print("=" * 80)
    print("✅ TEST RESULTS - DUAL BASELINE SYSTEM")
    print("=" * 80)
    print()
    
    # Verify all new fields are present
    required_fields = [
        'initial_usd_baseline', 'initial_crypto_baseline',
        'final_usd_baseline', 'final_crypto_baseline',
        'apy_usd', 'apy_btc',
        'baseline_return_usd_pct', 'baseline_return_btc_pct',
        'longest_idle_time', 'max_idle_candles', 'max_idle_minutes'
    ]
    
    missing_fields = [f for f in required_fields if f not in result]
    if missing_fields:
        print(f"❌ Missing fields: {', '.join(missing_fields)}")
        return 1
    
    print("📈 BASELINE TRACKING:")
    print(f"   Initial USD Baseline:  ${result['initial_usd_baseline']:.2f}")
    print(f"   Final USD Baseline:    ${result['final_usd_baseline']:.2f}")
    print(f"   USD Return:            {result['baseline_return_usd_pct']:.2f}%")
    print()
    print(f"   Initial BTC Baseline:  {result['initial_crypto_baseline']:.8f} BTC")
    print(f"   Final BTC Baseline:    {result['final_crypto_baseline']:.8f} BTC")
    print(f"   BTC Return:            {result['baseline_return_btc_pct']:.2f}%")
    print()
    
    print("💰 APY CALCULATIONS:")
    print(f"   APY (USD):             {result['apy_usd']:.2f}%")
    print(f"   APY (BTC):             {result['apy_btc']:.2f}%")
    print()
    
    print("⏰ IDLE TIME TRACKING:")
    print(f"   Longest Idle Period:   {result['longest_idle_time']}")
    print(f"   (in candles):          {result['max_idle_candles']}")
    print(f"   (in minutes):          {result['max_idle_minutes']}")
    print()
    
    print("📊 PERFORMANCE METRICS:")
    print(f"   Total Trades:          {result['trades']}")
    print(f"   Win Rate:              {result['win_rate']:.1f}%")
    print(f"   Avg Profit/Trade:      ${result['avg_profit_per_trade']:.2f}")
    print(f"   Current Value:         ${result['current_value']:.2f}")
    print(f"   Value Return:          {result['value_return_pct']:.2f}%")
    print(f"   Final Position:        {result['final_position'].upper()}")
    print()
    
    print("=" * 80)
    print("✅ ALL TESTS PASSED - DUAL BASELINE SYSTEM WORKING!")
    print("=" * 80)
    
    return 0

if __name__ == '__main__':
    sys.exit(main())
