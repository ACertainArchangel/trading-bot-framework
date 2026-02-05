#!/usr/bin/env python3
"""
Coinbase Account Inspector

Inspect your Coinbase account balances, orders, and other useful information.
Safe to run - does NOT execute any trades.

Run with: python examples/inspect_real_account.py
"""

import sys
import json
from pathlib import Path
from datetime import datetime

# Add framework to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from framework.interfaces.coinbase import CoinbaseInterface


# =============================================================================
# CONFIGURATION
# =============================================================================

SECRETS_FILE = "secrets1.json"  # Which secrets file to use
DEFAULT_PRODUCT = "BTC-USD"     # Default trading pair


# =============================================================================
# SECRETS LOADING
# =============================================================================

def load_secrets(filename: str) -> dict:
    """Load API credentials from secrets file."""
    secrets_path = Path(__file__).parent.parent / "secrets" / filename
    
    if not secrets_path.exists():
        print(f"\n❌ Secrets file not found: {secrets_path}")
        print(f"\nTo create one, add a file at secrets/{filename} with:")
        print(json.dumps({
            "coinbase_api_key_name": "organizations/xxx/apiKeys/xxx",
            "coinbase_api_private_key": "-----BEGIN EC PRIVATE KEY-----\n...\n-----END EC PRIVATE KEY-----\n"
        }, indent=2))
        sys.exit(1)
    
    with open(secrets_path) as f:
        secrets = json.load(f)
    
    required = ['coinbase_api_key_name', 'coinbase_api_private_key']
    for key in required:
        if key not in secrets:
            print(f"\n❌ Missing '{key}' in secrets file")
            sys.exit(1)
    
    return secrets


# =============================================================================
# ACCOUNT INSPECTION FUNCTIONS
# =============================================================================

def get_all_balances(interface: CoinbaseInterface) -> list:
    """Get all non-zero account balances."""
    result = interface._request('GET', '/api/v3/brokerage/accounts')
    
    balances = []
    for account in result.get('accounts', []):
        available_val = account.get('available_balance', {}).get('value', '0')
        hold_val = account.get('hold', {}).get('value', '0')
        available = float(available_val) if available_val else 0.0
        hold = float(hold_val) if hold_val else 0.0
        total = available + hold
        
        if total > 0.00000001:  # Filter dust
            balances.append({
                'currency': account['currency'],
                'available': available,
                'hold': hold,
                'total': total,
                'uuid': account['uuid']
            })
    
    return sorted(balances, key=lambda x: x['currency'])


def get_recent_orders(interface: CoinbaseInterface, limit: int = 10) -> list:
    """Get recent orders."""
    result = interface._request('GET', '/api/v3/brokerage/orders/historical/batch')
    
    orders = []
    for order in result.get('orders', [])[:limit]:
        filled_size = order.get('filled_size') or order.get('order_configuration', {}).get('limit_limit_gtc', {}).get('base_size', '0')
        filled_val = order.get('filled_value', '0')
        
        orders.append({
            'id': order.get('order_id', '')[:8],
            'product': order.get('product_id', ''),
            'side': order.get('side', ''),
            'status': order.get('status', ''),
            'size': float(filled_size) if filled_size else 0.0,
            'value': float(filled_val) if filled_val else 0.0,
            'created': order.get('created_time', '')[:19]
        })
    
    return orders


def get_products(interface: CoinbaseInterface) -> list:
    """Get available trading products."""
    result = interface._request('GET', '/api/v3/brokerage/products')
    
    products = []
    for product in result.get('products', []):
        if product.get('status') == 'online':
            price_str = product.get('price', '0')
            volume_str = product.get('volume_24h', '0')
            
            products.append({
                'id': product['product_id'],
                'base': product['base_currency_id'],
                'quote': product['quote_currency_id'],
                'price': float(price_str) if price_str else 0.0,
                'volume_24h': float(volume_str) if volume_str else 0.0
            })
    
    return products


