#!/usr/bin/env python3
"""
Paper Trading Runner for Market Maker

Uses real order book data from Coinbase but simulates order execution.
Perfect for testing strategy logic without risking real money.

Usage:
    python -m market_making.paper_trading [options]
    
Options:
    --product_id PAIR     Trading pair (default: WET-USD)
    --trade_size USD      Size per trade in USD (default: 50)
    --min_profit PCT      Minimum profit % to execute (default: 0.01)
    --initial_usd USD     Starting USD balance (default: 1000)
    --interval SECS       Seconds between checks (default: 5)
    --max_rounds N        Maximum rounds to execute (default: unlimited)
    --verbose             Show detailed logging
"""

import argparse
import signal
import sys
import time
from datetime import datetime
from typing import Optional

from .market_maker import (
    MarketMaker,
    UnprofitableTradeError,
    InsufficientSpreadError,
    UnexpectedFeeError
)


class PaperTrader:
    """
    Paper trading wrapper around MarketMaker.
    
    Runs a continuous loop checking for profitable opportunities
    and executing simulated trades.
    """
    
    def __init__(
        self,
        product_id: str = "WET-USD",  # 4 decimal precision, $8M volume, 0.047% profit
        trade_size_usd: float = 50.0,
        min_profit_rate: float = 0.0001,
        fee_rate: float = 0.00025,
        initial_usd: float = 1000.0,
        check_interval: float = 5.0,
        max_rounds: Optional[int] = None,
        verbose: bool = False
    ):
        """
        Initialize paper trader.
        
        Args:
            product_id: Trading pair
            trade_size_usd: USD amount per trade
            min_profit_rate: Minimum profit rate (0.0001 = 0.01%)
            fee_rate: Expected maker fee rate
            initial_usd: Starting USD balance
            check_interval: Seconds between market checks
            max_rounds: Maximum rounds to execute (None = unlimited)
            verbose: Enable detailed logging
        """
        self.check_interval = check_interval
        self.max_rounds = max_rounds
        self.verbose = verbose
        self.running = False
        
        # Logger function
        def logger(msg: str):
            timestamp = datetime.now().strftime("%H:%M:%S")
            if verbose or not msg.startswith("   "):
                print(f"[{timestamp}] {msg}")
        
        # Initialize market maker
        self.mm = MarketMaker(
            product_id=product_id,
            fee_rate=fee_rate,
            min_profit_rate=min_profit_rate,
            trade_size_usd=trade_size_usd,
            logger=logger
        )
        
        # Set initial balances
        self.mm.set_balances(usd=initial_usd, asset=0.0)
        
        # Stats
        self.opportunities_checked = 0
        self.opportunities_skipped = 0
        self.start_time: Optional[datetime] = None
    
    def run_single_check(self) -> bool:
        """
        Check market and execute trade if profitable.
        
        Returns:
            True if a trade was executed
        """
        self.opportunities_checked += 1
        
        try:
            # Check if market is profitable
            analysis = self.mm.check_profitability()
            
            # Market is profitable - execute trade
            if self.verbose:
                print(f"📊 Spread: {analysis['spread_pct']:.4f}% | "
                      f"Expected profit: ${analysis['net_profit']:.4f}")
            
            # Start trade round
            buy_order, sell_order = self.mm.start_trade_round(analysis)
            
            # Simulate fills at analysis prices
            self.mm.simulate_fill(buy_order, fill_price=analysis["bid_price"])
            self.mm.simulate_fill(sell_order, fill_price=analysis["ask_price"])
            
            # Complete round
            self.mm.complete_round()
            
            return True
            
        except (UnprofitableTradeError, InsufficientSpreadError) as e:
            self.opportunities_skipped += 1
            if self.verbose:
                print(f"⏭️  Skipped: {e}")
            return False
            
        except UnexpectedFeeError as e:
            print(f"❌ FEE ERROR: {e}")
            self.running = False
            return False
            
        except Exception as e:
            print(f"❌ Error: {e}")
            if self.verbose:
                import traceback
                traceback.print_exc()
            return False
    
    def run(self):
        """Run continuous paper trading loop."""
        self.running = True
        self.start_time = datetime.now()
        
        print()
        print("=" * 60)
        print("📄 PAPER TRADING MODE - No real money at risk!")
        print("=" * 60)
        print(f"Product: {self.mm.product_id}")
        print(f"Trade Size: ${self.mm.trade_size_usd:.2f}")
        print(f"Check Interval: {self.check_interval}s")
        print(f"Max Rounds: {self.max_rounds or 'Unlimited'}")
        print("-" * 60)
        print("Press Ctrl+C to stop")
        print()
        
        try:
            while self.running:
                self.run_single_check()
                
                # Check if we've hit max rounds
                if self.max_rounds and self.mm.total_trades >= self.max_rounds:
                    print(f"\n🏁 Reached maximum rounds ({self.max_rounds})")
                    break
                
                # Wait before next check
                time.sleep(self.check_interval)
                
        except KeyboardInterrupt:
            print("\n\n⚠️  Stopping paper trader...")
        
        self.running = False
        self.print_summary()
    
    def print_summary(self):
        """Print trading session summary."""
        elapsed = (datetime.now() - self.start_time).total_seconds() if self.start_time else 0
        hours = elapsed / 3600
        
        stats = self.mm.get_stats()
        
        print()
        print("=" * 60)
        print("📊 PAPER TRADING SESSION SUMMARY")
        print("=" * 60)
        print(f"Duration: {elapsed/60:.1f} minutes ({hours:.2f} hours)")
        print(f"Opportunities Checked: {self.opportunities_checked}")
        print(f"Opportunities Skipped: {self.opportunities_skipped}")
        print(f"Trade Execution Rate: {stats['total_trades'] / self.opportunities_checked * 100:.1f}%"
              if self.opportunities_checked > 0 else "N/A")
        print()
        
        self.mm.print_stats()
        
        # Calculate annualized metrics
        if hours > 0 and stats['initial_usd'] > 0:
            hourly_return = stats['pnl_pct'] / hours
            daily_return = hourly_return * 24
            annual_return = (1 + daily_return/100) ** 365 * 100 - 100
            
            print()
            print("📈 PROJECTED RETURNS (if conditions persist)")
            print("-" * 50)
            print(f"Hourly Return: {hourly_return:.4f}%")
            print(f"Daily Return: {daily_return:.4f}%")
            print(f"Annual Return (compounded): {annual_return:.2f}%")


