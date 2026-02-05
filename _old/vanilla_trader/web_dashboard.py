from flask import Flask, render_template, jsonify
from flask_socketio import SocketIO, emit
from flask_cors import CORS
from datetime import datetime, timezone, timedelta
from streams import TickerStream, CBTickerStream, TestTickerStream
import threading
import json
import argparse

app = Flask(__name__)
app.config['SECRET_KEY'] = 'trading-bot-secret'
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Global state
ticker_stream = None
main_logs = []
stream_logs = []

# Configuration
config = {
    'stream_type': 'live',  # 'live' or 'test'
    'product_id': 'BTC-USD',
    'granularity': '1m',
    'bot': None,  # Future: bot class to use
    'exchange': None,  # Future: exchange interface
    'trade_history': []  # Store all executed trades
}


def ticker_logger(msg):
    """Logger for TickerStream - sends to 'stream' log window."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_entry = {"time": timestamp, "message": msg}
    stream_logs.append(log_entry)
    
    # Keep only last 100 logs
    if len(stream_logs) > 100:
        stream_logs.pop(0)
    
    # Emit to all connected clients
    socketio.emit('stream_log', log_entry, namespace='/')


def main_logger(msg):
    """Logger for main application - sends to 'main' log window."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_entry = {"time": timestamp, "message": msg}
    main_logs.append(log_entry)
    
    # Keep only last 100 logs
    if len(main_logs) > 100:
        main_logs.pop(0)
    
    # Emit to all connected clients
    socketio.emit('main_log', log_entry, namespace='/')


def on_new_candle(candle):
    """Callback when TickerStream receives a new candle."""
    # Format: [timestamp, low, high, open, close, volume]
    candle_data = {
        "time": candle[0] * 1000,  # Convert to milliseconds for JS
        "open": candle[3],
        "high": candle[2],
        "low": candle[1],
        "close": candle[4],
        "volume": candle[5]
    }
    socketio.emit('new_candle', candle_data, namespace='/')

    #This is already logged in the stream logger
    #main_logger(f"📊 New candle: ${candle[4]:.2f}") 


@app.route('/')
def index():
    """Serve the main dashboard page."""
    return render_template('dashboard.html')


@app.route('/api/candles')
def get_candles():
    """Get all current candle data."""
    if ticker_stream is None:
        return jsonify({"error": "Stream not initialized"}), 503
    
    candles = ticker_stream.get_candles()
    
    # Format for frontend: [{time, open, high, low, close, volume}, ...]
    formatted = [
        {
            "time": c[0] * 1000,  # Milliseconds for JS
            "open": c[3],
            "high": c[2],
            "low": c[1],
            "close": c[4],
            "volume": c[5]
        }
        for c in candles
    ]
    
    return jsonify(formatted)


@app.route('/api/logs')
def get_logs():
    """Get current log state."""
    return jsonify({
        "main": main_logs,
        "stream": stream_logs
    })


@app.route('/api/config')
def get_config():
    """Get current dashboard configuration."""
    # Create a JSON-serializable copy of config (exclude bot object)
    info = {k: v for k, v in config.items() if k != 'bot'}
    info['candle_count'] = len(ticker_stream) if ticker_stream else 0
    info['stream_running'] = ticker_stream._running if ticker_stream else False
    
    # Add test stream specific info
    if config['stream_type'] == 'test' and ticker_stream:
        if hasattr(ticker_stream, 'get_progress'):
            info['progress'] = ticker_stream.get_progress()
        if hasattr(ticker_stream, 'is_complete'):
            info['complete'] = ticker_stream.is_complete()
    
    return jsonify(info)


