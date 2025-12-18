#!/usr/bin/env python3
"""
Generic Live Bot - Real Trading with Coinbase Advanced Trade

⚠️  WARNING: This bot trades with REAL MONEY! ⚠️

Usage:
    python live_bot.py <strategy_name> [options]

Examples:
    python live_bot.py ema_cross --fast 50 --slow 200 --port 5003
    python live_bot.py momentum --period 10 --buy_threshold 1.0 --sell_threshold -1.0
    python live_bot.py macd --short_window 12 --long_window 26 --signal_window 9

Options:
    --fee_rate N          Fee rate as decimal (default: 0.00025 = 0.025% VIP maker)
    --loss_tolerance N    Max acceptable loss as decimal (default: 0.0)
    --granularity G       Candle size: 1m, 5m, 15m, 1h (default: 1m)
    --port N              Dashboard port (default: 5003)
    --history_hours N     Hours of historical data to preload (default: 6)
    
    Strategy-specific parameters are passed as --param_name value

Requirements:
    - secrets.json file with Coinbase API credentials:
      {
        "coinbase_api_key_name": "your_key_name",
        "coinbase_api_private_key": "-----BEGIN EC PRIVATE KEY-----\\n...\\n-----END EC PRIVATE KEY-----"
      }
"""

import os
import sys
import json
import argparse
from datetime import datetime, timezone, timedelta
import threading
import time

from trader_bot import Bot
from interfaces.CoinbaseAdvancedTradeInterface import CoinbaseAdvancedTradeInterface
from web_dashboard import initialize_stream, main_logger, socketio, app, config, emit_bot_state
from strategies import *
from strategies.ema_cross import EMACrossStrategy
from strategies.momentum import MomentumStrategy
from strategies.macd import MACDStrategy
from strategies.rsi import RSIStrategy
from strategies.bollinger import BollingerStrategy


# Strategy registry mapping names to classes
STRATEGIES = {
    'ema_cross': EMACrossStrategy,
    'greedy_ema_cross': GreedyEMACrossStrategy,
    'momentum': MomentumStrategy,
    'greedy_momentum': GreedyMomentumStrategy,
    'macd': MACDStrategy,
    'rsi': RSIStrategy,
    'bollinger': BollingerStrategy,
}


def get_api_credentials(instance_id=1):
    """Load API credentials from secrets/secretsN.json"""
    secrets_file = f'secrets/secrets{instance_id}.json'
    
    if not os.path.exists(secrets_file):
        print(f"❌ ERROR: {secrets_file} file not found")
        print()
        print(f"Please create a {secrets_file} file with your Coinbase API credentials:")
        print('{')
        print('  "coinbase_api_key_name": "your_api_key_name",')
        print('  "coinbase_api_private_key": "-----BEGIN EC PRIVATE KEY-----\\n...\\n-----END EC PRIVATE KEY-----"')
        print('}')
        print()
        print("Get your credentials from: https://www.coinbase.com/settings/api")
        sys.exit(1)
    
    try:
        with open(secrets_file, 'r') as f:
            secrets = json.load(f)
        
        api_key_name = secrets.get('coinbase_api_key_name')
        api_private_key = secrets.get('coinbase_api_private_key')
        
        if not all([api_key_name, api_private_key]):
            print(f"❌ ERROR: Missing required fields in {secrets_file}")
            print()
            print("Required fields:")
            print("  - coinbase_api_key_name")
            print("  - coinbase_api_private_key")
            sys.exit(1)
        
        return api_key_name, api_private_key
        
    except json.JSONDecodeError as e:
        print(f"❌ ERROR: Invalid JSON in {secrets_file}: {e}")
        sys.exit(1)


