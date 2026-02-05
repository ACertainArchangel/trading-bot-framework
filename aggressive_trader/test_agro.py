#!/usr/bin/env python3
"""
Backtest script for aggressive trader.

Runs historical data in fast motion with:
- Real Coinbase data from the last 24h
- Web dashboard with SL/TP visualization
- Configurable strategy and playback speed
"""

import sys
import time
import argparse
from datetime import datetime, timezone, timedelta
from typing import List, Tuple

# Local imports
from CBData import CoinbaseDataFetcher
from interfaces.paper_trading import PaperTradingInterface, OrderSide
from strategies.base import MomentumStrategy, BreakoutStrategy, EntrySignal, Candle
from strategies.macd import MACDStrategy, MACDHistogramStrategy
from strategies.mean_reversion import MeanReversionStrategy, RSIMeanReversionStrategy
from strategies.super_strat import SuperStrat
from position import PositionSide
import web_dashboard


def convert_candle(raw_candle: tuple) -> Candle:
    """Convert raw candle tuple to Candle dataclass."""
    return Candle(
        timestamp=raw_candle[0],
        open=raw_candle[3],
        high=raw_candle[2],
        low=raw_candle[1],
        close=raw_candle[4],
        volume=raw_candle[5]
    )


class TestTickerStream:
    """
    Fake ticker stream for backtesting.
    Replays historical data one candle at a time.
    """
    
    def __init__(self, candles: List[Tuple], on_new_candle=None, logger=None):
        self.all_candles = candles
        self.on_new_candle = on_new_candle
        self.log = logger or print
        self._current_index = 50  # Start with some history
        self._running = False
    
    def get_candles(self) -> List[Tuple]:
        """Get candles up to current index."""
        return self.all_candles[:self._current_index]
    
    def get_latest(self) -> Tuple:
        """Get most recent candle."""
        if self._current_index > 0:
            return self.all_candles[self._current_index - 1]
        return None
    
    def advance(self) -> bool:
        """
        Advance to next candle.
        Returns False if no more candles.
        """
        if self._current_index >= len(self.all_candles):
            return False
        
        candle = self.all_candles[self._current_index]
        self._current_index += 1
        
        if self.on_new_candle:
            self.on_new_candle(candle)
        
        return True
    
    def get_progress(self) -> dict:
        """Get backtest progress."""
        return {
            'current': self._current_index,
            'total': len(self.all_candles),
            'pct': (self._current_index / len(self.all_candles)) * 100
        }
    
    def is_complete(self) -> bool:
        return self._current_index >= len(self.all_candles)
    
    def __len__(self):
        return self._current_index
    
    def start(self):
        self._running = True
    
    def stop(self):
        self._running = False