@app.route('/api/indicators')
def get_indicators():
    """Calculate and return all available indicators for current candles."""
    if ticker_stream is None:
        return jsonify({"error": "Stream not initialized"}), 503
    
    candles = ticker_stream.get_candles()
    if len(candles) < 200:  # Need enough data for longest indicator
        return jsonify({"error": "Not enough data"}), 400
    
    closes = [c[4] for c in candles]
    highs = [c[2] for c in candles]
    lows = [c[1] for c in candles]
    times = [c[0] * 1000 for c in candles]  # Convert to milliseconds
    
    indicators = {}
    
    # EMAs
    for period in [9, 12, 20, 26, 50, 100, 200]:
        ema = calculate_ema(closes, period)
        indicators[f'ema_{period}'] = {
            'times': times,
            'values': ema,
            'name': f'EMA({period})',
            'type': 'line',
            'visible': period not in [50, 200]  # Hide EMA 50 and 200 by default
        }
    
    # SMAs
    for period in [20, 50, 100, 200]:
        sma = calculate_sma(closes, period)
        indicators[f'sma_{period}'] = {
            'times': times,
            'values': sma,
            'name': f'SMA({period})',
            'type': 'line',
            'visible': True  # Show all SMAs by default
        }
    
    # Bollinger Bands
    bb = calculate_bollinger_bands(closes, 20, 2)
    indicators['bb_upper'] = {
        'times': times,
        'values': bb['upper'],
        'name': 'BB Upper',
        'type': 'line',
        'visible': True
    }
    indicators['bb_middle'] = {
        'times': times,
        'values': bb['middle'],
        'name': 'BB Middle',
        'type': 'line',
        'visible': True
    }
    indicators['bb_lower'] = {
        'times': times,
        'values': bb['lower'],
        'name': 'BB Lower',
        'type': 'line',
        'visible': True
    }
    
    # RSI
    rsi = calculate_rsi(closes, 14)
    indicators['rsi'] = {
        'times': times,
        'values': rsi,
        'name': 'RSI(14)',
        'type': 'oscillator',
        'subplot': True,
        'visible': True
    }
    
    # Stochastic
    stoch = calculate_stochastic(highs, lows, closes, 14, 3)
    indicators['stoch_k'] = {
        'times': times,
        'values': stoch['k'],
        'name': 'Stoch %K',
        'type': 'oscillator',
        'subplot': True,
        'visible': True
    }
    indicators['stoch_d'] = {
        'times': times,
        'values': stoch['d'],
        'name': 'Stoch %D',
        'type': 'oscillator',
        'subplot': True,
        'visible': True
    }
    
    return jsonify(indicators)


def calculate_ema(values, period):
    """Calculate Exponential Moving Average."""
    if len(values) < period:
        return [None] * len(values)
    
    ema = [None] * (period - 1)
    multiplier = 2 / (period + 1)
    ema.append(sum(values[:period]) / period)  # First EMA is SMA
    
    for i in range(period, len(values)):
        ema.append((values[i] * multiplier) + (ema[-1] * (1 - multiplier)))
    
    return ema


def calculate_sma(values, period):
    """Calculate Simple Moving Average."""
    if len(values) < period:
        return [None] * len(values)
    
    sma = [None] * (period - 1)
    for i in range(period - 1, len(values)):
        sma.append(sum(values[i - period + 1:i + 1]) / period)
    
    return sma


def calculate_bollinger_bands(values, period, std_dev):
    """Calculate Bollinger Bands."""
    sma = calculate_sma(values, period)
    upper = []
    lower = []
    
    for i in range(len(values)):
        if sma[i] is None:
            upper.append(None)
            lower.append(None)
        else:
            window = values[max(0, i - period + 1):i + 1]
            std = (sum((x - sma[i]) ** 2 for x in window) / len(window)) ** 0.5
            upper.append(sma[i] + (std * std_dev))
            lower.append(sma[i] - (std * std_dev))
    
    return {'upper': upper, 'middle': sma, 'lower': lower}


def calculate_rsi(values, period=14):
    """Calculate Relative Strength Index."""
    if len(values) < period + 1:
        return [None] * len(values)
    
    rsi = [None] * period
    gains = []
    losses = []
    
    for i in range(1, len(values)):
        change = values[i] - values[i - 1]
        gains.append(max(change, 0))
        losses.append(abs(min(change, 0)))
    
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    if avg_loss == 0:
        rsi.append(100)
    else:
        rs = avg_gain / avg_loss
        rsi.append(100 - (100 / (1 + rs)))
    
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        
        if avg_loss == 0:
            rsi.append(100)
        else:
            rs = avg_gain / avg_loss
            rsi.append(100 - (100 / (1 + rs)))
    
    return rsi


