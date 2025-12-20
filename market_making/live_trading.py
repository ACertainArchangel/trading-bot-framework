#!/usr/bin/env python3
"""
Live Trading Runner for Market Maker

⚠️  WARNING: This trades with REAL MONEY! ⚠️

Uses:
- Real Coinbase order book
- Real order execution
- secrets/secrets2.json for API credentials
- Web dashboard on port 5004

Usage:
    python -m market_making.live_trading [options]
    
Options:
    --product_id PAIR     Trading pair (default: VVV-USD)
    --trade_size USD      Size per trade in USD (default: 50)
    --min_profit PCT      Minimum profit % to execute (default: 0.01)
    --interval SECS       Seconds between checks (default: 10)
    --max_rounds N        Maximum rounds to execute (default: unlimited)
    --port N              Dashboard port (default: 5004)
    --secrets FILE        Secrets file path (default: secrets/secrets2.json)
    --no-confirm          Skip confirmation prompt
"""

import argparse
import signal
import sys
import time
import threading
from datetime import datetime
from typing import Optional

from flask import Flask, render_template_string, jsonify
from flask_socketio import SocketIO

from .live_executor import LiveMarketMaker, load_credentials
from .market_maker import (
    UnprofitableTradeError,
    InsufficientSpreadError,
    UnexpectedFeeError
)


# Flask app for dashboard
app = Flask(__name__)
app.config['SECRET_KEY'] = 'market_maker_secret'
socketio = SocketIO(app, cors_allowed_origins="*")

# Global state
trader = None
log_messages = []