def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully."""
    print("\n⚠️  Received interrupt signal...")
    sys.exit(0)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Paper trading for ZEC-USD market making",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument("--product_id", type=str, default="WET-USD",
                       help="Trading pair (default: WET-USD)")
    parser.add_argument("--trade_size", type=float, default=50.0,
                       help="Trade size in USD (default: 50)")
    parser.add_argument("--min_profit", type=float, default=0.01,
                       help="Minimum profit %% to execute (default: 0.01)")
    parser.add_argument("--fee_rate", type=float, default=0.025,
                       help="Expected fee rate %% (default: 0.025)")
    parser.add_argument("--initial_usd", type=float, default=1000.0,
                       help="Starting USD balance (default: 1000)")
    parser.add_argument("--interval", type=float, default=5.0,
                       help="Seconds between checks (default: 5)")
    parser.add_argument("--max_rounds", type=int, default=None,
                       help="Maximum rounds to execute (default: unlimited)")
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="Show detailed logging")
    
    return parser.parse_args()


def main():
    """Main entry point."""
    # Set up signal handler
    signal.signal(signal.SIGINT, signal_handler)
    
    args = parse_args()
    
    # Convert percentages to decimals
    min_profit_rate = args.min_profit / 100
    fee_rate = args.fee_rate / 100
    
    trader = PaperTrader(
        product_id=args.product_id,
        trade_size_usd=args.trade_size,
        min_profit_rate=min_profit_rate,
        fee_rate=fee_rate,
        initial_usd=args.initial_usd,
        check_interval=args.interval,
        max_rounds=args.max_rounds,
        verbose=args.verbose
    )
    
    trader.run()


if __name__ == "__main__":
    main()