def calculate_stochastic(highs, lows, closes, k_period=14, d_period=3):
    """Calculate Stochastic Oscillator."""
    if len(closes) < k_period:
        return {'k': [None] * len(closes), 'd': [None] * len(closes)}
    
    k_values = [None] * (k_period - 1)
    
    for i in range(k_period - 1, len(closes)):
        window_high = max(highs[i - k_period + 1:i + 1])
        window_low = min(lows[i - k_period + 1:i + 1])
        
        if window_high == window_low:
            k_values.append(50)
        else:
            k = 100 * (closes[i] - window_low) / (window_high - window_low)
            k_values.append(k)
    
    # Calculate %D (SMA of %K)
    d_values = [None] * (k_period + d_period - 2)
    for i in range(k_period + d_period - 2, len(k_values)):
        valid_k = [k for k in k_values[i - d_period + 1:i + 1] if k is not None]
        if valid_k:
            d_values.append(sum(valid_k) / len(valid_k))
        else:
            d_values.append(None)
    
    return {'k': k_values, 'd': d_values}


@app.route('/api/bot_state')
def get_bot_state():
    """Get current bot state."""
    if config.get('bot'):
        bot = config['bot']
        candles = ticker_stream.get_candles() if ticker_stream else []
        current_price = candles[-1][4] if candles else 0
        
        # Calculate min profitable prices
        min_sell_price = None
        min_buy_price = None
        
        if bot.position == 'long' and bot.asset > 0:
            # Min sell price to beat currency baseline
            min_sell_price = bot.currency_baseline / (bot.asset * (1 - bot.fee_rate))
        
        if bot.position == 'short' and bot.currency > 0:
            # Min buy price to beat asset baseline
            min_buy_price = (bot.currency * (1 - bot.fee_rate)) / bot.asset_baseline if bot.asset_baseline > 0 else None
        
        # Calculate APY metrics
        # Real APY: actual portfolio value change in USD terms
        # BTC APY: portfolio value change in BTC terms (positive if you're outperforming BTC)
        real_apy = 0.0
        apy_btc = 0.0
        elapsed_seconds = 0
        elapsed_str = "0s"
        
        # Calculate current portfolio value in USD and BTC
        if bot.position == 'long':
            current_portfolio_usd = bot.asset * current_price
            current_portfolio_btc = bot.asset
        else:
            current_portfolio_usd = bot.currency
            current_portfolio_btc = bot.currency / current_price if current_price > 0 else 0
        
        # Get initial values
        initial_usd = getattr(bot, 'initial_usd_baseline', 0)
        initial_btc = getattr(bot, 'initial_crypto_baseline', 0)
        
        if hasattr(bot, 'start_time') and bot.start_time:
            now = datetime.now(timezone.utc)
            elapsed = now - bot.start_time
            elapsed_seconds = elapsed.total_seconds()
            
            # Calculate APY with smart handling for different time periods
            if elapsed_seconds >= 60:
                years = elapsed_seconds / (365.25 * 24 * 3600)
                
                # Real APY: (current_usd - initial_usd) / initial_usd, annualized
                if initial_usd > 0:
                    ratio = current_portfolio_usd / initial_usd
                    if elapsed_seconds < 86400:  # Less than 1 day - linear extrapolation
                        return_pct = (ratio - 1) * 100
                        real_apy = return_pct * (365.25 * 24 * 3600 / elapsed_seconds)
                    else:
                        try:
                            if ratio > 0:
                                real_apy = ((ratio ** (1 / years)) - 1) * 100
                        except (OverflowError, ValueError):
                            real_apy = None
                
                # BTC APY: how much has your BTC holdings increased?
                # Positive = outperforming just holding BTC
                if initial_btc > 0:
                    ratio = current_portfolio_btc / initial_btc
                    if elapsed_seconds < 86400:  # Less than 1 day - linear extrapolation
                        return_pct = (ratio - 1) * 100
                        apy_btc = return_pct * (365.25 * 24 * 3600 / elapsed_seconds)
                    else:
                        try:
                            if ratio > 0:
                                apy_btc = ((ratio ** (1 / years)) - 1) * 100
                        except (OverflowError, ValueError):
                            apy_btc = None
        
        return jsonify({
            'position': bot.position,
            'currency': bot.currency,
            'asset': bot.asset,
            'currency_baseline': bot.currency_baseline,
            'asset_baseline': bot.asset_baseline,
            'initial_usd_baseline': getattr(bot, 'initial_usd_baseline', 0),
            'initial_crypto_baseline': getattr(bot, 'initial_crypto_baseline', 0),
            'fee_rate': bot.fee_rate,
            'loss_tolerance': bot.loss_tolerance,
            'min_sell_price': min_sell_price,
            'min_buy_price': min_buy_price,
            'current_price': current_price,
            'current_portfolio_usd': current_portfolio_usd,
            'current_portfolio_btc': current_portfolio_btc,
            'real_apy': real_apy,
            'apy_btc': apy_btc,
            'elapsed_time': elapsed_str,
            'elapsed_seconds': elapsed_seconds
        })
    return jsonify({'error': 'No bot configured'}), 404


