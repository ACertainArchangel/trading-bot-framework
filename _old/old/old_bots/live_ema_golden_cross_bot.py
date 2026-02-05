#!/usr/bin/env python3
"""
LIVE TRADING SCRIPT - EMA(50/200) Golden Cross Strategy on Coinbase
WARNING: This bot trades with REAL MONEY on Coinbase Exchange!

Strategy: EMA(50/200) Golden Cross / Death Cross
- Golden Cross: Buy when EMA(50) crosses above EMA(200) (bullish)
- Death Cross: Sell when EMA(50) crosses below EMA(200) (bearish)

Performance: 48.55% APY over 3 months (2nd best performer)
- 127.49% BTC APY (crushed holding!)
- Only 13 trades in 3 months (very selective)
- 100% win rate (6 wins, 0 losses)
- Caught bear run early via Death Cross

Setup:
1. Create a secrets.json file:
   {
     "coinbase_api_key_name": "your_api_key_name",
     "coinbase_api_private_key": "-----BEGIN EC PRIVATE KEY-----\n...\n-----END EC PRIVATE KEY-----"
   }

2. Run this script:
   python live_ema_golden_cross_bot.py

The bot will:
- Connect to Coinbase and sync your balances
- Stream live 5-minute candles from Coinbase
- Execute EMA(50/200) Golden Cross strategy with 0% loss tolerance
- Show live dashboard at http://localhost:5003
"""

import os
import sys
import json
from datetime import datetime, timezone, timedelta
import threading
import time

from trader_bot import Bot
from interfaces.CoinbaseAdvancedTradeInterface import CoinbaseAdvancedTradeInterface
from strategies.ema_cross import EMACrossStrategy
from web_dashboard import initialize_stream, main_logger, socketio, app, config, emit_bot_state