def confirm_live_trading(strategy_name, strategy_params, fee_rate, loss_tolerance):
    """Ask user to confirm they want to trade with real money"""
    print("=" * 80)
    print("⚠️  LIVE TRADING MODE - REAL MONEY WARNING")
    print("=" * 80)
    print()
    print("This bot will trade with REAL MONEY on Coinbase Exchange!")
    print()
    print("Strategy Configuration:")
    print(f"  • Strategy: {strategy_name}")
    print(f"  • Parameters: {strategy_params}")
    print(f"  • Fee Rate: {fee_rate * 100:.3f}%")
    print(f"  • Loss Tolerance: {loss_tolerance * 100:.2f}%")
    print(f"  • Trading Pair: BTC-USD")
    print()
    print("The bot will:")
    print("  ✓ Execute trades automatically based on strategy signals")
    print("  ✓ Use your actual Coinbase balance")
    print("  ✓ Respect loss tolerance and fee calculations")
    print("  ✓ Update every minute with new candle data")
    print()
    
    response = input("Type 'YES' to start live trading: ")
    
    if response.strip().upper() != 'YES':
        print("❌ Live trading cancelled")
        sys.exit(0)
    
    print()
    print("✅ Starting live trading...")
    print()


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Live trading bot with real money on Coinbase',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    # Required
    parser.add_argument('strategy', type=str, choices=STRATEGIES.keys(),
                       help='Strategy to use for live trading')
    
    # Optional bot parameters
    parser.add_argument('--instance', type=int, default=1,
                       help='Bot instance number for parallel bots (default: 1)')
    parser.add_argument('--fee_rate', type=float, default=0.00025,
                       help='Fee rate as decimal (default: 0.00025 = 0.025%%)')
    parser.add_argument('--loss_tolerance', type=float, default=0.0,
                       help='Loss tolerance as decimal (default: 0.0)')
    parser.add_argument('--granularity', type=str, default='1m',
                       choices=['1m', '5m', '15m', '1h'],
                       help='Candle granularity (default: 1m)')
    parser.add_argument('--port', type=int, default=5003,
                       help='Dashboard port (default: 5003)')
    parser.add_argument('--history_hours', type=int, default=6,
                       help='Hours of historical data to preload (default: 6)')
    
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