def emit_bot_state():
    """Emit current bot state to all clients, including projected APY metrics."""
    if config.get('bot'):
        bot = config['bot']
        candles = ticker_stream.get_candles() if ticker_stream else []
        current_price = candles[-1][4] if candles else 0
        
        # Calculate min profitable prices (accounting for loss tolerance)
        min_sell_price = None
        min_buy_price = None
        
        if bot.position == 'long' and bot.asset > 0:
            # Minimum acceptable currency = baseline * (1 - loss_tolerance)
            min_acceptable_currency = bot.currency_baseline * (1 - bot.loss_tolerance)
            min_sell_price = min_acceptable_currency / (bot.asset * (1 - bot.fee_rate))
        
        if bot.position == 'short' and bot.currency > 0:
            # Minimum acceptable asset = baseline * (1 - loss_tolerance)
            min_acceptable_asset = bot.asset_baseline * (1 - bot.loss_tolerance)
            min_buy_price = (bot.currency * (1 - bot.fee_rate)) / min_acceptable_asset if min_acceptable_asset > 0 else None
        
        # Calculate APY metrics (Real APY and BTC APY)
        # Real APY: actual portfolio value change in USD terms
        # BTC APY: portfolio value change in BTC terms (positive if outperforming BTC)
        real_apy = 0.0
        apy_btc = 0.0
        elapsed_seconds = 0
        elapsed_str = "0s"
        
        # Calculate current portfolio value in USD and BTC
        if bot.position == 'long':
            current_portfolio_usd = bot.asset * current_price
            current_portfolio_btc = bot.asset
        else:
            current_portfolio_usd = bot.currency
            current_portfolio_btc = bot.currency / current_price if current_price > 0 else 0
        
        # Get initial values
        initial_usd = getattr(bot, 'initial_usd_baseline', 0)
        initial_btc = getattr(bot, 'initial_crypto_baseline', 0)
        
        if hasattr(bot, '_ticker_stream') and bot._ticker_stream and hasattr(bot, 'initial_candle_count'):
            # Calculate elapsed time based on candles processed (market time)
            current_candle_count = len(bot._ticker_stream.get_candles())
            candles_processed = current_candle_count - bot.initial_candle_count
            
            # Convert granularity to minutes
            granularity = bot._ticker_stream.granularity
            granularity_minutes = {'1m': 1, '5m': 5, '15m': 15, '1h': 60, '6h': 360, '1d': 1440}.get(granularity, 5)
            
            # Calculate elapsed time in minutes based on candles
            elapsed_minutes = candles_processed * granularity_minutes
            elapsed_seconds = elapsed_minutes * 60
            
            # Format elapsed time
            total_minutes = int(elapsed_minutes)
            days = total_minutes // 1440
            hours = (total_minutes % 1440) // 60
            mins = total_minutes % 60
            if days > 0:
                elapsed_str = f"{days}d {hours}h {mins}m"
            elif hours > 0:
                elapsed_str = f"{hours}h {mins}m"
            else:
                elapsed_str = f"{mins}m"
            
            # Calculate APY with smart handling for different time periods
            if elapsed_seconds >= 60:
                years = elapsed_seconds / (365.25 * 24 * 3600)
                
                # Real APY: (current_usd - initial_usd) / initial_usd, annualized
                if initial_usd > 0:
                    ratio = current_portfolio_usd / initial_usd
                    if elapsed_seconds < 86400:  # Less than 1 day - linear extrapolation
                        return_pct = (ratio - 1) * 100
                        real_apy = return_pct * (365.25 * 24 * 3600 / elapsed_seconds)
                    else:
                        try:
                            if ratio > 0:
                                real_apy = ((ratio ** (1 / years)) - 1) * 100
                        except (OverflowError, ValueError):
                            real_apy = None
                
                # BTC APY: how much has your BTC holdings increased?
                # Positive = outperforming just holding BTC
                if initial_btc > 0:
                    ratio = current_portfolio_btc / initial_btc
                    if elapsed_seconds < 86400:  # Less than 1 day - linear extrapolation
                        return_pct = (ratio - 1) * 100
                        apy_btc = return_pct * (365.25 * 24 * 3600 / elapsed_seconds)
                    else:
                        try:
                            if ratio > 0:
                                apy_btc = ((ratio ** (1 / years)) - 1) * 100
                        except (OverflowError, ValueError):
                            apy_btc = None
        
        state = {
            'position': bot.position,
            'currency': bot.currency,
            'asset': bot.asset,
            'currency_baseline': bot.currency_baseline,
            'asset_baseline': bot.asset_baseline,
            'initial_usd_baseline': getattr(bot, 'initial_usd_baseline', 0),
            'initial_crypto_baseline': getattr(bot, 'initial_crypto_baseline', 0),
            'fee_rate': bot.fee_rate,
            'loss_tolerance': bot.loss_tolerance,
            'min_sell_price': min_sell_price,
            'min_buy_price': min_buy_price,
            'current_price': current_price,
            'current_portfolio_usd': current_portfolio_usd,
            'current_portfolio_btc': current_portfolio_btc,
            'real_apy': real_apy,
            'apy_btc': apy_btc,
            'elapsed_time': elapsed_str,
            'elapsed_seconds': elapsed_seconds
        }
        
        socketio.emit('bot_state', state, namespace='/')


