#!/usr/bin/env python3
"""
Generic Test Bot - Paper Trading with Historical Data

Usage:
    python test_bot.py <strategy_name> [options]

Examples:
    python test_bot.py ema_cross --fast 12 --slow 26 --days 90 --port 5003
    python test_bot.py momentum --period 10 --buy_threshold 1.0 --sell_threshold -1.0
    python test_bot.py macd --short_window 12 --long_window 26 --signal_window 9
    python test_bot.py rsi --period 14 --oversold 30 --overbought 70

Options:
    --days N              Number of days of historical data (default: 10)
    --granularity G       Candle size: 1m, 5m, 15m, 1h, 6h, 1d (default: 5m)
    --starting_currency N Starting USD balance (default: 1000.0)
    --fee_rate N          Fee rate as percentage (default: 0.025)
    --loss_tolerance N    Max acceptable loss % (default: 0.0)
    --playback_speed N    Replay speed per candle in seconds (default: 0.001 = fast backtesting)
    --port N              Dashboard port (default: 5003)
    
    Strategy-specific parameters are passed as --param_name value
"""

import sys
import argparse
from datetime import datetime, timezone, timedelta
import threading
import time

from trader_bot import Bot
from interfaces.PaperTradingInterface import PaperTradingInterface
from web_dashboard import initialize_stream, main_logger, socketio, app, config, emit_bot_state
from strategies.ema_cross import EMACrossStrategy
from strategies.greedy_ema_cross import GreedyEMACrossStrategy
from strategies.momentum import MomentumStrategy
from strategies.greedy_momentum import GreedyMomentumStrategy
from strategies.macd import MACDStrategy
from strategies.rsi import RSIStrategy
from strategies.bollinger import BollingerStrategy
from strategies.greedy_macd import GreedyMACDStrategy

# Strategy registry mapping names to classes
STRATEGIES = {
    'ema_cross': EMACrossStrategy,
    'greedy_ema_cross': GreedyEMACrossStrategy,
    'momentum': MomentumStrategy,
    'greedy_momentum': GreedyMomentumStrategy,
    'macd': MACDStrategy,
    'rsi': RSIStrategy,
    'bollinger': BollingerStrategy,
    'greedy_macd': GreedyMACDStrategy
}


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Test trading bot with paper trading on historical data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    # Required
    parser.add_argument('strategy', type=str, choices=STRATEGIES.keys(),
                       help='Strategy to test')
    
    # Optional bot parameters
    parser.add_argument('--instance', type=int, default=1,
                       help='Bot instance number for parallel bots (default: 1)')
    parser.add_argument('--days', type=int, default=10,
                       help='Days of historical data (default: 10)')
    parser.add_argument('--age', type=int, default=0,
                       help='How many days ago the data period should end (default: 0 = now)')
    parser.add_argument('--granularity', type=str, default='5m',
                       choices=['1m', '5m', '15m', '1h', '6h', '1d'],
                       help='Candle granularity (default: 5m)')
    parser.add_argument('--starting_currency', type=float, default=1000.0,
                       help='Starting USD balance (default: 1000.0)')
    parser.add_argument('--fee_rate', type=float, default=0.025,
                       help='Fee rate as percentage (default: 0.025)')
    parser.add_argument('--loss_tolerance', type=float, default=0.0,
                       help='Loss tolerance as percentage (default: 0.0)')
    parser.add_argument('--playback_speed', type=float, default=0.001,
                       help='Playback speed per candle in seconds (default: 0.001 = 1000 candles/sec for fast backtesting)')
    parser.add_argument('--port', type=int, default=5003,
                       help='Dashboard port (default: 5003)')
    
    # Parse known args first, then get remaining for strategy params
    args, unknown = parser.parse_known_args()
    
    # Parse strategy-specific parameters
    strategy_params = {}
    i = 0
    while i < len(unknown):
        if unknown[i].startswith('--'):
            param_name = unknown[i][2:]  # Remove '--'
            if i + 1 < len(unknown) and not unknown[i + 1].startswith('--'):
                value = unknown[i + 1]
                # Try to convert to appropriate type
                try:
                    if '.' in value:
                        strategy_params[param_name] = float(value)
                    else:
                        strategy_params[param_name] = int(value)
                except ValueError:
                    strategy_params[param_name] = value
                i += 2
            else:
                strategy_params[param_name] = True
                i += 1
        else:
            i += 1
    
    args.strategy_params = strategy_params
    return args


