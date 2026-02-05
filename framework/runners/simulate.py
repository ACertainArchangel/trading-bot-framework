"""
Simulate Runner - Replay backtests with visual dashboard.

This module provides a simulation runner that replays historical data
at configurable speed with a live dashboard for visualization.
"""

import sys
import time
import threading
from io import StringIO
from pathlib import Path
from datetime import datetime
from typing import Type, Optional, Dict, List

from ..core.candle import Candle
from ..strategies.base import Strategy
from ..interfaces.paper import PaperInterface
from ..data.fetcher import DataFetcher


class SimulationState:
    """Shared state for simulation with dashboard."""
    
    def __init__(self, starting_balance: float):
        self.starting_value = starting_balance
        self.current_value = starting_balance
        self.position = "short"
        self.trades = []
        self.equity_curve = []
        self.logs = []
        self.candles = []
        self.running = False
        self.paused = False
        self.playback_speed = 0.1
        self.interface = None
        self.strategy_name = ""
        self._lock = threading.Lock()
    
    def add_log(self, msg: str):
        with self._lock:
            entry = {
                'time': datetime.now().strftime("%H:%M:%S"),
                'message': msg
            }
            self.logs.append(entry)
            if len(self.logs) > 200:
                self.logs.pop(0)
    
    def add_trade(self, trade_type: str, price: float, amount: float, 
                  value: float, timestamp: float):
        with self._lock:
            self.trades.append({
                'timestamp': timestamp,
                'type': trade_type,
                'price': price,
                'amount': amount,
                'value': value
            })
    
    def update_equity(self, value: float, timestamp: float):
        with self._lock:
            self.equity_curve.append({
                'time': timestamp * 1000,
                'value': value
            })
            self.current_value = value


