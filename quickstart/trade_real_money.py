#!/usr/bin/env python3
"""
REAL MONEY TRADING

⚠️  WARNING: This script trades with REAL money on Coinbase.  ⚠️
Only run if you understand the risks and have tested with paper trading.

Uses the AdaptiveStrategy from dynamic_allocation example, modified for
spot trading (no leverage, no shorting - Coinbase limitation).

Run with: python examples/trade_real_money.py
"""

import sys
import json
import time
import threading
from pathlib import Path
from datetime import datetime

# Add framework to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from framework import Strategy, Candle
from framework.interfaces.coinbase import CoinbaseInterface
from framework.data.stream import LiveStream
from framework.indicators import ema, rsi, atr


# =============================================================================
# CONFIGURATION
# =============================================================================

PRODUCT_ID = "BTC-USD"          # Trading pair
SECRETS_FILE = "secrets1.json"  # Which secrets file to use
MIN_USD_BALANCE = 10.0          # Minimum USD to trade with
CHECK_INTERVAL = 60             # Seconds between checks
WARMUP_CANDLES = 50             # Candles before trading starts
DASHBOARD_PORT = 5003           # Dashboard port


# =============================================================================
# STRATEGY (Adapted for spot trading - no leverage/shorting)
# =============================================================================

class SpotAdaptiveStrategy(Strategy):
    """
    Adaptive strategy modified for Coinbase spot trading.
    
    Key differences from the leveraged version:
    - Max allocation is 1.0 (no leverage on Coinbase)
    - No shorting (Coinbase spot doesn't support it)
    """
    
    def __init__(self, fast_period: int = 9, slow_period: int = 21, **kwargs):
        super().__init__(**kwargs)
        self.fast_period = fast_period
        self.slow_period = slow_period
    
    def _get_confidence(self, candles: list[Candle]) -> float:
        """
        Calculate confidence level (0.0 to 1.0) based on RSI.
        Higher confidence near oversold, lower near overbought.
        """
        if len(candles) < 14:
            return 0.8
        
        rsi_vals = rsi(candles, 14)
        if rsi_vals[-1] is None:
            return 0.8
        
        current_rsi = rsi_vals[-1]
        
        # Scale position based on RSI (capped at 1.0 for spot trading)
        if current_rsi < 30:
            return 1.0  # Full confidence when oversold
        elif current_rsi < 40:
            return 0.9
        elif current_rsi > 70:
            return 0.5  # Low confidence when overbought
        elif current_rsi > 60:
            return 0.7
        return 0.8
    
    def buy_signal(self, candles: list[Candle]):
        """
        Return allocation (0.0 to 1.0) for spot trading.
        """
        if len(candles) < self.slow_period + 2:
            return False
        
        fast = ema(candles, self.fast_period)
        slow = ema(candles, self.slow_period)
        
        if None in [fast[-1], fast[-2], slow[-1], slow[-2]]:
            return False
        
        # Bullish crossover
        if fast[-1] > slow[-1] and fast[-2] <= slow[-2]:
            return self._get_confidence(candles)
        
        return False
    
    def sell_signal(self, candles: list[Candle]):
        """
        Return True to sell (no shorting on spot).
        """
        if len(candles) < self.slow_period + 2:
            return False
        
        fast = ema(candles, self.fast_period)
        slow = ema(candles, self.slow_period)
        
        if None in [fast[-1], fast[-2], slow[-1], slow[-2]]:
            return False
        
        # Bearish crossover - just exit, no short
        if fast[-1] < slow[-1] and fast[-2] >= slow[-2]:
            return True
        
        return False


# =============================================================================
# LIVE TRADING STATE
# =============================================================================

class LiveTradingState:
    """Shared state for live trading with dashboard."""
    
    def __init__(self, interface, stream, strategy_name):
        self.interface = interface
        self.stream = stream
        self.strategy_name = strategy_name
        self.starting_value = 0.0
        self.current_value = 0.0
        self.position = "short"
        self.trades = []
        self.equity_curve = []
        self.logs = []
        self.running = True
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
    
    def update_equity(self, value: float):
        import time as t
        with self._lock:
            self.equity_curve.append({
                'time': t.time() * 1000,
                'value': value
            })


# =============================================================================
# DASHBOARD
# =============================================================================

