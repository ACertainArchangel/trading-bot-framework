from typing import Dict, Tuple
from .Interface import Interface
import requests
import time
import hmac
import hashlib
import base64
from datetime import datetime

class CoinbaseInterface(Interface):
    """
    Live trading interface for Coinbase Exchange API.
    Requires API credentials to be set after initialization.
    """
    
    def __init__(self, api_key: str = None, api_secret: str = None, api_passphrase: str = None):
        super().__init__()
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_passphrase = api_passphrase
        self.base_url = "https://api.exchange.coinbase.com"
        self.connected = False

    def __str__(self):
        return f"CoinbaseInterface(connected={self.connected})"

    def _generate_signature(self, timestamp: str, method: str, request_path: str, body: str = ''):
        """Generate authentication signature for Coinbase API"""
        message = timestamp + method + request_path + body
        hmac_key = base64.b64decode(self.api_secret)
        signature = hmac.new(hmac_key, message.encode(), hashlib.sha256)
        return base64.b64encode(signature.digest()).decode()

    def _make_request(self, method: str, endpoint: str, body: dict = None):
        """Make authenticated request to Coinbase API"""
        timestamp = str(time.time())
        request_path = endpoint
        body_str = '' if body is None else str(body)
        
        signature = self._generate_signature(timestamp, method, request_path, body_str)
        
        headers = {
            'CB-ACCESS-KEY': self.api_key,
            'CB-ACCESS-SIGN': signature,
            'CB-ACCESS-TIMESTAMP': timestamp,
            'CB-ACCESS-PASSPHRASE': self.api_passphrase,
            'Content-Type': 'application/json'
        }
        
        url = self.base_url + endpoint
        
        if method == 'GET':
            response = requests.get(url, headers=headers)
        elif method == 'POST':
            response = requests.post(url, headers=headers, json=body)
        
        response.raise_for_status()
        return response.json()

    def connect_to_exchange(self):
        """Test connection by fetching account info"""
        if not all([self.api_key, self.api_secret, self.api_passphrase]):
            raise ValueError("API credentials not set")
        
        try:
            accounts = self._make_request('GET', '/accounts')
            self.connected = True
            return accounts
        except Exception as e:
            raise ConnectionError(f"Failed to connect to Coinbase: {e}")

    def assert_exchange_sync(self, bot):
        """Verify bot's balance matches exchange"""
        currency_balance = self.fetch_exchange_balance_currency()
        asset_balance = self.fetch_exchange_balance_asset()
        
        currency_code = bot.pair.split('-')[1]
        asset_code = bot.pair.split('-')[0]
        
        if abs(bot.currency - currency_balance['available']) > 0.00000001:
            raise AssertionError(f"Currency mismatch: Bot={bot.currency}, Exchange={currency_balance['available']}")
        
        if abs(bot.asset - asset_balance['available']) > 0.00000001:
            raise AssertionError(f"Asset mismatch: Bot={bot.asset}, Exchange={asset_balance['available']}")

    def fetch_exchange_balance_currency(self) -> Dict[str, float]:
        """Fetch currency (quote) balance from exchange"""
        currency_code = self.bot.pair.split('-')[1]
        accounts = self._make_request('GET', '/accounts')
        
        for account in accounts:
            if account['currency'] == currency_code:
                return {
                    "balance": float(account['balance']),
                    "available": float(account['available']),
                    "hold": float(account['hold'])
                }
        
        raise ValueError(f"No account found for {currency_code}")

    def fetch_exchange_balance_asset(self) -> Dict[str, float]:
        """Fetch asset (base) balance from exchange"""
        asset_code = self.bot.pair.split('-')[0]
        accounts = self._make_request('GET', '/accounts')
        
        for account in accounts:
            if account['currency'] == asset_code:
                return {
                    "balance": float(account['balance']),
                    "available": float(account['available']),
                    "hold": float(account['hold'])
                }
        
        raise ValueError(f"No account found for {asset_code}")

    def execute_buy(self, price: float, fee_rate: float, currency: float) -> Tuple[float, float]:
        """
        Execute market buy order on Coinbase.
        Returns (amount_received, amount_spent)
        """
        # Place market order to buy with all available currency
        order_data = {
            "type": "market",
            "side": "buy",
            "product_id": self.bot.pair,
            "funds": str(currency)
        }
        
        order_result = self._make_request('POST', '/orders', order_data)
        order_id = order_result['id']
        
        # Wait for order to fill
        time.sleep(1)
        filled_order = self._make_request('GET', f'/orders/{order_id}')
        
        amount_received = float(filled_order['filled_size'])
        amount_spent = float(filled_order['funds'])
        
        return (amount_received, amount_spent)

    def execute_sell(self, price: float, fee_rate: float, asset: float) -> Tuple[float, float]:
        """
        Execute market sell order on Coinbase.
        Returns (amount_received, amount_spent)
        """
        # Place market order to sell all available asset
        order_data = {
            "type": "market",
            "side": "sell",
            "product_id": self.bot.pair,
            "size": str(asset)
        }
        
        order_result = self._make_request('POST', '/orders', order_data)
        order_id = order_result['id']
        
        # Wait for order to fill
        time.sleep(1)
        filled_order = self._make_request('GET', f'/orders/{order_id}')
        
        amount_spent = float(filled_order['filled_size'])
        amount_received = float(filled_order['funds'])
        
        return (amount_received, amount_spent)