#!/usr/bin/env python3
"""
Backtesting Library - Reusable backtesting framework for trading strategies.

This library provides a strategy-agnostic backtesting framework that can test
any trading strategy with different parameters and loss tolerances.
"""

import multiprocessing as mp
from datetime import datetime, timezone, timedelta
from typing import List, Tuple, Dict, Any, Type
from trader_bot import Bot
from interfaces.PaperTradingInterface import PaperTradingInterface
from strategies.base import Strategy
from CBData import CoinbaseDataFetcher
import sys
from io import StringIO


def load_historical_data(months: int = 3, granularity: str = '5m', product_id: str = 'BTC-USD', age_days: int = 0) -> List:
    """
    Load historical data to be shared across all tests.
    
    Args:
        months: Number of months of historical data to load
        granularity: Candle interval ('1m', '5m', '15m', '1h', '1d')
        product_id: Trading pair (e.g., 'BTC-USD')
        age_days: How many days in the past the period should END (0 = now, 90 = 90 days ago)
    
    Returns:
        List of candles [timestamp, low, high, open, close, volume]
    """
    now = datetime.now(timezone.utc)
    end_date = now - timedelta(days=age_days)
    start_date = end_date - timedelta(days=30 * months)
    
    print(f"📦 Loading {months} months of {granularity} candles for {product_id}...")
    print(f"📅 Date range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    if age_days > 0:
        print(f"📍 Test period ends {age_days} days ago")
    
    api = CoinbaseDataFetcher(product_id=product_id)
    candles = api.fetch_candles(
        granularity=granularity,
        start=start_date,
        end=end_date
    )
    
    print(f"✅ Loaded {len(candles)} candles")
    return candles


def calculate_metrics(bot: Bot, candles: List, trades: int, wins: int, losses: int, 
                     rejected_buys: int, rejected_sells: int, 
                     granularity: str, starting_currency: float, months: int) -> Dict[str, Any]:
    """
    Calculate comprehensive backtest metrics using dual baseline system.
    
    Args:
        bot: The trading bot instance
        candles: Historical candle data
        trades: Total number of executed trades
        wins: Number of winning cycles
        losses: Number of losing cycles
        rejected_buys: Number of rejected buy attempts
        rejected_sells: Number of rejected sell attempts
        granularity: Candle interval ('1m', '5m', '15m', '1h', '1d')
        starting_currency: Initial starting currency
        months: Time period in months
    
    Returns:
        Dictionary containing all calculated metrics
    """
    years = months / 12
    current_price = candles[-1][4]
    
    # Get final baseline values from bot (dual baseline system)
    final_usd_baseline = bot.currency_baseline
    final_crypto_baseline = bot.asset_baseline
    initial_usd_baseline = bot.initial_usd_baseline
    initial_crypto_baseline = bot.initial_crypto_baseline
    
    # Calculate current value based on position
    if bot.position == "short":
        current_value = bot.currency
    else:
        current_value = bot.asset * current_price
    
    # Calculate APY using dual baselines - use safe calculation to avoid overflow
    import math
    apy_usd = 0.0
    apy_btc = 0.0
    
    # Convert years to seconds for period comparison  
    total_seconds = years * 365.25 * 24 * 3600
    
    if initial_usd_baseline > 0 and years > 0:
        try:
            ratio = final_usd_baseline / initial_usd_baseline
            # For periods < 1 day, use simple linear extrapolation to avoid overflow
            if total_seconds < 86400:  # Less than 1 day
                return_pct = (ratio - 1) * 100
                apy_usd = return_pct * (365.25 * 24 * 3600 / total_seconds)
            else:
                # For longer periods, use proper compound APY
                if ratio > 0:
                    apy_usd = ((ratio ** (1 / years)) - 1) * 100
        except (OverflowError, ValueError):
            apy_usd = 0.0
    
    if initial_crypto_baseline > 0 and years > 0:
        try:
            ratio = final_crypto_baseline / initial_crypto_baseline
            # For periods < 1 day, use simple linear extrapolation to avoid overflow  
            if total_seconds < 86400:  # Less than 1 day
                return_pct = (ratio - 1) * 100
                apy_btc = return_pct * (365.25 * 24 * 3600 / total_seconds)
            else:
                # For longer periods, use proper compound APY
                if ratio > 0:
                    apy_btc = ((ratio ** (1 / years)) - 1) * 100
        except (OverflowError, ValueError):
            apy_btc = 0.0
    
    # Calculate return percentages
    value_return = ((current_value - initial_usd_baseline) / initial_usd_baseline) * 100
    baseline_return_usd = ((final_usd_baseline - initial_usd_baseline) / initial_usd_baseline) * 100
    baseline_return_btc = ((final_crypto_baseline - initial_crypto_baseline) / initial_crypto_baseline) * 100
    
    # Calculate win rate based on complete cycles
    complete_cycles = wins + losses
    win_rate = (wins / complete_cycles * 100) if complete_cycles > 0 else 0
    
    # Calculate average profit per complete cycle
    total_profit = current_value - initial_usd_baseline
    avg_profit = total_profit / complete_cycles if complete_cycles > 0 else 0
    
    # Calculate longest idle time
    granularity_minutes = {'1m': 1, '5m': 5, '15m': 15, '1h': 60, '6h': 360, '1d': 1440}.get(granularity, 5)
    max_idle_minutes = bot.max_idle_candles * granularity_minutes
    idle_days = max_idle_minutes // 1440
    idle_hours = (max_idle_minutes % 1440) // 60
    idle_mins = max_idle_minutes % 60
    
    if idle_days > 0:
        longest_idle_str = f"{idle_days}d {idle_hours}h {idle_mins}m"
    elif idle_hours > 0:
        longest_idle_str = f"{idle_hours}h {idle_mins}m"
    else:
        longest_idle_str = f"{idle_mins}m"
    
    return {
        'initial_usd_baseline': initial_usd_baseline,
        'initial_crypto_baseline': initial_crypto_baseline,
        'final_usd_baseline': final_usd_baseline,
        'final_crypto_baseline': final_crypto_baseline,
        'current_value': current_value,
        'baseline_return_usd_pct': baseline_return_usd,
        'baseline_return_btc_pct': baseline_return_btc,
        'value_return_pct': value_return,
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
        'longest_idle_time': longest_idle_str,
        'max_idle_candles': bot.max_idle_candles,
        'max_idle_minutes': max_idle_minutes,
        'success': True
    }


def run_single_backtest(strategy_class: Type[Strategy], strategy_params: Dict[str, Any],
                       candles: List, starting_currency: float, loss_tolerance: float,
                       fee_rate: float = 0.025, pair: str = "BTC-USD",
                       min_candles: int = 35, months: int = 3, granularity: str = '5m') -> Dict[str, Any]:
    """
    Run a single backtest with a specific strategy and parameters.
    
    Args:
        strategy_class: Strategy class to instantiate
        strategy_params: Parameters to pass to strategy constructor
        candles: Historical candle data
        starting_currency: Starting USD amount
        loss_tolerance: Loss tolerance (0.0 = never take loss)
        fee_rate: Trading fee rate
        pair: Trading pair
        min_candles: Minimum candles needed before trading
        months: Time period for APY calculation
    
    Returns:
        Dictionary containing backtest results and metrics
    """
    try:
        # Suppress all print output during backtest
        old_stdout = sys.stdout
        sys.stdout = StringIO()
        
        # Get initial price from early candles for baseline calculation
        initial_price = candles[min_candles][4] if len(candles) > min_candles else candles[0][4]
        
        # Create interface with starting balance, then create bot
        interface = PaperTradingInterface(starting_currency=starting_currency, starting_asset=0.0)
        bot = Bot(
            interface=interface,
            strategy=strategy_class,
            pair=pair,
            fee_rate=fee_rate,
            fee_in_percent=True,
            loss_tolerance=loss_tolerance,
            strategy_params=strategy_params,
            initial_price=initial_price
        )
        
        # Verify configuration
        # Track metrics
        trades = 0
        wins = 0
        losses = 0
        rejected_buys = 0
        rejected_sells = 0
        cycle_start_value = starting_currency
        cycle_start_value = starting_currency
        initial_usd = starting_currency
        last_usd_held = starting_currency
        initial_btc = None
        
        # Simulate trading through all candles
        # Use slice once per iteration (Python slicing is optimized for this pattern)
        for i in range(min_candles, len(candles)):
            candle = candles[i]
            window = candles[:i+1]
            current_price = candle[4]
            # Update idle time tracking (mimics bot's _check_signals_on_new_candle)
            bot.candles_since_last_trade += 1
            if bot.candles_since_last_trade > bot.max_idle_candles:
                bot.max_idle_candles = bot.candles_since_last_trade
            
            # Check buy signal
            if bot.position == "short" and bot.buy_signal(window):
                cycle_start_value = bot.currency
                if bot.execute_buy(current_price):
                    trades += 1
                    # Note: bot.execute_buy already resets candles_since_last_trade
                else:
                    rejected_buys += 1
            
            # Check sell signal
            elif bot.position == "long" and bot.sell_signal(window):
                if bot.execute_sell(current_price):
                    trades += 1
                    profit = bot.currency - cycle_start_value
                    if profit > 0:
                        wins += 1
                    else:
                        losses += 1
                    # Note: bot.execute_sell already resets candles_since_last_trade
                else:
                    rejected_sells += 1
                    rejected_sells += 1
        
        # Restore stdout
        sys.stdout = old_stdout
        # Calculate metrics
        metrics = calculate_metrics(
            bot, candles, trades, wins, losses,
            rejected_buys, rejected_sells,
            granularity, starting_currency, months
        )
        
        # Add strategy info
        metrics['strategy'] = strategy_class.__name__
        metrics['strategy_params'] = strategy_params
        metrics['loss_tolerance'] = loss_tolerance
        metrics['loss_tolerance_pct'] = loss_tolerance * 100
        
        return metrics
        
    except Exception as e:
        sys.stdout = old_stdout
        return {
            'strategy': strategy_class.__name__,
            'strategy_params': strategy_params,
            'loss_tolerance': loss_tolerance,
            'loss_tolerance_pct': loss_tolerance * 100,
            'error': str(e),
            'success': False
        }


def run_backtest_wrapper(args: Tuple) -> Dict[str, Any]:
    """
    Wrapper function for multiprocessing.
    Unpacks arguments and calls run_single_backtest.
    """
    (strategy_class, strategy_params, candles, starting_currency, loss_tolerance, 
     fee_rate, pair, min_candles, months, strategy_name, loss_tolerance_pct) = args
    
    result = run_single_backtest(
        strategy_class, strategy_params, candles, starting_currency,
        loss_tolerance, fee_rate, pair, min_candles, months
    )
    
    # Add optional fields if provided
    if strategy_name is not None:
        result['strategy_name'] = strategy_name
    if loss_tolerance_pct is not None:
        result['loss_tolerance_pct'] = loss_tolerance_pct
    
    return result


def parallel_backtest_runner(test_configs: List[Dict[str, Any]], candles: List,
                            starting_currency: float = 1000.0,
                            fee_rate: float = 0.025, pair: str = "BTC-USD",
                            min_candles: int = 35, months: int = 3) -> List[Dict[str, Any]]:
    """
    Run multiple backtests in parallel using multiprocessing.
    
    Args:
        test_configs: List of test configurations, each containing:
            - 'strategy_class': Strategy class
            - 'strategy_params': Dict of strategy parameters
            - 'loss_tolerance': Loss tolerance value
            - 'strategy_name': (optional) Custom name for the strategy
            - 'loss_tolerance_pct': (optional) Loss tolerance as percentage
        candles: Historical candle data
        starting_currency: Starting USD amount
        fee_rate: Trading fee rate
        pair: Trading pair
        min_candles: Minimum candles before trading
        months: Time period for calculations
    
    Returns:
        List of result dictionaries from each backtest
    """

    start_time = datetime.now()

    # Prepare arguments for parallel processing
    args_list = [
        (
            config['strategy_class'],
            config['strategy_params'],
            candles,
            starting_currency,
            config['loss_tolerance'],
            fee_rate,
            pair,
            min_candles,
            months,
            config.get('strategy_name'),  # Optional custom name
            config.get('loss_tolerance_pct')  # Optional pre-calculated percentage
        )
        for config in test_configs
    ]
    
    # Use multiprocessing Pool to run tests in parallel with progress bar
    try:
        from tqdm import tqdm
        use_tqdm = True
    except ImportError:
        use_tqdm = False
        print(f"💡 Install tqdm for progress bars: pip install tqdm")
        print()
    
    with mp.Pool(processes=mp.cpu_count()) as pool:
        if use_tqdm:
            results = list(tqdm(
                pool.imap(run_backtest_wrapper, args_list),
                total=len(args_list),
                desc="Running backtests",
                unit="test"
            ))
        else:
            results = pool.map(run_backtest_wrapper, args_list)
    
    print()
    print("✅ All tests complete!")
    print()
    
    # Print summary of results
    for i, result in enumerate(results, 1):
        if result['success']:
            # Use custom strategy_name if provided, otherwise use strategy class name
            strategy_name = result.get('strategy_name', result['strategy'])
            loss_tol_pct = result.get('loss_tolerance_pct', result['loss_tolerance'] * 100)
            
            print(f"  [{i}/{len(results)}] {strategy_name} @ {loss_tol_pct:.2f}% loss → "
                  f"APY_USD: {result['apy_usd']:.1f}%, Trades: {result['trades']}, "
                  f"Rejected: {result['rejected_buys']}B/{result['rejected_sells']}S")
        else:
            print(f"  [{i}/{len(results)}] FAILED: {result.get('error', 'Unknown error')}")
    print()

    elapsed_time = datetime.now() - start_time
    elapsed_time = elapsed_time.total_seconds()
    
    print(f"⏱️  Total backtest time: {elapsed_time:.1f} seconds")
    print(f"⚡ Average time per test: {elapsed_time/len(test_configs):.1f} seconds")
    print()
    
    return results
