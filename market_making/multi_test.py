"""
Run extended activity test on multiple tokens simultaneously
"""

import requests
import time
import math
from concurrent.futures import ThreadPoolExecutor, as_completed

FEE_RATE = 0.00025
MONITOR = 120  # 2 minutes


def test_token(product_id: str) -> dict:
    """Test a single token for activity."""
    
    # Get tick size
    url = 'https://api.coinbase.com/api/v3/brokerage/market/products'
    resp = requests.get(url, timeout=10)
    data = resp.json()
    
    product = None
    for p in data.get('products', []):
        if p.get('product_id') == product_id:
            product = p
            break
    
    if not product:
        return {'product_id': product_id, 'error': 'not found'}
    
    TICK = float(product.get('quote_increment', '0.000001'))
    
    book_url = 'https://api.coinbase.com/api/v3/brokerage/market/product_book'
    
    buy_fills = 0
    sell_fills = 0
    
    last_bid = None
    last_ask = None
    
    start = time.time()
    while (time.time() - start) < MONITOR:
        try:
            resp = requests.get(book_url, params={'product_id': product_id, 'limit': 5}, timeout=10)
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
        
        our_buy = bid + TICK
        min_sell = math.ceil(our_buy * (1 + FEE_RATE) / (1 - FEE_RATE) / TICK) * TICK
        our_sell = max(min_sell, ask - TICK)
        
        if last_bid is not None:
            if bid < last_bid:
                if last_bid <= our_buy:
                    buy_fills += 1
            
            if ask > last_ask:
                if last_ask >= our_sell:
                    sell_fills += 1
        
        last_bid = bid
        last_ask = ask
        time.sleep(0.2)
    
    return {
        'product_id': product_id,
        'buy_fills': buy_fills,
        'sell_fills': sell_fills,
        'both': buy_fills > 0 and sell_fills > 0
    }


def main():
    tokens = ['GST-USD', 'DOGINME-USD', 'BNKR-USD', 'NOICE-USD', 'SWFTC-USD', 'ACS-USD']
    
    print('=' * 70)
    print(f'MULTI-TOKEN ACTIVITY TEST - {MONITOR}s each')
    print('=' * 70)
    print()
    print(f'Testing: {", ".join(tokens)}')
    print('Running sequentially to avoid rate limits...')
    print()
    
    results = []
    for token in tokens:
        print(f'Testing {token}...')
        result = test_token(token)
        results.append(result)
        print(f'  {token}: {result["buy_fills"]} buy fills, {result["sell_fills"]} sell fills')
        print()
    
    print('=' * 70)
    print('RESULTS')
    print('=' * 70)
    print()
    
    for r in results:
        status = '✅' if r.get('both') else '❌'
        print(f'{status} {r["product_id"]}: {r["buy_fills"]} buys, {r["sell_fills"]} sells')
    
    print()
    
    # Best candidate
    both_sided = [r for r in results if r.get('both')]
    if both_sided:
        best = max(both_sided, key=lambda x: min(x['buy_fills'], x['sell_fills']))
        print(f'🏆 BEST: {best["product_id"]} ({best["buy_fills"]} buys, {best["sell_fills"]} sells)')
    else:
        print('❌ No token had activity on both sides')
        
        # Show which had any activity
        any_activity = [r for r in results if r.get('buy_fills', 0) > 0 or r.get('sell_fills', 0) > 0]
        if any_activity:
            print()
            print('Tokens with partial activity:')
            for r in any_activity:
                if r['buy_fills'] > 0:
                    print(f'  {r["product_id"]}: {r["buy_fills"]} BUY fills (sellers hitting)')
                if r['sell_fills'] > 0:
                    print(f'  {r["product_id"]}: {r["sell_fills"]} SELL fills (buyers taking)')


if __name__ == '__main__':
    main()