class SimpleAggressiveBot:
    """
    Simple aggressive trading bot for backtesting.
    """
    
    def __init__(self, interface: PaperTradingInterface, strategy, 
                 pair: str = "BTC-USD", logger=None):
        self.interface = interface
        self.strategy = strategy
        self.pair = pair
        self._log = logger or print
        
        # Position tracking
        self.position = None
        self.highest_price = 0
        
        # Stats
        self.running = False
        self.wins = 0
        self.losses = 0
        
        # For dashboard compatibility
        self.order_manager = self
        self.brackets = []
    
    @property
    def open_positions(self):
        if self.position:
            return [self.position]
        return []
    
    def process_tick(self, candles: list, current_price: float, candle_time_ms: float = 0):
        """Process a price tick."""
        # Set candle timestamp for accurate trade markers
        if candle_time_ms > 0:
            self.interface.set_candle_time(candle_time_ms)
        
        filled = self.interface.update_price(current_price)
        
        if self.position:
            self._check_position(current_price)
        else:
            self._check_entry(candles, current_price)
    
    def _check_position(self, current_price: float):
        """Check if position should be closed."""
        pos = self.position
        
        # Update trailing stop
        if pos['trailing'] and pos['side'] == 'LONG':
            if current_price > self.highest_price:
                self.highest_price = current_price
                new_sl = self.highest_price * (1 - pos['sl_pct'])
                if new_sl > pos['sl_price']:
                    pos['sl_price'] = new_sl
                    self._update_brackets()
        
        # Check stop loss
        if pos['side'] == 'LONG' and current_price <= pos['sl_price']:
            self._close_position(current_price, "STOP_LOSS")
            return
        
        # Check take profit
        if pos['side'] == 'LONG' and current_price >= pos['tp_price']:
            self._close_position(current_price, "TAKE_PROFIT")
            return
    
    def _check_entry(self, candles: list, current_price: float):
        """Check for entry signal."""
        candle_objs = [convert_candle(c) for c in candles]
        signal = self.strategy.should_enter(candle_objs, current_price)
        
        if signal and signal.side == PositionSide.LONG:
            self._open_position(signal, current_price)
    
    def _open_position(self, signal: EntrySignal, current_price: float):
        """Open a new position."""
        available = self.interface.currency
        size = self.strategy.calculate_position_size(available, current_price, signal)
        
        if size * current_price < 10:
            return
        
        order = self.interface.place_market_order(OrderSide.BUY, size)
        
        if order.status.value == "FILLED":
            entry_price = order.filled_price
            # signal.stop_loss_pct and take_profit_pct are already decimals (0.06 = 6%)
            sl_price = entry_price * (1 - signal.stop_loss_pct)
            tp_price = entry_price * (1 + signal.take_profit_pct)
            
            self.position = {
                'side': 'LONG',
                'entry_price': entry_price,
                'size': size,
                'sl_price': sl_price,
                'tp_price': tp_price,
                'sl_pct': signal.stop_loss_pct,
                'tp_pct': signal.take_profit_pct,
                'trailing': signal.use_trailing_stop,
                'entry_time': datetime.utcnow(),
            }
            self.highest_price = entry_price
            self._update_brackets()
            
            self._log(f"🎯 LONG @ ${entry_price:.2f} | SL: ${sl_price:.2f} | TP: ${tp_price:.2f}")
    
    def _close_position(self, current_price: float, reason: str):
        """Close the current position."""
        pos = self.position
        order = self.interface.place_market_order(OrderSide.SELL, pos['size'])
        
        if order.status.value == "FILLED":
            exit_price = order.filled_price
            pnl = (exit_price - pos['entry_price']) * pos['size']
            pnl_pct = (exit_price / pos['entry_price'] - 1) * 100
            
            if pnl >= 0:
                self.wins += 1
            else:
                self.losses += 1
            
            emoji = "🛑" if reason == "STOP_LOSS" else "🎯"
            color = "🔴" if pnl < 0 else "🟢"
            
            self._log(f"{emoji} {reason} @ ${exit_price:.2f} | {color} P&L: ${pnl:.2f} ({pnl_pct:+.2f}%)")
            
            self.position = None
            self.brackets = []
    
    def _update_brackets(self):
        """Update brackets list for dashboard."""
        if not self.position:
            self.brackets = []
            return
        
        class FakePosition:
            def __init__(self, pos_dict):
                self.side = PositionSide.LONG if pos_dict['side'] == 'LONG' else PositionSide.SHORT
                self.entry_price = pos_dict['entry_price']
                self.stop_loss_price = pos_dict['sl_price']
                self.take_profit_price = pos_dict['tp_price']
                self.size = pos_dict['size']
                self.entry_time = pos_dict.get('entry_time')
                self.trailing_stop_pct = pos_dict['sl_pct'] if pos_dict['trailing'] else None
                self.highest_price = pos_dict['entry_price']
                self.is_filled = True
                self.exit_reason = None
        
        class FakeBracket:
            def __init__(self, pos):
                self.position = pos
        
        self.brackets = [FakeBracket(FakePosition(self.position))]