def run_test_bot(args):
    """
    Run a test bot with the specified strategy.
    """
    strategy_class = STRATEGIES[args.strategy]
    
    main_logger("=" * 80)
    main_logger(f"📊 PAPER TRADING TEST - {strategy_class.__name__}")
    main_logger("=" * 80)
    main_logger("")
    
    # Create paper trading interface with starting balance
    main_logger("🤖 Initializing trading bot...")
    interface = PaperTradingInterface(starting_currency=args.starting_currency, starting_asset=0.0)
    
    # Create bot (it will sync from interface)
    bot = Bot(
        interface=interface,
        strategy=strategy_class,
        pair="BTC-USD",
        fee_rate=args.fee_rate,
        fee_in_percent=True,
        loss_tolerance=args.loss_tolerance,
        strategy_params=args.strategy_params
    )
    
    # Register bot with config for dashboard
    config['bot'] = bot
    
    main_logger(f"📊 Strategy: {bot.strategy.name}")
    main_logger(f"⚙️  Parameters: {args.strategy_params}")
    main_logger(f"💰 Starting balance: ${args.starting_currency:.2f}")
    main_logger(f"💱 Fee rate: {args.fee_rate}%")
    main_logger(f"🛡️  Loss tolerance: {args.loss_tolerance}%")
    main_logger("")
    
    # Periodically emit bot state for dashboard
    def emit_bot_state_loop():
        while True:
            time.sleep(2)
            emit_bot_state()
    
    state_thread = threading.Thread(target=emit_bot_state_loop, daemon=True)
    state_thread.start()
    
    # Initialize test stream with historical data
    now = datetime.now(timezone.utc)
    end_time = now - timedelta(days=args.age)
    start_time = end_time - timedelta(days=args.days)
    
    main_logger(f"📅 Loading {args.days} days of {args.granularity} candles...")
    main_logger(f"   From: {start_time.strftime('%Y-%m-%d %H:%M UTC')}")
    main_logger(f"   To:   {end_time.strftime('%Y-%m-%d %H:%M UTC')}")
    main_logger("")
    
    ticker_stream = initialize_stream(
        stream_type='test',
        product_id='BTC-USD',
        granularity=args.granularity,
        start_date=start_time.isoformat(),
        end_date=end_time.isoformat(),
        playback_speed=args.playback_speed,
        rate_limit_delay=0.0  # No delay for fast backtesting
    )
    
    main_logger(f"✅ Test stream initialized")
    
    # Get initial price from first candle for baseline calculations
    candles = ticker_stream.get_candles()
    if candles and len(candles) > 0:
        initial_price = candles[0][4]  # Close price of first candle
        main_logger(f"💵 Initial price: ${initial_price:.2f}")
        # Update bot with initial price for baseline calculations
        bot.initial_price = initial_price
        # Recalculate baselines if they weren't set properly
        if bot.initial_crypto_baseline == 0.0 and bot.position == "short":
            bot.asset_baseline = bot.currency / initial_price
            bot.initial_crypto_baseline = bot.asset_baseline
            main_logger(f"✓ Crypto baseline calculated: {bot.initial_crypto_baseline:.8f} BTC")
        elif bot.initial_usd_baseline == 0.0 and bot.position == "long":
            bot.currency_baseline = bot.asset * initial_price
            bot.initial_usd_baseline = bot.currency_baseline
            main_logger(f"✓ USD baseline calculated: ${bot.initial_usd_baseline:.2f}")
    main_logger("")
    main_logger(f"🎬 Playback speed: {args.playback_speed}x")
    main_logger("")
    main_logger(f"💡 STRATEGY: {bot.strategy.name}")
    
    # Print strategy explanation if available
    if hasattr(bot.strategy, 'explain'):
        for line in bot.strategy.explain():
            main_logger(f"   {line}")
    
    main_logger("")
    main_logger(f"🌐 Dashboard running at: http://localhost:{args.port}")
    main_logger(f"🚀 Starting bot...")
    main_logger("")
    
    # Start bot trading logic
    bot_thread = threading.Thread(
        target=bot.trading_logic_loop,
        args=(ticker_stream,),
        daemon=True
    )
    bot_thread.start()
    
    # Run Flask dashboard
    try:
        socketio.run(app, port=args.port, debug=False, allow_unsafe_werkzeug=True)
    except KeyboardInterrupt:
        main_logger("")
        main_logger("🛑 Test stopped by user")
        main_logger(f"📊 Final Balance - USD: ${bot.currency:.2f}, BTC: {bot.asset:.8f}")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nAvailable strategies:")
        for name, cls in STRATEGIES.items():
            print(f"  - {name}: {cls.__name__}")
        sys.exit(1)
    
    args = parse_args()
    run_test_bot(args)
