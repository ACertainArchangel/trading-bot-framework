from typing import Dict, Tuple
from .Interface import Interface
import requests
import time
import hmac
import hashlib
import json
from datetime import datetime

class CoinbaseAdvancedTradeInterface(Interface):
    """
    Live trading interface for Coinbase Advanced Trade API.
    Uses the new API format with name (key name) and privateKey (EC private key).
    
    Note: This interface syncs FROM the exchange. Call connect_to_exchange()
    to fetch and populate currency, asset, and position attributes.
    """
    
    def __init__(self, api_key_name: str = None, api_private_key: str = None, pair: str = "BTC-USD"):
        super().__init__()
        self.api_key_name = api_key_name
        self.api_private_key = api_private_key
        self.pair = pair
        self.base_url = "https://api.coinbase.com"
        self.connected = False
        
        # These will be set by connect_to_exchange()
        self.currency = 0.0
        self.asset = 0.0
        self.position = "short"

    def __str__(self):
        return f"CoinbaseAdvancedTradeInterface(connected={self.connected})"

    def _generate_jwt_token(self, method: str, request_path: str):
        """Generate JWT token for Advanced Trade API authentication using official SDK"""
        from coinbase import jwt_generator
        
        # Use official Coinbase SDK to generate JWT
        jwt_uri = jwt_generator.format_jwt_uri(method, request_path)
        token = jwt_generator.build_rest_jwt(jwt_uri, self.api_key_name, self.api_private_key)
        return token

    def _make_request(self, method: str, endpoint: str, body: dict = None):
        """Make authenticated request to Coinbase Advanced Trade API"""
        request_path = endpoint
        token = self._generate_jwt_token(method, request_path)
        
        headers = {
            'Authorization': f'Bearer {token}',
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
        """
        Connect to exchange and fetch current balances.
        Populates currency, asset, and position attributes.
        """
        if not all([self.api_key_name, self.api_private_key]):
            raise ValueError("API credentials not set")
        
        try:
            result = self._make_request('GET', '/api/v3/brokerage/accounts')
            self.connected = True
            
            # Fetch and set balances
            self.currency = self.fetch_exchange_balance_currency()
            self.asset = self.fetch_exchange_balance_asset()
            
            # Determine position based on what we're holding
            if self.asset > 0.0001:  # Has meaningful crypto (> dust)
                self.position = "long"
            else:
                self.position = "short"
            
            return result
        except Exception as e:
            raise ConnectionError(f"Failed to connect to Coinbase: {e}")

    def assert_exchange_sync(self, bot):
        """Verify bot's balance matches exchange (allowing for dust/rounding errors)"""
        currency_balance = self.fetch_exchange_balance_currency()
        asset_balance = self.fetch_exchange_balance_asset()
        
        currency_code = bot.pair.split('-')[1]
        asset_code = bot.pair.split('-')[0]
        
        # Allow for dust and rounding errors
    def fetch_exchange_balance_currency(self) -> float:
        """Fetch currency (quote) balance from exchange (USD only, not USDC)"""
        currency_code = self.pair.split('-')[1]  # 'USD' from 'BTC-USD'
        result = self._make_request('GET', '/api/v3/brokerage/accounts')
        
        for account in result.get('accounts', []):
            # Exact match only - USD not USDC
            if account['currency'] == currency_code:
                available = float(account['available_balance']['value'])
                hold = float(account['hold']['value']) if 'hold' in account else 0.0
                balance = available + hold
        if asset_diff > asset_tolerance:
            raise AssertionError(f"Asset mismatch: Bot={bot.asset}, Exchange={asset_balance}, Diff={asset_diff}")

    def fetch_exchange_balance_currency(self) -> float:
        """Fetch currency (quote) balance from exchange (USD only, not USDC)"""
        currency_code = self.pair.split('-')[1]  # 'USD' from 'BTC-USD'
        result = self._make_request('GET', '/api/v3/brokerage/accounts')
        
        for account in result.get('accounts', []):
            # Exact match only - USD not USDC
            if account['currency'] == currency_code:
                available = float(account['available_balance']['value'])
                hold = float(account['hold']['value']) if 'hold' in account else 0.0
                balance = available + hold
                return balance  # Return float, not dict
        
        raise ValueError(f"No account found for {currency_code} (looking for exact match)")

    def fetch_exchange_balance_asset(self) -> float:
        """Fetch asset (base) balance from exchange"""
        asset_code = self.pair.split('-')[0]
        result = self._make_request('GET', '/api/v3/brokerage/accounts')
        
        for account in result.get('accounts', []):
            if account['currency'] == asset_code:
                available = float(account['available_balance']['value'])
                hold = float(account['hold']['value']) if 'hold' in account else 0.0
                balance = available + hold
                return balance  # Return float, not dict
        
        raise ValueError(f"No account found for {asset_code}")

    def execute_buy(self, price: float, fee_rate: float, currency: float, spread_pct: float = 0.035) -> Tuple[float, float]:
        """
        Execute LIMIT buy order (maker) on Coinbase Advanced Trade.
        Validates 0.025% maker fee is applied.
        
        Args:
            price: Current market price
            fee_rate: Expected fee rate (0.00025 for 0.025% maker)
            currency: Amount of USD to spend
            spread_pct: Percentage below market to place limit order (default 0.02 = 0.02%)
        
        Returns (amount_received, amount_spent)
        """
        # Validate expected fee rate is 0.025% (0.00025)
        expected_fee_rate = 0.00025
        if abs(fee_rate - expected_fee_rate) > 0.000001:
            raise ValueError(f"Fee rate mismatch! Expected {expected_fee_rate} (0.025% maker), got {fee_rate}")
        
        # Calculate limit price using configurable spread
        spread_multiplier = 1 - (spread_pct / 100)
        limit_price = price * spread_multiplier
        
        # Calculate how much BTC we can buy with available USD
        btc_size = currency / limit_price
        
        # Place LIMIT order (maker - gets 0.025% fee)
        order_data = {
            "client_order_id": f"buy_{int(time.time())}",
            "product_id": self.pair,
            "side": "BUY",
            "order_configuration": {
                "limit_limit_gtc": {
                    "base_size": f"{btc_size:.8f}",
                    "limit_price": f"{limit_price:.2f}",
                    "post_only": True  # Ensures maker order (rejects if would match immediately)
                }
            }
        }
        
        order_result = self._make_request('POST', '/api/v3/brokerage/orders', order_data)
        
        # Check for errors in response
        if 'error_response' in order_result:
            error = order_result['error_response']
            raise RuntimeError(f"Buy order failed: {error.get('error', 'Unknown error')} - {error.get('message', 'No message')} - {error.get('error_details', '')}")
        
        if 'success_response' not in order_result:
            raise RuntimeError(f"Unexpected buy order response: {order_result}")
        
        order_id = order_result['success_response']['order_id']
        print(f"✅ Buy order placed: {order_id}")
        
        # Wait for order to fill (may take time as limit order)
        max_wait = 300  # 5 minutes max
        wait_time = 0
        order_filled = False
        while wait_time < max_wait:
            time.sleep(5)
            wait_time += 5
            filled_order = self._make_request('GET', f'/api/v3/brokerage/orders/historical/{order_id}')
            order = filled_order.get('order', {})
            
            if order.get('status') == 'FILLED':
                order_filled = True
                break
            elif order.get('status') in ['CANCELLED', 'EXPIRED', 'FAILED']:
                raise RuntimeError(f"Order {order_id} failed with status: {order.get('status')}")
        
        # Check if order actually filled
        if not order_filled:
            # Cancel the order since it didn't fill in time
            try:
                cancel_result = self._make_request('POST', '/api/v3/brokerage/orders/batch_cancel', 
                                                   {"order_ids": [order_id]})
                print(f"⚠️  Cancelled unfilled buy order {order_id}")
            except Exception as e:
                print(f"⚠️  Failed to cancel order {order_id}: {e}")
            raise RuntimeError(f"Buy order {order_id} did not fill within {max_wait} seconds. Status: {order.get('status', 'UNKNOWN')}. Order cancelled.")
        
        # Validate maker fee was applied
        # Debug: print order details to understand structure
        print(f"📊 Order details: status={order.get('status')}, filled_size={order.get('filled_size')}, total_fees={order.get('total_fees')}")
        
        total_fees = float(order.get('total_fees', 0))
        filled_size = float(order.get('filled_size', 0))
        avg_filled_price = float(order.get('average_filled_price', 0))
        
        if filled_size > 0 and avg_filled_price > 0:
            filled_value = filled_size * avg_filled_price
            actual_fee_rate = total_fees / filled_value if filled_value > 0 else 0
            
            print(f"💰 Fee validation: fees=${total_fees:.2f}, value=${filled_value:.2f}, rate={actual_fee_rate*100:.4f}%")
            
            if total_fees > 0 and abs(actual_fee_rate - expected_fee_rate) > 0.0001:  # Allow 0.01% tolerance
                raise RuntimeError(f"Fee validation failed! Expected 0.025% maker fee, got {actual_fee_rate*100:.4f}%")
        else:
            print(f"⚠️  Cannot validate fees - insufficient order data")
        
        amount_received = filled_size
        amount_spent = filled_size * avg_filled_price
        
        return (amount_received, amount_spent)

    def execute_sell(self, price: float, fee_rate: float, asset: float, spread_pct: float = 0.035) -> Tuple[float, float]:
        """
        Execute LIMIT sell order (maker) on Coinbase Advanced Trade.
        Validates 0.025% maker fee is applied.
        
        Args:
            price: Current market price
            fee_rate: Expected fee rate (0.00025 for 0.025% maker)
            asset: Amount of BTC to sell
            spread_pct: Percentage above market to place limit order (default 0.02 = 0.02%)
        
        Returns (amount_received, amount_spent)
        """
        # Validate expected fee rate is 0.025% (0.00025)
        expected_fee_rate = 0.00025
        if abs(fee_rate - expected_fee_rate) > 0.000001:
            raise ValueError(f"Fee rate mismatch! Expected {expected_fee_rate} (0.025% maker), got {fee_rate}")
        
        # Calculate limit price using configurable spread
        spread_multiplier = 1 + (spread_pct / 100)
        limit_price = price * spread_multiplier
        
        # Place LIMIT order (maker - gets 0.025% fee)
        order_data = {
            "client_order_id": f"sell_{int(time.time())}",
            "product_id": self.pair,
            "side": "SELL",
            "order_configuration": {
                "limit_limit_gtc": {
                    "base_size": f"{asset:.8f}",
                    "limit_price": f"{limit_price:.2f}",
                    "post_only": True  # Ensures maker order (rejects if would match immediately)
                }
            }
        }
        
        order_result = self._make_request('POST', '/api/v3/brokerage/orders', order_data)
        
        # Check for errors in response
        if 'error_response' in order_result:
            error = order_result['error_response']
            raise RuntimeError(f"Sell order failed: {error.get('error', 'Unknown error')} - {error.get('message', 'No message')} - {error.get('error_details', '')}")
        
        if 'success_response' not in order_result:
            raise RuntimeError(f"Unexpected sell order response: {order_result}")
        
        order_id = order_result['success_response']['order_id']
        print(f"✅ Sell order placed: {order_id}")
        
        # Wait for order to fill (may take time as limit order)
        max_wait = 300  # 5 minutes max
        wait_time = 0
        order_filled = False
        while wait_time < max_wait:
            time.sleep(5)
            wait_time += 5
            filled_order = self._make_request('GET', f'/api/v3/brokerage/orders/historical/{order_id}')
            order = filled_order.get('order', {})
            
            if order.get('status') == 'FILLED':
                order_filled = True
                break
            elif order.get('status') in ['CANCELLED', 'EXPIRED', 'FAILED']:
                raise RuntimeError(f"Order {order_id} failed with status: {order.get('status')}")
        
        # Check if order actually filled
        if not order_filled:
            # Cancel the order since it didn't fill in time
            try:
                cancel_result = self._make_request('POST', '/api/v3/brokerage/orders/batch_cancel', 
                                                   {"order_ids": [order_id]})
                print(f"⚠️  Cancelled unfilled sell order {order_id}")
            except Exception as e:
                print(f"⚠️  Failed to cancel order {order_id}: {e}")
            raise RuntimeError(f"Sell order {order_id} did not fill within {max_wait} seconds. Status: {order.get('status', 'UNKNOWN')}. Order cancelled.")
        
        # Validate maker fee was applied
        # Debug: print order details to understand structure
        print(f"📊 Order details: status={order.get('status')}, filled_size={order.get('filled_size')}, total_fees={order.get('total_fees')}")
        
        total_fees = float(order.get('total_fees', 0))
        filled_size = float(order.get('filled_size', 0))
        avg_filled_price = float(order.get('average_filled_price', 0))
        
        if filled_size > 0 and avg_filled_price > 0:
            filled_value = filled_size * avg_filled_price
            actual_fee_rate = total_fees / filled_value if filled_value > 0 else 0
            
            print(f"💰 Fee validation: fees=${total_fees:.2f}, value=${filled_value:.2f}, rate={actual_fee_rate*100:.4f}%")
            
            if total_fees > 0 and abs(actual_fee_rate - expected_fee_rate) > 0.0001:  # Allow 0.01% tolerance
                raise RuntimeError(f"Fee validation failed! Expected 0.025% maker fee, got {actual_fee_rate*100:.4f}%")
        else:
            print(f"⚠️  Cannot validate fees - insufficient order data")
        
        amount_spent = filled_size
        amount_received = filled_size * avg_filled_price
        
        return (amount_received, amount_spent)