def get_fees(interface: CoinbaseInterface) -> dict:
    """Get current fee structure."""
    result = interface._request('GET', '/api/v3/brokerage/transaction_summary')
    
    fee_tier = result.get('fee_tier', {})
    maker = fee_tier.get('maker_fee_rate', '0')
    taker = fee_tier.get('taker_fee_rate', '0')
    volume = fee_tier.get('usd_from_30d_volume', '0')
    
    return {
        'maker_rate': float(maker) if maker else 0.0,
        'taker_rate': float(taker) if taker else 0.0,
        'pricing_tier': fee_tier.get('pricing_tier', 'Unknown'),
        'usd_30d_volume': float(volume) if volume else 0.0
    }


# =============================================================================
# DISPLAY FUNCTIONS
# =============================================================================

def print_header(title: str):
    """Print a section header."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def display_balances(balances: list, current_prices: dict = None):
    """Display account balances."""
    print_header("💰 ACCOUNT BALANCES")
    
    if not balances:
        print("  No balances found.")
        return
    
    total_usd = 0
    
    for bal in balances:
        currency = bal['currency']
        total = bal['total']
        
        # Get USD value
        usd_value = 0
        if currency in ('USD', 'USDC', 'USDT'):
            usd_value = total
        elif current_prices and f"{currency}-USD" in current_prices:
            usd_value = total * current_prices[f"{currency}-USD"]
        
        total_usd += usd_value
        
        hold_str = f" (hold: {bal['hold']:.8f})" if bal['hold'] > 0 else ""
        usd_str = f" ≈ ${usd_value:,.2f}" if usd_value > 0 else ""
        
        if currency in ('USD', 'USDC', 'USDT'):
            print(f"  {currency:6} ${total:,.2f}{hold_str}")
        else:
            print(f"  {currency:6} {total:.8f}{hold_str}{usd_str}")
    
    print(f"\n  {'─'*40}")
    print(f"  TOTAL VALUE: ${total_usd:,.2f}")


def display_orders(orders: list):
    """Display recent orders."""
    print_header("📋 RECENT ORDERS")
    
    if not orders:
        print("  No recent orders.")
        return
    
    print(f"  {'ID':<10} {'Product':<10} {'Side':<6} {'Status':<12} {'Size':<12} {'Created'}")
    print(f"  {'-'*10} {'-'*10} {'-'*6} {'-'*12} {'-'*12} {'-'*19}")
    
    for order in orders:
        print(f"  {order['id']:<10} {order['product']:<10} {order['side']:<6} "
              f"{order['status']:<12} {order['size']:<12.6f} {order['created']}")


def display_fees(fees: dict):
    """Display fee structure."""
    print_header("💸 FEE STRUCTURE")
    
    print(f"  Pricing Tier: {fees['pricing_tier']}")
    print(f"  30-day Volume: ${fees['usd_30d_volume']:,.2f}")
    print(f"  Maker Fee: {fees['maker_rate']*100:.3f}%")
    print(f"  Taker Fee: {fees['taker_rate']*100:.3f}%")


def display_prices(interface: CoinbaseInterface, products: list):
    """Display prices for major products."""
    print_header("📈 CURRENT PRICES")
    
    # Filter to major pairs
    major = ['BTC-USD', 'ETH-USD', 'SOL-USD', 'DOGE-USD', 'XRP-USD']
    
    prices = {}
    for product in products:
        if product['id'] in major and product['price'] > 0:
            prices[product['id']] = product['price']
    
    for pair in major:
        if pair in prices:
            print(f"  {pair}: ${prices[pair]:,.2f}")
    
    return prices


def display_position(interface: CoinbaseInterface, product_id: str):
    """Display current position for a specific product."""
    print_header(f"🎯 POSITION: {product_id}")
    
    parts = product_id.split('-')
    asset_code = parts[0]
    currency_code = parts[1]
    
    asset_bal = interface.get_balance(asset_code)
    currency_bal = interface.get_balance(currency_code)
    price = interface.get_current_price()
    
    total_value = currency_bal + (asset_bal * price)
    
    if asset_bal > 0.00000001:
        position = "LONG"
        position_value = asset_bal * price
        print(f"  Position: {position}")
        print(f"  {asset_code}: {asset_bal:.8f} (${position_value:,.2f})")
        print(f"  {currency_code}: ${currency_bal:,.2f}")
    else:
        position = "SHORT (Cash)"
        print(f"  Position: {position}")
        print(f"  {currency_code}: ${currency_bal:,.2f}")
    
    print(f"  Current Price: ${price:,.2f}")
    print(f"  Total Value: ${total_value:,.2f}")


# =============================================================================
# INTERACTIVE MENU
# =============================================================================

def interactive_menu(interface: CoinbaseInterface, products: list):
    """Interactive inspection menu."""
    
    while True:
        print("\n" + "="*60)
        print("  COINBASE INSPECTOR - MENU")
        print("="*60)
        print("  1. View All Balances")
        print("  2. View Recent Orders")
        print("  3. View Fee Structure")
        print("  4. View Current Prices")
        print("  5. View Position (BTC-USD)")
        print("  6. View Position (other pair)")
        print("  7. Refresh Connection")
        print("  0. Exit")
        print("="*60)
        
        choice = input("\nSelect option: ").strip()
        
        try:
            if choice == '1':
                balances = get_all_balances(interface)
                prices = {p['id']: p['price'] for p in products}
                display_balances(balances, prices)
                
            elif choice == '2':
                orders = get_recent_orders(interface)
                display_orders(orders)
                
            elif choice == '3':
                fees = get_fees(interface)
                display_fees(fees)
                
            elif choice == '4':
                prices = display_prices(interface, products)
                
            elif choice == '5':
                interface.product_id = "BTC-USD"
                interface.asset_code = "BTC"
                interface.currency_code = "USD"
                display_position(interface, "BTC-USD")
                
            elif choice == '6':
                pair = input("Enter product (e.g., ETH-USD): ").strip().upper()
                if '-' not in pair:
                    print("Invalid format. Use ASSET-CURRENCY (e.g., ETH-USD)")
                    continue
                interface.product_id = pair
                parts = pair.split('-')
                interface.asset_code = parts[0]
                interface.currency_code = parts[1]
                display_position(interface, pair)
                
            elif choice == '7':
                print("\n🔌 Refreshing connection...")
                interface.connect()
                products = get_products(interface)
                print("✅ Refreshed!")
                
            elif choice == '0':
                print("\n👋 Goodbye!")
                break
                
            else:
                print("Invalid option.")
                
        except Exception as e:
            print(f"\n❌ Error: {e}")


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("\n" + "="*60)
    print("  🔍 COINBASE ACCOUNT INSPECTOR")
    print("="*60)
    print("  Safe mode - No trades will be executed")
    print("="*60)
    
    # Load secrets
    print("\n🔑 Loading API credentials...")
    secrets = load_secrets(SECRETS_FILE)
    
    # Create interface
    interface = CoinbaseInterface(
        api_key=secrets['coinbase_api_key_name'],
        api_secret=secrets['coinbase_api_private_key'],
        product_id=DEFAULT_PRODUCT
    )
    
    # Connect
    print("🔌 Connecting to Coinbase...")
    interface.connect()
    print("✅ Connected!")
    
    # Get initial data
    print("📊 Fetching account data...")
    
    balances = get_all_balances(interface)
    orders = get_recent_orders(interface, limit=5)
    products = get_products(interface)
    fees = get_fees(interface)
    
    # Display summary
    prices = {p['id']: p['price'] for p in products}
    display_balances(balances, prices)
    display_fees(fees)
    display_position(interface, DEFAULT_PRODUCT)
    
    if orders:
        display_orders(orders)
    
    # Interactive menu
    response = input("\n\nEnter interactive mode? (y/n): ").strip().lower()
    if response == 'y':
        interactive_menu(interface, products)


if __name__ == "__main__":
    main()