def emit_trade_executed(trade_type, price):
    """Emit trade execution to all clients."""
    try:
        with app.app_context():
            candles = ticker_stream.get_candles() if ticker_stream else []
            trade_time = candles[-1][0] * 1000 if candles else datetime.now().timestamp() * 1000
            
            trade = {
                'type': trade_type,
                'price': price,
                'time': trade_time
            }
            
            # Store in history
            config['trade_history'].append(trade)
            
            print(f"🔔 Emitting trade: {trade_type} at ${price:.2f}")
            socketio.emit('trade_executed', trade, namespace='/')
    except Exception as e:
        print(f"Error emitting trade: {e}")


@socketio.on('connect')
def handle_connect():
    """Handle client connection."""
    main_logger(f"🔌 Client connected")
    
    # Send current logs to new client
    emit('log_history', {
        "main": main_logs,
        "stream": stream_logs
    })
    
    # Send current candle data
    if ticker_stream:
        candles = ticker_stream.get_candles()
        formatted = [
            {
                "time": c[0] * 1000,
                "open": c[3],
                "high": c[2],
                "low": c[1],
                "close": c[4],
                "volume": c[5]
            }
            for c in candles
        ]
        emit('initial_data', formatted)
        
        # Send trade history
        emit('trade_history', config.get('trade_history', []))


