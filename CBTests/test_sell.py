#!/usr/bin/env python3
"""
Test script to manually trigger a sell order using the bot's interface.
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
print("MANUAL SELL TEST")
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

if btc_balance < 0.0001:
    print("❌ Insufficient BTC balance to test sell (need at least 0.0001 BTC)")
    exit(1)

# Sell slightly less to account for any locked/unavailable balance
# Reduce by 0.1% to be safe
sell_amount = btc_balance * 0.999
print(f"⚠️  Adjusted sell amount: {sell_amount:.8f} BTC (99.9% of balance)")
print()

# Create a bot instance (needed for interface to access bot.pair)
bot = Bot(
    interface=interface,
    strategy=EMACrossStrategy,
    pair="BTC-USD",
    starting_currency=0,
    starting_asset=btc_balance,
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

# Attempt to sell
print("=" * 80)
print("ATTEMPTING SELL ORDER")
print("=" * 80)
print(f"  Amount to sell: {sell_amount:.8f} BTC")
print(f"  Current price: ${current_price:.2f}")
print(f"  Limit price: ${current_price * 1.005:.2f} (0.5% above market)")
print(f"  Expected fee rate: 0.025% (maker)")
print()

try:
    amount_received, amount_spent = interface.execute_sell(
        price=current_price,
        fee_rate=0.00025,
        asset=sell_amount
    )
    
    print("=" * 80)
    print("✅ SELL ORDER SUCCESSFUL!")
    print("=" * 80)
    print(f"  BTC sold: {amount_spent:.8f} BTC")
    print(f"  USD received: ${amount_received:.2f}")
    print()
    
except Exception as e:
    print("=" * 80)
    print("❌ SELL ORDER FAILED")
    print("=" * 80)
    print(f"Error: {e}")
    print()
    import traceback
    traceback.print_exc()
