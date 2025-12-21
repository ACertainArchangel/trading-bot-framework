from TickerStream import TickerStream
from datetime import datetime, timezone, timedelta
import threading
import time
from interfaces.CoinbaseInterface import CoinbaseInterface
from interfaces.PaperTradingInterface import PaperTradingInterface
from strategies import Strategy

# Global lock to prevent concurrent trade execution
_trade_lock = threading.Lock()

# Default no-op logger for backtesting/testing
def _noop_logger(msg: str):
    """Silent logger - does nothing. Used when no logger is provided."""
    pass

def _print_logger(msg: str):
    """Simple print logger - useful for debugging."""
    print(msg)

class Bot:
    """
    Trading bot that executes strategies based on market data.
    
    The interface is the single source of truth for balances and position.
    The bot syncs its state from the interface on initialization.
    
    Args:
        interface: Trading interface (must have currency, asset, position attributes)
        strategy: Strategy class or instance (can be set later if None)
        pair: Trading pair (e.g., "BTC-USD")
        fee_rate: Trading fee rate
        fee_in_percent: If True, fee_rate is in percent (e.g., 0.65 for 0.65%)
        loss_tolerance: Maximum acceptable loss before forced sell (as decimal, e.g., 0.01 for 1%)
        strategy_params: Parameters to pass to strategy constructor
        initial_price: Initial market price for baseline calculations (optional)
        logger: Logging function - signature: logger(msg: str). Default: silent (no logging)
        emit_trade: Callback when trade executes - signature: emit_trade(side: str, price: float). Default: None
    """
    def __init__(self, interface, strategy: Strategy = None, pair: str = "BTC-USD", 
                 fee_rate: float = 0.0065, fee_in_percent: bool = True, 
                 loss_tolerance: float = 0.0, strategy_params: dict = None, 
                 initial_price: float = None, logger=None, emit_trade=None):
        
        self.interface = interface
        self.pair = pair
        self.strategy = strategy
        self.strategy_params = strategy_params or {}
        self.initial_price = initial_price
        self.fee_rate = fee_rate if not fee_in_percent else fee_rate / 100.0
        self.loss_tolerance = loss_tolerance
        
        # Set up logging - default to silent for backtesting
        self._log = logger if logger is not None else _noop_logger
        self._emit_trade = emit_trade  # Callback for trade events (e.g., web dashboard)
        
        # Connect to exchange and sync bot state from interface
        self._log("🔌 Connecting to exchange...")
        interface.connect_to_exchange()
        
        # Validate interface has a clear position
        self._log("🔍 Validating interface state...")
        interface.validate_position()
        
        # Sync bot balances and position from interface (interface is source of truth)
        self.currency = float(interface.currency)
        self.asset = float(interface.asset)
        self.position = interface.position
        
        # Apply dust threshold - tiny amounts are treated as zero
        DUST_THRESHOLD_USD = 0.10  # $0.10
        DUST_THRESHOLD_ASSET = 0.01
        
        currency_is_dust = self.currency < DUST_THRESHOLD_USD
        asset_is_dust = self.asset < DUST_THRESHOLD_ASSET
        
        # If both are dust, pick the relatively larger one
        if currency_is_dust and asset_is_dust:
            if self.currency > 0 or self.asset > 0:
                currency_ratio = self.currency / DUST_THRESHOLD_USD
                asset_ratio = self.asset / DUST_THRESHOLD_ASSET
                self._log(f"⚠️  Both balances are dust: ${self.currency:.6f} USD, {self.asset:.8f} asset")
                if currency_ratio >= asset_ratio:
                    self.asset = 0.0  # Treat as SHORT
                    self.position = "short"
                    self._log(f"    Treating as SHORT (USD holder)")
                else:
                    self.currency = 0.0  # Treat as LONG
                    self.position = "long"
                    self._log(f"    Treating as LONG (asset holder)")
        elif currency_is_dust and not asset_is_dust:
            self.currency = 0.0  # Ignore dust USD
        elif asset_is_dust and not currency_is_dust:
            self.asset = 0.0  # Ignore dust asset
        
        # Verify position matches balances
        if self.asset > 0 and self.currency > 0:
            raise ValueError(
                f"Bot cannot start with both currency ({self.currency}) and asset ({self.asset}). "
                "Must have EITHER currency (SHORT) OR asset (LONG), not both."
            )
        if self.asset == 0 and self.currency == 0:
            raise ValueError(
                "Bot cannot start with zero balance. Interface must provide either currency or asset."
            )
        if self.position not in ["long", "short"]:
            raise ValueError(
                f"Invalid position '{self.position}'. Must be 'long' or 'short'."
            )
        
        # Log initialization
        self._log(f"🤖 Bot initialized and synced with interface")
        self._log(f"   Interface: {interface}")
        self._log(f"   Currency: {self.currency:.2f} {self.pair.split('-')[1]}")
        self._log(f"   Asset: {self.asset:.8f} {self.pair.split('-')[0]}")
        self._log(f"   Position: {self.position.upper()}")
        self._log(f"⚙️  Trading parameters:")
        self._log(f"   Fee Rate: {self.fee_rate*100:.4f}%")
        self._log(f"   Loss Tolerance: {self.loss_tolerance*100:.2f}%")
        
        # Verify exchange sync
        interface.assert_exchange_sync(self)

        # Initialize dual baseline system for accurate APY tracking
        # Both USD and crypto baselines are tracked from the start
        if self.position == "short":
            # Starting with USD
            self.currency_baseline = float(self.currency)
            self.initial_usd_baseline = float(self.currency)
            # Calculate theoretical crypto baseline (what we could have bought)
            if self.initial_price is not None:
                self.asset_baseline = self.currency / self.initial_price
                self.initial_crypto_baseline = self.asset_baseline
            else:
                # Fallback: will be set when first price is available
                self.asset_baseline = 0.0
                self.initial_crypto_baseline = 0.0
                self._log("⚠️ Warning: initial_price not provided. Crypto baseline will be set on first price update.")
        else:
            # Starting with crypto
            self.asset_baseline = float(self.asset)
            self.initial_crypto_baseline = float(self.asset)
            # Calculate theoretical USD baseline (what we could have sold for)
            if self.initial_price is not None:
                self.currency_baseline = self.asset * self.initial_price
                self.initial_usd_baseline = self.currency_baseline
            else:
                # Fallback: will be set when first price is available
                self.currency_baseline = 0.0
                self.initial_usd_baseline = 0.0
                self._log("⚠️ Warning: initial_price not provided. USD baseline will be set on first price update.")
        
        # Track start time for APY calculations
        self.start_time = datetime.now(timezone.utc)
        
        # Track idle time metrics
        self.candles_since_last_trade = 0
        self.max_idle_candles = 0
        
        # Initialize strategy if provided
        if self.strategy is not None:
            # If strategy is a class, instantiate it with this bot
            if isinstance(self.strategy, type):
                # Pass strategy_params to the strategy constructor
                # Also pass fee_rate and loss_tolerance for economics-aware trading
                self.strategy = self.strategy(
                    self, 
                    fee_rate=self.fee_rate,
                    loss_tolerance=self.loss_tolerance,
                    **self.strategy_params
                )
            # If strategy is already an instance, just set the bot reference
            elif hasattr(self.strategy, 'bot'):
                self.strategy.bot = self
            
            # Sync strategy with bot's economic state
            self._sync_strategy_economics()
            self._log(f"📊 Strategy initialized: {self.strategy}")
    
    def _sync_strategy_economics(self):
        """Sync the strategy's baseline values with the bot's current state."""
        if self.strategy is not None and hasattr(self.strategy, 'sync_from_bot'):
            self.strategy.sync_from_bot()

    def set_strategy(self, strategy: Strategy):
        """
        Set or change the trading strategy.
        
        Args:
            strategy: Strategy class or instance to use
        """
        if isinstance(strategy, type):
            self.strategy = strategy(
                self,
                fee_rate=self.fee_rate,
                loss_tolerance=self.loss_tolerance
            )
        else:
            self.strategy = strategy
            self.strategy.bot = self
        
        # Sync economics
        self._sync_strategy_economics()
        self._log(f"📊 Strategy changed to: {self.strategy}")

    def buy_signal(self, candles):
        """
        Determine if conditions are right to buy.
        Delegates to strategy if one is set, otherwise returns False.
        """
        if self.strategy is None:
            return False
        return self.strategy.buy_signal(candles)

    def sell_signal(self, candles):
        """
        Determine if conditions are right to sell.
        Delegates to strategy if one is set, otherwise returns False.
        """
        if self.strategy is None:
            return False
        return self.strategy.sell_signal(candles)

    def execute_buy(self, price: float):
        """
        Execute a BUY order (go from SHORT to LONG position).
        Only executes if the new position would be better than our best previous long position.
        """
        # Acquire lock to prevent concurrent execution
        with _trade_lock:
            # CRITICAL: Check position first - this prevents double-execution
            if self.position != "short":
                self._log(f"⚠️ BUY BLOCKED: Already in {self.position} position! This should never happen.")
                print(f"⚠️ CRITICAL: Attempted to buy while in {self.position} position!")
                return False

            # Calculate what we would receive
            amount_to_spend = self.currency
            amount_expected = (amount_to_spend * (1 - self.fee_rate)) / price
            
            # SAFETY NET: Double-check economics (strategies should already handle this)
            # This check should NEVER trigger if strategies are correctly implementing
            # would_be_profitable_buy() - but keeping it as defense-in-depth
            min_acceptable = self.asset_baseline * (1 - self.loss_tolerance)
            if amount_expected <= min_acceptable:
                loss_pct = ((min_acceptable - amount_expected) / self.asset_baseline) * 100
                self._log(f"⚠️ BUY SAFETY NET TRIGGERED: Strategy signaled buy but would receive {amount_expected:.8f} {self.pair.split('-')[0]}, need > {min_acceptable:.8f} (baseline {self.asset_baseline:.8f}, loss {loss_pct:.2f}%, tolerance {self.loss_tolerance*100:.2f}%)")
                self._log("⚠️ This indicates a bug in the strategy - it should have checked would_be_profitable_buy() before signaling!")
                return False
            
            # Execute the trade
            self._log(f"💰 EXECUTING BUY: Spending {amount_to_spend:.2f} {self.pair.split('-')[1]} at ${price:.2f}")
            print(f"💰 EXECUTING BUY at ${price:.2f}")
            
            # Execute on interface (pass current currency before updating state)
            interface_result_received, interface_result_spent = self.interface.execute_buy(price, self.fee_rate, self.currency)
            
            # Update bot state IMMEDIATELY to prevent race conditions
            self.position = "long"
            self.asset = amount_expected
            self.currency = 0.0
            
            # Verify execution
            if interface_result_received < amount_expected * 0.99:
                self._log(f"⚠️ Warning: Bot expected to receive {amount_expected} {self.pair.split('-')[0]} but interface reported only {interface_result_received} {self.pair.split('-')[0]}. There might be an issue.")
            if interface_result_spent > amount_to_spend * 1.01:
                self._log(f"⚠️ Warning: Bot expected to spend {amount_to_spend} {self.pair.split('-')[1]} but interface reported spending {interface_result_spent} {self.pair.split('-')[1]}. There might be an issue.")
            
            self.interface.assert_exchange_sync(self)

            # Assert that asset meets minimum acceptable threshold (baseline with tolerance)
            # Note: With loss_tolerance > 0, new baseline may be slightly less than old baseline
            assert self.asset > min_acceptable, f"Post-trade asset balance {self.asset:.8f} is not greater than min acceptable {min_acceptable:.8f} (baseline {self.asset_baseline:.8f} with {self.loss_tolerance*100:.2f}% tolerance)"

            # Update BOTH baselines - track progression of both USD and crypto
            # Asset baseline: actual crypto we now hold
            self.asset_baseline = self.asset
            # Currency baseline: theoretical USD value if we sold at this price
            self.currency_baseline = self.asset * price
            
            # Sync strategy with updated baselines
            self._sync_strategy_economics()
            
            # Reset idle time counter on successful trade
            self.candles_since_last_trade = 0
            
            self._log(f"✅ BUY COMPLETE: Now holding {self.asset:.8f} {self.pair.split('-')[0]} (crypto baseline: {self.asset_baseline:.8f}, usd baseline: ${self.currency_baseline:.2f})")
            
            # Emit trade to dashboard (if callback provided)
            if self._emit_trade:
                self._emit_trade('BUY', price)
            
            return True


    def execute_sell(self, price: float):
        """
        Execute a SELL order (go from LONG to SHORT position).
        Only executes if the new position would be better than our best previous short position.
        """
        # Acquire lock to prevent concurrent execution
        with _trade_lock:
            # CRITICAL: Check position first - this prevents double-execution
            if self.position != "long":
                self._log(f"⚠️ SELL BLOCKED: Already in {self.position} position! This should never happen.")
                print(f"⚠️ CRITICAL: Attempted to sell while in {self.position} position!")
                return False

            # Calculate what we would receive
            amount_to_sell = self.asset
            amount_expected = (amount_to_sell * price) * (1 - self.fee_rate)
            
            # SAFETY NET: Double-check economics (strategies should already handle this)
            # This check should NEVER trigger if strategies are correctly implementing
            # would_be_profitable_sell() - but keeping it as defense-in-depth
            min_acceptable = self.currency_baseline * (1 - self.loss_tolerance)
            if amount_expected <= min_acceptable:
                loss_pct = ((min_acceptable - amount_expected) / self.currency_baseline) * 100
                self._log(f"⚠️ SELL SAFETY NET TRIGGERED: Strategy signaled sell but would receive {amount_expected:.2f} {self.pair.split('-')[1]}, need > {min_acceptable:.2f} (baseline {self.currency_baseline:.2f}, loss {loss_pct:.2f}%, tolerance {self.loss_tolerance*100:.2f}%)")
                self._log("⚠️ This indicates a bug in the strategy - it should have checked would_be_profitable_sell() before signaling!")
                return False
            
            # Execute the trade
            self._log(f"💸 EXECUTING SELL: Selling {amount_to_sell:.8f} {self.pair.split('-')[0]} at ${price:.2f}")
            print(f"💸 EXECUTING SELL at ${price:.2f}")
            
            # Execute on interface (pass current asset before updating state)
            interface_result_received, interface_result_spent = self.interface.execute_sell(price, self.fee_rate, self.asset)
            
            # Update bot state IMMEDIATELY to prevent race conditions
            self.position = "short"
            self.currency = amount_expected
            self.asset = 0.0
            
            # Verify execution
            if interface_result_received < amount_expected * 0.99:
                self._log(f"⚠️ Warning: Bot expected to receive {amount_expected} {self.pair.split('-')[1]} but interface reported only {interface_result_received} {self.pair.split('-')[1]}. There might be an issue.")
            if interface_result_spent > amount_to_sell * 1.01:
                self._log(f"⚠️ Warning: Bot expected to spend {amount_to_sell} {self.pair.split('-')[0]} but interface reported spending {interface_result_spent} {self.pair.split('-')[0]}. There might be an issue.")
            
            self.interface.assert_exchange_sync(self)

            # Assert that currency meets minimum acceptable threshold (baseline with tolerance)
            # Note: With loss_tolerance > 0, new baseline may be slightly less than old baseline
            assert self.currency > min_acceptable, f"Post-trade currency balance {self.currency:.2f} is not greater than min acceptable {min_acceptable:.2f} (baseline {self.currency_baseline:.2f} with {self.loss_tolerance*100:.2f}% tolerance)"

            # Calculate profit/loss relative to old baseline
            profit = self.currency - self.currency_baseline
            
            # Update BOTH baselines - track progression of both USD and crypto
            # Currency baseline: actual USD we now hold
            self.currency_baseline = self.currency
            # Asset baseline: theoretical crypto we could buy at this price
            self.asset_baseline = self.currency / price
            
            # Sync strategy with updated baselines
            self._sync_strategy_economics()
            
            # Reset idle time counter on successful trade
            self.candles_since_last_trade = 0
            
            self._log(f"✅ SELL COMPLETE: Now holding ${self.currency:.2f} {self.pair.split('-')[1]} (usd baseline: ${self.currency_baseline:.2f}, crypto baseline: {self.asset_baseline:.8f}, profit: +${profit:.2f})")
            
            # Emit trade to dashboard (if callback provided)
            if self._emit_trade:
                self._emit_trade('SELL', price)
            
            return True

    def _check_signals_on_new_candle(self, candle: tuple):
        """
        Called whenever a new candle arrives. Checks for trading signals.
        This ensures we never miss a candle, regardless of playback speed.
        """
        candles = self._ticker_stream.get_candles()
        current_price = candle[4]  # Close price of the new candle
        
        # Update idle time tracking
        self.candles_since_last_trade += 1
        if self.candles_since_last_trade > self.max_idle_candles:
            self.max_idle_candles = self.candles_since_last_trade
        
        # Handle lazy initialization of baselines if initial_price wasn't provided
        if self.initial_price is None:
            self.initial_price = current_price
            if self.position == "short" and self.asset_baseline == 0.0:
                self.asset_baseline = self.currency / current_price
                self.initial_crypto_baseline = self.asset_baseline
            elif self.position == "long" and self.currency_baseline == 0.0:
                self.currency_baseline = self.asset * current_price
                self.initial_usd_baseline = self.currency_baseline
        
        try:
            if self.position == "long" and self.sell_signal(candles):
                # Store old baseline before trade
                old_baseline = self.currency_baseline
                # Try to execute sell - only updates position if successful
                executed = self.execute_sell(current_price)
                if executed:
                    profit = self.currency_baseline - old_baseline  # baseline was updated in execute_sell
                    self._log(f"📊 Position changed: LONG → SHORT at ${current_price:.2f}")
                    self._log(f"💵 Profit: +${profit:.2f} {self.pair.split('-')[1]} (was at ${old_baseline:.2f}, now ${self.currency_baseline:.2f})")
                    
            elif self.position == "short" and self.buy_signal(candles):
                # Store old baseline before trade
                old_baseline = self.asset_baseline
                # Try to execute buy - only updates position if successful
                executed = self.execute_buy(current_price)
                if executed:
                    asset_gain = self.asset_baseline - old_baseline  # baseline was updated in execute_buy
                    self._log(f"📊 Position changed: SHORT → LONG at ${current_price:.2f}")
                    self._log(f"📈 Asset gain: +{asset_gain:.8f} {self.pair.split('-')[0]} (was {old_baseline:.8f}, now {self.asset_baseline:.8f})")
        except Exception as e:
            self._log(f"❌ ERROR during trade execution: {e}")
            import traceback
            self._log(f"📋 Traceback:\n{traceback.format_exc()}")

    def trading_logic_loop(self, ticker_stream: TickerStream):
        self._ticker_stream = ticker_stream
        
        # Wait for initial data
        while len(ticker_stream.get_candles()) == 0:
            time.sleep(0.1)
        
        # Store initial candle count for elapsed time calculation
        self.initial_candle_count = len(ticker_stream.get_candles())
        
        self._log("🤖 Bot trading logic started.")
        
        # Initialize baselines
        initial_price = ticker_stream.get_candles()[-1][4]
        self.baseline_value = self.currency if self.position == "short" else self.asset * initial_price
        self.baseline_crypto = self.asset if self.position == "long" else self.currency / initial_price
        
        # Register callback to check signals on EVERY new candle
        ticker_stream.on_new_candle = self._check_signals_on_new_candle
        
        self._log("✅ Bot now checking signals on EVERY candle (event-driven)")
        
        # Keep thread alive
        while True:
            time.sleep(1)
        

if __name__ == '__main__':

    # Import web dashboard components only for live trading with web interface
    from web_dashboard import socketio, app, initialize_stream, main_logger, emit_trade_executed
    
    interface = PaperTradingInterface(starting_currency=1000.0, starting_asset=0.0)

    # Create bot with web dashboard logger and trade emitter
    bot = Bot(interface, logger=main_logger, emit_trade=emit_trade_executed)

    strategy = Strategy.macd.MACDStrategy(bot, short_window=12, long_window=26, signal_window=9, min_candles=50)
    bot.set_strategy(strategy)

    # Start the stream
    ticker_stream = initialize_stream()
    
    # Start web server (blocks here)
    main_logger("🌐 Starting web server on http://localhost:5001")
    web_thread = threading.Thread(target=lambda: socketio.run(app, host='0.0.0.0', port=5001), daemon=True)
    web_thread.start()

    # Start trading bot in background
    trading_thread = threading.Thread(target=lambda: bot.trading_logic_loop(ticker_stream), daemon=True)
    trading_thread.start()

    web_thread.join()
    trading_thread.join()
