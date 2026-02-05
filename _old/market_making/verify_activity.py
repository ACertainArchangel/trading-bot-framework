"""
Verify that:
1. Our calculated prices respect decimal precision
2. Detected activity would ACTUALLY fill our specific orders
"""

import requests
import time
import math
from decimal import Decimal, ROUND_DOWN, ROUND_UP

PRODUCT_ID = 'GST-USD'
FEE_RATE = 0.00025


def main():
    # First, get the ACTUAL precision requirements from Coinbase
    print('=' * 70)
    print('PRECISION & ACTIVITY VERIFICATION')
    print('=' * 70)
    print()

    # Fetch product details
    url = 'https://api.coinbase.com/api/v3/brokerage/market/products'
    resp = requests.get(url, timeout=10)
    data = resp.json()

    product = None
    for p in data.get('products', []):
        if p.get('product_id') == PRODUCT_ID:
            product = p
            break

    if not product:
        print('ERROR: Product not found')
        return

    quote_increment = product.get('quote_increment', '0.01')
    base_increment = product.get('base_increment', '1')

    print(f'Product: {PRODUCT_ID}')
    print(f'Quote Increment (price tick): {quote_increment}')
    print(f'Base Increment (size tick): {base_increment}')
    print()

    TICK = float(quote_increment)
    SIZE_TICK = float(base_increment)

    # Calculate decimal places
    price_decimals = len(quote_increment.split('.')[-1]) if '.' in quote_increment else 0
    size_decimals = len(base_increment.split('.')[-1]) if '.' in base_increment else 0

    print(f'Price decimals: {price_decimals} (we must use {price_decimals} decimal places)')
    print(f'Size decimals: {size_decimals} (we must use {size_decimals} decimal places)')
    print()

    # Get current order book
    book_url = 'https://api.coinbase.com/api/v3/brokerage/market/product_book'
    resp = requests.get(book_url, params={'product_id': PRODUCT_ID, 'limit': 5}, timeout=10)
    book = resp.json()

    pricebook = book.get('pricebook', {})
    bids = pricebook.get('bids', [])
    asks = pricebook.get('asks', [])

    best_bid = float(bids[0]['price'])
    best_ask = float(asks[0]['price'])
    mid = (best_bid + best_ask) / 2

    print(f'Current Book:')
    print(f'  Best Bid: ${best_bid:.{price_decimals}f}')
    print(f'  Best Ask: ${best_ask:.{price_decimals}f}')
    print(f'  Spread: ${best_ask - best_bid:.{price_decimals}f} ({(best_ask-best_bid)/mid*100:.3f}%)')
    print()

    # Calculate our positions WITH PROPER PRECISION
    our_buy_raw = best_bid + TICK
    our_buy = round(our_buy_raw, price_decimals)

    # Check buy price alignment
    print('=' * 70)
    print('PRECISION VERIFICATION')
    print('=' * 70)
    print()

    print(f'OUR BUY PRICE:')
    print(f'  Calculation: best_bid + tick = {best_bid} + {TICK} = {our_buy_raw}')
    print(f'  Rounded: {our_buy:.{price_decimals}f}')
    
    # Better tick alignment check
    buy_aligned = abs(round(our_buy / TICK) * TICK - our_buy) < 1e-10
    print(f'  Is aligned to tick? {buy_aligned}')
    print(f'  Is strictly > best_bid? {our_buy > best_bid}')
    print()

    # Calculate minimum profitable sell
    min_sell_continuous = our_buy * (1 + FEE_RATE) / (1 - FEE_RATE)
    min_sell_ticks = math.ceil(min_sell_continuous / TICK)
    min_sell = min_sell_ticks * TICK

    our_sell_raw = best_ask - TICK
    our_sell = max(min_sell, our_sell_raw)
    our_sell = round(our_sell, price_decimals)

    print(f'OUR SELL PRICE:')
    print(f'  Minimum for profit: ${min_sell:.{price_decimals}f}')
    print(f'  Ideal (ask - tick): ${our_sell_raw:.{price_decimals}f}')
    print(f'  Actual: ${our_sell:.{price_decimals}f}')
    
    sell_aligned = abs(round(our_sell / TICK) * TICK - our_sell) < 1e-10
    print(f'  Is aligned to tick? {sell_aligned}')
    print(f'  Is strictly < best_ask? {our_sell < best_ask}')
    print()

    if our_sell >= best_ask:
        print('⚠️  WARNING: Our sell >= best_ask - cannot undercut!')
    else:
        print('✅ Our sell undercuts best_ask')

    if our_buy <= best_bid:
        print('⚠️  WARNING: Our buy <= best_bid - cannot undercut!')
    else:
        print('✅ Our buy undercuts best_bid')

    # Verify profit math
    print()
    print('PROFIT VERIFICATION:')
    buy_cost = our_buy * (1 + FEE_RATE)  # What we pay per unit
    sell_proceeds = our_sell * (1 - FEE_RATE)  # What we get per unit
    profit_per_unit = sell_proceeds - buy_cost
    profit_pct = profit_per_unit / our_buy * 100
    print(f'  Buy cost per unit: ${buy_cost:.{price_decimals+2}f}')
    print(f'  Sell proceeds per unit: ${sell_proceeds:.{price_decimals+2}f}')
    print(f'  Net profit per unit: ${profit_per_unit:.{price_decimals+4}f} ({profit_pct:.4f}%)')
    
    if profit_per_unit > 0:
        print('  ✅ Trade is profitable')
    else:
        print('  ❌ Trade would LOSE money!')
        return

    print()
    print('=' * 70)
    print('ACTIVITY DETECTION VERIFICATION')
    print('=' * 70)
    print()

    print('Monitoring for 30s - checking if activity would fill OUR orders...')
    print(f'  Our BUY @ ${our_buy:.{price_decimals}f} - fills when sellers hit this price or better')
    print(f'  Our SELL @ ${our_sell:.{price_decimals}f} - fills when buyers take this price or worse')
    print()

    # Track activity that SPECIFICALLY would fill our orders
    our_buy_would_fill = 0
    our_sell_would_fill = 0
    generic_buy_events = 0
    generic_sell_events = 0

    last_bid = best_bid
    last_ask = best_ask
    last_bid_size = float(bids[0]['size'])
    last_ask_size = float(asks[0]['size'])

    start = time.time()
    checks = 0
    MONITOR_SECONDS = 30

    while (time.time() - start) < MONITOR_SECONDS:
        time.sleep(0.2)
        
        try:
            resp = requests.get(book_url, params={'product_id': PRODUCT_ID, 'limit': 5}, timeout=10)
            book = resp.json()
        except:
            continue
        
        pricebook = book.get('pricebook', {})
        bids = pricebook.get('bids', [])
        asks = pricebook.get('asks', [])
        
        if not bids or not asks:
            continue
        
        bid = float(bids[0]['price'])
        ask = float(asks[0]['price'])
        bid_size = float(bids[0]['size'])
        ask_size = float(asks[0]['size'])
        
        checks += 1
        
        # GENERIC activity detection (what we were doing before - potentially wrong)
        if ask > last_ask or (ask == last_ask and ask_size < last_ask_size * 0.5):
            generic_buy_events += 1
        if bid < last_bid or (bid == last_bid and bid_size < last_bid_size * 0.5):
            generic_sell_events += 1
        
        # CORRECT activity detection - would our orders fill?
        
        # For our SELL to fill: a buyer must take at or below our_sell
        # This happens when the ask gets lifted and the OLD ask was >= our_sell
        if ask > last_ask:
            if last_ask >= our_sell:
                # The ask that got filled was at or above our sell
                # Since our sell is better (lower), we would have been filled first!
                our_sell_would_fill += 1
                print(f'  ✅ SELL would fill: buyer took ${last_ask:.{price_decimals}f}, our sell ${our_sell:.{price_decimals}f} is better')
            else:
                print(f'  ❌ Buy at ${last_ask:.{price_decimals}f} - BELOW our sell ${our_sell:.{price_decimals}f}, would NOT fill us')
        
        # For our BUY to fill: a seller must hit at or above our_buy
        # This happens when the bid gets hit and the OLD bid was <= our_buy
        if bid < last_bid:
            if last_bid <= our_buy:
                # The bid that got hit was at or below our buy
                # Since our buy is better (higher), we would have been filled first!
                our_buy_would_fill += 1
                print(f'  ✅ BUY would fill: seller hit ${last_bid:.{price_decimals}f}, our buy ${our_buy:.{price_decimals}f} is better')
            else:
                print(f'  ❌ Sell at ${last_bid:.{price_decimals}f} - ABOVE our buy ${our_buy:.{price_decimals}f}, would NOT fill us')
        
        last_bid = bid
        last_ask = ask
        last_bid_size = bid_size
        last_ask_size = ask_size

    print()
    print('=' * 70)
    print('RESULTS')
    print('=' * 70)
    print()
    print(f'Generic activity (old method):')
    print(f'  Buy events: {generic_buy_events}')
    print(f'  Sell events: {generic_sell_events}')
    print()
    print(f'Activity that would fill OUR orders (correct method):')
    print(f'  Our SELL would fill: {our_sell_would_fill} times')
    print(f'  Our BUY would fill: {our_buy_would_fill} times')
    print()

    if our_sell_would_fill > 0 and our_buy_would_fill > 0:
        print('✅ CONFIRMED: Both sides would have filled with our specific prices!')
    elif our_sell_would_fill > 0 or our_buy_would_fill > 0:
        print('⚠️  Only one side would fill - need more monitoring')
    else:
        print('❌ Neither side would fill at our specific prices')


if __name__ == '__main__':
    main()
