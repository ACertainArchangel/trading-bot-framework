"""
Live Trading Runner - Deploy strategies with real money.

⚠️  WARNING: This uses REAL MONEY. Test thoroughly with paper trading first!
"""

from typing import Type, Optional, Dict, Any
import time
import signal
import json
import os
import threading

from ..strategies.base import Strategy
from ..data.stream import LiveStream
from ..interfaces.coinbase import CoinbaseInterface
from ..interfaces.base import Allocation, DEFAULT_ALLOCATION


class LiveTradingState:
    """Shared state for live trading with dashboard."""
    
    def __init__(self, starting_value: float):
        self.starting_value = starting_value
        self.current_value = starting_value
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


def live_trade(
    strategy: Type[Strategy],
    api_key: Optional[str] = None,
    api_secret: Optional[str] = None,
    secrets_file: Optional[str] = None,
    product_id: str = "BTC-USD",
    granularity: str = '1m',
    fee_rate: float = 0.00025,  # Coinbase maker fee
    loss_tolerance: float = 0.0,
    allocation: Optional[Allocation] = None,
    strategy_params: Optional[Dict[str, Any]] = None,
    check_interval: float = 1.0,
    confirm: bool = True,
    dashboard: bool = False,
    dashboard_port: int = 5002,
    history_days: int = 30
):
    """
    Run a strategy with real money on Coinbase.
    
    ⚠️  WARNING: This trades with REAL MONEY!
    
    Data Integrity:
        Trades are automatically gated behind data validity checks.
        If the market data has gaps or becomes stale, ALL TRADES ARE PAUSED
        until the data is restored. This protects you from making decisions
        based on incomplete information.
    
    Args:
        strategy: Strategy class to run
        api_key: Coinbase API key name (or use secrets_file)
        api_secret: Coinbase API private key (or use secrets_file)
        secrets_file: Path to JSON file with 'name' and 'privateKey'
        product_id: Trading pair
        granularity: Candle size
        fee_rate: Trading fee (0.00025 = 0.025% maker)
        loss_tolerance: Max acceptable loss
        allocation: Position sizing (0-1 for Coinbase spot).
                   Default: {'short': 0, 'long': 1}
                   Note: Coinbase spot doesn't support leverage or shorting.
        strategy_params: Additional strategy parameters
        check_interval: Seconds between signal checks
        confirm: If True, require user confirmation before starting
        dashboard: If True, launch web dashboard for visualization
        dashboard_port: Port for dashboard (default 5002)
        history_days: Days of historical data to load (default 30)
    
    Secrets File Format:
        {
            "name": "organizations/.../apiKeys/...",
            "privateKey": "-----BEGIN EC PRIVATE KEY-----\\n...\\n-----END EC PRIVATE KEY-----"
        }
    
    Example:
        >>> from framework import live_trade, Strategy
        >>> 
        >>> class MyStrategy(Strategy):
        ...     # ... well-tested strategy
        >>> 
        >>> # With visualization dashboard
        >>> live_trade(
        ...     MyStrategy,
        ...     secrets_file="secrets/my_api.json",
        ...     loss_tolerance=0.01,
        ...     dashboard=True
        ... )
    """
    strategy_params = strategy_params or {}
    
    # Load credentials
    if secrets_file:
        if not os.path.exists(secrets_file):
            raise FileNotFoundError(f"Secrets file not found: {secrets_file}")
        
        with open(secrets_file) as f:
            secrets = json.load(f)
        
        api_key = secrets.get('name')
        api_secret = secrets.get('privateKey')
    
    if not api_key or not api_secret:
        raise ValueError(
            "API credentials required. Provide api_key/api_secret "
            "or a secrets_file path."
        )
    
    print()
    print("⚠️  " + "=" * 56 + " ⚠️")
    print("⚠️  LIVE TRADING MODE - REAL MONEY AT RISK!              ⚠️")
    print("⚠️  " + "=" * 56 + " ⚠️")
    print()
    print(f"Strategy:    {strategy.__name__}")
    print(f"Product:     {product_id}")
    print(f"Granularity: {granularity}")
    print(f"Fee Rate:    {fee_rate * 100:.4f}%")
    print(f"Loss Tol:    {loss_tolerance * 100:.2f}%")
    print()
    
    # Confirmation
    if confirm:
        response = input("Type 'YES' to confirm live trading: ")
        if response.strip() != "YES":
            print("❌ Cancelled.")
            return None
    
    # Initialize interface
    print("\n🔌 Connecting to Coinbase...")
    interface = CoinbaseInterface(
        api_key=api_key,
        api_secret=api_secret,
        product_id=product_id,
        allocation=allocation
    )
    interface.connect()
    
    print(f"✅ Connected!")
    print(f"   Currency: ${interface.currency:,.2f}")
    print(f"   Asset: {interface.asset:.8f}")
    print(f"   Position: {interface.position.upper()}")
    
    # Get starting value
    current_price = interface.get_current_price()
    starting_value = interface.get_total_value(current_price)
    
    print(f"   Value: ${starting_value:,.2f}")
    
    # Create shared state for dashboard
    state = LiveTradingState(starting_value)
    state.strategy_name = strategy.__name__
    state.interface = interface
    state.position = interface.position
    
    # Launch dashboard if requested
    if dashboard:
        print(f"   Dashboard: http://localhost:{dashboard_port}")
        _launch_live_dashboard(
            state=state,
            product_id=product_id,
            granularity=granularity,
            port=dashboard_port
        )
    
    # Initialize strategy
    strat = strategy(
        fee_rate=fee_rate,
        loss_tolerance=loss_tolerance,
        **strategy_params
    )
    
    # Set baselines
    strat.currency_baseline = starting_value if interface.position == "short" else interface.asset * current_price
    strat.asset_baseline = starting_value / current_price if interface.position == "short" else interface.asset
    
    # Initialize stream
    stream = LiveStream(
        product_id=product_id,
        granularity=granularity,
        history_hours=history_days * 24
    )
    state.stream = stream
    state.running = True
    
    # Handle Ctrl+C
    running = True
    data_warning_shown = False
    
    def handle_stop(signum, frame):
        nonlocal running
        print("\n\n🛑 Stopping live trading...")
        running = False
        state.running = False
    
    signal.signal(signal.SIGINT, handle_stop)
    signal.signal(signal.SIGTERM, handle_stop)
    
    print()
    print("⏳ Waiting for valid market data...")
    
    try:
        stream.start()
        
        # Wait for valid data before trading with REAL MONEY
        wait_count = 0
        while running and not stream.is_data_valid():
            time.sleep(1)
            wait_count += 1
            if wait_count > 30:
                print("⚠️  Warning: Data validation taking longer than expected")
                wait_count = 0
        
        if not running:
            return
        
        print("✅ Market data validated")
        print()
        print("🚀 Live trading started. Press Ctrl+C to stop.")
        print("-" * 60)
        
        last_candle_ts = 0
        
        while running:
            # CRITICAL: Check data validity before any trade with real money
            if not stream.is_data_valid():
                if not data_warning_shown:
                    print("⚠️  DATA INTEGRITY ISSUE - ALL TRADES PAUSED")
                    print("   Will not execute trades until data is validated")
                    state.add_log("⚠️  DATA INTEGRITY ISSUE - trades paused")
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
            
            # Sync interface balances periodically
            interface.currency = interface.get_balance(interface.currency_code)
            interface.asset = interface.get_balance(interface.asset_code)
            
            # Update position
            if interface.asset > interface.DUST_ASSET:
                interface.position = "long"
            else:
                interface.position = "short"
            
            # Only process on new candles
            if current.timestamp > last_candle_ts:
                last_candle_ts = current.timestamp
                
                # Calculate current value
                if interface.position == "short":
                    current_value = interface.currency
                else:
                    current_value = interface.asset * current_price
                
                profit_pct = ((current_value - starting_value) / starting_value) * 100
                
                # Update state for dashboard
                state.position = interface.position
                state.update_equity(current_value, current.timestamp)
                
                # Check signals
                if interface.position == "short":
                    if strat.buy_signal(candles):
                        amount = interface.currency
                        expected_asset = (amount * (1 - fee_rate)) / current_price
                        min_acceptable = strat.asset_baseline * (1 - loss_tolerance)
                        
                        if expected_asset > min_acceptable:
                            msg = f"💰 BUYING @ ~${current_price:,.2f}..."
                            print(msg)
                            state.add_log(msg)
                            
                            try:
                                received, spent = interface.execute_buy(
                                    current_price, fee_rate, amount
                                )
                                
                                strat.asset_baseline = interface.asset
                                strat.currency_baseline = interface.asset * current_price
                                
                                msg = f"✅ Bought {received:.8f} for ${spent:,.2f}"
                                print(f"   {msg}")
                                state.add_log(msg)
                                state.add_trade('buy', current_price, received, current_value)
                                state.position = "long"
                            
                            except Exception as e:
                                msg = f"❌ Buy failed: {e}"
                                print(f"   {msg}")
                                state.add_log(msg)
                
                elif interface.position == "long":
                    if strat.sell_signal(candles):
                        amount = interface.asset
                        expected_currency = (amount * current_price) * (1 - fee_rate)
                        min_acceptable = strat.currency_baseline * (1 - loss_tolerance)
                        
                        if expected_currency > min_acceptable:
                            msg = f"💵 SELLING @ ~${current_price:,.2f}..."
                            print(msg)
                            state.add_log(msg)
                            
                            try:
                                received, spent = interface.execute_sell(
                                    current_price, fee_rate, amount
                                )
                                
                                strat.currency_baseline = interface.currency
                                strat.asset_baseline = interface.currency / current_price
                                
                                msg = f"✅ Sold {spent:.8f} for ${received:,.2f}"
                                print(f"   {msg}")
                                state.add_log(msg)
                                state.add_trade('sell', current_price, spent, received)
                                state.position = "short"
                            
                            except Exception as e:
                                msg = f"❌ Sell failed: {e}"
                                print(f"   {msg}")
                                state.add_log(msg)
            
            time.sleep(check_interval)
    
    finally:
        stream.stop()
    
    # Print summary
    interface.currency = interface.get_balance(interface.currency_code)
    interface.asset = interface.get_balance(interface.asset_code)
    
    final_price = interface.get_current_price()
    if interface.position == "short":
        final_value = interface.currency
    else:
        final_value = interface.asset * final_price
    
    profit_pct = ((final_value - starting_value) / starting_value) * 100
    
    print()
    print("=" * 60)
    print("📊 LIVE TRADING SUMMARY")
    print("=" * 60)
    print(f"Starting Value:  ${starting_value:,.2f}")
    print(f"Ending Value:    ${final_value:,.2f}")
    print(f"Profit/Loss:     {profit_pct:+.2f}%")
    print(f"Final Position:  {interface.position.upper()}")
    print("=" * 60)
    
    state.running = False
    return interface


def _launch_live_dashboard(
    state: LiveTradingState,
    product_id: str,
    granularity: str,
    port: int
):
    """Launch the live trading dashboard in a background thread."""
    import webbrowser
    
    def run_dashboard():
        try:
            from flask import Flask, render_template, jsonify
            from flask_socketio import SocketIO
            from flask_cors import CORS
            import os
            
            template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'dashboard', 'templates'))
            app = Flask(__name__, template_folder=template_dir)
            app.config['SECRET_KEY'] = 'live-trading-secret'
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
                return jsonify({
                    'strategy': state.strategy_name,
                    'product_id': product_id,
                    'granularity': granularity,
                    'starting_value': state.starting_value,
                    'current_value': state.current_value,
                    'position': state.position,
                    'profit_pct': ((state.current_value - state.starting_value) / state.starting_value) * 100,
                    'trade_count': len(state.trades),
                    'fees_paid': state.interface.get_fees_paid(),
                    'running': state.running,
                    'mode': 'live'
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
                                    'profit_pct': ((state.current_value - state.starting_value) / state.starting_value) * 100
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
