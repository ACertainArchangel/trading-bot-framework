#!/usr/bin/env python3
"""
LIVE TRADING SCRIPT - MACD Strategy on Coinbase
WARNING: This bot trades with REAL MONEY on Coinbase Exchange!

Setup:
1. Get your Coinbase API credentials from https://pro.coinbase.com/profile/api
   - You need: API Key, API Secret, and Passphrase
   - Make sure to enable trading permissions
   
2. Create a secrets.json file:
   {
     "coinbase_api_key": "your_api_key",
     "coinbase_api_secret": "your_api_secret",
     "coinbase_api_passphrase": "your_passphrase"
   }

3. Run this script:
   python live_macd_bot.py

The bot will:
- Connect to Coinbase and sync your balances
- Stream live 5-minute candles from Coinbase
- Execute MACD strategy with 0% loss tolerance (optimal)
- Show live dashboard at http://localhost:5003
"""

import os
import sys
import json
from datetime import datetime, timezone, timedelta
import threading
import time

from trader_bot import Bot
from interfaces.CoinbaseInterface import CoinbaseInterface
from strategies.macd import MACDStrategy
from web_dashboard import initialize_stream, main_logger, socketio, app, config, emit_bot_state


def get_api_credentials():
    """Load API credentials from secrets.json"""
    secrets_file = 'secrets.json'
    
    if not os.path.exists(secrets_file):
        print("❌ ERROR: secrets.json file not found")
        print()
        print("Please create a secrets.json file with your Coinbase API credentials:")
        print('{')
        print('  "coinbase_api_key": "your_api_key",')
        print('  "coinbase_api_secret": "your_api_secret",')
        print('  "coinbase_api_passphrase": "your_passphrase"')
        print('}')
        print()
        print("Get your credentials from: https://pro.coinbase.com/profile/api")
        sys.exit(1)
    
    try:
        with open(secrets_file, 'r') as f:
            secrets = json.load(f)
        
        api_key = secrets.get('coinbase_api_key')
        api_secret = secrets.get('coinbase_api_secret')
        api_passphrase = secrets.get('coinbase_api_passphrase')
        
        if not all([api_key, api_secret, api_passphrase]):
            print("❌ ERROR: Missing required fields in secrets.json")
            print()
            print("Required fields:")
            print("  - coinbase_api_key")
            print("  - coinbase_api_secret")
            print("  - coinbase_api_passphrase")
            sys.exit(1)
        
        return api_key, api_secret, api_passphrase
        
    except json.JSONDecodeError as e:
        print(f"❌ ERROR: Invalid JSON in secrets.json: {e}")
        sys.exit(1)


def confirm_live_trading():
    """Ask user to confirm they want to trade with real money"""
    print("=" * 80)
    print("⚠️  LIVE TRADING MODE - REAL MONEY WARNING")
    print("=" * 80)
    print()
    print("This bot will trade with REAL MONEY on Coinbase Exchange!")
    print()
    print("Strategy Configuration:")
    print("  • MACD Crossover (12/26/9)")
    print("  • Loss Tolerance: 0.0% (NEVER take a loss)")
    print("  • Fee Rate: 0.025% (You are special! Apparently...)")
    print("  • Trading Pair: BTC-USD")
    print()
    print("The bot will:")
    print("  ✓ Buy BTC when MACD crosses above signal line (bullish)")
    print("  ✓ Sell BTC when MACD crosses below signal line (bearish)")
    print("  ✓ Only execute trades that don't violate the baseline protection")
    print("  ✓ Update every 5 minutes with new candle data")
    print()
    
    response = input("Type 'YES' to start live trading: ")
    
    if response.strip().upper() != 'YES':
        print("❌ Live trading cancelled")
        sys.exit(0)
    
    print()
    print("✅ Starting live trading...")
    print()


