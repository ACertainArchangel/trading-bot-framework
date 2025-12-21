"""
Main trading bot for aggressive trading with SL/TP.
"""

import time
from datetime import datetime
from typing import Optional, Callable, List

from .position import Position, PositionSide, ExitReason
from .order_manager import OrderManager, BracketOrder
from .strategies import AggressiveStrategy, EntrySignal, Candle


class AggressiveBot:
    """
    Trading bot that uses stop-loss and take-profit orders.
    
    Key differences from vanilla bot:
    - Places bracket orders (entry + SL + TP)
    - Can check more frequently than once per minute
    - Supports multiple concurrent positions
    - Tracks detailed P&L per trade
    """
    
    def __init__(self, 
                 interface,
                 strategy: AggressiveStrategy,
                 pair: str = "BTC-USD",
                 fee_rate: float = 0.0025,
                 check_interval: float = 10.0,  # seconds
                 max_positions: int = 1,
                 logger: Callable[[str], None] = None):
        """
        Args:
            interface: Trading interface (Coinbase, Paper, etc.)
            strategy: Strategy instance
            pair: Trading pair
            fee_rate: Trading fee as decimal
            check_interval: Seconds between checks
            max_positions: Max concurrent positions
            logger: Logging function
        """
        self.interface = interface
        self.strategy = strategy
        self.pair = pair
        self.fee_rate = fee_rate
        self.check_interval = check_interval
        self.max_positions = max_positions
        
        self._log = logger or (lambda x: None)
        
        # Order management
        self.order_manager = OrderManager(
            interface=interface,
            fee_rate=fee_rate,
            logger=self._log
        )
        
        # State
        self.running = False
        self.candles: List[Candle] = []
        self.current_price: float = 0.0
        
        # Stats
        self.start_time: Optional[datetime] = None
        self.checks_performed: int = 0
        
    def load_historical_candles(self, candles: List[Candle]):
        """Load historical candle data."""
        self.candles = candles
        self._log(f"📊 Loaded {len(candles)} historical candles")
    
    def update_candle(self, candle: Candle):
        """Add new candle data."""
        self.candles.append(candle)
        # Keep reasonable history
        if len(self.candles) > 1000:
            self.candles = self.candles[-500:]
    
    def tick(self, current_price: float) -> Optional[BracketOrder]:
        """
        Process one tick of market data.
        
        Args:
            current_price: Current market price
            
        Returns:
            BracketOrder if new position opened, None otherwise
        """
        self.current_price = current_price
        self.checks_performed += 1
        
        # Update existing positions
        self.order_manager.update(current_price)
        
        # Check for early exit signals on open positions
        for bracket in self.order_manager.brackets:
            if bracket.position.is_filled:
                pos = bracket.position
                if self.strategy.should_exit_early(
                    self.candles, current_price, pos.entry_price, pos.side
                ):
                    self._log(f"📤 Strategy signals early exit")
                    self.order_manager._close_bracket(
                        bracket, current_price, ExitReason.STRATEGY_EXIT
                    )
        
        # Check if we can open new position
        open_count = len(self.order_manager.open_positions)
        pending_count = len(self.order_manager.pending_entries)
        
        if open_count + pending_count >= self.max_positions:
            return None  # At capacity
        
        # Check for entry signal
        signal = self.strategy.should_enter(self.candles, current_price)
        
        if signal:
            return self._execute_entry(signal, current_price)
        
        return None
    
    def _execute_entry(self, signal: EntrySignal, current_price: float) -> Optional[BracketOrder]:
        """Execute an entry signal."""
        # Get available capital
        available = float(self.interface.currency)
        
        # Calculate position size
        entry_price = signal.entry_price or current_price
        size = self.strategy.calculate_position_size(available, entry_price, signal)
        
        if size <= 0:
            self._log(f"⚠️ Position size too small")
            return None
        
        # Open bracket order
        self._log(f"🎯 Entry signal: {signal.side.value} - {signal.reason}")
        
        bracket = self.order_manager.open_bracket(
            side=signal.side,
            size=size,
            entry_price=entry_price,
            stop_loss_pct=signal.stop_loss_pct,
            take_profit_pct=signal.take_profit_pct,
            trailing_stop=signal.use_trailing_stop,
        )
        
        return bracket
    
    def run(self, price_feed: Callable[[], float], duration: Optional[float] = None):
        """
        Run the bot continuously.
        
        Args:
            price_feed: Function that returns current price
            duration: Optional max runtime in seconds
        """
        self.running = True
        self.start_time = datetime.utcnow()
        
        self._log("=" * 60)
        self._log(f"🚀 AGGRESSIVE BOT STARTED")
        self._log(f"   Pair: {self.pair}")
        self._log(f"   Strategy: {self.strategy.get_name()}")
        self._log(f"   Check interval: {self.check_interval}s")
        self._log(f"   Max positions: {self.max_positions}")
        self._log("=" * 60)
        
        start = time.time()
        
        try:
            while self.running:
                # Check duration limit
                if duration and (time.time() - start) >= duration:
                    self._log("⏰ Duration limit reached")
                    break
                
                # Get price and tick
                try:
                    price = price_feed()
                    self.tick(price)
                except Exception as e:
                    self._log(f"❌ Tick error: {e}")
                
                # Wait for next check
                time.sleep(self.check_interval)
                
        except KeyboardInterrupt:
            self._log("\n⚠️ Interrupted by user")
        finally:
            self.running = False
            self._print_summary()
    
    def stop(self):
        """Stop the bot."""
        self.running = False
    
    def close_all_positions(self):
        """Close all open positions at market."""
        self.order_manager.close_all(self.current_price, ExitReason.MANUAL)
    
    def _print_summary(self):
        """Print session summary."""
        stats = self.order_manager.get_stats()
        
        self._log("")
        self._log("=" * 60)
        self._log("📊 SESSION SUMMARY")
        self._log("=" * 60)
        self._log(f"Checks performed: {self.checks_performed}")
        self._log(f"Total trades: {stats.get('total_trades', 0)}")
        
        if stats.get('total_trades', 0) > 0:
            self._log(f"Win rate: {stats.get('win_rate', 0)*100:.1f}%")
            self._log(f"Total P&L: ${stats.get('total_pnl', 0):.4f}")
            self._log(f"Avg P&L per trade: ${stats.get('avg_pnl', 0):.4f}")
            self._log(f"Stop loss exits: {stats.get('stop_loss_exits', 0)}")
            self._log(f"Take profit exits: {stats.get('take_profit_exits', 0)}")
        
        # Open positions
        open_pos = self.order_manager.open_positions
        if open_pos:
            self._log(f"\nOpen positions: {len(open_pos)}")
            for pos in open_pos:
                self._log(f"  {pos.side.value} @ ${pos.entry_price:.2f}")
        
        self._log("=" * 60)
