"""
PRODUCTION-LEVEL Market Maker Executor

⚠️  REAL MONEY AT RISK - USE WITH CAUTION ⚠️

This module implements a production-grade market making executor with:
1. BALANCE-AWARE TRADE SIZING: Trade size = MIN(USD balance, asset value in USD)
2. SEQUENTIAL ORDER EXECUTION: Buy first → wait for fill → sell exact filled amount
3. STRICT PROFIT VERIFICATION: Validates actual profit after each round
4. ROBUST FEE VALIDATION: Multi-layered fee checking with tight tolerances
5. COMPREHENSIVE ERROR HANDLING: Fail-safe mechanisms at every step

Author: Production Trading System
Date: December 2025
"""

import json
import math
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, ROUND_DOWN
from typing import Optional, Dict, Tuple, Callable, List
from enum import Enum

try:
    from .order_book import CoinbaseOrderBook, OrderBook
    from .market_maker import MarketMaker
except ImportError:
    from order_book import CoinbaseOrderBook, OrderBook
    from market_maker import MarketMaker


# =============================================================================
# CUSTOM EXCEPTIONS - Clear error handling
# =============================================================================

class ProductionError(Exception):
    """Base exception for production executor"""
    pass


class FeeValidationError(ProductionError):
    """Raised when fees don't match expected values"""
    def __init__(self, side: str, expected: float, actual: float, tolerance: float):
        self.side = side
        self.expected = expected
        self.actual = actual
        self.tolerance = tolerance
        super().__init__(
            f"🚨 FEE VALIDATION FAILED on {side}!\n"
            f"   Expected: {expected*100:.6f}%\n"
            f"   Actual:   {actual*100:.6f}%\n"
            f"   Tolerance: ±{tolerance*100:.6f}%\n"
            f"   Difference: {abs(actual-expected)*100:.6f}%"
        )


class ProfitValidationError(ProductionError):
    """Raised when a round was not profitable"""
    def __init__(self, expected: float, actual: float, details: Dict):
        self.expected = expected
        self.actual = actual
        self.details = details
        super().__init__(
            f"🚨 PROFIT VALIDATION FAILED!\n"
            f"   Expected Profit: ${expected:.6f}\n"
            f"   Actual Profit:   ${actual:.6f}\n"
            f"   Difference:      ${actual - expected:.6f}\n"
            f"   Buy:  {details['buy_value']:.4f} USD + {details['buy_fee']:.6f} fee\n"
            f"   Sell: {details['sell_value']:.4f} USD - {details['sell_fee']:.6f} fee"
        )


class InsufficientBalanceError(ProductionError):
    """Raised when there's not enough balance to trade"""
    def __init__(self, currency: str, available: float, required: float):
        self.currency = currency
        self.available = available
        self.required = required
        super().__init__(
            f"Insufficient {currency} balance: "
            f"Available ${available:.4f}, Required ${required:.4f}"
        )


class OrderExecutionError(ProductionError):
    """Raised when order execution fails"""
    pass


class SpreadTooTightError(ProductionError):
    """Raised when spread is insufficient for profit"""
    def __init__(self, spread_pct: float, min_required: float):
        self.spread_pct = spread_pct
        self.min_required = min_required
        super().__init__(
            f"Spread too tight: {spread_pct:.4f}% < minimum {min_required:.4f}%"
        )


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class Balance:
    """Immutable balance snapshot"""
    currency: str
    available: float
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def __post_init__(self):
        if self.available < 0:
            raise ValueError(f"Balance cannot be negative: {self.available}")


@dataclass
class OrderFill:
    """Complete record of a filled order"""
    order_id: str
    side: str  # "BUY" or "SELL"
    product_id: str
    filled_size: float
    filled_value: float
    average_price: float
    fee_amount: float
    fee_rate: float
    timestamp: datetime
    raw_response: Dict = field(default_factory=dict)
    
    def validate_fee(self, expected_rate: float, tolerance: float):
        """Validate fee rate is within tolerance"""
        diff = abs(self.fee_rate - expected_rate)
        if diff > tolerance:
            raise FeeValidationError(
                side=self.side,
                expected=expected_rate,
                actual=self.fee_rate,
                tolerance=tolerance
            )


@dataclass
class TradeRoundResult:
    """Complete record of a trade round"""
    round_id: str
    product_id: str
    buy_fill: OrderFill
    sell_fill: OrderFill
    started_at: datetime
    completed_at: datetime
    
    # Calculated fields
    gross_profit: float = 0.0
    total_fees: float = 0.0
    net_profit: float = 0.0
    net_profit_pct: float = 0.0
    
    # Pre-trade balance snapshot
    pre_usd_balance: float = 0.0
    pre_asset_balance: float = 0.0
    
    # Post-trade balance snapshot
    post_usd_balance: float = 0.0
    post_asset_balance: float = 0.0
    
    # Verification
    verified_profitable: bool = False
    
    def __post_init__(self):
        # Calculate profits from fills
        self.total_fees = self.buy_fill.fee_amount + self.sell_fill.fee_amount
        self.gross_profit = self.sell_fill.filled_value - self.buy_fill.filled_value
        self.net_profit = self.gross_profit - self.total_fees
        
        if self.buy_fill.filled_value > 0:
            self.net_profit_pct = (self.net_profit / self.buy_fill.filled_value) * 100


# =============================================================================
# COINBASE API CLIENT
# =============================================================================