@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection."""
    main_logger(f"🔌 Client disconnected")


@socketio.on('change_granularity')
def handle_granularity_change(data):
    """Handle granularity change request - disabled to prevent breaking bot connections."""
    granularity = data.get('granularity', '1m')
    main_logger(f"⚠️ Granularity change to {granularity} blocked - would break bot connection")
    main_logger(f"💡 To change granularity, restart the bot with --granularity {granularity}")
    emit('error', {'message': f'Granularity change disabled. Restart bot with --granularity {granularity}'})


def initialize_stream(stream_type='live', product_id='BTC-USD', granularity='1m', **kwargs):
    """Initialize the ticker stream based on configuration."""
    global ticker_stream
    
    main_logger(f"🚀 Initializing {stream_type} stream for {product_id}...")
    
    if stream_type == 'live':
        # Live stream from Coinbase
        start_date = datetime.now(timezone.utc) - timedelta(hours=2)
        ticker_stream = CBTickerStream(
            start_date,
            product_id=product_id,
            granularity=granularity,
            on_new_candle=on_new_candle,
            logger=ticker_logger
        )
    
    elif stream_type == 'test':
        # Historical replay for backtesting
        start_date = kwargs.get('start_date') or datetime.now(timezone.utc) - timedelta(days=1)
        end_date = kwargs.get('end_date') or datetime.now(timezone.utc)
        playback_speed = kwargs.get('playback_speed', 1.0)
        initial_window = kwargs.get('initial_window', 50)
        rate_limit_delay = kwargs.get('rate_limit_delay', 3.0)
        
        # Handle both datetime objects and ISO strings
        start_str = start_date if isinstance(start_date, str) else start_date.isoformat()
        end_str = end_date if isinstance(end_date, str) else end_date.isoformat()
        main_logger(f"📅 Test period: {start_str} to {end_str}")
        main_logger(f"⚡ Playback speed: {playback_speed}s per candle")
        
        ticker_stream = TestTickerStream(
            start_date=start_date,
            end_date=end_date,
            product_id=product_id,
            granularity=granularity,
            playback_speed=playback_speed,
            initial_window=initial_window,
            rate_limit_delay=rate_limit_delay,
            on_new_candle=on_new_candle,
            logger=ticker_logger
        )
    
    else:
        raise ValueError(f"Unknown stream type: {stream_type}. Use 'live' or 'test'")
    
    ticker_stream.start()
    main_logger(f"✅ Stream initialized with {len(ticker_stream)} candles")
    
    # Update global config
    config['stream_type'] = stream_type
    config['product_id'] = product_id
    config['granularity'] = granularity

    return ticker_stream


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Trading Dashboard')
    parser.add_argument('--stream', choices=['live', 'test'], default='live',
                        help='Stream type: live (Coinbase) or test (historical replay)')
    parser.add_argument('--product', default='BTC-USD',
                        help='Trading pair (e.g., BTC-USD, ETH-USD)')
    parser.add_argument('--granularity', default='1m',
                        choices=['1m', '5m', '15m', '1h', '6h', '1d'],
                        help='Candle granularity')
    parser.add_argument('--port', type=int, default=5000,
                        help='Web server port')
    
    # Test stream specific options
    parser.add_argument('--start-date', type=str,
                        help='Test stream start date (ISO format: 2025-12-15T00:00:00)')
    parser.add_argument('--end-date', type=str,
                        help='Test stream end date (ISO format)')
    parser.add_argument('--speed', type=float, default=1.0,
                        help='Test stream playback speed (seconds per candle)')
    
    args = parser.parse_args()
    
    # Parse dates if provided
    kwargs = {}
    if args.start_date:
        kwargs['start_date'] = datetime.fromisoformat(args.start_date).replace(tzinfo=timezone.utc)
    if args.end_date:
        kwargs['end_date'] = datetime.fromisoformat(args.end_date).replace(tzinfo=timezone.utc)
    if args.stream == 'test':
        kwargs['playback_speed'] = args.speed
    
    # Initialize stream before starting server
    initialize_stream(
        stream_type=args.stream,
        product_id=args.product,
        granularity=args.granularity,
        **kwargs
    )
    
    main_logger(f"🌐 Starting web server on http://localhost:{args.port}")
    print("\n" + "=" * 70)
    print("🚀 Trading Dashboard Starting")
    print("=" * 70)
    print(f"📊 Stream: {args.stream.upper()}")
    print(f"📈 Product: {args.product}")
    print(f"⏱️  Granularity: {args.granularity}")
    print(f"🌐 URL: http://localhost:{args.port}")
    print("=" * 70 + "\n")
    
    # Start Flask server
    socketio.run(app, debug=False, host='0.0.0.0', port=args.port, use_reloader=False, allow_unsafe_werkzeug=True)