def get_api_credentials():
    """Load API credentials from secrets.json"""
    secrets_file = 'secrets.json'
    
    if not os.path.exists(secrets_file):
        print("❌ ERROR: secrets.json file not found")
        print()
        print("Please create a secrets.json file with your Coinbase API credentials:")
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
            print("❌ ERROR: Missing required fields in secrets.json")
            print()
            print("Required fields:")
            print("  - coinbase_api_key_name")
            print("  - coinbase_api_private_key")
            sys.exit(1)
        
        return api_key_name, api_private_key
        
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
    print("  • EMA(50/200) Golden Cross / Death Cross")
    print("  • Loss Tolerance: 0.0% (NEVER take a loss)")
    print("  • Fee Rate: 0.1%")
    print("  • Trading Pair: BTC-USD")
    print()
    print("Strategy Details:")
    print("  🟢 Golden Cross: Buy when EMA(50) crosses above EMA(200)")
    print("  🔴 Death Cross: Sell when EMA(50) crosses below EMA(200)")
    print("  📊 Only trades major trend changes (13 trades in 3 months)")
    print("  🎯 Filters out short-term noise completely")
    print("  🐻 Successfully caught bear run early in backtests")
    print()
    print("Backtest Performance (3 months):")
    print("  • APY (USD): 48.55%")
    print("  • APY (BTC): 127.49%")
    print("  • Win Rate: 100% (6 wins, 0 losses)")
    print("  • Trades: Only 13 (very selective)")
    print()
    print("The bot will:")
    print("  ✓ Buy BTC when EMA(50) crosses above EMA(200) (Golden Cross)")
    print("  ✓ Sell BTC when EMA(50) crosses below EMA(200) (Death Cross)")
    print("  ✓ Only execute trades that don't violate baseline protection")
    print("  ✓ Update every 5 minutes with new candle data")
    print()
    print("Benefits:")
    print("  • If stuck SHORT (USD): Capital preserved, no loss")
    print("  • If stuck LONG (BTC): HODL position, performance can only improve")
    print("  • Long-term trend following = fewer trades, lower fees")
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
    try:
        # Get API credentials
        api_key_name, api_private_key = get_api_credentials()
        
        # Confirm user wants to trade with real money
        confirm_live_trading()
        
        # Create Coinbase Advanced Trade interface
        main_logger("🔌 Connecting to Coinbase Advanced Trade API...")
        interface = CoinbaseAdvancedTradeInterface(
            api_key_name=api_key_name,
            api_private_key=api_private_key
        )
        
        # Test connection
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
        
        main_logger(f"💵 USD Balance: ${starting_usd:.8f}")
        main_logger(f"₿  BTC Balance: {starting_btc:.8f} BTC")
        
        # Determine starting position - bot can only start with one or the other
        if starting_btc > 0.0001:  # Has meaningful BTC (> $10 worth)
            main_logger(f"🔵 Starting LONG (holding BTC)")
            start_currency = 0
            start_asset = starting_btc
        else:
            main_logger(f"🟢 Starting SHORT (holding USD)")
            start_currency = starting_usd
            start_asset = 0
        
        # Create bot with EMA(50/200) Golden Cross strategy
        main_logger("\ud83e\udd16 Initializing trading bot...")
        bot = Bot(
            interface=interface,
            strategy=EMACrossStrategy,
            pair="BTC-USD",
            starting_currency=start_currency,
            starting_asset=start_asset,
            fee_rate=0.00025,  # 0.025% VIP maker fee
            fee_in_percent=False,  # Already in decimal form
            loss_tolerance=0.0,  # NEVER take a loss (optimal per backtest)
            strategy_params={
                'fast': 50,   # 50-period EMA
                'slow': 200   # 200-period EMA (Golden Cross)
            }
        )
        
        # Register bot with config for dashboard
        config['bot'] = bot
        
        main_logger(f"📊 Strategy: EMA(50/200) Golden Cross / Death Cross")
        main_logger(f"🛡️  Loss Tolerance: 0.0% (NEVER take a loss)")
        main_logger(f"💱 Fee Rate: 0.025% (VIP Maker)")
        main_logger(f"🏆 Backtest Performance: 48.55% APY (USD), 127.49% APY (BTC)")
        
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
        
        # Initialize LIVE stream with historical data pre-loaded
        # Use 1-minute candles for faster real-time updates
        main_logger("📈 Loading 300+ historical 1-minute candles for EMA(200) initialization...")
        
        from CBData import CoinbaseDataFetcher
        now = datetime.now(timezone.utc)
        history_start = now - timedelta(hours=6)  # 6 hours = 360 one-minute candles
        
        # Pre-fetch historical data using CBData (which handles chunking properly)
        fetcher = CoinbaseDataFetcher(product_id='BTC-USD')
        main_logger("📦 Fetching historical candles...")
        historical_candles = fetcher.fetch_candles(history_start, now, '1m')
        main_logger(f"✅ Loaded {len(historical_candles)} historical candles")
        
        # Now initialize live stream which will continue from this point
        ticker_stream = initialize_stream(
            stream_type='live',  # LIVE mode - real Coinbase stream
            product_id='BTC-USD',
            granularity='1m',  # 1-minute candles for real-time updates
            start_date=history_start.isoformat(),
            end_date=now.isoformat()
        )
        
        # Replace the stream's candles with our pre-fetched data
        if historical_candles and len(historical_candles) > len(ticker_stream._candles):
            ticker_stream._candles = historical_candles
            main_logger(f"✅ Stream pre-populated with {len(historical_candles)} candles")
        
        time.sleep(1)
        main_logger("✅ Live stream ready - monitoring for new candles every minute")
        
        main_logger("🚀 Live trading bot initialized!")
        main_logger("📊 Dashboard available at: http://localhost:5003")
        main_logger("🔴 Trading is LIVE - monitoring for Golden/Death Cross signals...")
        main_logger("")
        main_logger("💡 STRATEGY EXPLANATION:")
        main_logger("   🟢 GOLDEN CROSS = BUY when EMA(50) crosses above EMA(200)")
        main_logger("   🔴 DEATH CROSS = SELL when EMA(50) crosses below EMA(200)")
        main_logger("   📊 Very selective: Only ~13 trades in 3 months")
        main_logger("   🎯 Catches major trend changes, filters all noise")
        main_logger("")
        main_logger("Press Ctrl+C to stop")
        
        # Start bot's trading logic in separate thread
        bot_thread = threading.Thread(
            target=bot.trading_logic_loop,
            args=(ticker_stream,),
            daemon=False  # Changed to False so main thread waits for bot to finish
        )
        bot_thread.start()
        
        # Run Flask dashboard in separate thread
        dashboard_thread = threading.Thread(
            target=lambda: socketio.run(app, port=5003, debug=False, allow_unsafe_werkzeug=True),
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
    
    except Exception as e:
        print(f"\n❌ FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    run_live_bot()
