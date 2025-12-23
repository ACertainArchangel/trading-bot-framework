"""
Web dashboard for aggressive trader with SL/TP visualization.

Features:
- Real-time candlestick chart
- Entry, Stop Loss, and Take Profit lines on chart
- Position status panel
- Order book view
- Trade history
"""

from flask import Flask, render_template, jsonify
from flask_socketio import SocketIO
from flask_cors import CORS
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Callable
import threading
import json

app = Flask(__name__)
app.config['SECRET_KEY'] = 'aggressive-trader-secret'
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Global state
ticker_stream = None
main_logs = []
stream_logs = []

# Bot and interface references
bot = None
interface = None


def configure_dashboard(bot_instance, interface_instance, stream_instance):
    """Configure dashboard with bot, interface, and stream instances."""
    global bot, interface, ticker_stream
    bot = bot_instance
    interface = interface_instance
    ticker_stream = stream_instance


def ticker_logger(msg: str):
    """Logger for TickerStream - sends to 'stream' log window."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_entry = {"time": timestamp, "message": msg}
    stream_logs.append(log_entry)
    
    if len(stream_logs) > 100:
        stream_logs.pop(0)
    
    socketio.emit('stream_log', log_entry, namespace='/')


def main_logger(msg: str):
    """Logger for main application - sends to 'main' log window."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_entry = {"time": timestamp, "message": msg}
    main_logs.append(log_entry)
    
    if len(main_logs) > 100:
        main_logs.pop(0)
    
    socketio.emit('main_log', log_entry, namespace='/')


def on_new_candle(candle):
    """Callback when TickerStream receives a new candle."""
    candle_data = {
        "time": candle[0] * 1000,
        "open": candle[3],
        "high": candle[2],
        "low": candle[1],
        "close": candle[4],
        "volume": candle[5]
    }
    socketio.emit('new_candle', candle_data, namespace='/')
    
    # Also emit position updates
    emit_position_update()


def emit_position_update():
    """Emit current position state to all clients."""
    if bot:
        state = get_position_state()
        socketio.emit('position_update', state, namespace='/')


def get_position_state() -> dict:
    """Get current position state for dashboard."""
    if not bot or not interface:
        return {
            'has_position': False,
            'positions': [],
            'portfolio_value': 0,
            'currency': 0,
            'asset': 0,
        }
    
    positions = []
    
    # Get all open brackets from order manager
    if hasattr(bot, 'order_manager'):
        for bracket in bot.order_manager.brackets:
            pos = bracket.position
            if pos.is_filled and not pos.exit_reason:
                positions.append({
                    'side': pos.side.value,
                    'entry_price': pos.entry_price,
                    'stop_loss': pos.stop_loss_price,
                    'take_profit': pos.take_profit_price,
                    'size': pos.size,
                    'entry_time': pos.entry_time.isoformat() if pos.entry_time else None,
                    'trailing_stop': pos.trailing_stop_pct is not None,
                    'highest_price': pos.highest_price,
                })
    
    current_price = interface.current_price if interface else 0
    
    return {
        'has_position': len(positions) > 0,
        'positions': positions,
        'current_price': current_price,
        'portfolio_value': interface.get_portfolio_value() if interface else 0,
        'currency': interface.currency if interface else 0,
        'asset': interface.asset if interface else 0,
    }


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
    
    return jsonify(formatted)


@app.route('/api/position')
def get_position():
    """Get current position state."""
    return jsonify(get_position_state())


@app.route('/api/orders')
def get_orders():
    """Get open orders."""
    if not interface:
        return jsonify([])
    
    orders = interface.get_open_orders()
    return jsonify([o.to_dict() for o in orders])


@app.route('/api/trades')
def get_trades():
    """Get trade history."""
    if not interface:
        return jsonify([])
    
    return jsonify(interface.trade_history)


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
    info = {
        'pair': bot.pair if bot else 'BTC-USD',
        'candle_count': len(ticker_stream) if ticker_stream else 0,
        'stream_running': ticker_stream._running if ticker_stream else False,
        'bot_running': bot.running if bot else False,
    }
    
    return jsonify(info)


@app.route('/api/price_lines')
def get_price_lines():
    """
    Get horizontal price lines for the chart.
    Returns entry, stop-loss, and take-profit lines for all open positions.
    """
    lines = []
    
    if not bot or not hasattr(bot, 'order_manager'):
        return jsonify(lines)
    
    for i, bracket in enumerate(bot.order_manager.brackets):
        pos = bracket.position
        if pos.is_filled and not pos.exit_reason:
            # Entry line (blue)
            lines.append({
                'price': pos.entry_price,
                'label': f'Entry #{i+1}',
                'color': '#3B82F6',
                'style': 'solid',
            })
            
            # Stop loss line (red)
            if pos.stop_loss_price:
                label = f'SL #{i+1}'
                if pos.trailing_stop_pct:
                    label += ' (trailing)'
                lines.append({
                    'price': pos.stop_loss_price,
                    'label': label,
                    'color': '#EF4444',
                    'style': 'dashed',
                })
            
            # Take profit line (green)
            if pos.take_profit_price:
                lines.append({
                    'price': pos.take_profit_price,
                    'label': f'TP #{i+1}',
                    'color': '#22C55E',
                    'style': 'dashed',
                })
    
    return jsonify(lines)


@app.route('/api/indicators')
def get_indicators():
    """Calculate and return indicators."""
    if ticker_stream is None:
        return jsonify({"error": "Stream not initialized"}), 503
    
    candles = ticker_stream.get_candles()
    if len(candles) < 50:
        return jsonify({"error": "Not enough data"}), 400
    
    closes = [c[4] for c in candles]
    times = [c[0] * 1000 for c in candles]
    
    indicators = {}
    
    # EMA 20 and 50 for trend
    for period in [20, 50]:
        ema = calculate_ema(closes, period)
        indicators[f'ema_{period}'] = {
            'times': times,
            'values': ema,
            'name': f'EMA({period})',
            'type': 'line',
            'visible': True
        }
    
    return jsonify(indicators)


def calculate_ema(values: List[float], period: int) -> List[Optional[float]]:
    """Calculate Exponential Moving Average."""
    if len(values) < period:
        return [None] * len(values)
    
    ema = [None] * (period - 1)
    multiplier = 2 / (period + 1)
    ema.append(sum(values[:period]) / period)
    
    for i in range(period, len(values)):
        ema.append((values[i] * multiplier) + (ema[-1] * (1 - multiplier)))
    
    return ema


def run_dashboard(host: str = '0.0.0.0', port: int = 5005, debug: bool = False):
    """Run the Flask-SocketIO server."""
    socketio.run(app, host=host, port=port, debug=debug, allow_unsafe_werkzeug=True)


def run_dashboard_background(host: str = '0.0.0.0', port: int = 5005):
    """Run dashboard in background thread."""
    thread = threading.Thread(
        target=run_dashboard,
        args=(host, port, False),
        daemon=True
    )
    thread.start()
    return thread


if __name__ == '__main__':
    print("Starting aggressive trader dashboard...")
    run_dashboard(port=5005, debug=True)
