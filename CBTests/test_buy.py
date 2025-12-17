#!/usr/bin/env python3
"""
Test script to manually trigger a buy order using the bot's interface.
"""

import json
from interfaces.CoinbaseAdvancedTradeInterface import CoinbaseAdvancedTradeInterface
from trader_bot import Bot
from strategies.ema_cross import EMACrossStrategy

# Load API credentials
with open('secrets.json', 'r') as f:
    secrets = json.load(f)

api_key_name = secrets['coinbase_api_key_name']
api_private_key = secrets['coinbase_api_private_key']

print("=" * 80)
print("MANUAL BUY TEST")
print("=" * 80)
print()

# Create interface
interface = CoinbaseAdvancedTradeInterface(
    api_key_name=api_key_name,
    api_private_key=api_private_key
)

# Connect to exchange
print("📡 Connecting to Coinbase Advanced Trade API...")
result = interface.connect_to_exchange()
accounts = result.get('accounts', [])
print(f"✅ Connected! Found {len(accounts)} accounts")
print()

# Get current balances
usd_account = next((a for a in accounts if a['currency'] == 'USD'), None)
btc_account = next((a for a in accounts if a['currency'] == 'BTC'), None)

if not usd_account or not btc_account:
    print("❌ Could not find USD or BTC accounts")
    exit(1)

usd_balance = float(usd_account['available_balance']['value'])
btc_balance = float(btc_account['available_balance']['value'])

print(f"Current Balances:")
print(f"  USD: ${usd_balance:.8f}")
print(f"  BTC: {btc_balance:.8f} BTC")
print()

if usd_balance < 1.0:
    print("❌ Insufficient USD balance to test buy (need at least $1.00)")
    exit(1)

# Use a small amount for testing - $10 or 99.9% of balance, whichever is smaller
buy_amount = min(10.0, usd_balance * 0.999)
print(f"⚠️  Test buy amount: ${buy_amount:.2f}")
print()

# Create a bot instance (needed for interface to access bot.pair)
bot = Bot(
    interface=interface,
    strategy=EMACrossStrategy,
    pair="BTC-USD",
    starting_currency=usd_balance,
    starting_asset=0,
    fee_rate=0.00025,  # 0.025% VIP maker fee
    fee_in_percent=False,
    loss_tolerance=0.0,
    strategy_params={'fast': 50, 'slow': 200}
)

# Get current BTC price
print("💰 Fetching current BTC price...")
price_data = interface._make_request('GET', '/api/v3/brokerage/products/BTC-USD')
current_price = float(price_data['price'])
print(f"✅ Current BTC price: ${current_price:.2f}")
print()

# Attempt to buy
print("=" * 80)
print("ATTEMPTING BUY ORDER")
print("=" * 80)
print(f"  Amount to spend: ${buy_amount:.2f}")
print(f"  Current price: ${current_price:.2f}")
print(f"  Limit price: ${current_price * 0.99965:.2f} (0.035% below market)")
print(f"  Expected fee rate: 0.025% (maker)")
print()

try:
    amount_received, amount_spent = interface.execute_buy(
        price=current_price,
        fee_rate=0.00025,
        currency=buy_amount
    )
    
    print("=" * 80)
    print("✅ BUY ORDER SUCCESSFUL!")
    print("=" * 80)
    print(f"  USD spent: ${amount_spent:.2f}")
    print(f"  BTC received: {amount_received:.8f} BTC")
    print()
    
except Exception as e:
    print("=" * 80)
    print("❌ BUY ORDER FAILED")
    print("=" * 80)
    print(f"Error: {e}")
    print()
    import traceback
    traceback.print_exc()