def run_live_bot(args):
    """
    Run live trading bot with real money.
    """
    strategy_class = STRATEGIES[args.strategy]
    
    # Get API credentials for this instance
    api_key_name, api_private_key = get_api_credentials(args.instance)
    
    # Confirm user wants to trade with real money
    confirm_live_trading(
        args.strategy,
        args.strategy_params,
        args.fee_rate,
        args.loss_tolerance
    )
    
    main_logger("🔌 Connecting to Coinbase Advanced Trade API...")
    interface = CoinbaseAdvancedTradeInterface(
        api_key_name=api_key_name,
        api_private_key=api_private_key
    )
    
    # Test connection and get balances
    result = interface.connect_to_exchange()
    accounts = result.get('accounts', [])
    main_logger(f"✅ Connected to Coinbase - Found {len(accounts)} accounts")
    
    # Fetch current balances
    main_logger("💰 Fetching account balances...")
    
    btc_account = next((a for a in accounts if a['currency'] == 'BTC'), None)
    usd_account = next((a for a in accounts if a['currency'] == 'USD'), None)
    
    if not btc_account or not usd_account:
        main_logger("❌ Could not find BTC or USD accounts")
        sys.exit(1)
    
    starting_btc = float(btc_account['available_balance']['value'])
    starting_usd = float(usd_account['available_balance']['value'])
    
    main_logger(f"💵 USD Balance: ${starting_usd:.2f}")
    main_logger(f"₿  BTC Balance: {starting_btc:.8f} BTC")
    
    # Determine starting position - bot can only start with one or the other
    if starting_btc > 0.0001:  # Has meaningful BTC (> ~$8 worth)
        main_logger(f"🔵 Starting LONG (holding BTC)")
    else:
        main_logger(f"🟢 Starting SHORT (holding USD)")
    
    # Note: Interface already has correct balances from fetch_exchange_balance calls
    # The Bot will sync from the interface, so we don't pass starting balances anymore
    
    # Create bot with specified strategy
    main_logger("🤖 Initializing trading bot...")
    bot = Bot(
        interface=interface,
        strategy=strategy_class,
        pair="BTC-USD",
        fee_rate=args.fee_rate,
        fee_in_percent=False,  # Already in decimal form
        loss_tolerance=args.loss_tolerance,
        strategy_params=args.strategy_params
    )
    
    # Register bot with config for dashboard
    config['bot'] = bot
    
    main_logger(f"📊 Strategy: {bot.strategy.name}")
    main_logger(f"⚙️  Parameters: {args.strategy_params}")
    main_logger(f"💱 Fee Rate: {args.fee_rate * 100:.3f}%")
    main_logger(f"🛡️  Loss Tolerance: {args.loss_tolerance * 100:.2f}%")
    
    # Verify sync with exchange
    try:
        interface.assert_exchange_sync(bot)
        main_logger("✅ Bot balances synced with exchange")
    except AssertionError as e:
        main_logger(f"⚠️  Balance mismatch: {e}")
        main_logger("⚠️  Continuing anyway - bot will use its tracked balances")
    
    # Start periodic state emission for dashboard
    def emit_bot_state_loop():
        while True:
            time.sleep(2)
            emit_bot_state()
    
    state_thread = threading.Thread(target=emit_bot_state_loop, daemon=True)
    state_thread.start()
    
    # Initialize LIVE stream with historical data pre-loaded
    main_logger(f"📈 Loading {args.history_hours} hours of historical {args.granularity} candles...")
    
    from CBData import CoinbaseDataFetcher
    now = datetime.now(timezone.utc)
    history_start = now - timedelta(hours=args.history_hours)
    
    # Pre-fetch historical data
    fetcher = CoinbaseDataFetcher(product_id='BTC-USD')
    main_logger("📦 Fetching historical candles...")
    historical_candles = fetcher.fetch_candles(history_start, now, args.granularity)
    main_logger(f"✅ Loaded {len(historical_candles)} historical candles")
    
    # Initialize live stream
    ticker_stream = initialize_stream(
        stream_type='live',
        product_id='BTC-USD',
        granularity=args.granularity,
        start_date=history_start.isoformat(),
        end_date=now.isoformat()
    )
    
    # Replace with pre-fetched data if we got more
    if historical_candles and len(historical_candles) > len(ticker_stream._candles):
        ticker_stream._candles = historical_candles
        main_logger(f"✅ Stream pre-populated with {len(historical_candles)} candles")
    
    # Get initial price from historical data or fetch current price
    initial_price = None
    candles = ticker_stream.get_candles()
    if candles and len(candles) > 0:
        initial_price = candles[0][4]  # Close price of first candle
    else:
        # Fetch current market price as fallback
        try:
            current_price_data = interface.get_current_price('BTC-USD')
            initial_price = float(current_price_data)
            main_logger(f"💵 Current market price: ${initial_price:.2f}")
        except:
            main_logger("⚠️ Could not fetch initial price - baselines may be inaccurate")
    
    if initial_price:
        bot.initial_price = initial_price
        main_logger(f"💵 Initial price set: ${initial_price:.2f}")
        # Recalculate baselines if they weren't set properly
        if bot.initial_crypto_baseline == 0.0 and bot.position == "short":
            bot.asset_baseline = bot.currency / initial_price
            bot.initial_crypto_baseline = bot.asset_baseline
            main_logger(f"✓ Crypto baseline calculated: {bot.initial_crypto_baseline:.8f} BTC")
        elif bot.initial_usd_baseline == 0.0 and bot.position == "long":
            bot.currency_baseline = bot.asset * initial_price
            bot.initial_usd_baseline = bot.currency_baseline
            main_logger(f"✓ USD baseline calculated: ${bot.initial_usd_baseline:.2f}")
    
    time.sleep(1)
    main_logger("✅ Live stream ready - monitoring for new candles")
    
    main_logger("🚀 Live trading bot initialized!")
    main_logger(f"📊 Dashboard available at: http://localhost:{args.port}")
    main_logger("🔴 Trading is LIVE - monitoring for signals...")
    main_logger("")
    main_logger(f"💡 STRATEGY: {bot.strategy.name}")
    
    # Print strategy explanation if available
    if hasattr(bot.strategy, 'explain'):
        for line in bot.strategy.explain():
            main_logger(f"   {line}")
    
    main_logger("")
    main_logger("Press Ctrl+C to stop")
    
    # Start bot's trading logic
    bot_thread = threading.Thread(
        target=bot.trading_logic_loop,
        args=(ticker_stream,),
        daemon=False
    )
    bot_thread.start()
    
    # Run Flask dashboard
    dashboard_thread = threading.Thread(
        target=lambda: socketio.run(app, port=args.port, debug=False, allow_unsafe_werkzeug=True),
        daemon=True
    )
    dashboard_thread.start()
    
    # Keep main thread alive
    try:
        while bot_thread.is_alive():
            bot_thread.join(timeout=1.0)
    except KeyboardInterrupt:
        main_logger("")
        main_logger("🛑 Shutting down bot...")
        main_logger(f"📊 Final Balance - USD: ${bot.currency:.2f}, BTC: {bot.asset:.8f}")
        main_logger("👋 Goodbye!")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nAvailable strategies:")
        for name, cls in STRATEGIES.items():
            print(f"  - {name}: {cls.__name__}")
        sys.exit(1)
    
    args = parse_args()
    
    try:
        run_live_bot(args)
    except Exception as e:
        print(f"\n❌ FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
