"""
Paper Trading Runner - Test strategies with fake money in real-time.

Perfect for validating strategies before going live.
"""

from typing import Type, Optional, Dict, Any, Callable
import time
import signal
import sys
import threading

from ..strategies.base import Strategy
from ..data.stream import LiveStream
from ..interfaces.paper import PaperInterface
from ..interfaces.base import Allocation, DEFAULT_ALLOCATION


class PaperTradingState:
    """Shared state for paper trading with dashboard."""
    
    def __init__(self, starting_balance: float):
        self.starting_balance = starting_balance
        self.current_value = starting_balance
        self.position = "short"
        self.trades = []
        self.equity_curve = []
        self.logs = []
        self.running = False
        self.interface = None
        self.stream = None
        self.strategy_name = ""
        self._lock = threading.Lock()
    
    def add_log(self, msg: str):
        from datetime import datetime
        with self._lock:
            entry = {
                'time': datetime.now().strftime("%H:%M:%S"),
                'message': msg
            }
            self.logs.append(entry)
            if len(self.logs) > 200:
                self.logs.pop(0)
    
    def add_trade(self, trade_type: str, price: float, amount: float, value: float):
        import time as t
        with self._lock:
            self.trades.append({
                'timestamp': t.time(),
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


def paper_trade(
    strategy: Type[Strategy],
    starting_balance: float = 1000.0,
    product_id: str = "BTC-USD",
    granularity: str = '1m',
    fee_rate: float = 0.0025,
    loss_tolerance: float = 0.0,
    allocation: Optional[Allocation] = None,
    strategy_params: Optional[Dict[str, Any]] = None,
    check_interval: float = 1.0,
    run_forever: bool = True,
    dashboard: bool = False,
    dashboard_port: int = 5002,
    history_days: int = 30
):
    """
    Run a strategy in paper trading mode (fake money, real market data).
    
    This simulates live trading without risking real capital. Perfect for
    final validation before deploying with real money.
    
    Data Integrity:
        Trades are automatically gated behind data validity checks.
        If the market data has gaps or becomes stale, trading is paused
        until the data is restored. You'll see console warnings when this happens.
    
    Args:
        strategy: Strategy class to run
        starting_balance: Initial fake USD balance
        product_id: Trading pair (e.g., "BTC-USD")
        granularity: Candle size
        fee_rate: Simulated trading fee
        loss_tolerance: Max acceptable loss
        allocation: Position sizing config. Default: {'short': 0, 'long': 1}
                   Examples:
                     {'short': -1, 'long': 1}  # Enable shorting
                     {'short': -3, 'long': 3}  # 3x leverage perps
        strategy_params: Additional strategy parameters
        check_interval: Seconds between signal checks
        run_forever: If True, run until Ctrl+C
        dashboard: If True, launch web dashboard for visualization
        dashboard_port: Port for dashboard (default 5002)
        history_days: Days of historical data to load (default 30)
    
    Example:
        >>> from framework import paper_trade, Strategy
        >>> 
        >>> class MyStrategy(Strategy):
        ...     # ... your strategy implementation
        >>> 
        >>> # With visualization dashboard
        >>> paper_trade(MyStrategy, starting_balance=5000, dashboard=True)
        
        # Press Ctrl+C to stop
    """
    strategy_params = strategy_params or {}
    
    # Create shared state for dashboard
    state = PaperTradingState(starting_balance)
    state.strategy_name = strategy.__name__
    
    # Launch dashboard if requested
    if dashboard:
        _launch_paper_dashboard(
            state=state,
            product_id=product_id,
            granularity=granularity,
            port=dashboard_port
        )
    
    print("=" * 60)
    print("📝 PAPER TRADING MODE")
    print("=" * 60)
    print(f"Strategy:    {strategy.__name__}")
    print(f"Product:     {product_id}")
    print(f"Granularity: {granularity}")
    print(f"Starting:    ${starting_balance:,.2f}")
    print(f"Fee Rate:    {fee_rate * 100:.3f}%")
    if dashboard:
        print(f"Dashboard:   http://localhost:{dashboard_port}")
    print("=" * 60)
    print()
    
    # Initialize components
    # Create strategy
    strat = strategy(
        fee_rate=fee_rate,
        loss_tolerance=loss_tolerance,
        **strategy_params
    )
    
    # Set allocation on interface (from param or strategy default)
    effective_allocation = allocation if allocation is not None else strat.allocation
    interface = PaperInterface(starting_currency=starting_balance, allocation=effective_allocation)
    state.interface = interface
    
    # Set up baselines (will be updated on first candle)
    strat.currency_baseline = starting_balance
    strat.asset_baseline = 0.0
    
    stream = LiveStream(
        product_id=product_id,
        granularity=granularity,
        history_hours=history_days * 24
    )
    state.stream = stream
    state.running = True
    
    # Handle Ctrl+C gracefully
    running = True
    data_warning_shown = False
    
    def handle_stop(signum, frame):
        nonlocal running
        print("\n\n🛑 Stopping paper trading...")
        running = False
        state.running = False
    
    signal.signal(signal.SIGINT, handle_stop)
    signal.signal(signal.SIGTERM, handle_stop)
    
    try:
        stream.start()
        
        # Wait for valid data
        print("⏳ Waiting for valid market data...")
        wait_count = 0
        while running and not stream.is_data_valid():
            time.sleep(1)
            wait_count += 1
            if wait_count > 30:
                print("⚠️  Warning: Data validation taking longer than expected")
                wait_count = 0
        
        if not running:
            return
        
        # Initialize baseline with current price
        candles = stream.get_candles()
        if candles:
            initial_price = candles[-1].close
            strat.asset_baseline = starting_balance / initial_price
            print(f"📊 Initial price: ${initial_price:,.2f}")
            print(f"   USD Baseline: ${strat.currency_baseline:,.2f}")
            print(f"   Asset Baseline: {strat.asset_baseline:.8f}")
        
        print()
        print("🚀 Paper trading started. Press Ctrl+C to stop.")
        print("-" * 60)
        
        last_candle_ts = 0
        
        while running:
            # Check data validity before processing
            if not stream.is_data_valid():
                if not data_warning_shown:
                    print("⚠️  Data integrity issue detected - pausing trades until resolved")
                    state.add_log("⚠️  Data integrity issue - trades paused")
                    data_warning_shown = True
                time.sleep(check_interval)
                continue
            elif data_warning_shown:
                print("✅ Data integrity restored - resuming trades")
                state.add_log("✅ Data integrity restored")
                data_warning_shown = False
            
            candles = stream.get_candles()
            
            if not candles or len(candles) < 50:
                time.sleep(check_interval)
                continue
            
            current = candles[-1]
            current_price = current.close
            
            # Only process on new candles
            if current.timestamp > last_candle_ts:
                last_candle_ts = current.timestamp
                
                # Calculate current value (handles long and short positions)
                current_value = interface.get_total_value(current_price)
                
                profit_pct = ((current_value - starting_balance) / starting_balance) * 100
                
                # Update state for dashboard
                state.position = interface.position
                state.update_equity(current_value, current.timestamp)
                
                # Check signals based on position
                # "short" -> can buy to go long (closes any leveraged short first)
                if interface.position == "short":
                    buy_result = strat.buy_signal(candles)
                    should_buy, signal_alloc = strat.parse_signal(buy_result)
                    
                    if should_buy:
                        # Apply signal allocation if provided
                        if signal_alloc is not None:
                            interface.allocation = {'long': signal_alloc, 'short': interface.allocation.get('short', 0)}
                        
                        was_short = interface.position == "short"
                        
                        amount = interface.currency
                        expected_asset = (amount * (1 - fee_rate)) / current_price
                        min_acceptable = strat.asset_baseline * (1 - loss_tolerance)
                        
                        if expected_asset > min_acceptable:
                            interface.execute_buy(current_price, fee_rate, amount)
                            
                            strat.asset_baseline = interface.asset
                            strat.currency_baseline = interface.asset * current_price
                            
                            new_value = interface.get_total_value(current_price)
                            new_profit_pct = ((new_value - starting_balance) / starting_balance) * 100
                            
                            if was_short:
                                msg = f"🔄 COVER @ ${current_price:,.2f} | Closed short -> Long {interface.asset:.8f} | Value: ${new_value:,.2f} ({new_profit_pct:+.2f}%)"
                            else:
                                msg = f"💰 BUY @ ${current_price:,.2f} | Got {interface.asset:.8f} | Value: ${new_value:,.2f} ({new_profit_pct:+.2f}%)"
                            print(msg)
                            state.add_log(msg)
                            state.add_trade('buy', current_price, interface.asset, new_value)
                            state.position = "long"
                
                # Handle sell signals - closes longs or opens shorts
                elif interface.position == "long":
                    sell_result = strat.sell_signal(candles)
                    should_sell, signal_alloc = strat.parse_signal(sell_result)
                    
                    if should_sell:
                        # Apply signal allocation if provided (for shorts)
                        if signal_alloc is not None:
                            interface.allocation = {'long': interface.allocation.get('long', 1), 'short': signal_alloc}
                        
                        amount = interface.asset
                        expected_currency = (amount * current_price) * (1 - fee_rate)
                        min_acceptable = strat.currency_baseline * (1 - loss_tolerance)
                        
                        if expected_currency > min_acceptable:
                            interface.execute_sell(current_price, fee_rate, amount)
                            
                            strat.currency_baseline = interface.currency
                            strat.asset_baseline = interface.currency / current_price
                            
                            sell_value = interface.get_total_value(current_price)
                            new_profit_pct = ((sell_value - starting_balance) / starting_balance) * 100
                            
                            if interface.position == "short":
                                msg = f"📉 SHORT @ ${current_price:,.2f} | Sold & opened short | Value: ${sell_value:,.2f} ({new_profit_pct:+.2f}%)"
                            else:
                                msg = f"💵 SELL @ ${current_price:,.2f} | Got ${interface.currency:,.2f} | Value: ${sell_value:,.2f} ({new_profit_pct:+.2f}%)"
                            print(msg)
                            state.add_log(msg)
                            state.add_trade('sell', current_price, amount, sell_value)
                            state.position = interface.position
            
            if not run_forever:
                break
            
            time.sleep(check_interval)
    
    finally:
        stream.stop()
    
    # Print summary
    final_price = stream.get_latest().close if stream.get_latest() else 0
    final_value = interface.get_total_value(final_price)
    
    profit_pct = ((final_value - starting_balance) / starting_balance) * 100
    
    print()
    print("=" * 60)
    print("📊 PAPER TRADING SUMMARY")
    print("=" * 60)
    print(f"Starting Value:  ${starting_balance:,.2f}")
    print(f"Ending Value:    ${final_value:,.2f}")
    print(f"Profit/Loss:     {profit_pct:+.2f}%")
    print(f"Total Trades:    {interface.get_trade_count()}")
    print(f"Fees Paid:       ${interface.get_fees_paid():,.2f}")
    print(f"Final Position:  {interface.position.upper()}")
    print("=" * 60)
    
    state.running = False
    return interface


def _launch_paper_dashboard(
    state: PaperTradingState,
    product_id: str,
    granularity: str,
    port: int
):
    """Launch the paper trading dashboard in a background thread."""
    import webbrowser
    
    def run_dashboard():
        try:
            from flask import Flask, render_template, jsonify, send_from_directory
            from flask_socketio import SocketIO
            from flask_cors import CORS
            import os
            
            template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'dashboard', 'templates'))
            app = Flask(__name__, template_folder=template_dir)
            app.config['SECRET_KEY'] = 'paper-trading-secret'
            CORS(app, resources={r"/*": {"origins": "*"}})
            socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')
            
            @app.route('/')
            def index():
                try:
                    return render_template('live_trading.html')
                except Exception as e:
                    return f"<h1>Dashboard Error</h1><p>Template error: {e}</p><p>Template dir: {template_dir}</p>", 500
            
            @app.route('/api/candles')
            def get_candles():
                if state.stream is None:
                    return jsonify([])
                candles = state.stream.get_candles()
                return jsonify([{
                    'time': c.timestamp * 1000,
                    'open': c.open,
                    'high': c.high,
                    'low': c.low,
                    'close': c.close,
                    'volume': c.volume
                } for c in candles])
            
            @app.route('/api/state')
            def get_state():
                fees_paid = state.interface.get_fees_paid() if state.interface else 0.0
                return jsonify({
                    'strategy': state.strategy_name,
                    'product_id': product_id,
                    'granularity': granularity,
                    'starting_balance': state.starting_balance,
                    'current_value': state.current_value,
                    'position': state.position,
                    'profit_pct': ((state.current_value - state.starting_balance) / state.starting_balance) * 100,
                    'trade_count': len(state.trades),
                    'fees_paid': fees_paid,
                    'running': state.running,
                    'mode': 'paper'
                })
            
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
                if state.stream is None:
                    return jsonify({})
                
                from ..indicators import ema, sma, rsi, macd, bollinger_bands
                
                candles = state.stream.get_candles()
                if len(candles) < 50:
                    return jsonify({})
                
                times = [c.timestamp * 1000 for c in candles]
                indicators = {}
                
                for period in [9, 20, 50]:
                    values = ema(candles, period)
                    indicators[f'ema_{period}'] = {
                        'times': times,
                        'values': values,
                        'name': f'EMA({period})',
                        'type': 'line'
                    }
                
                bb = bollinger_bands(candles, 20, 2)
                indicators['bb_upper'] = {'times': times, 'values': bb['upper'], 'name': 'BB Upper', 'type': 'line'}
                indicators['bb_lower'] = {'times': times, 'values': bb['lower'], 'name': 'BB Lower', 'type': 'line'}
                
                rsi_values = rsi(candles, 14)
                indicators['rsi'] = {'times': times, 'values': rsi_values, 'name': 'RSI(14)', 'type': 'oscillator'}
                
                # MACD with signal and histogram
                macd_result = macd(candles, 12, 26, 9)
                indicators['macd'] = {'times': times, 'values': macd_result['macd'], 'name': 'MACD', 'type': 'oscillator'}
                indicators['macd_signal'] = {'times': times, 'values': macd_result['signal'], 'name': 'Signal', 'type': 'oscillator'}
                indicators['macd_hist'] = {'times': times, 'values': macd_result['histogram'], 'name': 'Histogram', 'type': 'histogram'}
                
                return jsonify(indicators)
            
            # Background emitter for real-time updates
            def emit_updates():
                import time as t
                last_candle_count = 0
                while state.running:
                    if state.stream:
                        current_count = len(state.stream)
                        if current_count > last_candle_count:
                            candles = state.stream.get_candles()
                            if candles:
                                latest = candles[-1]
                                socketio.emit('candle', {
                                    'time': latest.timestamp * 1000,
                                    'open': latest.open,
                                    'high': latest.high,
                                    'low': latest.low,
                                    'close': latest.close,
                                    'volume': latest.volume
                                })
                                socketio.emit('state', {
                                    'current_value': state.current_value,
                                    'position': state.position,
                                    'profit_pct': ((state.current_value - state.starting_balance) / state.starting_balance) * 100
                                })
                            last_candle_count = current_count
                    t.sleep(1)
            
            emitter_thread = threading.Thread(target=emit_updates, daemon=True)
            emitter_thread.start()
            
            socketio.run(app, host='0.0.0.0', port=port, debug=False, use_reloader=False, log_output=False)
        
        except ImportError as e:
            print(f"⚠️  Dashboard dependencies not installed: {e}")
    
    dashboard_thread = threading.Thread(target=run_dashboard, daemon=True)
    dashboard_thread.start()
    
    # Open browser after a short delay
    def open_browser():
        time.sleep(2)
        webbrowser.open(f'http://localhost:{port}')
    
    browser_thread = threading.Thread(target=open_browser, daemon=True)
    browser_thread.start()