def launch_dashboard(state: LiveTradingState, product_id: str):
    """Launch the live trading dashboard in a background thread."""
    import webbrowser
    
    def run_dashboard():
        try:
            from flask import Flask, render_template, jsonify
            from flask_socketio import SocketIO
            from flask_cors import CORS
            from framework.indicators import ema, rsi, macd, bollinger_bands
            import os
            
            template_dir = os.path.abspath(os.path.join(
                Path(__file__).parent.parent,
                'framework', 'dashboard', 'templates'
            ))
            app = Flask(__name__, template_folder=template_dir)
            app.config['SECRET_KEY'] = 'live-trading-secret'
            CORS(app, resources={r"/*": {"origins": "*"}})
            socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')
            
            @app.route('/')
            def index():
                return render_template('live_trading.html')
            
            @app.route('/api/candles')
            def get_candles():
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
                profit_pct = ((state.current_value - state.starting_value) / state.starting_value) * 100 if state.starting_value > 0 else 0
                return jsonify({
                    'strategy': state.strategy_name,
                    'product_id': product_id,
                    'granularity': '1m',
                    'starting_balance': state.starting_value,
                    'current_value': state.current_value,
                    'position': state.position,
                    'profit_pct': profit_pct,
                    'trade_count': len(state.trades),
                    'fees_paid': state.interface.get_fees_paid(),
                    'running': state.running,
                    'mode': 'LIVE'
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
                candles = state.stream.get_candles()
                if len(candles) < 50:
                    return jsonify({})
                
                times = [c.timestamp * 1000 for c in candles]
                
                ema9 = ema(candles, 9)
                ema20 = ema(candles, 20)
                rsi_vals = rsi(candles, 14)
                macd_result = macd(candles)
                bb_result = bollinger_bands(candles, 20, 2.0)
                
                return jsonify({
                    'ema_9': {'times': times, 'values': ema9, 'name': 'EMA 9'},
                    'ema_20': {'times': times, 'values': ema20, 'name': 'EMA 20'},
                    'rsi': {'times': times, 'values': rsi_vals, 'name': 'RSI'},
                    'macd': {'times': times, 'values': macd_result['macd'], 'name': 'MACD'},
                    'macd_signal': {'times': times, 'values': macd_result['signal'], 'name': 'Signal'},
                    'macd_histogram': {'times': times, 'values': macd_result['histogram'], 'name': 'Histogram'},
                    'bb_upper': {'times': times, 'values': bb_result['upper'], 'name': 'BB Upper'},
                    'bb_middle': {'times': times, 'values': bb_result['middle'], 'name': 'BB Middle'},
                    'bb_lower': {'times': times, 'values': bb_result['lower'], 'name': 'BB Lower'}
                })
            
            # Real-time updates
            def emit_updates():
                import time as t
                last_candle_count = 0
                last_trade_count = 0
                last_log_count = 0
                
                while state.running:
                    candles = state.stream.get_candles()
                    current_candle_count = len(candles)
                    current_trade_count = len(state.trades)
                    current_log_count = len(state.logs)
                    
                    # Emit new candle
                    if current_candle_count > last_candle_count and candles:
                        latest = candles[-1]
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
                    
                    # Emit state
                    profit_pct = ((state.current_value - state.starting_value) / state.starting_value) * 100 if state.starting_value > 0 else 0
                    socketio.emit('state', {
                        'current_value': state.current_value,
                        'position': state.position,
                        'profit_pct': profit_pct,
                        'trade_count': current_trade_count,
                        'fees_paid': state.interface.get_fees_paid()
                    })
                    
                    t.sleep(0.5)
            
            emitter = threading.Thread(target=emit_updates, daemon=True)
            emitter.start()
            
            socketio.run(app, host='0.0.0.0', port=DASHBOARD_PORT, debug=False,
                        use_reloader=False, log_output=False)
        
        except ImportError as e:
            print(f"⚠️  Dashboard dependencies missing: {e}")
    
    dashboard_thread = threading.Thread(target=run_dashboard, daemon=True)
    dashboard_thread.start()
    
    # Open browser
    def open_browser():
        time.sleep(2)
        webbrowser.open(f'http://localhost:{DASHBOARD_PORT}')
    
    threading.Thread(target=open_browser, daemon=True).start()


# =============================================================================
# SECRETS LOADING
# =============================================================================

def load_secrets(filename: str) -> dict:
    """Load API credentials from secrets file."""
    secrets_path = Path(__file__).parent.parent / "secrets" / filename
    
    if not secrets_path.exists():
        raise FileNotFoundError(
            f"Secrets file not found: {secrets_path}\n"
            f"Create a secrets/{filename} with your Coinbase API credentials."
        )
    
    with open(secrets_path) as f:
        secrets = json.load(f)
    
    required = ['coinbase_api_key_name', 'coinbase_api_private_key']
    for key in required:
        if key not in secrets:
            raise ValueError(f"Missing '{key}' in secrets file")
    
    return secrets


# =============================================================================
# BALANCE CHECKS
# =============================================================================

def check_balances(interface: CoinbaseInterface) -> dict:
    """Check and validate account balances."""
    usd = interface.get_balance("USD")
    btc = interface.get_balance(interface.asset_code)
    price = interface.get_current_price()
    
    total_value = usd + (btc * price)
    
    return {
        'usd': usd,
        'btc': btc,
        'price': price,
        'total_value': total_value,
        'position': interface.position
    }


def print_balances(balances: dict):
    """Pretty print balance information."""
    print(f"\n{'='*50}")
    print(f"💰 ACCOUNT BALANCES")
    print(f"{'='*50}")
    print(f"  USD:         ${balances['usd']:,.2f}")
    print(f"  BTC:         {balances['btc']:.8f}")
    print(f"  BTC Price:   ${balances['price']:,.2f}")
    print(f"  Total Value: ${balances['total_value']:,.2f}")
    print(f"  Position:    {balances['position'].upper()}")
    print(f"{'='*50}\n")


# =============================================================================
# MAIN TRADING LOOP
# =============================================================================

def run_live_trading():
    """Main trading loop."""
    print("\n" + "="*60)
    print("⚠️  REAL MONEY TRADING - COINBASE")
    print("="*60)
    print(f"  Product:  {PRODUCT_ID}")
    print(f"  Strategy: SpotAdaptiveStrategy (EMA crossover + RSI)")
    print(f"  Interval: {CHECK_INTERVAL}s")
    print(f"  Dashboard: http://localhost:{DASHBOARD_PORT}")
    print("="*60)
    
    # Load secrets
    print("\n🔑 Loading API credentials...")
    secrets = load_secrets(SECRETS_FILE)
    
    # Create interface
    interface = CoinbaseInterface(
        api_key=secrets['coinbase_api_key_name'],
        api_secret=secrets['coinbase_api_private_key'],
        product_id=PRODUCT_ID
    )
    
    # Connect
    print("🔌 Connecting to Coinbase...")
    interface.connect()
    print("✅ Connected!")
    
    # Check balances
    balances = check_balances(interface)
    print_balances(balances)
    
    # Validate minimum balance
    if balances['usd'] < MIN_USD_BALANCE and balances['position'] == 'short':
        raise ValueError(
            f"Insufficient USD balance: ${balances['usd']:.2f} "
            f"(minimum: ${MIN_USD_BALANCE:.2f})"
        )
    
    # Initialize data stream
    print(f"\n📊 Initializing data stream for {PRODUCT_ID}...")
    stream = LiveStream(product_id=PRODUCT_ID, granularity="1m")
    stream.start()
    
    # Warmup
    print(f"⏳ Warming up with {WARMUP_CANDLES} candles...")
    while len(stream.get_candles()) < WARMUP_CANDLES:
        time.sleep(1)
        sys.stdout.write(f"\r   Got {len(stream.get_candles())}/{WARMUP_CANDLES} candles...")
        sys.stdout.flush()
    print(f"\n✅ Warmup complete!")
    
    # Initialize strategy
    strategy = SpotAdaptiveStrategy(fast_period=9, slow_period=21)
    strategy.asset_baseline = balances['btc'] if balances['btc'] > 0 else balances['usd'] / balances['price']
    strategy.currency_baseline = balances['total_value']
    
    # Create state for dashboard
    state = LiveTradingState(interface, stream, "SpotAdaptiveStrategy")
    state.starting_value = balances['total_value']
    state.current_value = balances['total_value']
    state.position = interface.position
    state.update_equity(balances['total_value'])
    
    # Launch dashboard
    print(f"\n🌐 Launching dashboard at http://localhost:{DASHBOARD_PORT}...")
    launch_dashboard(state, PRODUCT_ID)
    time.sleep(3)  # Give dashboard time to start
    
    # Trading loop
    print("\n🤖 Starting trading loop (Ctrl+C to stop)...")
    print("-" * 60)
    
    trade_count = 0
    start_value = balances['total_value']
    
    try:
        while True:
            candles = stream.get_candles()
            
            if not candles:
                time.sleep(1)
                continue
            
            current_price = candles[-1].close
            current_time = datetime.now().strftime("%H:%M:%S")
            
            # Update balances periodically
            balances = check_balances(interface)
            profit_pct = ((balances['total_value'] - start_value) / start_value) * 100
            
            # Update state
            state.current_value = balances['total_value']
            state.position = interface.position
            state.update_equity(balances['total_value'])
            
            print(f"[{current_time}] Price: ${current_price:,.2f} | "
                  f"Value: ${balances['total_value']:,.2f} ({profit_pct:+.2f}%) | "
                  f"Position: {balances['position'].upper()}")
            
            # Check signals
            if interface.position == "short":  # Has USD, can buy
                buy_result = strategy.buy_signal(candles)
                should_buy, allocation = strategy.parse_signal(buy_result)
                
                if should_buy:
                    allocation = min(allocation or 1.0, 1.0)  # Cap at 1.0
                    amount = balances['usd'] * allocation
                    
                    msg = f"🟢 BUY @ ${current_price:,.2f} | Allocation: {allocation:.0%} | Amount: ${amount:,.2f}"
                    print(f"\n{msg}")
                    state.add_log(msg)
                    
                    # Execute buy
                    received, spent = interface.execute_buy(current_price, 0.006, amount)
                    trade_count += 1
                    
                    msg = f"✅ Bought {received:.8f} BTC for ${spent:,.2f}"
                    print(f"   {msg}")
                    state.add_log(msg)
                    state.add_trade('buy', current_price, received, balances['total_value'])
                    
            elif interface.position == "long":  # Has BTC, can sell
                sell_result = strategy.sell_signal(candles)
                should_sell, _ = strategy.parse_signal(sell_result)
                
                if should_sell:
                    amount = interface.asset
                    
                    msg = f"🔴 SELL @ ${current_price:,.2f} | Amount: {amount:.8f} BTC"
                    print(f"\n{msg}")
                    state.add_log(msg)
                    
                    # Execute sell
                    received, spent = interface.execute_sell(current_price, 0.006, amount)
                    trade_count += 1
                    
                    msg = f"✅ Sold {spent:.8f} BTC for ${received:,.2f}"
                    print(f"   {msg}")
                    state.add_log(msg)
                    state.add_trade('sell', current_price, amount, balances['total_value'])
            
            time.sleep(CHECK_INTERVAL)
            
    except KeyboardInterrupt:
        print("\n\n🛑 Stopping trading...")
        state.running = False
        
        # Final summary
        balances = check_balances(interface)
        profit_pct = ((balances['total_value'] - start_value) / start_value) * 100
        
        print("\n" + "="*60)
        print("📊 SESSION SUMMARY")
        print("="*60)
        print(f"  Start Value:  ${start_value:,.2f}")
        print(f"  End Value:    ${balances['total_value']:,.2f}")
        print(f"  Profit/Loss:  {profit_pct:+.2f}%")
        print(f"  Trades:       {trade_count}")
        print(f"  Fees Paid:    ${interface.get_fees_paid():,.2f}")
        print("="*60)
        
        stream.stop()


if __name__ == "__main__":
    # Confirmation prompt
    print("\n" + "⚠️ "*20)
    print("\n  THIS SCRIPT TRADES WITH REAL MONEY!")
    print("  Make sure you have tested with paper trading first.")
    print("\n" + "⚠️ "*20)
    
    confirm = input("\nType 'I UNDERSTAND' to continue: ")
    if confirm.strip() != "I UNDERSTAND":
        print("Aborted.")
        sys.exit(1)
    
    run_live_trading()
