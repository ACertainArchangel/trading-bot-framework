#!/usr/bin/env python3
"""
Test script for MACD strategy with paper trading.
Run this to see the MACD bot in action on historical data.
"""

from trader_bot import Bot
from interfaces.PaperTradingInterface import PaperTradingInterface
from strategies.macd import MACDStrategy
from web_dashboard import initialize_stream, main_logger, socketio, app, config, emit_bot_state, emit_trade_executed
import threading

def run_macd_bot():
    """
    Run a paper trading bot with MACD strategy on test data.
    """
    # Create paper trading interface
    interface = PaperTradingInterface()
    
    # Create bot with MACD strategy
    bot = Bot(
        interface=interface,
        strategy=MACDStrategy,  # Pass the class, it will be instantiated
        pair="BTC-USD",
        starting_currency=1000.0,
        starting_asset=0.0,
        fee_rate=0.00025,  # 0.025% fee because I am a very important person apparently
        fee_in_percent=True,
        loss_tolerance=0.0  # 0% = NEVER take a loss (optimal per backtest results)
    )
    
    # Register bot with config so dashboard can access it
    config['bot'] = bot
    
    main_logger(f"🚀 Starting MACD bot test run")
    main_logger(f"📊 Strategy: {bot.strategy}")
    
    # Periodically emit bot state
    def emit_bot_state_loop():
        import time
        while True:
            time.sleep(2)  # Update every 2 seconds
            emit_bot_state()
    
    state_thread = threading.Thread(target=emit_bot_state_loop, daemon=True)
    state_thread.start()
    
    # Initialize test stream with recent historical data
    from datetime import datetime, timezone, timedelta
    
    # Get one week of data from one week ago until now
    # Using 5-minute candles with automatic chunked loading (2016 candles total)
    now = datetime.now(timezone.utc)
    time_ago = now - timedelta(days=10)
    
    main_logger(f"📅 Loading TEN DAYS of 5-minute candles (this will take ~20 seconds due to API rate limits)...")
    
    ticker_stream = initialize_stream(
        stream_type='test',
        product_id='BTC-USD',
        granularity='5m',  # 5-minute candles for one month (2016 candles)
        start_date=time_ago.isoformat(),
        end_date=now.isoformat(),
        playback_speed=0.05,  # Slower replay for better visualization
        rate_limit_delay=1.0  # 1 second delay between API chunks
    )
    
    main_logger(f"📈 Test stream initialized: THREE MONTHS from {time_ago.strftime('%Y-%m-%d %H:%M')} to {now.strftime('%Y-%m-%d %H:%M')}")
    
    # Start the bot's trading logic
    bot_thread = threading.Thread(
        target=bot.trading_logic_loop,
        args=(ticker_stream,),
        daemon=True
    )
    bot_thread.start()
    
    # Run Flask app
    socketio.run(app, port=5003, debug=False, allow_unsafe_werkzeug=True)

if __name__ == '__main__':
    run_macd_bot()
