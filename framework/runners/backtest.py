"""
Backtest Runner - Test strategies on historical data.

The simplest way to evaluate a strategy before risking real capital.
"""

from dataclasses import dataclass, field
from typing import Type, Dict, Any, List, Optional
from datetime import datetime, timezone
import sys
from io import StringIO

from ..strategies.base import Strategy
from ..core.candle import Candle
from ..data.fetcher import DataFetcher
from ..interfaces.paper import PaperInterface
from ..interfaces.base import Allocation, DEFAULT_ALLOCATION


@dataclass
class BacktestResult:
    """
    Results from a backtest run.
    
    Contains all metrics needed to evaluate strategy performance.
    """
    # Strategy info
    strategy_name: str
    strategy_params: Dict[str, Any]
    
    # Time info
    start_date: str
    end_date: str
    duration_days: float
    
    # Performance
    starting_value: float
    ending_value: float
    total_return_pct: float
    annualized_return_pct: float  # APY
    
    # Trading activity
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate_pct: float
    
    # Risk metrics
    max_drawdown_pct: float = 0.0
    longest_drawdown_days: float = 0.0
    
    # Position info
    final_position: str = "short"
    time_in_market_pct: float = 0.0
    
    # Raw data
    trade_log: List[Dict] = field(default_factory=list)
    equity_curve: List[float] = field(default_factory=list)
    
    # Status
    success: bool = True
    error: Optional[str] = None
    
    def __str__(self) -> str:
        """Pretty print results."""
        if not self.success:
            return f"❌ Backtest Failed: {self.error}"
        
        emoji = "🟢" if self.total_return_pct > 0 else "🔴"
        
        return f"""
{emoji} {self.strategy_name} Backtest Results
{'='*50}
Period: {self.start_date} to {self.end_date} ({self.duration_days:.0f} days)

📈 Performance:
   Starting Value:  ${self.starting_value:,.2f}
   Ending Value:    ${self.ending_value:,.2f}
   Total Return:    {self.total_return_pct:+.2f}%
   Annualized (APY): {self.annualized_return_pct:+.2f}%

📊 Trading Activity:
   Total Trades:    {self.total_trades}
   Win Rate:        {self.win_rate_pct:.1f}% ({self.winning_trades}W / {self.losing_trades}L)
   Final Position:  {self.final_position.upper()}

⚠️  Risk:
   Max Drawdown:    {self.max_drawdown_pct:.2f}%
"""
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'strategy_name': self.strategy_name,
            'strategy_params': self.strategy_params,
            'start_date': self.start_date,
            'end_date': self.end_date,
            'duration_days': self.duration_days,
            'starting_value': self.starting_value,
            'ending_value': self.ending_value,
            'total_return_pct': self.total_return_pct,
            'annualized_return_pct': self.annualized_return_pct,
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'win_rate_pct': self.win_rate_pct,
            'max_drawdown_pct': self.max_drawdown_pct,
            'final_position': self.final_position,
            'success': self.success,
            'error': self.error
        }


