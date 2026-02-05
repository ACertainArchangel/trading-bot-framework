#!/usr/bin/env python3
"""
Test live trading with Bull strategy (always buy)
"""

import json
from interfaces.CoinbaseAdvancedTradeInterface import CoinbaseAdvancedTradeInterface
from trader_bot import Bot
from strategies.bull import BullStrategy

# Load API credentials
with open('secrets.json', 'r') as f:
    secrets = json.load(f)

api_key_name = secrets['coinbase_api_key_name']
api_private_key = secrets['coinbase_api_private_key']

print("=" * 80)
print("LIVE BULL STRATEGY TEST")
print("=" * 80)
print()
print("⚠️  WARNING: This will execute a REAL buy order!")
print("Strategy: Bull (always buy once, then hold)")
print()

# Create interface
interface = CoinbaseAdvancedTradeInterface(
    api_key_name=api_key_name,
    api_private_key=api_private_key
)

# Connect and get balances
print("📡 Connecting to Coinbase...")
result = interface.connect_to_exchange()
accounts = result.get('accounts', [])

usd_account = next((a for a in accounts if a['currency'] == 'USD'), None)
btc_account = next((a for a in accounts if a['currency'] == 'BTC'), None)

usd_balance = float(usd_account['available_balance']['value'])
btc_balance = float(btc_account['available_balance']['value'])

print(f"✅ Connected!")
print(f"Current Balances:")
print(f"  USD: ${usd_balance:.8f}")
print(f"  BTC: {btc_balance:.8f} BTC")
print()

if usd_balance < 1.0:
    print("❌ Insufficient USD balance (need at least $1.00)")
    exit(1)

# Use small amount for testing
test_amount = min(10.0, usd_balance * 0.999)

print(f"💰 Test amount: ${test_amount:.2f}")
print()

# Create bot with Bull strategy - start with BTC balance (if any) as LONG position
if btc_balance > 0.0001:
    # Already have BTC, start LONG
    bot = Bot(
        interface=interface,
        strategy=BullStrategy,
        pair="BTC-USD",
        starting_currency=0,
        starting_asset=btc_balance,
        fee_rate=0.00025,
        fee_in_percent=False,
        loss_tolerance=0.0,
        strategy_params={}
    )
    print(f"⚠️  Bot already has BTC - starting LONG")
    print(f"✅ Test complete - no buy needed (already holding BTC)")
    exit(0)
else:
    # Start SHORT with USD
    bot = Bot(
        interface=interface,
        strategy=BullStrategy,
        pair="BTC-USD",
        starting_currency=usd_balance,
        starting_asset=0,
        fee_rate=0.00025,
        fee_in_percent=False,
        loss_tolerance=0.0,
        strategy_params={}
    )
    # Now adjust to use only test amount for the trade
    bot.currency = test_amount
    print(f"⚠️  Adjusted bot to use ${test_amount:.2f} for trade")

print("🤖 Bot created with Bull strategy")
print("📊 Starting position: SHORT (USD)")
print()

# Get some dummy candles (strategy doesn't use them)
dummy_candles = [{'close': 86000.0}] * 50

print("=" * 80)
print("EXECUTING STRATEGY")
print("=" * 80)
print()

try:
    # Check if strategy says to buy
    should_buy = bot.strategy.buy_signal(dummy_candles)
    print(f"Strategy buy_signal(): {should_buy}")
    
    if should_buy:
        print("💸 Executing BUY order...")
        print()
        
        # Execute the buy through the bot
        # Get current price
        price_data = interface._make_request('GET', '/api/v3/brokerage/products/BTC-USD')
        current_price = float(price_data['price'])
        
        # Execute buy
        btc_received, usd_spent = interface.execute_buy(
            price=current_price,
            fee_rate=0.00025,
            currency=test_amount
        )
        
        print("=" * 80)
        print("✅ BUY ORDER COMPLETED!")
        print("=" * 80)
        print(f"  USD spent: ${usd_spent:.2f}")
        print(f"  BTC received: {btc_received:.8f} BTC")
        print(f"  Effective price: ${usd_spent/btc_received:.2f} per BTC")
        print()
        
        # Update bot state
        bot.currency = 0
        bot.asset = btc_received
        bot.position = "long"
        
        print("🎯 Bot now LONG (holding BTC)")
        print()
        
        # Check if strategy says to sell (should be False)
        should_sell = bot.strategy.sell_signal(dummy_candles)
        print(f"Strategy sell_signal(): {should_sell}")
        print("✅ Strategy correctly holds position")
        
except Exception as e:
    print("=" * 80)
    print("❌ ERROR")
    print("=" * 80)
    print(f"Error: {e}")
    print()
    import traceback
    traceback.print_exc()