def simulate(
    strategy: Type[Strategy],
    days: int = 30,
    starting_balance: float = 1000.0,
    product_id: str = "BTC-USD",
    granularity: str = '5m',
    fee_rate: float = 0.0025,
    loss_tolerance: float = 0.0,
    allocation: Optional[Dict] = None,
    playback_speed: float = 0.1,
    warmup_candles: int = 50,
    strategy_params: Optional[Dict] = None,
    dashboard: bool = True,
    dashboard_port: int = 5002,
    verbose: bool = True
):
    """
    Run a backtest simulation with live-style playback.
    
    Replays historical data at configurable speed, showing trades
    as they would have occurred. Perfect for visualizing strategy behavior.
    
    Args:
        strategy: Strategy class to test
        days: Days of historical data to replay
        starting_balance: Initial USD balance
        product_id: Trading pair (e.g., 'BTC-USD', 'ETH-USD')
        granularity: Candle size ('1m', '5m', '15m', '1h')
        fee_rate: Trading fee as decimal (0.0025 = 0.25%)
        loss_tolerance: Max acceptable loss as decimal
        allocation: Position sizing. None=dynamic from strategy.
                   Examples: {'short': -1, 'long': 1} for shorting
        playback_speed: Seconds per candle (0.05=fast, 0.5=medium, 1.0=slow)
        warmup_candles: Candles of history before trading starts
        strategy_params: Parameters passed to strategy constructor
        dashboard: Launch web dashboard for visualization
        dashboard_port: Port for dashboard (default 5002)
        verbose: Print progress to console
    
    Example:
        >>> from framework import simulate
        >>> from framework.strategies.examples import EMACrossover
        >>> 
        >>> simulate(
        ...     EMACrossover,
        ...     days=14,
        ...     playback_speed=0.05,
        ...     strategy_params={'fast_period': 9, 'slow_period': 21}
        ... )
    """
    strategy_params = strategy_params or {}
    
    def log(msg):
        if verbose:
            print(msg)
    
    log("=" * 60)
    log("🎬 BACKTEST SIMULATION - Live Replay Mode")
    log("=" * 60)
    log("")
    
    # Fetch historical data
    log(f"📦 Loading {days} days of {granularity} candles...")
    fetcher = DataFetcher(product_id, verbose=False)
    all_candles = fetcher.get_candles(days=days, granularity=granularity)
    log(f"✅ Loaded {len(all_candles)} candles")
    log("")
    
    if len(all_candles) < warmup_candles:
        log(f"❌ Not enough data (need {warmup_candles}, got {len(all_candles)})")
        return
    
    # Initialize
    min_candles = warmup_candles
    initial_price = all_candles[min_candles].close
    
    # Create strategy
    strat = strategy(
        fee_rate=fee_rate,
        loss_tolerance=loss_tolerance,
        allocation=allocation,
        **strategy_params
    )
    
    # Set allocation on interface (from param or strategy default)
    effective_allocation = allocation if allocation is not None else strat.allocation
    interface = PaperInterface(starting_currency=starting_balance, allocation=effective_allocation)
    
    # Set up baselines
    currency_baseline = starting_balance
    asset_baseline = starting_balance / initial_price
    strat.currency_baseline = currency_baseline
    strat.asset_baseline = asset_baseline
    
    # Create shared state
    state = SimulationState(starting_balance)
    state.strategy_name = strategy.__name__
    state.interface = interface
    state.playback_speed = playback_speed
    state.running = True
    
    alloc = interface.allocation
    log(f"📊 Strategy: {strategy.__name__}")
    log(f"💰 Starting Balance: ${starting_balance:,.2f}")
    log(f"📈 Allocation: Long={alloc.get('long', 1)}x, Short={alloc.get('short', 0)}x")
    log(f"🎬 Playback Speed: {playback_speed}s per candle")
    log(f"📊 Warmup: {warmup_candles} candles")
    log(f"📅 Period: {all_candles[0].datetime.strftime('%Y-%m-%d')} to {all_candles[-1].datetime.strftime('%Y-%m-%d')}")
    log("")
    
    # Launch dashboard
    if dashboard:
        log(f"🌐 Dashboard: http://localhost:{dashboard_port}")
        _launch_dashboard(state, product_id, granularity, dashboard_port)
        time.sleep(1)
    
    log("")
    log("🚀 Starting simulation...")
    log("   Press Ctrl+C to stop")
    log("")
    
    # Track metrics
    wins = 0
    losses = 0
    cycle_start_value = starting_balance
    
    try:
        for i in range(min_candles, len(all_candles)):
            if not state.running:
                break
            
            while state.paused and state.running:
                time.sleep(0.1)
            
            window = all_candles[:i + 1]
            current_candle = all_candles[i]
            current_price = current_candle.close
            
            # Update state
            with state._lock:
                state.candles = window.copy()
            
            current_value = interface.get_total_value(current_price)
            state.update_equity(current_value, current_candle.timestamp)
            state.position = interface.position
            
            # Buy signals (when in short/cash position)
            if interface.position == "short":
                buy_result = strat.buy_signal(window)
                should_buy, signal_alloc = strat.parse_signal(buy_result)
                
                if should_buy:
                    # Apply signal allocation if provided
                    if signal_alloc is not None:
                        interface.allocation = {'long': signal_alloc, 'short': interface.allocation.get('short', 0)}
                    
                    was_short = interface.position == "short"
                    
                    interface.execute_buy(current_price, fee_rate, interface.currency)
                    
                    if was_short:
                        new_value = interface.get_total_value(current_price)
                        pnl = new_value - cycle_start_value
                        pnl_pct = (pnl / cycle_start_value) * 100
                        wins += 1 if pnl > 0 else 0
                        losses += 1 if pnl <= 0 else 0
                        emoji = "🟢" if pnl > 0 else "🔴"
                        log(f"📈 COVER @ ${current_price:,.2f} | {emoji} {pnl_pct:+.2f}% | {current_candle.datetime.strftime('%Y-%m-%d %H:%M')}")
                    
                    cycle_start_value = interface.get_total_value(current_price)
                    
                    state.add_trade('buy', current_price, interface.asset,
                                   interface.get_total_value(current_price),
                                   current_candle.timestamp)
                    state.add_log(f"🟢 BUY @ ${current_price:,.2f}")
                    state.position = interface.position
                    
                    asset_baseline = interface.asset if interface.asset > 0 else interface.get_total_value(current_price) / current_price
                    currency_baseline = interface.get_total_value(current_price)
                    strat.currency_baseline = currency_baseline
                    strat.asset_baseline = asset_baseline
                    
                    log(f"🟢 BUY  @ ${current_price:,.2f} | {current_candle.datetime.strftime('%Y-%m-%d %H:%M')}")
            
            # Sell signals
            elif interface.position == "long":
                sell_result = strat.sell_signal(window)
                should_sell, signal_alloc = strat.parse_signal(sell_result)
                
                if should_sell:
                    # Apply signal allocation if provided (for shorts)
                    if signal_alloc is not None:
                        interface.allocation = {'long': interface.allocation.get('long', 1), 'short': signal_alloc}
                    
                    amount = interface.asset
                    interface.execute_sell(current_price, fee_rate, amount)
                    
                    current_val = interface.get_total_value(current_price)
                    profit = current_val - cycle_start_value
                    profit_pct = (profit / cycle_start_value) * 100
                    
                    wins += 1 if profit > 0 else 0
                    losses += 1 if profit <= 0 else 0
                    emoji = "🟢" if profit > 0 else "🔴"
                    
                    log(f"🔴 SELL @ ${current_price:,.2f} | {emoji} {profit_pct:+.2f}% | {current_candle.datetime.strftime('%Y-%m-%d %H:%M')}")
                    
                    # Log if we opened a short
                    if interface._short_size > 0:
                        log(f"📉 SHORT @ ${current_price:,.2f} | {current_candle.datetime.strftime('%Y-%m-%d %H:%M')}")
                    
                    cycle_start_value = interface.get_total_value(current_price)
                    
                    state.add_trade('sell', current_price, amount,
                                   interface.get_total_value(current_price),
                                   current_candle.timestamp)
                    state.add_log(f"🔴 SELL @ ${current_price:,.2f} ({profit_pct:+.2f}%)")
                    state.position = interface.position
                    
                    currency_baseline = interface.get_total_value(current_price)
                    asset_baseline = currency_baseline / current_price
                    strat.currency_baseline = currency_baseline
                    strat.asset_baseline = asset_baseline
            
            time.sleep(state.playback_speed)
        
        # Complete
        state.running = False
        final_value = interface.get_total_value(all_candles[-1].close)
        total_return = ((final_value - starting_balance) / starting_balance) * 100
        total_trades = wins + losses
        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
        
        log("")
        log("=" * 60)
        log("📊 SIMULATION COMPLETE")
        log("=" * 60)
        log(f"💰 Starting Value:  ${starting_balance:,.2f}")
        log(f"💰 Ending Value:    ${final_value:,.2f}")
        log(f"📈 Total Return:    {total_return:+.2f}%")
        log(f"📊 Trades:          {total_trades} ({wins}W / {losses}L)")
        log(f"🎯 Win Rate:        {win_rate:.1f}%")
        log(f"💸 Fees Paid:       ${interface.get_fees_paid():,.2f}")
        log("")
        
        if dashboard:
            log("🌐 Dashboard still running. Press Ctrl+C to exit.")
            while True:
                time.sleep(1)
    
    except KeyboardInterrupt:
        state.running = False
        log("\n👋 Simulation stopped")