def backtest(
    strategy: Type[Strategy],
    months: int = 3,
    days: Optional[int] = None,
    starting_balance: float = 1000.0,
    fee_rate: float = 0.0025,
    loss_tolerance: float = 0.0,
    allocation: Optional[Allocation] = None,
    product_id: str = "BTC-USD",
    granularity: str = '5m',
    strategy_params: Optional[Dict] = None,
    candles: Optional[List[Candle]] = None,
    verbose: bool = False,
    min_candles: int = 50
) -> BacktestResult:
    """
    Backtest a strategy on historical data.
    
    This is the main entry point for testing strategies.
    
    Args:
        strategy: Strategy class to test
        months: Months of historical data (default: 3)
        days: Days of data (overrides months if provided)
        starting_balance: Initial USD balance
        fee_rate: Trading fee as decimal (0.0025 = 0.25%)
        loss_tolerance: Max acceptable loss (0.0 = no losses allowed)
        allocation: Position sizing config. Default: {'short': 0, 'long': 1}
                   Examples:
                     {'short': -1, 'long': 1}  # Enable shorting
                     {'short': -3, 'long': 3}  # 3x leverage perps
        product_id: Trading pair
        granularity: Candle size ('1m', '5m', '15m', '1h')
        strategy_params: Additional parameters for strategy constructor
        candles: Pre-loaded candles (skips data fetching if provided)
        verbose: Print progress messages
        min_candles: Minimum candles before trading starts
    
    Returns:
        BacktestResult with all performance metrics
    
    Example:
        >>> from framework import backtest, Strategy
        >>> 
        >>> class SimpleMA(Strategy):
        ...     def buy_signal(self, candles):
        ...         if len(candles) < 20:
        ...             return False
        ...         ma = sum(c.close for c in candles[-20:]) / 20
        ...         return candles[-1].close > ma
        ...     
        ...     def sell_signal(self, candles):
        ...         if len(candles) < 20:
        ...             return False
        ...         ma = sum(c.close for c in candles[-20:]) / 20
        ...         return candles[-1].close < ma
        >>> 
        >>> result = backtest(SimpleMA, months=6)
        >>> print(result)
    """
    strategy_params = strategy_params or {}
    
    # Allow allocation to be passed via strategy_params for convenience
    if allocation is None and 'allocation' in strategy_params:
        allocation = strategy_params.pop('allocation')
    
    def log(msg):
        if verbose:
            print(msg)
    
    try:
        # Load data
        if candles is None:
            log(f"📦 Loading historical data...")
            fetcher = DataFetcher(product_id, verbose=False)
            
            if days is not None:
                candles = fetcher.get_candles(days=days, granularity=granularity)
            else:
                candles = fetcher.get_candles(months=months, granularity=granularity)
            
            log(f"✅ Loaded {len(candles)} candles")
        
        if len(candles) < min_candles:
            return BacktestResult(
                strategy_name=strategy.__name__,
                strategy_params=strategy_params,
                start_date="",
                end_date="",
                duration_days=0,
                starting_value=starting_balance,
                ending_value=starting_balance,
                total_return_pct=0,
                annualized_return_pct=0,
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                win_rate_pct=0,
                success=False,
                error=f"Insufficient data: {len(candles)} candles (need {min_candles})"
            )
        
        # Initialize
        initial_price = candles[min_candles].close
        
        # Determine if using dynamic allocation
        # Create strategy
        strat = strategy(
            fee_rate=fee_rate,
            loss_tolerance=loss_tolerance,
            **strategy_params
        )
        
        # Set allocation on interface (from param or strategy default)
        effective_allocation = allocation if allocation is not None else strat.allocation
        interface = PaperInterface(starting_currency=starting_balance, allocation=effective_allocation)
        
        # Set up economics tracking
        currency_baseline = starting_balance
        asset_baseline = starting_balance / initial_price
        strat.currency_baseline = currency_baseline
        strat.asset_baseline = asset_baseline
        
        # Track metrics
        wins = 0
        losses = 0
        cycle_start_value = starting_balance
        equity_curve = []
        peak_value = starting_balance
        max_drawdown = 0.0
        
        log(f"🚀 Running backtest...")
        
        # Suppress output during simulation
        if not verbose:
            old_stdout = sys.stdout
            sys.stdout = StringIO()
        
        try:
            # Simulate trading
            for i in range(min_candles, len(candles)):
                window = candles[:i + 1]
                current_price = candles[i].close
                
                # Track equity (handles long and short positions)
                current_value = interface.get_total_value(current_price)
                
                equity_curve.append(current_value)
                
                # Track drawdown
                if current_value > peak_value:
                    peak_value = current_value
                drawdown = (peak_value - current_value) / peak_value * 100
                if drawdown > max_drawdown:
                    max_drawdown = drawdown
                
                # Handle buy signals - closes shorts or opens longs
                if interface.position == "short":
                    buy_result = strat.buy_signal(window)
                    should_buy, signal_alloc = strat.parse_signal(buy_result)
                    
                    if should_buy:
                        # Apply signal allocation if provided
                        if signal_alloc is not None:
                            interface.allocation = {'long': signal_alloc, 'short': interface.allocation.get('short', 0)}
                        
                        was_short = interface.position == "short"
                        pre_short_value = interface.get_total_value(current_price) if was_short else None
                        
                        # Check profitability
                        amount = interface.currency
                        expected_asset = (amount * (1 - fee_rate)) / current_price
                        min_acceptable = asset_baseline * (1 - loss_tolerance)
                        
                        if expected_asset > min_acceptable:
                            interface.execute_buy(current_price, fee_rate, amount)
                            
                            # Track short P&L if we just closed a short
                            if was_short and pre_short_value is not None:
                                short_pnl = interface.currency - cycle_start_value
                                if short_pnl > 0:
                                    wins += 1
                                else:
                                    losses += 1
                            
                            # Set cycle start for new long position
                            cycle_start_value = interface.currency
                            
                            # Update baselines
                            asset_baseline = interface.asset
                            currency_baseline = interface.asset * current_price
                            strat.currency_baseline = currency_baseline
                            strat.asset_baseline = asset_baseline
                
                # Handle sell signals - closes longs or opens shorts
                elif interface.position == "long":
                    sell_result = strat.sell_signal(window)
                    should_sell, signal_alloc = strat.parse_signal(sell_result)
                    
                    if should_sell:
                        # Apply signal allocation if provided (for shorts)
                        if signal_alloc is not None:
                            interface.allocation = {'long': interface.allocation.get('long', 1), 'short': signal_alloc}
                        
                        # Check profitability
                        amount = interface.asset
                        expected_currency = (amount * current_price) * (1 - fee_rate)
                        min_acceptable = currency_baseline * (1 - loss_tolerance)
                        
                        if expected_currency > min_acceptable:
                            interface.execute_sell(current_price, fee_rate, amount)
                            
                            # Track long P&L
                            profit = interface.currency - cycle_start_value
                            if profit > 0:
                                wins += 1
                            else:
                                losses += 1
                            
                            # If we just opened a short, set cycle start to total value
                            if interface.position == "short":
                                cycle_start_value = interface.get_total_value(current_price)
                            
                            # Update baselines
                            currency_baseline = interface.currency
                            asset_baseline = interface.currency / current_price
                            strat.currency_baseline = currency_baseline
                            strat.asset_baseline = asset_baseline
        
        finally:
            if not verbose:
                sys.stdout = old_stdout
        
        # Calculate final metrics
        final_price = candles[-1].close
        ending_value = interface.get_total_value(final_price)
        
        total_return = ((ending_value - starting_balance) / starting_balance) * 100
        
        # Calculate duration and APY
        start_ts = candles[min_candles].timestamp
        end_ts = candles[-1].timestamp
        duration_days = (end_ts - start_ts) / 86400
        years = duration_days / 365.25
        
        if years > 0 and ending_value > 0 and starting_balance > 0:
            ratio = ending_value / starting_balance
            if ratio > 0:
                apy = ((ratio ** (1 / years)) - 1) * 100
            else:
                apy = -100
        else:
            apy = 0
        
        total_trades = len(interface.trade_log)
        complete_cycles = wins + losses
        win_rate = (wins / complete_cycles * 100) if complete_cycles > 0 else 0
        
        result = BacktestResult(
            strategy_name=strategy.__name__,
            strategy_params=strategy_params,
            start_date=candles[min_candles].datetime.strftime('%Y-%m-%d'),
            end_date=candles[-1].datetime.strftime('%Y-%m-%d'),
            duration_days=duration_days,
            starting_value=starting_balance,
            ending_value=ending_value,
            total_return_pct=total_return,
            annualized_return_pct=apy,
            total_trades=total_trades,
            winning_trades=wins,
            losing_trades=losses,
            win_rate_pct=win_rate,
            max_drawdown_pct=max_drawdown,
            final_position=interface.position,
            trade_log=interface.trade_log,
            equity_curve=equity_curve
        )
        
        if verbose:
            print(result)
        
        return result
    
    except Exception as e:
        return BacktestResult(
            strategy_name=strategy.__name__ if hasattr(strategy, '__name__') else str(strategy),
            strategy_params=strategy_params,
            start_date="",
            end_date="",
            duration_days=0,
            starting_value=starting_balance,
            ending_value=starting_balance,
            total_return_pct=0,
            annualized_return_pct=0,
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            win_rate_pct=0,
            success=False,
            error=str(e)
        )


