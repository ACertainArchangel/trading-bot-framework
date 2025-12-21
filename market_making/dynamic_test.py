"""
Dynamic positioning test - recalculate on every check
"""

import requests
import time
import math
import sys

PRODUCT_ID = sys.argv[1] if len(sys.argv) > 1 else 'GST-USD'
FEE_RATE = 0.00025
MONITOR = 60  # 60 seconds


def main():
    print('=' * 70)
    print(f'DYNAMIC POSITIONING TEST - {PRODUCT_ID} - {MONITOR}s')
    print('=' * 70)
    print()
    
    # Get tick size from API
    url = 'https://api.coinbase.com/api/v3/brokerage/market/products'
    resp = requests.get(url, timeout=10)
    data = resp.json()
    
    product = None
    for p in data.get('products', []):
        if p.get('product_id') == PRODUCT_ID:
            product = p
            break
    
    if not product:
        print(f'ERROR: {PRODUCT_ID} not found')
        return
    
    TICK = float(product.get('quote_increment', '0.000001'))
    price_dec = len(product.get('quote_increment', '0.000001').split('.')[-1])
    
    print(f'Tick size: ${TICK}')
    print('Strategy: Recalculate positions on EVERY check')
    print('This simulates continuous requoting')
    print()

    book_url = 'https://api.coinbase.com/api/v3/brokerage/market/product_book'

    buy_fills = 0
    sell_fills = 0
    buy_misses = []
    sell_misses = []

    last_bid = None
    last_ask = None

    start = time.time()
    while (time.time() - start) < MONITOR:
        try:
            resp = requests.get(book_url, params={'product_id': PRODUCT_ID, 'limit': 5}, timeout=10)
            book = resp.json()
        except:
            time.sleep(0.2)
            continue
        
        pricebook = book.get('pricebook', {})
        bids = pricebook.get('bids', [])
        asks = pricebook.get('asks', [])
        
        if not bids or not asks:
            time.sleep(0.2)
            continue
        
        bid = float(bids[0]['price'])
        ask = float(asks[0]['price'])
        
        # Calculate our positions NOW based on CURRENT book
        our_buy = bid + TICK  # 1 tick above best bid
        min_sell = math.ceil(our_buy * (1 + FEE_RATE) / (1 - FEE_RATE) / TICK) * TICK
        our_sell = max(min_sell, ask - TICK)  # 1 tick below best ask, or min for profit
        
        if last_bid is not None:
            # Check if activity would fill our CURRENT positions
            
            # BUY fills when sellers hit at or below our_buy
            if bid < last_bid:
                if last_bid <= our_buy:
                    buy_fills += 1
                    print(f'  BUY fill: seller hit ${last_bid:.6f}, our buy ${our_buy:.6f}')
                else:
                    buy_misses.append(last_bid - our_buy)
            
            # SELL fills when buyers take at or above our_sell  
            if ask > last_ask:
                if last_ask >= our_sell:
                    sell_fills += 1
                    print(f'  SELL fill: buyer took ${last_ask:.6f}, our sell ${our_sell:.6f}')
                else:
                    # This is the issue - buyer took BELOW our sell
                    gap = our_sell - last_ask
                    gap_ticks = int(gap / TICK)
                    sell_misses.append(gap_ticks)
                    print(f'  MISS: buyer at ${last_ask:.6f}, our sell ${our_sell:.6f} (+{gap_ticks} ticks too high)')
        
        last_bid = bid
        last_ask = ask
        time.sleep(0.2)

    print()
    print('=' * 70)
    print('RESULTS')
    print('=' * 70)
    print(f'BUY fills: {buy_fills}')
    print(f'SELL fills: {sell_fills}')
    
    if sell_misses:
        avg_miss = sum(sell_misses) / len(sell_misses)
        print(f'SELL misses: {len(sell_misses)} (avg {avg_miss:.1f} ticks too high)')
    
    print()

    if buy_fills > 0 and sell_fills > 0:
        print('✅ Both sides would fill - GST-USD is viable!')
    elif buy_fills > 0:
        print('⚠️  Only BUY side fills - sellers are active but buyers are cautious')
        print('   This means we can buy but may struggle to sell')
    else:
        print('❌ Insufficient activity')


if __name__ == '__main__':
    main()