def _launch_dashboard(state: SimulationState, product_id: str, 
                      granularity: str, port: int):
    """Launch simulation dashboard in background thread."""
    
    def run_dashboard():
        from flask import Flask, render_template, jsonify, request
        from flask_socketio import SocketIO
        from flask_cors import CORS
        import logging
        
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)
        
        import framework
        framework_dir = Path(framework.__file__).parent
        template_dir = framework_dir / 'dashboard' / 'templates'
        
        app = Flask(__name__, template_folder=str(template_dir))
        CORS(app)
        socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')
        
        @app.route('/')
        def index():
            return render_template('live_trading.html')
        
        @app.route('/api/state')
        def get_state():
            with state._lock:
                interface = state.interface
                fees = interface.get_fees_paid() if interface else 0
                return jsonify({
                    'running': state.running,
                    'paused': state.paused,
                    'position': state.position,
                    'current_value': state.current_value,
                    'starting_value': state.starting_value,
                    'profit_pct': ((state.current_value - state.starting_value) / state.starting_value) * 100,
                    'currency': interface.currency if interface else 0,
                    'asset': interface.asset if interface else 0,
                    'strategy': state.strategy_name,
                    'trade_count': len(state.trades),
                    'fees_paid': fees
                })
        
        @app.route('/api/candles')
        def get_candles():
            with state._lock:
                candles = state.candles.copy()
            return jsonify([{
                'time': c.timestamp * 1000,
                'open': c.open,
                'high': c.high,
                'low': c.low,
                'close': c.close,
                'volume': c.volume
            } for c in candles])
        
        @app.route('/api/trades')
        def get_trades():
            with state._lock:
                return jsonify(state.trades.copy())
        
        @app.route('/api/equity')
        def get_equity():
            with state._lock:
                return jsonify(state.equity_curve.copy())
        
        @app.route('/api/logs')
        def get_logs():
            with state._lock:
                return jsonify(state.logs.copy())
        
        @app.route('/api/indicators')
        def get_indicators():
            with state._lock:
                candles = state.candles.copy()
            
            if not candles:
                return jsonify({})
            
            from ..indicators import ema, rsi, macd, bollinger_bands
            
            ema9_vals = ema(candles, 9)
            ema21_vals = ema(candles, 21)
            rsi_vals = rsi(candles, 14)
            macd_result = macd(candles)
            bb_result = bollinger_bands(candles, 20, 2.0)
            
            timestamps = [c.timestamp * 1000 for c in candles]
            
            return jsonify({
                'ema_9': {'times': timestamps, 'values': ema9_vals, 'name': 'EMA 9'},
                'ema_20': {'times': timestamps, 'values': ema21_vals, 'name': 'EMA 21'},
                'rsi': {'times': timestamps, 'values': rsi_vals, 'name': 'RSI'},
                'macd': {'times': timestamps, 'values': macd_result['macd'], 'name': 'MACD'},
                'macd_signal': {'times': timestamps, 'values': macd_result['signal'], 'name': 'Signal'},
                'macd_histogram': {'times': timestamps, 'values': macd_result['histogram'], 'name': 'Histogram'},
                'bb_upper': {'times': timestamps, 'values': bb_result['upper'], 'name': 'BB Upper'},
                'bb_middle': {'times': timestamps, 'values': bb_result['middle'], 'name': 'BB Middle'},
                'bb_lower': {'times': timestamps, 'values': bb_result['lower'], 'name': 'BB Lower'}
            })
        
        @app.route('/api/control', methods=['POST'])
        def control():
            data = request.get_json()
            if 'paused' in data:
                state.paused = data['paused']
            if 'speed' in data:
                state.playback_speed = max(0.01, float(data['speed']))
            return jsonify({'ok': True})
        
        def emit_updates():
            last_candle_count = 0
            last_trade_count = 0
            last_log_count = 0
            while state.running:
                with state._lock:
                    current_candle_count = len(state.candles)
                    current_trade_count = len(state.trades)
                    current_log_count = len(state.logs)
                    
                    # Emit new candles
                    if current_candle_count > last_candle_count and state.candles:
                        latest = state.candles[-1]
                        socketio.emit('candle', {
                            'time': latest.timestamp * 1000,
                            'open': latest.open,
                            'high': latest.high,
                            'low': latest.low,
                            'close': latest.close,
                            'volume': latest.volume
                        })
                        last_candle_count = current_candle_count
                    
                    # Emit new trades
                    if current_trade_count > last_trade_count:
                        for trade in state.trades[last_trade_count:]:
                            socketio.emit('trade', trade)
                        last_trade_count = current_trade_count
                    
                    # Emit new logs
                    if current_log_count > last_log_count:
                        for log_entry in state.logs[last_log_count:]:
                            socketio.emit('log', log_entry)
                        last_log_count = current_log_count
                    
                    # Emit state update
                    interface = state.interface
                    fees = interface.get_fees_paid() if interface else 0
                    socketio.emit('state', {
                        'current_value': state.current_value,
                        'position': state.position,
                        'profit_pct': ((state.current_value - state.starting_value) / state.starting_value) * 100,
                        'trade_count': current_trade_count,
                        'fees_paid': fees
                    })
                time.sleep(0.05)
        
        update_thread = threading.Thread(target=emit_updates, daemon=True)
        update_thread.start()
        
        socketio.run(app, host='0.0.0.0', port=port, debug=False, 
                    allow_unsafe_werkzeug=True)
    
    dashboard_thread = threading.Thread(target=run_dashboard, daemon=True)
    dashboard_thread.start()
