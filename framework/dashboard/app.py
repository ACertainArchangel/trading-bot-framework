"""
Dashboard Flask Application - Real-time trading visualization.
"""

from flask import Flask, render_template, jsonify
from flask_socketio import SocketIO
from flask_cors import CORS
from datetime import datetime
from typing import Optional, Type
import os

from ..data.stream import LiveStream
from ..strategies.base import Strategy
from ..indicators import ema, sma, rsi, macd, bollinger_bands, stochastic


def create_app(
    product_id: str = "BTC-USD",
    granularity: str = '1m',
    strategy: Optional[Type[Strategy]] = None
):
    """
    Create and configure the Flask dashboard application.
    """
    template_dir = os.path.join(os.path.dirname(__file__), 'templates')
    app = Flask(__name__, template_folder=template_dir)
    app.config['SECRET_KEY'] = 'trading-framework-secret'
    
    CORS(app)
    socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')
    
    # Global state
    logs = []
    stream = None
    
    def log(msg: str):
        """Add log entry and emit to clients."""
        entry = {
            'time': datetime.now().strftime("%H:%M:%S"),
            'message': msg
        }
        logs.append(entry)
        if len(logs) > 100:
            logs.pop(0)
        socketio.emit('log', entry)
    
    def on_candle(candle):
        """Handle new candle from stream."""
        data = {
            'time': candle.timestamp * 1000,
            'open': candle.open,
            'high': candle.high,
            'low': candle.low,
            'close': candle.close,
            'volume': candle.volume
        }
        socketio.emit('candle', data)
    
    @app.route('/')
    def index():
        """Serve dashboard page."""
        return render_template('dashboard.html')
    
    @app.route('/api/candles')
    def get_candles():
        """Get all candle data."""
        if stream is None:
            return jsonify({'error': 'Stream not started'}), 503
        
        candles = stream.get_candles()
        return jsonify([{
            'time': c.timestamp * 1000,
            'open': c.open,
            'high': c.high,
            'low': c.low,
            'close': c.close,
            'volume': c.volume
        } for c in candles])
    
    @app.route('/api/indicators')
    def get_indicators():
        """Calculate and return indicators."""
        if stream is None:
            return jsonify({'error': 'Stream not started'}), 503
        
        candles = stream.get_candles()
        if len(candles) < 50:
            return jsonify({'error': 'Insufficient data'}), 400
        
        times = [c.timestamp * 1000 for c in candles]
        
        indicators = {}
        
        # EMAs
        for period in [9, 12, 20, 26, 50]:
            values = ema(candles, period)
            indicators[f'ema_{period}'] = {
                'times': times,
                'values': values,
                'name': f'EMA({period})',
                'type': 'line'
            }
        
        # SMAs
        for period in [20, 50, 200]:
            values = sma(candles, period)
            indicators[f'sma_{period}'] = {
                'times': times,
                'values': values,
                'name': f'SMA({period})',
                'type': 'line'
            }
        
        # Bollinger Bands
        bb = bollinger_bands(candles, 20, 2)
        indicators['bb_upper'] = {
            'times': times,
            'values': bb['upper'],
            'name': 'BB Upper',
            'type': 'line'
        }
        indicators['bb_lower'] = {
            'times': times,
            'values': bb['lower'],
            'name': 'BB Lower',
            'type': 'line'
        }
        
        # RSI
        rsi_values = rsi(candles, 14)
        indicators['rsi'] = {
            'times': times,
            'values': rsi_values,
            'name': 'RSI(14)',
            'type': 'oscillator',
            'min': 0,
            'max': 100
        }
        
        # MACD
        m = macd(candles, 12, 26, 9)
        indicators['macd'] = {
            'times': times,
            'values': m['macd'],
            'name': 'MACD',
            'type': 'histogram'
        }
        indicators['macd_signal'] = {
            'times': times,
            'values': m['signal'],
            'name': 'MACD Signal',
            'type': 'line'
        }
        
        # Stochastic
        stoch = stochastic(candles, 14, 3)
        indicators['stoch_k'] = {
            'times': times,
            'values': stoch['k'],
            'name': 'Stoch %K',
            'type': 'oscillator'
        }
        indicators['stoch_d'] = {
            'times': times,
            'values': stoch['d'],
            'name': 'Stoch %D',
            'type': 'oscillator'
        }
        
        return jsonify(indicators)
    
    @app.route('/api/logs')
    def get_logs():
        """Get log entries."""
        return jsonify(logs)
    
    @app.route('/api/config')
    def get_config():
        """Get dashboard configuration."""
        return jsonify({
            'product_id': product_id,
            'granularity': granularity,
            'strategy': strategy.__name__ if strategy else None,
            'candle_count': len(stream) if stream else 0,
            'running': stream._running if stream else False
        })
    
    @socketio.on('connect')
    def handle_connect():
        """Handle client connection."""
        nonlocal stream
        
        if stream is None:
            log(f"Starting stream for {product_id}...")
            stream = LiveStream(
                product_id=product_id,
                granularity=granularity,
                on_candle=on_candle,
                logger=log
            )
            stream.start()
        
        log("Client connected")
    
    return app, socketio