def add_log(msg: str):
    """Add a log message with timestamp."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_entry = f"[{timestamp}] {msg}"
    log_messages.append(log_entry)
    if len(log_messages) > 100:
        log_messages.pop(0)
    print(log_entry)
    socketio.emit('log', {'message': log_entry})


# Dashboard HTML
DASHBOARD_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>ZEC Market Maker</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: #1a1a2e;
            color: #eee;
            margin: 0;
            padding: 20px;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        h1 { color: #00d4ff; text-align: center; }
        .warning { 
            background: #ff4444; 
            color: white; 
            padding: 10px; 
            text-align: center;
            border-radius: 5px;
            margin-bottom: 20px;
        }
        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
        .card {
            background: #16213e;
            border-radius: 10px;
            padding: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
        }
        .card h2 { color: #00d4ff; margin-top: 0; }
        .stat-row { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #2a3f5f; }
        .stat-label { color: #888; }
        .stat-value { font-weight: bold; }
        .positive { color: #00ff88; }
        .negative { color: #ff4444; }
        .neutral { color: #00d4ff; }
        #logs {
            background: #0f0f1a;
            padding: 15px;
            border-radius: 5px;
            height: 300px;
            overflow-y: auto;
            font-family: monospace;
            font-size: 12px;
        }
        .log-line { margin: 2px 0; }
        .order-book { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
        .bids { color: #00ff88; }
        .asks { color: #ff4444; }
        .spread-indicator {
            text-align: center;
            padding: 10px;
            background: #2a3f5f;
            border-radius: 5px;
            margin: 10px 0;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🦓 ZEC Market Maker</h1>
        <div class="warning">⚠️ LIVE TRADING MODE - Real money at risk!</div>
        
        <div class="grid">
            <div class="card">
                <h2>📊 Portfolio</h2>
                <div class="stat-row">
                    <span class="stat-label">USD Balance</span>
                    <span class="stat-value neutral" id="usd-balance">$0.00</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">ZEC Balance</span>
                    <span class="stat-value" id="zec-balance">0.0000</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Total Portfolio</span>
                    <span class="stat-value neutral" id="total-portfolio">$0.00</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Initial USD</span>
                    <span class="stat-value" id="initial-usd">$0.00</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">P&L</span>
                    <span class="stat-value" id="pnl">$0.00 (0.00%)</span>
                </div>
            </div>
            
            <div class="card">
                <h2>📈 Trading Stats</h2>
                <div class="stat-row">
                    <span class="stat-label">Total Trades</span>
                    <span class="stat-value" id="total-trades">0</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Profitable</span>
                    <span class="stat-value positive" id="profitable-trades">0</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Win Rate</span>
                    <span class="stat-value" id="win-rate">0%</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Total Profit</span>
                    <span class="stat-value" id="total-profit">$0.0000</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Total Fees</span>
                    <span class="stat-value negative" id="total-fees">$0.0000</span>
                </div>
            </div>
            
            <div class="card">
                <h2>📖 Order Book</h2>
                <div class="spread-indicator">
                    <div>Spread: <span id="spread">0.0000%</span></div>
                    <div>Mid Price: <span id="mid-price">$0.00</span></div>
                </div>
                <div class="order-book">
                    <div>
                        <strong class="bids">Bids (Buy)</strong>
                        <div id="bids"></div>
                    </div>
                    <div>
                        <strong class="asks">Asks (Sell)</strong>
                        <div id="asks"></div>
                    </div>
                </div>
            </div>
            
            <div class="card">
                <h2>📜 Activity Log</h2>
                <div id="logs"></div>
            </div>
        </div>
    </div>
    
    <script>
        const socket = io();
        
        socket.on('stats', function(data) {
            document.getElementById('usd-balance').textContent = '$' + data.usd_balance.toFixed(2);
            document.getElementById('zec-balance').textContent = data.asset_balance.toFixed(4);
            document.getElementById('total-portfolio').textContent = '$' + data.total_portfolio_usd.toFixed(2);
            document.getElementById('initial-usd').textContent = '$' + data.initial_usd.toFixed(2);
            
            const pnl = data.pnl_usd;
            const pnlPct = data.pnl_pct;
            const pnlElement = document.getElementById('pnl');
            pnlElement.textContent = '$' + pnl.toFixed(2) + ' (' + pnlPct.toFixed(2) + '%)';
            pnlElement.className = 'stat-value ' + (pnl >= 0 ? 'positive' : 'negative');
            
            document.getElementById('total-trades').textContent = data.total_trades;
            document.getElementById('profitable-trades').textContent = data.profitable_trades;
            document.getElementById('win-rate').textContent = data.win_rate.toFixed(1) + '%';
            
            const profit = data.total_profit;
            const profitElement = document.getElementById('total-profit');
            profitElement.textContent = '$' + profit.toFixed(4);
            profitElement.className = 'stat-value ' + (profit >= 0 ? 'positive' : 'negative');
            
            document.getElementById('total-fees').textContent = '$' + data.total_fees.toFixed(4);
        });
        
        socket.on('order_book', function(data) {
            document.getElementById('spread').textContent = data.spread_pct.toFixed(4) + '%';
            document.getElementById('mid-price').textContent = '$' + data.mid_price.toFixed(4);
            
            let bidsHtml = '';
            data.bids.forEach(function(b) {
                bidsHtml += '<div class="bids">$' + b.price.toFixed(4) + ' × ' + b.size.toFixed(4) + '</div>';
            });
            document.getElementById('bids').innerHTML = bidsHtml;
            
            let asksHtml = '';
            data.asks.forEach(function(a) {
                asksHtml += '<div class="asks">$' + a.price.toFixed(4) + ' × ' + a.size.toFixed(4) + '</div>';
            });
            document.getElementById('asks').innerHTML = asksHtml;
        });
        
        socket.on('log', function(data) {
            const logsDiv = document.getElementById('logs');
            logsDiv.innerHTML += '<div class="log-line">' + data.message + '</div>';
            logsDiv.scrollTop = logsDiv.scrollHeight;
        });
    </script>
</body>
</html>
'''


@app.route('/')
def dashboard():
    return render_template_string(DASHBOARD_HTML)


@app.route('/api/stats')
def api_stats():
    if trader and trader.mm:
        return jsonify(trader.mm.get_stats())
    return jsonify({})


class LiveTrader:
    """Live trading runner with web dashboard."""
    
    def __init__(
        self,
        api_key_name: str,
        api_private_key: str,
        product_id: str = "ZEC-USD",
        trade_size_usd: float = 50.0,
        min_profit_rate: float = 0.0001,
        fee_rate: float = 0.00025,
        check_interval: float = 10.0,
        max_rounds: Optional[int] = None,
        dashboard_port: int = 5004
    ):
        """Initialize live trader."""
        self.check_interval = check_interval
        self.max_rounds = max_rounds
        self.dashboard_port = dashboard_port
        self.running = False
        self.start_time: Optional[datetime] = None
        
        # Initialize live market maker
        self.mm = LiveMarketMaker(
            api_key_name=api_key_name,
            api_private_key=api_private_key,
            product_id=product_id,
            fee_rate=fee_rate,
            min_profit_rate=min_profit_rate,
            trade_size_usd=trade_size_usd,
            logger=add_log
        )
        
        # Stats
        self.opportunities_checked = 0
        self.opportunities_skipped = 0
    
    def emit_stats(self):
        """Send stats to dashboard."""
        if self.mm:
            socketio.emit('stats', self.mm.get_stats())
    
    def emit_order_book(self):
        """Send order book to dashboard."""
        try:
            book = self.mm.order_book.fetch_order_book(limit=5)
            socketio.emit('order_book', {
                'spread_pct': book.spread_percent or 0,
                'mid_price': book.mid_price or 0,
                'bids': [{'price': b.price, 'size': b.size} for b in book.bids[:5]],
                'asks': [{'price': a.price, 'size': a.size} for a in book.asks[:5]]
            })
        except Exception as e:
            add_log(f"⚠️  Order book fetch error: {e}")
    
    def run_single_check(self) -> bool:
        """Check market and execute trade if profitable."""
        self.opportunities_checked += 1
        
        try:
            # Check profitability
            analysis = self.mm.check_profitability()
            
            add_log(f"📊 Spread: {analysis['spread_pct']:.4f}% | "
                   f"Expected profit: ${analysis['net_profit']:.4f}")
            
            # Execute live trade
            success = self.mm.execute_live_round(analysis)
            
            if success:
                self.emit_stats()
            
            return success
            
        except (UnprofitableTradeError, InsufficientSpreadError) as e:
            self.opportunities_skipped += 1
            # Don't spam logs for normal skips
            return False
            
        except UnexpectedFeeError as e:
            add_log(f"❌ FEE ERROR: {e}")
            self.running = False
            return False
            
        except Exception as e:
            add_log(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def trading_loop(self):
        """Main trading loop."""
        add_log("🚀 Starting live trading loop...")
        
        # Sync balances from exchange
        add_log("💰 Syncing balances from Coinbase...")
        self.mm.sync_balances_from_exchange()
        self.emit_stats()
        
        while self.running:
            try:
                # Emit order book
                self.emit_order_book()
                
                # Check for trading opportunity
                self.run_single_check()
                
                # Check if we've hit max rounds
                if self.max_rounds and self.mm.total_trades >= self.max_rounds:
                    add_log(f"🏁 Reached maximum rounds ({self.max_rounds})")
                    break
                
                # Wait before next check
                time.sleep(self.check_interval)
                
            except Exception as e:
                add_log(f"❌ Loop error: {e}")
                time.sleep(self.check_interval)
        
        self.running = False
        add_log("⏹️  Trading loop stopped")
        self.mm.print_stats()
    
    def run(self):
        """Start trading with web dashboard."""
        global trader
        trader = self
        
        self.running = True
        self.start_time = datetime.now()
        
        # Start trading in background thread
        trading_thread = threading.Thread(target=self.trading_loop, daemon=True)
        trading_thread.start()
        
        # Start dashboard
        add_log(f"📊 Dashboard available at http://localhost:{self.dashboard_port}")
        socketio.run(app, host='0.0.0.0', port=self.dashboard_port, debug=False)


def confirm_live_trading(product_id: str, trade_size: float, fee_rate: float):
    """Ask user to confirm live trading."""
    print()
    print("=" * 70)
    print("⚠️  LIVE TRADING MODE - REAL MONEY WARNING")
    print("=" * 70)
    print()
    print("This bot will trade with REAL MONEY on Coinbase Exchange!")
    print()
    print("Configuration:")
    print(f"  • Product: {product_id}")
    print(f"  • Trade Size: ${trade_size:.2f}")
    print(f"  • Fee Rate: {fee_rate * 100:.4f}%")
    print()
    print("The bot will:")
    print("  ✓ Place real limit orders on Coinbase")
    print("  ✓ Execute trades automatically when spread is profitable")
    print("  ✓ Use your actual Coinbase balance")
    print()
    
    response = input("Type 'YES' to start live trading: ")
    
    if response.strip().upper() != 'YES':
        print("❌ Live trading cancelled")
        sys.exit(0)
    
    print()
    print("✅ Starting live trading...")
    print()


def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully."""
    global trader
    print("\n⚠️  Received interrupt signal...")
    if trader:
        trader.running = False
    sys.exit(0)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Live trading for ZEC-USD market making",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument("--product_id", type=str, default="ZEC-USD",
                       help="Trading pair (default: ZEC-USD)")
    parser.add_argument("--trade_size", type=float, default=50.0,
                       help="Trade size in USD (default: 50)")
    parser.add_argument("--min_profit", type=float, default=0.01,
                       help="Minimum profit %% to execute (default: 0.01)")
    parser.add_argument("--fee_rate", type=float, default=0.025,
                       help="Expected fee rate %% (default: 0.025)")
    parser.add_argument("--interval", type=float, default=10.0,
                       help="Seconds between checks (default: 10)")
    parser.add_argument("--max_rounds", type=int, default=None,
                       help="Maximum rounds to execute (default: unlimited)")
    parser.add_argument("--port", type=int, default=5004,
                       help="Dashboard port (default: 5004)")
    parser.add_argument("--secrets", type=str, default="secrets/secrets2.json",
                       help="Secrets file path (default: secrets/secrets2.json)")
    parser.add_argument("--no-confirm", action="store_true",
                       help="Skip confirmation prompt")
    
    return parser.parse_args()


def main():
    """Main entry point."""
    # Set up signal handler
    signal.signal(signal.SIGINT, signal_handler)
    
    args = parse_args()
    
    # Load credentials
    try:
        api_key_name, api_private_key = load_credentials(args.secrets)
    except (FileNotFoundError, ValueError) as e:
        print(f"❌ {e}")
        sys.exit(1)
    
    # Convert percentages to decimals
    min_profit_rate = args.min_profit / 100
    fee_rate = args.fee_rate / 100
    
    # Confirm with user
    if not args.no_confirm:
        confirm_live_trading(args.product_id, args.trade_size, fee_rate)
    
    # Create and run trader
    live_trader = LiveTrader(
        api_key_name=api_key_name,
        api_private_key=api_private_key,
        product_id=args.product_id,
        trade_size_usd=args.trade_size,
        min_profit_rate=min_profit_rate,
        fee_rate=fee_rate,
        check_interval=args.interval,
        max_rounds=args.max_rounds,
        dashboard_port=args.port
    )
    
    live_trader.run()


if __name__ == "__main__":
    main()