def batch_backtest(
    strategies: List[Dict[str, Any]],
    months: int = 3,
    days: Optional[int] = None,
    starting_balance: float = 1000.0,
    fee_rate: float = 0.0025,
    loss_tolerance: float = 0.0,
    product_id: str = "BTC-USD",
    granularity: str = '5m',
    candles: Optional[List[Candle]] = None,
    verbose: bool = False
) -> List[BacktestResult]:
    """
    Run multiple backtests efficiently (shares data loading).
    
    Args:
        strategies: List of dicts with 'strategy' (class) and optional 'params'
        months: Months of historical data
        days: Days of data (overrides months if provided)
        starting_balance: Initial USD
        fee_rate: Trading fee as decimal (0.0025 = 0.25%)
        loss_tolerance: Max acceptable loss (0.0 = no losses allowed)
        product_id: Trading pair
        granularity: Candle size
        candles: Pre-loaded candles (skips data fetching if provided)
        verbose: Print per-strategy progress
    
    Returns:
        List of BacktestResult objects
    
    Example:
        >>> results = batch_backtest([
        ...     {'strategy': MAStrategy, 'params': {'period': 10}},
        ...     {'strategy': MAStrategy, 'params': {'period': 20}},
        ...     {'strategy': RSIStrategy},
        ... ], fee_rate=0.001)
    """
    # Load data once if not provided
    if candles is None:
        print(f"📦 Loading data for batch backtest...")
        fetcher = DataFetcher(product_id, verbose=False)
        if days is not None:
            candles = fetcher.get_candles(days=days, granularity=granularity)
        else:
            candles = fetcher.get_candles(months=months, granularity=granularity)
        print(f"✅ Loaded {len(candles)} candles")
    
    results = []
    total = len(strategies)
    
    for i, config in enumerate(strategies, 1):
        strat_class = config['strategy']
        params = config.get('params', {})
        
        print(f"[{i}/{total}] Testing {strat_class.__name__}...", end=" ")
        
        result = backtest(
            strat_class,
            candles=candles,
            starting_balance=starting_balance,
            fee_rate=fee_rate,
            loss_tolerance=loss_tolerance,
            strategy_params=params,
            verbose=False
        )
        
        if result.success:
            print(f"Return: {result.total_return_pct:+.2f}%")
        else:
            print(f"❌ {result.error}")
        
        results.append(result)
    
    # Print summary
    successful = [r for r in results if r.success]
    if successful:
        best = max(successful, key=lambda r: r.total_return_pct)
        print(f"\n🏆 Best: {best.strategy_name} ({best.total_return_pct:+.2f}%)")
    
    return results


