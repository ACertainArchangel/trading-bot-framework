"""
CoinbaseInterface - Live trading on Coinbase Advanced Trade.

This interface connects to the real Coinbase exchange for live trading.
USE WITH CAUTION - real money is involved!
"""

from typing import Tuple, Optional, List, Dict
import time
from .base import TradingInterface, Allocation, DEFAULT_ALLOCATION


class CoinbaseInterface(TradingInterface):
    """
    Live trading interface for Coinbase Advanced Trade API.
    
    ⚠️  WARNING: This uses real money! Test with paper trading first.
    
    Note: Coinbase spot trading only supports allocation values between 0 and 1.
    No leverage or shorting available on spot markets.
    
    Example:
        interface = CoinbaseInterface(
            api_key="your-key-name",
            api_secret="-----BEGIN EC PRIVATE KEY-----...",
            product_id="BTC-USD"
        )
        interface.connect()
    """
    
    BASE_URL = "https://api.coinbase.com"
    
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        product_id: str = "BTC-USD",
        allocation: Optional[Allocation] = None
    ):
        """
        Initialize Coinbase interface.
        
        Args:
            api_key: Coinbase API key name
            api_secret: Coinbase EC private key (PEM format)
            product_id: Trading pair (e.g., "BTC-USD")
            allocation: Position sizing (must be 0-1 for spot trading)
        """
        super().__init__(allocation=allocation)
        
        self.api_key = api_key
        self.api_secret = api_secret
        self.product_id = product_id
        self.connected = False
        
        # Parse currency/asset from product_id
        parts = product_id.split('-')
        self.asset_code = parts[0]  # e.g., 'BTC'
        self.currency_code = parts[1]  # e.g., 'USD'
        
        self.trade_log: List[Dict] = []
    
    def _validate_allocation(self, alloc: Allocation):
        """Validate allocation for Coinbase spot trading (0-1 range only)."""
        super()._validate_allocation(alloc)
        
        if alloc['long'] > 1:
            raise ValueError(
                f"Coinbase spot trading does not support leverage. "
                f"Long allocation must be <= 1, got {alloc['long']}"
            )
        if alloc['short'] < 0:
            raise ValueError(
                f"Coinbase spot trading does not support shorting. "
                f"Short allocation must be 0, got {alloc['short']}"
            )
    
    def _generate_jwt(self, method: str, path: str) -> str:
        """Generate JWT token for API authentication."""
        try:
            from coinbase import jwt_generator
            jwt_uri = jwt_generator.format_jwt_uri(method, path)
            return jwt_generator.build_rest_jwt(jwt_uri, self.api_key, self.api_secret)
        except ImportError:
            raise ImportError(
                "Coinbase SDK required for live trading. "
                "Install with: pip install coinbase-advanced-py"
            )
    
    def _request(self, method: str, endpoint: str, body: dict = None) -> dict:
        """Make authenticated API request."""
        import requests
        
        token = self._generate_jwt(method, endpoint)
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        url = self.BASE_URL + endpoint
        
        if method == 'GET':
            response = requests.get(url, headers=headers, timeout=30)
        elif method == 'POST':
            response = requests.post(url, headers=headers, json=body, timeout=30)
        else:
            raise ValueError(f"Unsupported method: {method}")
        
        response.raise_for_status()
        return response.json()
    
    def connect(self) -> bool:
        """
        Connect to Coinbase and sync balances.
        
        Returns:
            True if connected successfully
        """
        try:
            # Test connection and fetch accounts
            result = self._request('GET', '/api/v3/brokerage/accounts')
            
            # Update balances
            self.currency = self._fetch_balance(self.currency_code)
            self.asset = self._fetch_balance(self.asset_code)
            
            # Determine position
            if self.asset > self.DUST_ASSET:
                self.position = "long"
            else:
                self.position = "short"
            
            self.connected = True
            return True
            
        except Exception as e:
            raise ConnectionError(f"Failed to connect to Coinbase: {e}")
    
    def _fetch_balance(self, currency: str) -> float:
        """Fetch balance for a specific currency."""
        result = self._request('GET', '/api/v3/brokerage/accounts')
        
        for account in result.get('accounts', []):
            if account['currency'] == currency:
                available = float(account['available_balance']['value'])
                hold = float(account.get('hold', {}).get('value', 0))
                return available + hold
        
        return 0.0
    
    def execute_buy(
        self,
        price: float,
        fee_rate: float,
        amount: float
    ) -> Tuple[float, float]:
        """
        Execute a buy order on Coinbase.
        
        Places a limit order slightly below market price to ensure maker fee.
        
        Args:
            price: Current market price
            fee_rate: Expected fee rate
            amount: USD to spend
        
        Returns:
            (asset_received, currency_spent)
        """
        if not self.connected:
            raise RuntimeError("Not connected. Call connect() first.")
        
        # Calculate limit price (0.035% below market for maker)
        limit_price = price * 0.99965
        asset_size = amount / limit_price
        
        order = {
            "client_order_id": f"buy_{int(time.time())}",
            "product_id": self.product_id,
            "side": "BUY",
            "order_configuration": {
                "limit_limit_gtc": {
                    "base_size": f"{asset_size:.8f}",
                    "limit_price": f"{limit_price:.2f}",
                    "post_only": True
                }
            }
        }
        
        result = self._request('POST', '/api/v3/brokerage/orders', order)
        
        if 'error_response' in result:
            error = result['error_response']
            raise RuntimeError(f"Buy failed: {error}")
        
        order_id = result['success_response']['order_id']
        
        # Wait for fill
        filled = self._wait_for_fill(order_id)
        
        # Update local state
        self.currency = self._fetch_balance(self.currency_code)
        self.asset = self._fetch_balance(self.asset_code)
        self.position = "long"
        
        return (filled['filled_size'], filled['filled_value'])
    
    def execute_sell(
        self,
        price: float,
        fee_rate: float,
        amount: float
    ) -> Tuple[float, float]:
        """
        Execute a sell order on Coinbase.
        
        Args:
            price: Current market price
            fee_rate: Expected fee rate
            amount: Asset to sell
        
        Returns:
            (currency_received, asset_spent)
        """
        if not self.connected:
            raise RuntimeError("Not connected. Call connect() first.")
        
        # Calculate limit price (0.035% above market for maker)
        limit_price = price * 1.00035
        
        order = {
            "client_order_id": f"sell_{int(time.time())}",
            "product_id": self.product_id,
            "side": "SELL",
            "order_configuration": {
                "limit_limit_gtc": {
                    "base_size": f"{amount:.8f}",
                    "limit_price": f"{limit_price:.2f}",
                    "post_only": True
                }
            }
        }
        
        result = self._request('POST', '/api/v3/brokerage/orders', order)
        
        if 'error_response' in result:
            error = result['error_response']
            raise RuntimeError(f"Sell failed: {error}")
        
        order_id = result['success_response']['order_id']
        
        # Wait for fill
        filled = self._wait_for_fill(order_id)
        
        # Update local state
        self.currency = self._fetch_balance(self.currency_code)
        self.asset = self._fetch_balance(self.asset_code)
        self.position = "short"
        
        return (filled['filled_value'], filled['filled_size'])
    
    def _wait_for_fill(
        self,
        order_id: str,
        timeout: int = 300,
        poll_interval: int = 5
    ) -> dict:
        """Wait for an order to fill."""
        elapsed = 0
        
        while elapsed < timeout:
            order = self._request('GET', f'/api/v3/brokerage/orders/historical/{order_id}')
            
            status = order.get('order', {}).get('status', '')
            
            if status == 'FILLED':
                return {
                    'filled_size': float(order['order'].get('filled_size', 0)),
                    'filled_value': float(order['order'].get('filled_value', 0))
                }
            
            if status in ('CANCELLED', 'EXPIRED', 'FAILED'):
                raise RuntimeError(f"Order {status}: {order}")
            
            time.sleep(poll_interval)
            elapsed += poll_interval
        
        raise TimeoutError(f"Order {order_id} did not fill within {timeout}s")
    
    def get_balance(self, asset: str) -> float:
        """Get balance of specific asset."""
        return self._fetch_balance(asset)
    
    def get_current_price(self) -> float:
        """Get current market price."""
        result = self._request('GET', f'/api/v3/brokerage/products/{self.product_id}')
        return float(result['price'])
    
    def get_fees_paid(self) -> float:
        """Get total fees paid in USD."""
        return sum(t.get('fee_paid', 0) for t in self.trade_log)
