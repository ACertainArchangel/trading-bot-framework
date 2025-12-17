#!/usr/bin/env python3
"""
Backtest Greedy Strategies

Tests the Greedy Momentum and Greedy EMA Cross strategies with different parameter combinations:
- Various momentum periods / EMA periods
- Different patience levels (how long to wait before becoming greedy)
- Different profit margins for greedy trades
- Multiple loss tolerance values

This helps find the optimal balance between patience and greed.
"""

import multiprocessing as mp
from datetime import datetime
from strategies.greedy_momentum import GreedyMomentumStrategy
from strategies.greedy_ema_cross import GreedyEMACrossStrategy
from backtest_lib import load_historical_data, parallel_backtest_runner


def main():
    print("=" * 80)
    print("🧪 GREEDY STRATEGIES BACKTEST")
    print("=" * 80)
    print()
    
    # Load historical data once (shared across all tests)
    candles = load_historical_data(months=3, granularity='5m')
    print()
    
    # Define parameter combinations to test
    base_configs = []
    
    # Different patience levels (in candles at 5min intervals)
    # 144 = 12 hours, 288 = 1 day, 576 = 2 days, 1152 = 4 days
    patience_levels = [144, 288, 576, 1152]
    
    # Different profit margins for greedy trades
    profit_margins = [0.3, 0.5, 0.75, 1.0]
    
    # === GREEDY MOMENTUM ===
    # Different momentum periods
    momentum_periods = [10, 14, 20]
    
    # Momentum thresholds (keeping consistent)
    buy_threshold = 2.0
    sell_threshold = -2.0
    
    # Generate all momentum combinations
    for period in momentum_periods:
        for patience in patience_levels:
            for margin in profit_margins:
                base_configs.append({
                    'strategy_class': GreedyMomentumStrategy,
                    'strategy_params': {
                        'period': period,
                        'buy_threshold': buy_threshold,
                        'sell_threshold': sell_threshold,
                        'profit_margin': margin,
                        'patience_candles': patience
                    },
                    'name': f"GreedyMom(p={period}, patience={patience}, margin={margin}%)"
                })
    
    # === GREEDY EMA CROSS ===
    # Different EMA pairs
    ema_pairs = [(9, 21), (12, 26), (50, 200)]
    
    # Generate all EMA combinations
    for fast, slow in ema_pairs:
        for patience in patience_levels:
            for margin in profit_margins:
                base_configs.append({
                    'strategy_class': GreedyEMACrossStrategy,
                    'strategy_params': {
                        'fast': fast,
                        'slow': slow,
                        'profit_margin': margin,
                        'patience_candles': patience
                    },
                    'name': f"GreedyEMA({fast}/{slow}, patience={patience}, margin={margin}%)"
                })
    
    # Loss tolerance values to test
    loss_tolerances = [0.0, 0.001, 0.005, 0.01, 0.025]
    
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
    
    print(f"🚀 Running {len(test_configs)} backtests in parallel...")
    print(f"   • Greedy Momentum: {len(momentum_periods)} periods × {len(patience_levels)} patience × {len(profit_margins)} margins")
    print(f"   • Greedy EMA Cross: {len(ema_pairs)} EMA pairs × {len(patience_levels)} patience × {len(profit_margins)} margins")
    print(f"   • {len(base_configs)} strategy configurations × {len(loss_tolerances)} loss tolerances = {len(test_configs)} total tests")
    print()
    
    # Run all backtests in parallel
    results = parallel_backtest_runner(test_configs, candles)
    
    # Filter successful results (trades >= 1 and APY data exists)
    successful_results = [r for r in results if r.get('success', False) and r.get('trades', 0) >= 1]
    
    if not successful_results:
        print("\n❌ No successful backtests completed.")
        return
    
    print(f"\n✅ Filtered {len(successful_results)}/{len(test_configs)} successful tests (>= 1 trade)")
    print()
    
    # Sort by APY (USD)
    successful_results.sort(key=lambda x: x.get('apy_usd', 0), reverse=True)
    
    # Print summary of all results
    print("=" * 150)
    print("RESULTS - ALL SUCCESSFUL TESTS (sorted by APY)")
    print("=" * 150)
    for i, result in enumerate(successful_results, 1):
        strategy_name = result.get('strategy_name', 'Unknown')
        loss_tol = result.get('loss_tolerance_pct', 0)
        apy = result.get('apy_usd', 0)
        trades = result.get('trades', 0)
        rejected_buys = result.get('rejected_buys', 0)
        rejected_sells = result.get('rejected_sells', 0)
        
        print(f"  [{i}/{len(successful_results)}] {strategy_name} @ {loss_tol:.2f}% loss → "
              f"APY_USD: {apy:.1f}%, Trades: {trades}, Rejected: {rejected_buys}B/{rejected_sells}S")
    
    # Print top 20 performers
    print()
    print("=" * 150)
    print("RESULTS - TOP 20 PERFORMERS")
    print("=" * 150)
    top_20 = successful_results[:20]
    for i, result in enumerate(top_20, 1):
        strategy_name = result.get('strategy_name', 'Unknown')
        loss_tol = result.get('loss_tolerance_pct', 0)
        apy = result.get('apy_usd', 0)
        trades = result.get('trades', 0)
        current_value = result.get('current_value', 0)
        value_return = result.get('value_return_pct', 0)
        rejected_buys = result.get('rejected_buys', 0)
        rejected_sells = result.get('rejected_sells', 0)
        
        # Determine final position
        starting_currency = result.get('starting_currency', 10000)
        final_position = "USD" if abs(current_value - starting_currency) < 1 else "BTC"
        
        print(f"  {i:2d}. {strategy_name:60s} @ {loss_tol:5.2f}% loss → "
              f"APY: {apy:6.1f}%, Return: {value_return:6.1f}%, Trades: {trades:3d}, "
              f"Rejected: {rejected_buys}B/{rejected_sells}S, Final: {final_position}")
    
    # Analyze by parameter
    print()
    print("=" * 150)
    print("BEST PERFORMANCE BY PERIOD")
    print("=" * 150)
    for period in momentum_periods:
        period_results = [r for r in successful_results if f"p={period}" in r.get('strategy_name', '')]
        if period_results:
            best = period_results[0]
            print(f"  Period {period:2d}: {best.get('apy_usd', 0):6.1f}% APY - "
                  f"{best.get('strategy_name', 'Unknown')} @ {best.get('loss_tolerance_pct', 0):.2f}% loss")
    
    print()
    print("=" * 150)
    print("BEST PERFORMANCE BY PATIENCE LEVEL")
    print("=" * 150)
    for patience in patience_levels:
        patience_results = [r for r in successful_results if f"patience={patience}" in r.get('strategy_name', '')]
        if patience_results:
            best = patience_results[0]
            hours = patience * 5 // 60
            print(f"  Patience {patience:4d} candles ({hours:2d}h): {best.get('apy_usd', 0):6.1f}% APY - "
                  f"{best.get('strategy_name', 'Unknown')} @ {best.get('loss_tolerance_pct', 0):.2f}% loss")
    
    print()
    print("=" * 150)
    print("BEST PERFORMANCE BY PROFIT MARGIN")
    print("=" * 150)
    for margin in profit_margins:
        margin_results = [r for r in successful_results if f"margin={margin}%" in r.get('strategy_name', '')]
        if margin_results:
            best = margin_results[0]
            print(f"  Margin {margin:.2f}%: {best.get('apy_usd', 0):6.1f}% APY - "
                  f"{best.get('strategy_name', 'Unknown')} @ {best.get('loss_tolerance_pct', 0):.2f}% loss")
    
    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"backtest_results/greedy_strategies_{timestamp}.txt"
    
    with open(output_file, 'w') as f:
        f.write("=" * 150 + "\n")
        f.write("GREEDY STRATEGIES BACKTEST RESULTS\n")
        f.write("=" * 150 + "\n\n")
        f.write(f"Test configurations: {len(test_configs)}\n")
        f.write(f"Successful tests: {len(successful_results)}\n")
        f.write(f"Data: 3 months, 5-minute candles\n\n")
        
        f.write("TOP 20 PERFORMERS:\n")
        f.write("=" * 150 + "\n")
        for i, result in enumerate(top_20, 1):
            strategy_name = result.get('strategy_name', 'Unknown')
            loss_tol = result.get('loss_tolerance_pct', 0)
            apy = result.get('apy_usd', 0)
            trades = result.get('trades', 0)
            current_value = result.get('current_value', 0)
            value_return = result.get('value_return_pct', 0)
            rejected_buys = result.get('rejected_buys', 0)
            rejected_sells = result.get('rejected_sells', 0)
            
            starting_currency = 1000  # Default from backtest
            final_position = "USD" if abs(current_value - starting_currency) < 1 else "BTC"
            
            f.write(f"  {i:2d}. {strategy_name:60s} @ {loss_tol:5.2f}% loss → "
                   f"APY: {apy:6.1f}%, Return: {value_return:6.1f}%, Trades: {trades:3d}, "
                   f"Rejected: {rejected_buys}B/{rejected_sells}S, Final: {final_position}\n")
        
        f.write("\n")
        f.write("=" * 150 + "\n")
        f.write("ALL RESULTS:\n")
        f.write("=" * 150 + "\n")
        for i, result in enumerate(successful_results, 1):
            strategy_name = result.get('strategy_name', 'Unknown')
            loss_tol = result.get('loss_tolerance_pct', 0)
            apy = result.get('apy_usd', 0)
            trades = result.get('trades', 0)
            rejected_buys = result.get('rejected_buys', 0)
            rejected_sells = result.get('rejected_sells', 0)
            
            f.write(f"  [{i}/{len(successful_results)}] {strategy_name} @ {loss_tol:.2f}% loss → "
                   f"APY_USD: {apy:.1f}%, Trades: {trades}, Rejected: {rejected_buys}B/{rejected_sells}S\n")
    
    print()
    print(f"📁 Results saved to: {output_file}")
    print()


if __name__ == "__main__":
    main()