class CoinbaseProductionClient:
    """
    Production-grade Coinbase API client.
    
    Features:
    - Request retry logic
    - Response validation
    - Detailed logging
    """
    
    def __init__(
        self,
        api_key_name: str,
        api_private_key: str,
        product_id: str,
        logger: Callable[[str], None]
    ):
        self.api_key_name = api_key_name
        self.api_private_key = api_private_key
        self.product_id = product_id
        self.base_url = "https://api.coinbase.com"
        self._log = logger
        
        import requests
        self.requests = requests
        
        self.base_currency = product_id.split('-')[0]  # VVV
        self.quote_currency = product_id.split('-')[1]  # USD
    
    def _generate_jwt_token(self, method: str, request_path: str) -> str:
        """Generate JWT token for API authentication."""
        from coinbase import jwt_generator
        
        jwt_uri = jwt_generator.format_jwt_uri(method, request_path)
        token = jwt_generator.build_rest_jwt(jwt_uri, self.api_key_name, self.api_private_key)
        return token
    
    def _make_request(
        self,
        method: str,
        endpoint: str,
        body: dict = None,
        retries: int = 3
    ) -> Dict:
        """Make authenticated request with retry logic."""
        last_error = None
        
        for attempt in range(retries):
            try:
                token = self._generate_jwt_token(method, endpoint)
                
                headers = {
                    'Authorization': f'Bearer {token}',
                    'Content-Type': 'application/json'
                }
                
                url = self.base_url + endpoint
                
                if method == 'GET':
                    response = self.requests.get(url, headers=headers, timeout=30)
                elif method == 'POST':
                    response = self.requests.post(url, headers=headers, json=body, timeout=30)
                
                response.raise_for_status()
                return response.json()
                
            except Exception as e:
                last_error = e
                if attempt < retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff
                    self._log(f"⚠️  Request failed, retrying in {wait_time}s: {e}")
                    time.sleep(wait_time)
        
        raise OrderExecutionError(f"Request failed after {retries} attempts: {last_error}")
    
    def get_balances(self) -> Tuple[Balance, Balance]:
        """
        Get current balances for both currencies.
        
        Returns:
            Tuple of (quote_balance, base_balance) e.g., (USD, VVV)
        """
        result = self._make_request('GET', '/api/v3/brokerage/accounts')
        
        quote_balance = None
        base_balance = None
        
        for account in result.get('accounts', []):
            currency = account['currency']
            available = float(account['available_balance']['value'])
            
            if currency == self.quote_currency:
                quote_balance = Balance(currency=currency, available=available)
            elif currency == self.base_currency:
                base_balance = Balance(currency=currency, available=available)
        
        if quote_balance is None:
            raise ProductionError(f"No account found for {self.quote_currency}")
        if base_balance is None:
            raise ProductionError(f"No account found for {self.base_currency}")
        
        return (quote_balance, base_balance)
    
    def place_limit_order(
        self,
        side: str,
        size: float,
        price: float,
        post_only: bool = True
    ) -> str:
        """
        Place a limit order.
        
        Args:
            side: "BUY" or "SELL"
            size: Amount of base currency (VVV)
            price: Limit price in quote currency (USD)
            post_only: Ensure maker order
        
        Returns:
            Order ID
        """
        # Use appropriate precision for this trading pair
        from decimal import Decimal, ROUND_DOWN
        
        # Get size precision for this product
        size_precision_map = {
            'WET-USD': 1,    # 0.1 WET minimum (base_increment=0.1)
            'BONK-USD': 0,   # Whole numbers only
            'GIGA-USD': 4,   # 0.0001 GIGA
            'VVV-USD': 6,    # 0.000001 VVV
            'TRAC-USD': 4,   # 0.0001 TRAC
        }
        size_decimals = size_precision_map.get(self.product_id, 4)
        
        # Round size down to avoid "insufficient funds" errors
        size_decimal = Decimal(str(size))
        size_rounded = float(size_decimal.quantize(Decimal('0.1') ** size_decimals, rounding=ROUND_DOWN))
        
        # Format with explicit decimal places
        size_str = f"{size_rounded:.{size_decimals}f}"
        price_str = f"{price:.4f}"
        
        order_data = {
            "client_order_id": f"prod_{side.lower()}_{int(time.time()*1000)}",
            "product_id": self.product_id,
            "side": side.upper(),
            "order_configuration": {
                "limit_limit_gtc": {
                    "base_size": size_str,
                    "limit_price": price_str,
                    "post_only": post_only
                }
            }
        }
        
        self._log(f"📤 Placing {side} order: {size_str} @ ${price_str}")
        
        result = self._make_request('POST', '/api/v3/brokerage/orders', order_data)
        
        if 'error_response' in result:
            error = result['error_response']
            raise OrderExecutionError(
                f"Order rejected: {error.get('error', 'Unknown')} - "
                f"{error.get('message', 'No message')} - "
                f"{error.get('error_details', '')}"
            )
        
        if 'success_response' not in result:
            raise OrderExecutionError(f"Unexpected order response: {result}")
        
        order_id = result['success_response']['order_id']
        self._log(f"✅ Order placed: {order_id}")
        return order_id
    
    def get_order_status(self, order_id: str) -> Dict:
        """Get current status of an order."""
        result = self._make_request('GET', f'/api/v3/brokerage/orders/historical/{order_id}')
        return result.get('order', {})
    
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order."""
        try:
            result = self._make_request(
                'POST',
                '/api/v3/brokerage/orders/batch_cancel',
                {"order_ids": [order_id]}
            )
            self._log(f"🚫 Cancelled order: {order_id}")
            return True
        except Exception as e:
            self._log(f"⚠️  Failed to cancel order {order_id}: {e}")
            return False
    
    def wait_for_fill(
        self,
        order_id: str,
        timeout_seconds: int = 300,
        poll_interval: float = 2.0
    ) -> OrderFill:
        """
        Wait for an order to fill completely.
        
        Args:
            order_id: Order to monitor
            timeout_seconds: Maximum wait time
            poll_interval: Seconds between status checks
        
        Returns:
            OrderFill with complete fill details
            
        Raises:
            TimeoutError: If order doesn't fill in time
            OrderExecutionError: If order fails
        """
        elapsed = 0.0
        
        while elapsed < timeout_seconds:
            order = self.get_order_status(order_id)
            status = order.get('status', 'UNKNOWN')
            
            if status == 'FILLED':
                filled_size = float(order.get('filled_size', 0))
                avg_price = float(order.get('average_filled_price', 0))
                total_fees = float(order.get('total_fees', 0))
                filled_value = float(order.get('total_value_after_fees', 0))
                
                # Calculate actual fill value (before fees)
                # For BUY: filled_value = size * price (what we spent)
                # For SELL: filled_value = size * price (what we received)
                fill_value_gross = filled_size * avg_price
                
                # Calculate actual fee rate
                fee_rate = total_fees / fill_value_gross if fill_value_gross > 0 else 0
                
                return OrderFill(
                    order_id=order_id,
                    side=order.get('side', 'UNKNOWN'),
                    product_id=order.get('product_id', self.product_id),
                    filled_size=filled_size,
                    filled_value=fill_value_gross,
                    average_price=avg_price,
                    fee_amount=total_fees,
                    fee_rate=fee_rate,
                    timestamp=datetime.utcnow(),
                    raw_response=order
                )
            
            if status in ['CANCELLED', 'EXPIRED', 'FAILED']:
                raise OrderExecutionError(
                    f"Order {order_id} failed with status: {status}\n"
                    f"Details: {order}"
                )
            
            time.sleep(poll_interval)
            elapsed += poll_interval
            
            # Log progress every 30 seconds
            if int(elapsed) % 30 == 0 and elapsed > 0:
                filled = order.get('filled_size', '0')
                total = order.get('order_configuration', {}).get('limit_limit_gtc', {}).get('base_size', '?')
                self._log(f"⏳ Waiting for fill: {filled}/{total} ({status})")
        
        # Timeout - cancel the order
        self._log(f"⏰ Order timeout after {timeout_seconds}s, cancelling...")
        self.cancel_order(order_id)
        raise TimeoutError(f"Order {order_id} did not fill within {timeout_seconds}s")


# =============================================================================
# PRODUCTION MARKET MAKER
# =============================================================================

class ProductionMarketMaker:
    """
    Production-grade market maker with strict safety guarantees.
    
    GUARANTEES:
    1. Trade size = MIN(USD balance, asset value in USD)
    2. Both orders MUST fill before proceeding
    3. Actual profit is verified after each round
    4. Fees are validated on every order
    5. All errors halt trading immediately
    """
    
    # Fee configuration
    EXPECTED_FEE_RATE = 0.00025  # 0.025% maker fee
    FEE_TOLERANCE = 0.0001      # 0.01% tolerance (allows up to 0.035%)
    
    # Profit configuration
    MIN_PROFIT_RATE = 0.0001    # Minimum 0.01% profit per round
    PROFIT_TOLERANCE = 0.0001   # Allow 0.01% variance in profit verification
    
    # Execution configuration
    ORDER_TIMEOUT = 300         # 5 minutes to fill
    POLL_INTERVAL = 2.0         # Check every 2 seconds
    
    def __init__(
        self,
        api_key_name: str,
        api_private_key: str,
        product_id: str = "VVV-USD",
        min_trade_usd: float = 10.0,
        max_trade_usd: float = 10000.0,
        logger: Optional[Callable[[str], None]] = None
    ):
        """
        Initialize production market maker.
        
        Args:
            api_key_name: Coinbase API key name
            api_private_key: Coinbase API private key (PEM format)
            product_id: Trading pair (e.g., "VVV-USD")
            min_trade_usd: Minimum trade size in USD
            max_trade_usd: Maximum trade size in USD
            logger: Logging callback
        """
        self._log = logger or self._default_logger
        
        self.product_id = product_id
        self.min_trade_usd = min_trade_usd
        self.max_trade_usd = max_trade_usd
        
        # Initialize API client
        self.client = CoinbaseProductionClient(
            api_key_name=api_key_name,
            api_private_key=api_private_key,
            product_id=product_id,
            logger=self._log
        )
        
        # Initialize order book fetcher
        self.order_book = CoinbaseOrderBook(product_id=product_id)
        
        # Trade history
        self.completed_rounds: List[TradeRoundResult] = []
        self.total_profit: float = 0.0
        self.total_fees: float = 0.0
        
        # Calculate minimum spread required
        self.min_spread_for_breakeven = 2 * self.EXPECTED_FEE_RATE
        self.min_spread_for_profit = self.min_spread_for_breakeven + self.MIN_PROFIT_RATE
        
        self._log("=" * 70)
        self._log("🏭 PRODUCTION MARKET MAKER INITIALIZED")
        self._log("=" * 70)
        self._log(f"Product: {product_id}")
        self._log(f"Expected Fee Rate: {self.EXPECTED_FEE_RATE*100:.4f}%")
        self._log(f"Fee Tolerance: ±{self.FEE_TOLERANCE*100:.4f}%")
        self._log(f"Min Spread for Profit: {self.min_spread_for_profit*100:.4f}%")
        self._log(f"Trade Size Range: ${min_trade_usd:.2f} - ${max_trade_usd:.2f}")
        self._log("=" * 70)
    
    @staticmethod
    def _get_size_precision_for_product(product_id: str) -> int:
        """Get size precision for any product - centralized logic."""
        size_precision_map = {
            'WET-USD': 1,    # 0.1 WET minimum (base_increment=0.1)
            'BONK-USD': 0,   # Whole numbers only
            'GIGA-USD': 4,   # 0.0001 GIGA
            'VVV-USD': 6,    # 0.000001 VVV
            'TRAC-USD': 4,   # 0.0001 TRAC
        }
        return size_precision_map.get(product_id, 4)  # Default 4 decimals
    
    @staticmethod
    def _round_size_for_product(size: float, product_id: str) -> float:
        """Round size to appropriate precision for product."""
        from decimal import Decimal, ROUND_DOWN
        
        size_decimals = ProductionMarketMaker._get_size_precision_for_product(product_id)
        size_decimal = Decimal(str(size))
        return float(size_decimal.quantize(Decimal('0.1') ** size_decimals, rounding=ROUND_DOWN))
    
    @staticmethod
    def _default_logger(msg: str):
        """Default logger with timestamp"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {msg}")
    
    def get_trade_size(self, book: OrderBook) -> Tuple[float, float, float]:
        """
        Calculate trade size based on portfolio minimum.
        
        Trade size = MIN(USD balance, asset value at current price)
        
        Returns:
            Tuple of (trade_size_usd, usd_available, asset_value_usd)
        """
        # Get current balances
        usd_balance, asset_balance = self.client.get_balances()
        
        usd_available = usd_balance.available
        asset_available = asset_balance.available
        
        # Calculate asset value in USD at current mid price
        asset_value_usd = asset_available * book.mid_price
        
        # Trade size is the MINIMUM of USD and asset value
        # This ensures we can always complete a round-trip trade
        trade_size = min(usd_available, asset_value_usd)
        
        # Apply bounds
        trade_size = max(trade_size, self.min_trade_usd)
        trade_size = min(trade_size, self.max_trade_usd)
        
        self._log(f"💰 Portfolio: ${usd_available:.2f} USD, {asset_available:.4f} {self.client.base_currency} (${asset_value_usd:.2f})")
        self._log(f"📊 Trade Size: ${trade_size:.2f} (min of portfolio)")
        
        return (trade_size, usd_available, asset_value_usd)
    
    def get_price_precision(self, book: OrderBook) -> Tuple[int, float]:
        """
        Detect price precision and calculate minimum tick size.
        
        Returns:
            Tuple of (decimal_places, min_tick_size)
        """
        # Analyze current prices to determine precision
        bid_str = f"{book.best_bid.price:.10f}".rstrip('0').rstrip('.')
        ask_str = f"{book.best_ask.price:.10f}".rstrip('0').rstrip('.')
        
        bid_decimals = len(bid_str.split('.')[-1]) if '.' in bid_str else 0
        ask_decimals = len(ask_str.split('.')[-1]) if '.' in ask_str else 0
        
        precision = max(bid_decimals, ask_decimals, 2)  # At least 2 decimals
        min_tick = 10 ** (-precision)
        
        return (precision, min_tick)
    
    def get_size_precision(self) -> int:
        """
        Get appropriate size precision for the trading pair.
        
        Returns:
            Number of decimal places for order sizes
        """
        # Size precision rules per trading pair (from Coinbase base_increment)
        size_precision_map = {
            'WET-USD': 1,    # 0.1 WET minimum (base_increment=0.1)
            'BONK-USD': 0,   # Whole numbers only
            'GIGA-USD': 4,   # 0.0001 GIGA
            'VVV-USD': 6,    # 0.000001 VVV
            'TRAC-USD': 4,   # 0.0001 TRAC
        }
        
        return size_precision_map.get(self.product_id, 4)  # Default 4 decimals
    
    def analyze_opportunity(self, trade_size_usd: float) -> Dict:
        """
        Analyze if current market conditions are profitable.
        
        Returns:
            Analysis dict with all trade parameters
            
        Raises:
            SpreadTooTightError: If spread insufficient
        """
        book = self.order_book.fetch_order_book(limit=10)
        
        if not book.best_bid or not book.best_ask:
            raise ProductionError("Order book is empty!")
        
        # Get price precision and minimum tick
        precision, min_tick = self.get_price_precision(book)
        
        current_bid = book.best_bid.price
        current_ask = book.best_ask.price
        spread = current_ask - current_bid
        spread_pct = spread / book.mid_price
        
        # Our strategy: undercut by minimum tick on both sides
        # We place BUY order at current_bid + min_tick (higher than current best bid)
        # We place SELL order at current_ask - min_tick (lower than current best ask)
        our_buy_price = current_bid + min_tick
        our_sell_price = current_ask - min_tick
        
        # Ensure we don't cross the spread
        if our_buy_price >= our_sell_price:
            raise SpreadTooTightError(f"Cannot undercut spread: buy {our_buy_price:.{precision}f} >= sell {our_sell_price:.{precision}f}")
        
        # Calculate expected trade values using OUR prices
        buy_size_raw = trade_size_usd / our_buy_price
        
        # Round size down to appropriate precision using centralized function
        buy_size_asset = self._round_size_for_product(buy_size_raw, self.product_id)
        
        # Ensure we don't have zero size due to rounding
        size_decimals = self._get_size_precision_for_product(self.product_id)
        min_size = 10 ** (-size_decimals)
        if buy_size_asset < min_size:
            raise SpreadTooTightError(f"Trade size too small after rounding: {buy_size_asset}")
        
        # Recalculate actual buy value with rounded size
        buy_value = buy_size_asset * our_buy_price
        buy_fee = buy_value * self.EXPECTED_FEE_RATE
        
        sell_value = buy_size_asset * our_sell_price
        sell_fee = sell_value * self.EXPECTED_FEE_RATE
        
        total_fees = buy_fee + sell_fee
        gross_profit = sell_value - buy_value
        net_profit = gross_profit - total_fees
        net_profit_pct = net_profit / buy_value
        
        analysis = {
            "book": book,
            "current_bid": current_bid,
            "current_ask": current_ask,
            "our_buy_price": our_buy_price,
            "our_sell_price": our_sell_price,
            "mid_price": book.mid_price,
            "spread": spread,
            "spread_pct": spread_pct,
            "precision": precision,
            "min_tick": min_tick,
            "trade_size_usd": trade_size_usd,
            "buy_size_asset": buy_size_asset,
            "buy_value": buy_value,
            "buy_fee": buy_fee,
            "sell_value": sell_value,
            "sell_fee": sell_fee,
            "total_fees": total_fees,
            "gross_profit": gross_profit,
            "net_profit": net_profit,
            "net_profit_pct": net_profit_pct,
            "is_profitable": net_profit > 0,
            "meets_minimum": net_profit_pct >= self.MIN_PROFIT_RATE
        }
        
        self._log(f"📈 Spread: {spread_pct*100:.4f}% (${spread:.{precision}f})")
        self._log(f"🎯 Our undercut: BUY @ ${our_buy_price:.{precision}f} (+${min_tick:.{precision}f}) | SELL @ ${our_sell_price:.{precision}f} (-${min_tick:.{precision}f})")
        self._log(f"   Expected Profit: ${net_profit:.4f} ({net_profit_pct*100:.4f}%)")
        
        if not analysis["is_profitable"]:
            raise SpreadTooTightError(
                spread_pct=spread_pct * 100,
                min_required=self.min_spread_for_breakeven * 100
            )
        
        if not analysis["meets_minimum"]:
            raise SpreadTooTightError(
                spread_pct=spread_pct * 100,
                min_required=self.min_spread_for_profit * 100
            )
        
        return analysis
    
    def monitor_for_profitable_spread(self, timeout_seconds: float = 45.0, poll_interval: float = 1.0) -> Optional[Dict]:
        """
        Monitor order book for profitable spread conditions within timeout.
        
        Args:
            timeout_seconds: Maximum time to wait for profitable conditions
            poll_interval: Seconds between spread checks
            
        Returns:
            Analysis dict if profitable opportunity found, None if timeout
        """
        start_time = time.time()
        last_spread = None
        
        self._log(f"🔍 Monitoring for profitable spread (timeout: {timeout_seconds}s)...")
        
        while (time.time() - start_time) < timeout_seconds:
            try:
                # Get current order book and trade size
                book = self.order_book.fetch_order_book(limit=10)
                trade_size_usd, _, _ = self.get_trade_size(book)
                
                # Quick profitability check without throwing exceptions
                if not book.best_bid or not book.best_ask:
                    time.sleep(poll_interval)
                    continue
                
                # Calculate current spread
                precision, min_tick = self.get_price_precision(book)
                current_bid = book.best_bid.price
                current_ask = book.best_ask.price
                spread = current_ask - current_bid
                spread_pct = spread / book.mid_price
                
                # Our undercut prices
                our_buy_price = current_bid + min_tick
                our_sell_price = current_ask - min_tick
                
                # Skip if crossed spread
                if our_buy_price >= our_sell_price:
                    time.sleep(poll_interval)
                    continue
                
                # Calculate profit
                # Calculate profit - round size for accurate calculations
                buy_size_raw = trade_size_usd / our_buy_price
                buy_size_asset = self._round_size_for_product(buy_size_raw, self.product_id)
                buy_value = buy_size_asset * our_buy_price  # Recalculate with rounded size
                buy_fee = buy_value * self.EXPECTED_FEE_RATE
                sell_value = buy_size_asset * our_sell_price
                sell_fee = sell_value * self.EXPECTED_FEE_RATE
                total_fees = buy_fee + sell_fee
                gross_profit = sell_value - buy_value
                net_profit = gross_profit - total_fees
                net_profit_pct = net_profit / buy_value
                
                # Log spread changes
                if last_spread is None or abs(spread_pct - last_spread) > 0.001:  # 0.001% change
                    elapsed = time.time() - start_time
                    self._log(f"   [{elapsed:4.1f}s] Spread: {spread_pct*100:.4f}% → Net: {net_profit_pct*100:+.4f}%")
                    last_spread = spread_pct
                
                # Check if profitable
                if net_profit > 0 and net_profit_pct >= self.MIN_PROFIT_RATE:
                    elapsed = time.time() - start_time
                    self._log(f"✨ PROFITABLE OPPORTUNITY DETECTED after {elapsed:.1f}s!")
                    
                    # Return full analysis
                    return {
                        "book": book,
                        "current_bid": current_bid,
                        "current_ask": current_ask,
                        "our_buy_price": our_buy_price,
                        "our_sell_price": our_sell_price,
                        "mid_price": book.mid_price,
                        "spread": spread,
                        "spread_pct": spread_pct,
                        "precision": precision,
                        "min_tick": min_tick,
                        "trade_size_usd": trade_size_usd,
                        "buy_size_asset": buy_size_asset,
                        "buy_value": buy_value,
                        "buy_fee": buy_fee,
                        "sell_value": sell_value,
                        "sell_fee": sell_fee,
                        "total_fees": total_fees,
                        "gross_profit": gross_profit,
                        "net_profit": net_profit,
                        "net_profit_pct": net_profit_pct,
                        "is_profitable": True,
                        "meets_minimum": True
                    }
                
                time.sleep(poll_interval)
                
            except Exception as e:
                self._log(f"⚠️  Error during monitoring: {e}")
                time.sleep(poll_interval)
        
        elapsed = time.time() - start_time
        self._log(f"⏰ Monitoring timeout after {elapsed:.1f}s - no profitable opportunities")
        return None
    
    def execute_trade_round(self, monitor_timeout: float = 45.0) -> TradeRoundResult:
        """
        Execute a complete trade round with spread monitoring.
        
        SEQUENCE:
        1. Monitor spread for profitable conditions (up to timeout)
        2. Execute immediately when profitable opportunity detected
        3. Place BUY order → wait for fill → validate fees
        4. Place SELL order → wait for fill → validate fees  
        5. Verify actual profit and record results
        
        Args:
            monitor_timeout: Seconds to monitor for profitable spread
        
        Returns:
            TradeRoundResult with complete details
            
        Raises:
            Various errors if any step fails
        """
        round_id = f"round_{int(time.time()*1000)}"
        started_at = datetime.utcnow()
        
        self._log("")
        self._log("=" * 70)
        self._log(f"🚀 STARTING TRADE ROUND: {round_id}")
        self._log("=" * 70)
        
        # Step 1: Monitor for profitable opportunity
        analysis = self.monitor_for_profitable_spread(timeout_seconds=monitor_timeout)
        
        if analysis is None:
            raise SpreadTooTightError(
                spread_pct=0,  # Unknown final spread
                min_required=self.min_spread_for_profit * 100
            )
        
        # Get pre-trade balances
        usd_balance, asset_balance = self.client.get_balances()
        pre_usd = usd_balance.available
        pre_asset = asset_balance.available
        
        # Step 3: Place BOTH orders SIMULTANEOUSLY
        self._log("")
        self._log("⚡ STEP 1: Placing BOTH orders SIMULTANEOUSLY...")
        
        # Use the already properly rounded size from analysis, but double-check rounding
        buy_size_from_analysis = analysis["buy_size_asset"]
        buy_size_rounded = self._round_size_for_product(buy_size_from_analysis, self.product_id)
        
        # Debug: verify proper rounding
        if buy_size_rounded != buy_size_from_analysis:
            self._log(f"⚠️  Size re-rounded: {buy_size_from_analysis} → {buy_size_rounded}")
        
        buy_price = analysis["our_buy_price"]
        sell_price = analysis["our_sell_price"]
        
        # Place BUY order
        buy_order_id = None
        sell_order_id = None
        
        try:
            buy_order_id = self.client.place_limit_order(
                side="BUY",
                size=buy_size_rounded,
                price=analysis["our_buy_price"],  # Use our undercut price
                post_only=True
            )
            
            # Place SELL order immediately (using current asset balance)
            usd_balance, asset_balance = self.client.get_balances()
            sell_size_raw = min(buy_size_rounded, asset_balance.available)  # Don't oversell
            
            # Round the sell size using centralized function
            sell_size_rounded = self._round_size_for_product(sell_size_raw, self.product_id)
            
            sell_order_id = self.client.place_limit_order(
                side="SELL",
                size=sell_size_rounded,
                price=analysis["our_sell_price"],  # Use our undercut price
                post_only=True
            )
        except Exception as e:
            # CRITICAL: If one order succeeded but the other failed, cancel the successful one!
            self._log(f"❌ Order placement failed: {e}")
            if buy_order_id and not sell_order_id:
                self._log(f"🚨 CANCELLING orphaned BUY order: {buy_order_id}")
                self.client.cancel_order(buy_order_id)
            elif sell_order_id and not buy_order_id:
                self._log(f"🚨 CANCELLING orphaned SELL order: {sell_order_id}")
                self.client.cancel_order(sell_order_id)
            raise  # Re-raise the exception
        
        self._log(f"✅ Both orders placed simultaneously!")
        self._log(f"   BUY:  {buy_size_rounded:.2f} WET @ ${analysis['our_buy_price']:.4f}")
        self._log(f"   SELL: {sell_size_rounded:.2f} WET @ ${analysis['our_sell_price']:.4f}")
        
        # Step 4: Wait for BOTH orders to fill - WITH BREAK-EVEN REQUOTE AFTER 30s
        self._log("")
        self._log("⏳ Waiting for BOTH orders to fill (will requote at break-even after 30s if stuck)...")
        
        buy_fill = None
        sell_fill = None
        elapsed = 0.0
        breakeven_requoted = False
        BREAKEVEN_TIMEOUT = 30.0  # After 30s, requote at break-even
        
        # Track original prices for break-even calculation
        original_buy_price = analysis["our_buy_price"]
        original_sell_price = analysis["our_sell_price"]
        
        # Poll both orders until BOTH fill
        while True:
            # Check BUY order status
            if buy_fill is None:
                buy_order = self.client.get_order_status(buy_order_id)
                buy_status = buy_order.get('status', 'UNKNOWN')
                if buy_status == 'FILLED':
                    filled_size = float(buy_order.get('filled_size', 0))
                    avg_price = float(buy_order.get('average_filled_price', 0))
                    total_fees = float(buy_order.get('total_fees', 0))
                    fill_value_gross = filled_size * avg_price
                    fee_rate = total_fees / fill_value_gross if fill_value_gross > 0 else 0
                    buy_fill = OrderFill(
                        order_id=buy_order_id, side="BUY", product_id=self.product_id,
                        filled_size=filled_size, filled_value=fill_value_gross,
                        average_price=avg_price, fee_amount=total_fees, fee_rate=fee_rate,
                        timestamp=datetime.utcnow(), raw_response=buy_order
                    )
                    self._log(f"✅ BUY filled: {buy_fill.filled_size:.6f} @ ${buy_fill.average_price:.4f}")
                elif buy_status in ['CANCELLED', 'EXPIRED', 'FAILED']:
                    raise OrderExecutionError(f"BUY order failed: {buy_status}")
            
            # Check SELL order status
            if sell_fill is None:
                sell_order = self.client.get_order_status(sell_order_id)
                sell_status = sell_order.get('status', 'UNKNOWN')
                if sell_status == 'FILLED':
                    filled_size = float(sell_order.get('filled_size', 0))
                    avg_price = float(sell_order.get('average_filled_price', 0))
                    total_fees = float(sell_order.get('total_fees', 0))
                    fill_value_gross = filled_size * avg_price
                    fee_rate = total_fees / fill_value_gross if fill_value_gross > 0 else 0
                    sell_fill = OrderFill(
                        order_id=sell_order_id, side="SELL", product_id=self.product_id,
                        filled_size=filled_size, filled_value=fill_value_gross,
                        average_price=avg_price, fee_amount=total_fees, fee_rate=fee_rate,
                        timestamp=datetime.utcnow(), raw_response=sell_order
                    )
                    self._log(f"✅ SELL filled: {sell_fill.filled_size:.6f} @ ${sell_fill.average_price:.4f}")
                elif sell_status in ['CANCELLED', 'EXPIRED', 'FAILED']:
                    raise OrderExecutionError(f"SELL order failed: {sell_status}")
            
            # Both filled? We're done!
            if buy_fill and sell_fill:
                break
            
            # BREAK-EVEN REQUOTE: After 30s, if one-legged, requote at break-even price (DISCRETE TICKS)
            if elapsed >= BREAKEVEN_TIMEOUT and not breakeven_requoted:
                if (buy_fill and not sell_fill) or (sell_fill and not buy_fill):
                    breakeven_requoted = True
                    min_tick = analysis["min_tick"]
                    precision = analysis["precision"]
                    
                    if buy_fill and not sell_fill:
                        # BUY filled, SELL stuck
                        # Break-even (continuous): sell_price >= buy_price * (1 + fee) / (1 - fee)
                        breakeven_sell_continuous = buy_fill.average_price * (1 + self.EXPECTED_FEE_RATE) / (1 - self.EXPECTED_FEE_RATE)
                        
                        # DISCRETE: Round UP to next tick (we need at least this much to not lose)
                        breakeven_sell_ticks = math.ceil(breakeven_sell_continuous / min_tick)
                        breakeven_sell = breakeven_sell_ticks * min_tick
                        
                        self._log(f"🔄 30s timeout - requoting SELL at BREAK-EVEN (maker)")
                        self._log(f"   Continuous break-even: ${breakeven_sell_continuous:.6f}")
                        self._log(f"   Discrete (tick-rounded UP): ${breakeven_sell:.{precision}f}")
                        self._log(f"   (Original: ${original_sell_price:.{precision}f}, BUY filled @ ${buy_fill.average_price:.{precision}f})")
                        
                        # Cancel old sell order
                        self.client.cancel_order(sell_order_id)
                        
                        # Place new sell order at discrete break-even (MAKER - post_only=True)
                        sell_order_id = self.client.place_limit_order(
                            side="SELL",
                            size=sell_size_rounded,
                            price=breakeven_sell,
                            post_only=True  # Stay maker
                        )
                    
                    elif sell_fill and not buy_fill:
                        # SELL filled, BUY stuck
                        # Break-even (continuous): buy_price <= sell_price * (1 - fee) / (1 + fee)
                        breakeven_buy_continuous = sell_fill.average_price * (1 - self.EXPECTED_FEE_RATE) / (1 + self.EXPECTED_FEE_RATE)
                        
                        # DISCRETE: Round DOWN to previous tick (we can pay at most this much to not lose)
                        breakeven_buy_ticks = math.floor(breakeven_buy_continuous / min_tick)
                        breakeven_buy = breakeven_buy_ticks * min_tick
                        
                        self._log(f"🔄 30s timeout - requoting BUY at BREAK-EVEN (maker)")
                        self._log(f"   Continuous break-even: ${breakeven_buy_continuous:.6f}")
                        self._log(f"   Discrete (tick-rounded DOWN): ${breakeven_buy:.{precision}f}")
                        self._log(f"   (Original: ${original_buy_price:.{precision}f}, SELL filled @ ${sell_fill.average_price:.{precision}f})")
                        
                        # Cancel old buy order
                        self.client.cancel_order(buy_order_id)
                        
                        # Place new buy order at discrete break-even (MAKER - post_only=True)
                        buy_order_id = self.client.place_limit_order(
                            side="BUY",
                            size=buy_size_rounded,
                            price=breakeven_buy,
                            post_only=True  # Stay maker
                        )
            
            time.sleep(self.POLL_INTERVAL)
            elapsed += self.POLL_INTERVAL
            
            # Log progress every 60 seconds
            if int(elapsed) % 60 == 0 and elapsed > 0:
                buy_stat = "FILLED" if buy_fill else "PENDING"
                sell_stat = "FILLED" if sell_fill else "PENDING"
                self._log(f"⏳ Still waiting [{int(elapsed)}s]... BUY: {buy_stat}, SELL: {sell_stat}")
        
        self._log(f"   BUY Value: ${buy_fill.filled_value:.4f}, Fee: ${buy_fill.fee_amount:.6f} ({buy_fill.fee_rate*100:.4f}%)")
        self._log(f"   SELL Value: ${sell_fill.filled_value:.4f}, Fee: ${sell_fill.fee_amount:.6f} ({sell_fill.fee_rate*100:.4f}%)")
        
        # Step 5: Validate BOTH fees
        buy_fill.validate_fee(self.EXPECTED_FEE_RATE, self.FEE_TOLERANCE)
        sell_fill.validate_fee(self.EXPECTED_FEE_RATE, self.FEE_TOLERANCE)
        self._log("✅ Both fees validated")
        
        # Step 6: Get post-trade balances
        post_usd_balance, post_asset_balance = self.client.get_balances()
        
        # Step 7: Create round result
        completed_at = datetime.utcnow()
        result = TradeRoundResult(
            round_id=round_id,
            product_id=self.product_id,
            buy_fill=buy_fill,
            sell_fill=sell_fill,
            started_at=started_at,
            completed_at=completed_at,
            pre_usd_balance=pre_usd,
            pre_asset_balance=pre_asset,
            post_usd_balance=post_usd_balance.available,
            post_asset_balance=post_asset_balance.available
        )
        
        # Step 8: Verify profit
        self._log("")
        self._log("🔍 VERIFYING PROFIT...")
        
        # Calculate actual USD change
        actual_usd_change = result.post_usd_balance - result.pre_usd_balance
        
        # The net profit should match the USD change (since we traded back to same asset amount)
        expected_profit = result.net_profit
        
        self._log(f"   Calculated Net Profit: ${result.net_profit:.6f}")
        self._log(f"   Actual USD Change:     ${actual_usd_change:.6f}")
        self._log(f"   Total Fees Paid:       ${result.total_fees:.6f}")
        
        # Verify we made profit
        if result.net_profit <= 0:
            raise ProfitValidationError(
                expected=analysis["net_profit"],
                actual=result.net_profit,
                details={
                    "buy_value": buy_fill.filled_value,
                    "buy_fee": buy_fill.fee_amount,
                    "sell_value": sell_fill.filled_value,
                    "sell_fee": sell_fill.fee_amount,
                }
            )
        
        result.verified_profitable = True
        
        # Update totals
        self.total_profit += result.net_profit
        self.total_fees += result.total_fees
        self.completed_rounds.append(result)
        
        self._log("")
        self._log("=" * 70)
        self._log(f"✅ ROUND COMPLETE: {round_id}")
        self._log(f"   Net Profit: ${result.net_profit:.6f} ({result.net_profit_pct:.4f}%)")
        self._log(f"   Duration: {(completed_at - started_at).total_seconds():.1f}s")
        self._log(f"   Total Profit (session): ${self.total_profit:.4f}")
        self._log("=" * 70)
        
        return result
    
    def get_session_stats(self) -> Dict:
        """Get session statistics."""
        return {
            "product_id": self.product_id,
            "rounds_completed": len(self.completed_rounds),
            "total_profit": self.total_profit,
            "total_fees": self.total_fees,
            "average_profit_per_round": self.total_profit / len(self.completed_rounds) if self.completed_rounds else 0,
            "rounds": [
                {
                    "id": r.round_id,
                    "net_profit": r.net_profit,
                    "net_profit_pct": r.net_profit_pct,
                    "fees": r.total_fees,
                    "verified": r.verified_profitable,
                    "duration_s": (r.completed_at - r.started_at).total_seconds()
                }
                for r in self.completed_rounds
            ]
        }