def main():
    parser = argparse.ArgumentParser(description='Aggressive Trader Backtest')
    parser.add_argument('--strategy', type=str, default='momentum', 
                        choices=['momentum', 'breakout', 'macd', 'macd-histogram', 'mean-reversion', 'rsi-reversion', 'super'],
                        help='Strategy to use')
    parser.add_argument('--hours', type=int, default=24,
                        help='Hours of historical data to backtest')
    parser.add_argument('--starting_currency', type=float, default=1000.0,
                        help='Starting USD balance')
    parser.add_argument('--port', type=int, default=5005,
                        help='Dashboard port')
    parser.add_argument('--trailing', action='store_true',
                        help='Use trailing stop')
    parser.add_argument('--speed', type=float, default=0.005,
                        help='Playback speed (seconds per candle)')
    parser.add_argument('--lookback', type=int, default=20,
                        help='Strategy lookback period')
    parser.add_argument('--threshold', type=float, default=0.3,
                        help='Strategy threshold percentage')
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("🎯 AGGRESSIVE TRADER - Backtest Mode")
    print("=" * 60)
    print(f"Strategy: {args.strategy}")
    print(f"Period: Last {args.hours} hours")
    print(f"Starting Capital: ${args.starting_currency:.2f}")
    print(f"Trailing Stop: {args.trailing}")
    print(f"Playback Speed: {args.speed}s per candle")
    print(f"Dashboard: http://localhost:{args.port}")
    print("=" * 60)
    
    # Fetch historical data
    print("\n📡 Fetching historical data...")
    fetcher = CoinbaseDataFetcher(product_id="BTC-USD")
    start_time = datetime.now(timezone.utc) - timedelta(hours=args.hours)
    candles = fetcher.fetch_candles(start_time, None, '1m')
    print(f"✅ Loaded {len(candles)} candles")
    
    if len(candles) < 100:
        print("❌ Not enough data!")
        return
    
    # Create strategy
    if args.strategy == 'momentum':
        strategy = MomentumStrategy(
            lookback=args.lookback,
            threshold_pct=args.threshold / 100,
        )
    elif args.strategy == 'breakout':
        strategy = BreakoutStrategy(lookback=args.lookback)
    elif args.strategy == 'macd':
        strategy = MACDStrategy(fast_period=12, slow_period=26, signal_period=9)
    elif args.strategy == 'macd-histogram':
        strategy = MACDHistogramStrategy(fast_period=12, slow_period=26, signal_period=9)
    elif args.strategy == 'mean-reversion':
        strategy = MeanReversionStrategy(
            bb_period=args.lookback,
            bb_std=2.0,
            atr_period=14,
            atr_sl_multiplier=1.5,
            min_distance_pct=args.threshold
        )
    elif args.strategy == 'rsi-reversion':
        strategy = RSIMeanReversionStrategy(
            rsi_period=14,
            rsi_oversold=30,
            rsi_neutral=50,
            atr_period=14,
            atr_sl_multiplier=2.0
        )
    elif args.strategy == 'super':
        strategy = SuperStrat(
            # Use class defaults for all parameters
            volume_spike_threshold=2.0,
            volume_lookback=20,
            sr_lookback=50
            # sl_scale and tp_scale will use DEFAULT_SL_SCALE and DEFAULT_TP_SCALE
        )
        print(f"📊 SuperStrat config: SL={strategy.DEFAULT_STOP_LOSS_PCT*strategy.sl_scale:.3%}, TP={strategy.DEFAULT_TAKE_PROFIT_PCT*strategy.tp_scale:.3%}")
    else:
        strategy = MomentumStrategy(lookback=args.lookback, threshold_pct=args.threshold / 100)
    
    # Only set trailing stop - SL/TP come from strategy defaults
    strategy.use_trailing_stop = args.trailing
    
    # Create interface
    interface = PaperTradingInterface(
        initial_currency=args.starting_currency,
        fee_rate=0.00025,  # Coinbase VIP4 fee (0.025%)
        logger=web_dashboard.main_logger
    )
    
    # Create test stream
    stream = TestTickerStream(
        candles=candles,
        on_new_candle=web_dashboard.on_new_candle,
        logger=web_dashboard.ticker_logger
    )
    
    # Create bot
    bot = SimpleAggressiveBot(
        interface=interface,
        strategy=strategy,
        logger=web_dashboard.main_logger
    )
    
    # Configure dashboard
    web_dashboard.configure_dashboard(bot, interface, stream)
    
    # Start dashboard
    print(f"\n🌐 Starting dashboard at http://localhost:{args.port}")
    web_dashboard.run_dashboard_background(port=args.port)
    time.sleep(1)
    
    stream.start()
    
    # Record start price for comparison
    start_price = candles[50][4]  # Close price at start
    
    print("\n▶️  Starting backtest... Press Ctrl+C to stop.\n")
    
    try:
        while stream.advance():
            current_candles = stream.get_candles()
            if current_candles:
                current_candle = current_candles[-1]
                current_price = current_candle[4]  # Close price
                candle_time_ms = current_candle[0] * 1000  # Timestamp in ms
                interface.update_price(current_price)
                bot.process_tick(current_candles, current_price, candle_time_ms)
            
            # Update dashboard
            web_dashboard.emit_position_update()
            
            time.sleep(args.speed)
            
            # Show progress every 100 candles
            progress = stream.get_progress()
            if progress['current'] % 100 == 0:
                print(f"📊 Progress: {progress['pct']:.1f}% | Portfolio: ${interface.get_portfolio_value():.2f}")
        
        print("\n✅ Backtest complete!")
        
    except KeyboardInterrupt:
        print("\n\n⏸️  Backtest stopped early.")
    finally:
        stream.stop()
        
        # Final summary
        end_price = candles[-1][4]
        btc_return = ((end_price / start_price) - 1) * 100
        
        final_value = interface.get_portfolio_value()
        pnl = final_value - args.starting_currency
        pnl_pct = (final_value / args.starting_currency - 1) * 100
        
        total_trades = bot.wins + bot.losses
        win_rate = (bot.wins / total_trades * 100) if total_trades > 0 else 0
        
        # Calculate APY
        hours_tested = args.hours
        if pnl_pct > 0:
            apy = ((1 + pnl_pct/100) ** (8760 / hours_tested) - 1) * 100
        else:
            apy = pnl_pct * (8760 / hours_tested)
        
        print("\n" + "=" * 60)
        print("📊 BACKTEST RESULTS")
        print("=" * 60)
        print(f"Period:          {args.hours} hours")
        print(f"Starting Value:  ${args.starting_currency:.2f}")
        print(f"Final Value:     ${final_value:.2f}")
        print(f"P&L:             ${pnl:+.2f} ({pnl_pct:+.2f}%)")
        print(f"Estimated APY:   {apy:+.1f}%")
        print("-" * 60)
        print(f"Total Trades:    {total_trades}")
        print(f"Wins:            {bot.wins}")
        print(f"Losses:          {bot.losses}")
        print(f"Win Rate:        {win_rate:.1f}%")
        print("-" * 60)
        print(f"BTC Return:      {btc_return:+.2f}%")
        print(f"vs HODL:         {pnl_pct - btc_return:+.2f}%")
        print("=" * 60)
        
        # Keep dashboard running
        print("\n📺 Dashboard still running. Press Ctrl+C again to exit.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("Goodbye!")


if __name__ == "__main__":
    main()