def run_live_bot():
    """
    Run live trading bot connected to Coinbase Exchange.
    """
    # Get API credentials
    api_key, api_secret, api_passphrase = get_api_credentials()
    
    # Confirm user wants to trade with real money
    confirm_live_trading()
    
    # Create Coinbase interface
    main_logger("🔌 Connecting to Coinbase Exchange...")
    interface = CoinbaseInterface(
        api_key=api_key,
        api_secret=api_secret,
        api_passphrase=api_passphrase
    )
    
    # Test connection
    try:
        accounts = interface.connect_to_exchange()
        main_logger(f"✅ Connected to Coinbase - Found {len(accounts)} accounts")
    except Exception as e:
        main_logger(f"❌ Failed to connect: {e}")
        sys.exit(1)
    
    # Fetch current balances
    main_logger("💰 Fetching account balances...")
    
    # Note: We need to create bot first, then sync balances
    # For now, let's start with fetched balances
    btc_account = next((a for a in accounts if a['currency'] == 'BTC'), None)
    usd_account = next((a for a in accounts if a['currency'] == 'USD'), None)
    
    if not btc_account or not usd_account:
        main_logger("❌ Could not find BTC or USD accounts")
        sys.exit(1)
    
    starting_btc = float(btc_account['available'])
    starting_usd = float(usd_account['available'])
    
    main_logger(f"💵 USD Balance: ${starting_usd:.2f}")
    main_logger(f"₿  BTC Balance: {starting_btc:.8f} BTC")
    
    # Create bot with MACD strategy
    main_logger("🤖 Initializing trading bot...")
    bot = Bot(
        interface=interface,
        strategy=MACDStrategy,
        pair="BTC-USD",
        starting_currency=starting_usd,
        starting_asset=starting_btc,
        fee_rate=0.00025,  # 0.025% typical Coinbase fee for vip 4 which is me for some reason beyond my understanding
        fee_in_percent=True,
        loss_tolerance=0.0  # NEVER take a loss (optimal per backtest)
    )
    
    # Register bot with config for dashboard
    config['bot'] = bot
    
    main_logger(f"📊 Strategy: MACD Crossover (12/26/9)")
    main_logger(f"🛡️  Loss Tolerance: 0.0% (NEVER take a loss)")
    main_logger(f"💱 Fee Rate: 0.025% (You are special! Apparently...)")
    
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
            time.sleep(2)  # Update dashboard every 2 seconds
            emit_bot_state()
    
    state_thread = threading.Thread(target=emit_bot_state_loop, daemon=True)
    state_thread.start()
    
    # Initialize LIVE stream from Coinbase
    # First, load some historical data so MACD has context (need 35+ candles)
    main_logger("📈 Loading historical data for MACD initialization (35 candles minimum)...")
    now = datetime.now(timezone.utc)
    history_start = now - timedelta(hours=3)  # 3 hours = 36 candles at 5-min intervals
    
    ticker_stream = initialize_stream(
        stream_type='live',  # LIVE mode - real-time data from Coinbase!
        product_id='BTC-USD',
        granularity='5m',  # 5-minute candles
        start_date=history_start.isoformat(),
        end_date=now.isoformat()
    )
    
    main_logger("🚀 Live trading bot initialized!")
    main_logger("📊 Dashboard available at: http://localhost:5003")
    main_logger("🔴 Trading is LIVE - monitoring for signals...")
    main_logger("")
    main_logger("Press Ctrl+C to stop")
    
    # Start bot's trading logic in separate thread
    bot_thread = threading.Thread(
        target=bot.trading_logic_loop,
        args=(ticker_stream,),
        daemon=True
    )
    bot_thread.start()
    
    # Run Flask dashboard
    try:
        socketio.run(app, port=5003, debug=False, allow_unsafe_werkzeug=True)
    except KeyboardInterrupt:
        main_logger("")
        main_logger("🛑 Shutting down bot...")
        main_logger(f"📊 Final Balance - USD: ${bot.currency:.2f}, BTC: {bot.asset:.8f}")
        main_logger("👋 Goodbye!")


if __name__ == '__main__':
    run_live_bot()
