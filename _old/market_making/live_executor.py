"""
Live Trading Executor for Market Maker

Executes real trades on Coinbase using the Advanced Trade API.
Uses secrets2.json for credentials and handles simultaneous order execution.
"""

import json
import os
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Tuple, Callable

from .market_maker import (
    MarketMaker,
    Order,
    OrderSide,
    OrderStatus,
    TradeRound,
    UnexpectedFeeError,
    UnprofitableTradeError
)
from .order_book import OrderBook


@dataclass 
class LiveOrderResult:
    """Result of a live order execution"""
    order_id: str
    status: str
    filled_size: float
    filled_value: float
    average_price: float
    fees: float
    fee_rate: float
    raw_response: Dict


class CoinbaseExecutor:
    """
    Executes orders on Coinbase Advanced Trade API.
    
    Handles:
    - Limit order placement (maker orders for lower fees)
    - Order status monitoring
    - Fill validation
    - Fee validation
    """
    
    def __init__(
        self,
        api_key_name: str,
        api_private_key: str,
        product_id: str = "ZEC-USD",
        logger: Optional[Callable[[str], None]] = None
    ):
        """
        Initialize executor with Coinbase credentials.
        
        Args:
            api_key_name: Coinbase API key name
            api_private_key: Coinbase API private key (PEM format)
            product_id: Trading pair
            logger: Logging callback
        """
        self.api_key_name = api_key_name
        self.api_private_key = api_private_key
        self.product_id = product_id
        self.base_url = "https://api.coinbase.com"
        self._log = logger or print
        
        # Import here to avoid dependency issues
        import requests
        self.requests = requests
    
    def _generate_jwt_token(self, method: str, request_path: str) -> str:
        """Generate JWT token for API authentication."""
        from coinbase import jwt_generator
        
        jwt_uri = jwt_generator.format_jwt_uri(method, request_path)
        token = jwt_generator.build_rest_jwt(jwt_uri, self.api_key_name, self.api_private_key)
        return token
    
    def _make_request(self, method: str, endpoint: str, body: dict = None) -> Dict:
        """Make authenticated request to Coinbase API."""
        token = self._generate_jwt_token(method, endpoint)
        
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        url = self.base_url + endpoint
        
        if method == 'GET':
            response = self.requests.get(url, headers=headers)
        elif method == 'POST':
            response = self.requests.post(url, headers=headers, json=body)
        
        response.raise_for_status()
        return response.json()
    
    def get_account_balance(self, currency: str) -> float:
        """Get balance for a specific currency."""
        result = self._make_request('GET', '/api/v3/brokerage/accounts')
        
        for account in result.get('accounts', []):
            if account['currency'] == currency:
                available = float(account['available_balance']['value'])
                return available
        
        raise ValueError(f"No account found for {currency}")
    
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
            size: Amount of base currency
            price: Limit price
            post_only: If True, ensures maker order (rejects if would cross)
        
        Returns:
            Order ID
        """
        order_data = {
            "client_order_id": f"{side.lower()}_{int(time.time())}_{int(size*1000)}",
            "product_id": self.product_id,
            "side": side.upper(),
            "order_configuration": {
                "limit_limit_gtc": {
                    "base_size": f"{size:.8f}",
                    "limit_price": f"{price:.4f}",
                    "post_only": post_only
                }
            }
        }
        
        result = self._make_request('POST', '/api/v3/brokerage/orders', order_data)
        
        if 'error_response' in result:
            error = result['error_response']
            raise RuntimeError(
                f"Order failed: {error.get('error', 'Unknown')} - "
                f"{error.get('message', 'No message')} - "
                f"{error.get('error_details', '')}"
            )
        
        if 'success_response' not in result:
            raise RuntimeError(f"Unexpected order response: {result}")
        
        order_id = result['success_response']['order_id']
        self._log(f"📤 Placed {side} order: {order_id}")
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
        poll_interval: int = 5
    ) -> LiveOrderResult:
        """
        Wait for an order to fill.
        
        Args:
            order_id: Order to monitor
            timeout_seconds: Maximum wait time
            poll_interval: Seconds between status checks
        
        Returns:
            LiveOrderResult with fill details
            
        Raises:
            TimeoutError: If order doesn't fill in time
            RuntimeError: If order fails
        """
        elapsed = 0
        
        while elapsed < timeout_seconds:
            order = self.get_order_status(order_id)
            status = order.get('status', 'UNKNOWN')
            
            if status == 'FILLED':
                filled_size = float(order.get('filled_size', 0))
                avg_price = float(order.get('average_filled_price', 0))
                total_fees = float(order.get('total_fees', 0))
                filled_value = filled_size * avg_price
                fee_rate = total_fees / filled_value if filled_value > 0 else 0
                
                return LiveOrderResult(
                    order_id=order_id,
                    status=status,
                    filled_size=filled_size,
                    filled_value=filled_value,
                    average_price=avg_price,
                    fees=total_fees,
                    fee_rate=fee_rate,
                    raw_response=order
                )
            
            if status in ['CANCELLED', 'EXPIRED', 'FAILED']:
                raise RuntimeError(f"Order {order_id} failed with status: {status}")
            
            time.sleep(poll_interval)
            elapsed += poll_interval
        
        # Timeout - cancel the order
        self.cancel_order(order_id)
        raise TimeoutError(f"Order {order_id} did not fill within {timeout_seconds}s")


class LiveMarketMaker(MarketMaker):
    """
    Live trading market maker that executes real orders on Coinbase.
    
    Extends MarketMaker with:
    - Coinbase API integration
    - Simultaneous order placement
    - Partial fill handling
    - Price drift monitoring
    """
    
    def __init__(
        self,
        api_key_name: str,
        api_private_key: str,
        product_id: str = "ZEC-USD",
        fee_rate: float = 0.00025,
        fee_tolerance: float = 0.0001,
        min_profit_rate: float = 0.0001,
        trade_size_usd: float = 100.0,
        max_position_usd: float = 1000.0,
        order_timeout: int = 300,
        logger: Optional[Callable[[str], None]] = None
    ):
        """
        Initialize live market maker.
        
        Args:
            api_key_name: Coinbase API key name
            api_private_key: Coinbase API private key
            product_id: Trading pair
            fee_rate: Expected maker fee rate
            fee_tolerance: Maximum fee variance
            min_profit_rate: Minimum profit per round
            trade_size_usd: USD per trade
            max_position_usd: Maximum position
            order_timeout: Seconds to wait for fills
            logger: Logging callback
        """
        super().__init__(
            product_id=product_id,
            fee_rate=fee_rate,
            fee_tolerance=fee_tolerance,
            min_profit_rate=min_profit_rate,
            trade_size_usd=trade_size_usd,
            max_position_usd=max_position_usd,
            logger=logger
        )
        
        self.order_timeout = order_timeout
        
        # Initialize executor
        self.executor = CoinbaseExecutor(
            api_key_name=api_key_name,
            api_private_key=api_private_key,
            product_id=product_id,
            logger=logger
        )
        
        self._log("🔐 Live trading enabled - REAL MONEY AT RISK!")
    
    def sync_balances_from_exchange(self):
        """Fetch and sync balances from Coinbase."""
        base_currency = self.product_id.split('-')[0]  # ZEC
        quote_currency = self.product_id.split('-')[1]  # USD
        
        usd_balance = self.executor.get_account_balance(quote_currency)
        asset_balance = self.executor.get_account_balance(base_currency)
        
        self.set_balances(usd=usd_balance, asset=asset_balance)
    
    def execute_live_round(self, analysis: Dict) -> bool:
        """
        Execute a live trading round.
        
        Places buy order first, waits for fill, then places sell order.
        This is safer than simultaneous orders for low-liquidity pairs.
        
        Args:
            analysis: Profitability analysis
        
        Returns:
            True if round completed successfully
        """
        # Start trade round (creates Order objects)
        buy_order, sell_order = self.start_trade_round(analysis)
        
        try:
            # Place buy order
            self._log("📤 Placing BUY order...")
            buy_order_id = self.executor.place_limit_order(
                side="BUY",
                size=buy_order.size,
                price=buy_order.price,
                post_only=True
            )
            buy_order.id = buy_order_id
            buy_order.status = OrderStatus.OPEN
            
            # Wait for buy to fill
            self._log("⏳ Waiting for BUY to fill...")
            buy_result = self.executor.wait_for_fill(buy_order_id, self.order_timeout)
            
            # Validate fee
            self.validate_fee_rate(buy_result.fee_rate)
            
            # Update buy order
            buy_order.filled_size = buy_result.filled_size
            buy_order.filled_value = buy_result.filled_value
            buy_order.fees = buy_result.fees
            buy_order.status = OrderStatus.FILLED
            buy_order.filled_at = datetime.utcnow()
            
            self._log(f"✅ BUY filled: {buy_result.filled_size:.4f} @ ${buy_result.average_price:.4f}")
            
            # Update balances
            self.usd_balance -= (buy_result.filled_value + buy_result.fees)
            self.asset_balance += buy_result.filled_size
            
            # Now place sell order for what we bought
            self._log("📤 Placing SELL order...")
            
            # Re-fetch order book for current ask price
            book = self.order_book.fetch_order_book(limit=10)
            sell_price = book.best_ask.price if book.best_ask else sell_order.price
            
            sell_order_id = self.executor.place_limit_order(
                side="SELL",
                size=buy_result.filled_size,  # Sell what we bought
                price=sell_price,
                post_only=True
            )
            sell_order.id = sell_order_id
            sell_order.price = sell_price
            sell_order.size = buy_result.filled_size
            sell_order.status = OrderStatus.OPEN
            
            # Wait for sell to fill
            self._log("⏳ Waiting for SELL to fill...")
            sell_result = self.executor.wait_for_fill(sell_order_id, self.order_timeout)
            
            # Validate fee
            self.validate_fee_rate(sell_result.fee_rate)
            
            # Update sell order
            sell_order.filled_size = sell_result.filled_size
            sell_order.filled_value = sell_result.filled_value
            sell_order.fees = sell_result.fees
            sell_order.status = OrderStatus.FILLED
            sell_order.filled_at = datetime.utcnow()
            
            self._log(f"✅ SELL filled: {sell_result.filled_size:.4f} @ ${sell_result.average_price:.4f}")
            
            # Update balances
            self.asset_balance -= sell_result.filled_size
            self.usd_balance += (sell_result.filled_value - sell_result.fees)
            
            # Complete the round
            self.complete_round()
            
            return True
            
        except TimeoutError as e:
            self._log(f"⏰ Timeout: {e}")
            # If buy filled but sell timed out, we're holding inventory
            if buy_order.status == OrderStatus.FILLED:
                self._log("⚠️  Holding inventory - sell order timed out")
            return False
            
        except UnexpectedFeeError as e:
            self._log(f"❌ Fee validation failed: {e}")
            raise
            
        except Exception as e:
            self._log(f"❌ Trade error: {e}")
            import traceback
            traceback.print_exc()
            return False


def load_credentials(secrets_file: str = "secrets/secrets2.json") -> Tuple[str, str]:
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
            f"Please create it with your Coinbase API credentials:\n"
            f'{{\n'
            f'  "coinbase_api_key_name": "your_key_name",\n'
            f'  "coinbase_api_private_key": "-----BEGIN EC PRIVATE KEY-----\\n...\\n-----END EC PRIVATE KEY-----"\n'
            f'}}'
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
    
    return api_key_name, api_private_key