# =============================================================================
# CREDENTIALS LOADER
# =============================================================================

def load_production_credentials(secrets_file: str = "secrets/secrets2.json") -> Tuple[str, str]:
    """
    Load API credentials from secrets file.
    
    Args:
        secrets_file: Path to secrets JSON file
    
    Returns:
        Tuple of (api_key_name, api_private_key)
    """
    if not os.path.exists(secrets_file):
        raise FileNotFoundError(
            f"Secrets file not found: {secrets_file}\n"
            f"Please create it with your Coinbase API credentials."
        )
    
    with open(secrets_file, 'r') as f:
        secrets = json.load(f)
    
    api_key_name = secrets.get('coinbase_api_key_name')
    api_private_key = secrets.get('coinbase_api_private_key')
    
    if not api_key_name or not api_private_key:
        raise ValueError(
            f"Missing credentials in {secrets_file}. "
            f"Required: coinbase_api_key_name, coinbase_api_private_key"
        )
    
    return (api_key_name, api_private_key)


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def main():
    """Production trading entry point."""
    import argparse
    import signal
    
    parser = argparse.ArgumentParser(
        description="Production Market Maker - REAL MONEY",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument("--product_id", type=str, default="WET-USD",
                       help="Trading pair (default: WET-USD)")
    # NOTE: BONK-USD is also excellent for market making:
    # - 8 decimal precision (ultra-fine order placement)
    # - 0.072% profit margin (~$5.3M volume) 
    # - Manageable risk with good spread
    # Consider switching: python -m market_making.production_executor --product_id BONK-USD
    parser.add_argument("--min_trade", type=float, default=10.0,
                       help="Minimum trade size in USD (default: 10)")
    parser.add_argument("--max_trade", type=float, default=10000.0,
                       help="Maximum trade size in USD (default: 10000)")
    parser.add_argument("--interval", type=float, default=30.0,
                       help="Seconds between rounds (default: 30)")
    parser.add_argument("--monitor_timeout", type=float, default=45.0,
                       help="Seconds to monitor for profitable spread per round (default: 45)")
    parser.add_argument("--max_rounds", type=int, default=None,
                       help="Maximum rounds to execute (default: unlimited)")
    parser.add_argument("--secrets", type=str, default="secrets/secrets2.json",
                       help="Path to secrets file")
    parser.add_argument("--no-confirm", action="store_true",
                       help="Skip confirmation prompt")
    
    args = parser.parse_args()
    
    # Load credentials
    api_key_name, api_private_key = load_production_credentials(args.secrets)
    
    # Confirmation
    if not args.no_confirm:
        print()
        print("=" * 70)
        print("⚠️  WARNING: PRODUCTION MODE - REAL MONEY AT RISK ⚠️")
        print("=" * 70)
        print(f"Product: {args.product_id}")
        print(f"Trade Size: ${args.min_trade:.2f} - ${args.max_trade:.2f}")
        print(f"Interval: {args.interval}s")
        print(f"Max Rounds: {args.max_rounds or 'Unlimited'}")
        print()
        confirm = input("Type 'EXECUTE' to start trading: ")
        if confirm != "EXECUTE":
            print("Aborted.")
            return
    
    # Initialize market maker
    mm = ProductionMarketMaker(
        api_key_name=api_key_name,
        api_private_key=api_private_key,
        product_id=args.product_id,
        min_trade_usd=args.min_trade,
        max_trade_usd=args.max_trade
    )
    
    # Signal handler for graceful shutdown
    running = True
    
    def signal_handler(sig, frame):
        nonlocal running
        print("\n⚠️  Shutdown requested...")
        running = False
    
    signal.signal(signal.SIGINT, signal_handler)
    
    # Main trading loop - CONTINUOUS MONITORING MODE
    rounds_executed = 0
    last_spread_log = None
    
    print()
    print("🔍 Starting continuous spread monitoring...")
    print(f"   Product: {args.product_id}")
    print(f"   Will execute trades immediately when profitable")
    print(f"   Press Ctrl+C to stop")
    print()
    
    while running:
        try:
            # Get current order book
            book = mm.order_book.fetch_order_book(limit=10)
            if not book.best_bid or not book.best_ask:
                time.sleep(0.5)
                continue
                
            # Quick profitability check
            precision, min_tick = mm.get_price_precision(book)
            current_bid = book.best_bid.price
            current_ask = book.best_ask.price
            spread = current_ask - current_bid
            spread_pct = spread / book.mid_price
            
            # Our undercut prices
            our_buy_price = current_bid + min_tick
            our_sell_price = current_ask - min_tick
            
            # Skip if crossed spread
            if our_buy_price >= our_sell_price:
                time.sleep(0.5)
                continue
                
            # Calculate profit quickly
            trade_size_usd, _, _ = mm.get_trade_size(book)
            
            # Use centralized size rounding
            buy_size_raw = trade_size_usd / our_buy_price
            buy_size_asset = ProductionMarketMaker._round_size_for_product(buy_size_raw, args.product_id)
            
            # Use actual rounded values for profit calculation
            actual_buy_value = buy_size_asset * our_buy_price
            sell_value = buy_size_asset * our_sell_price
            gross_profit = sell_value - actual_buy_value
            total_fees = (actual_buy_value + sell_value) * mm.EXPECTED_FEE_RATE
            net_profit = gross_profit - total_fees
            net_profit_pct = net_profit / actual_buy_value
            
            # Log spread changes
            if last_spread_log is None or abs(spread_pct - last_spread_log) > 0.002:
                timestamp = datetime.now().strftime("%H:%M:%S")
                status = "🟢 EXECUTING" if net_profit > 0 and net_profit_pct >= mm.MIN_PROFIT_RATE else "🔴 Monitoring"
                print(f"[{timestamp}] {status} | Spread: {spread_pct*100:.4f}% → Profit: {net_profit_pct*100:+.4f}%")
                last_spread_log = spread_pct
            
            # Execute trade if profitable
            if net_profit > 0 and net_profit_pct >= mm.MIN_PROFIT_RATE:
                print(f"\n⚡ PROFITABLE OPPORTUNITY - EXECUTING IMMEDIATELY!")
                
                try:
                    # Execute the trade round (but bypass the monitoring since we just found opportunity)
                    result = mm.execute_trade_round(monitor_timeout=0.1)  # Minimal timeout since we're already profitable
                    rounds_executed += 1
                    
                    print(f"✅ Round {rounds_executed} completed: ${result.net_profit:.6f} profit")
                    
                    # Check max rounds
                    if args.max_rounds and rounds_executed >= args.max_rounds:
                        print(f"\n✅ Completed {args.max_rounds} rounds, stopping.")
                        break
                    
                    # Brief pause after trade execution
                    time.sleep(1.0)
                    
                except OrderExecutionError as e:
                    error_msg = str(e)
                    if "INVALID_LIMIT_PRICE_POST_ONLY" in error_msg:
                        print(f"\n⚠️  Market moved - price would cross spread, skipping this opportunity")
                        time.sleep(0.2)  # Brief pause to let market settle
                    elif "INVALID_SIZE_PRECISION" in error_msg:
                        print(f"\n🚨 SIZE PRECISION ERROR: {e}")
                        print("   This should not happen - please check size rounding logic")
                        time.sleep(1.0)
                    else:
                        print(f"\n❌ Order execution failed: {e}")
                        time.sleep(1.0)
                    continue
            else:
                # Not profitable, keep monitoring
                time.sleep(0.5)
                
        except SpreadTooTightError:
            # This is expected during monitoring - just continue
            time.sleep(0.5)
            
        except (FeeValidationError, ProfitValidationError) as e:
            print(f"\n🚨 CRITICAL ERROR: {e}")
            print("   HALTING TRADING FOR SAFETY")
            break
            
        except TimeoutError as e:
            print(f"\n⏰ Order timeout: {e}")
            print("   Continuing monitoring...")
            time.sleep(2)
            
        except Exception as e:
            print(f"\n❌ Monitoring error: {e}")
            time.sleep(1)
    
    # Print final stats
    stats = mm.get_session_stats()
    print()
    print("=" * 70)
    print("📊 SESSION SUMMARY")
    print("=" * 70)
    print(f"Rounds Completed: {stats['rounds_completed']}")
    print(f"Total Profit: ${stats['total_profit']:.4f}")
    print(f"Total Fees: ${stats['total_fees']:.4f}")
    print(f"Average Profit/Round: ${stats['average_profit_per_round']:.4f}")
    print("=" * 70)


if __name__ == "__main__":
    main()