def visualize_backtest(
    result: BacktestResult,
    candles: Optional[List[Candle]] = None,
    product_id: str = "BTC-USD",
    granularity: str = '5m',
    months: int = 3,
    port: int = 5002,
    open_browser: bool = True
):
    """
    Launch a dashboard to visualize backtest results.
    
    Shows the equity curve, trade markers, and performance metrics.
    
    Args:
        result: BacktestResult from a backtest run
        candles: Candle data used in backtest (will fetch if not provided)
        product_id: Trading pair (used if candles not provided)
        granularity: Candle size (used if candles not provided)
        months: Months of data (used if candles not provided)
        port: Web server port
        open_browser: Auto-open browser
    
    Example:
        >>> result = backtest(MyStrategy, months=3)
        >>> visualize_backtest(result)
    """
    import threading
    import webbrowser
    
    try:
        from flask import Flask, render_template, jsonify
        from flask_cors import CORS
    except ImportError:
        print("⚠️  Flask not installed. Run: pip install flask flask-cors")
        return
    
    # Load candles if not provided
    if candles is None:
        print(f"📦 Loading candle data...")
        fetcher = DataFetcher(product_id, verbose=False)
        candles = fetcher.get_candles(months=months, granularity=granularity)
    
    import os
    template_dir = os.path.join(os.path.dirname(__file__), '..', 'dashboard', 'templates')
    app = Flask(__name__, template_folder=template_dir)
    CORS(app)
    
    @app.route('/')
    def index():
        return render_template('backtest_results.html')
    
    @app.route('/api/candles')
    def get_candles():
        return jsonify([{
            'time': c.timestamp * 1000,
            'open': c.open,
            'high': c.high,
            'low': c.low,
            'close': c.close,
            'volume': c.volume
        } for c in candles])
    
    @app.route('/api/results')
    def get_results():
        return jsonify(result.to_dict())
    
    @app.route('/api/trades')
    def get_trades():
        return jsonify(result.trade_log)
    
    @app.route('/api/equity')
    def get_equity():
        # Match equity curve to candle times
        if result.equity_curve and candles:
            start_idx = 50  # min_candles default
            times = [c.timestamp * 1000 for c in candles[start_idx:start_idx + len(result.equity_curve)]]
            return jsonify({
                'times': times,
                'values': result.equity_curve
            })
        return jsonify({'times': [], 'values': []})
    
    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(f'http://localhost:{port}')).start()
    
    print(f"\n🌐 Backtest visualization at http://localhost:{port}")
    print(f"   Press Ctrl+C to stop\n")
    
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
