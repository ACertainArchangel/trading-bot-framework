"""
Sophisticated Token Scanner for Market Making

Finds tokens where:
1. We can position with spread > 0.05% (strictly profitable after fees)
2. Our prices strictly undercut BOTH best bid AND best ask
3. Real market orders are hitting prices at or better than ours (activity validation)

This eliminates dead markets like TROLL where spread exists but nobody trades.
"""

import requests
import time
import json
import math
from datetime import datetime
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from decimal import Decimal


# =============================================================================
# CONFIGURATION
# =============================================================================

FEE_RATE = 0.00025  # 0.025% maker fee
MIN_SPREAD_PCT = 0.0006  # 0.06% minimum (slightly above 2x fee for safety margin)
MIN_VOLUME_24H = 50000  # $50k minimum daily volume
ACTIVITY_MONITOR_SECONDS = 10  # How long to watch for market orders
MIN_TICK_BUFFER = 1  # Minimum ticks we must undercut by


@dataclass
class TokenCandidate:
    """A token that passed all filters."""
    product_id: str
    mid_price: float
    best_bid: float
    best_ask: float
    our_buy_price: float
    our_sell_price: float
    spread_pct: float
    our_spread_pct: float
    profit_margin_pct: float  # our_spread - 2*fee
    tick_size: float
    ticks_in_spread: int
    base_increment: str
    volume_24h: float
    
    # Activity metrics
    buy_activity: int  # Market orders that would fill our SELL
    sell_activity: int  # Market orders that would fill our BUY
    activity_duration: float


def get_all_usd_products() -> List[Dict]:
    """Fetch all USD trading pairs from Coinbase."""
    url = "https://api.coinbase.com/api/v3/brokerage/market/products"
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        products = [
            p for p in data.get('products', [])
            if p.get('quote_currency_id') == 'USD' 
            and p.get('status') == 'online'
            and not p.get('is_disabled', False)
            and not p.get('trading_disabled', False)
        ]
        
        return products
    except Exception as e:
        print(f"Error fetching products: {e}")
        return []


def get_order_book(product_id: str) -> Optional[Dict]:
    """Fetch order book for a product."""
    url = "https://api.coinbase.com/api/v3/brokerage/market/product_book"
    params = {"product_id": product_id, "limit": 10}
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except:
        return None


def calculate_positions(best_bid: float, best_ask: float, tick_size: float) -> Tuple[float, float, float]:
    """
    Calculate our buy and sell prices that:
    1. Strictly undercut both sides
    2. Have spread > MIN_SPREAD_PCT
    
    Returns: (our_buy_price, our_sell_price, our_spread_pct) or (0, 0, 0) if impossible
    """
    mid = (best_bid + best_ask) / 2
    
    # Our buy price: best_bid + 1 tick (undercut asks by being higher bid)
    our_buy = best_bid + tick_size
    
    # Calculate minimum sell price for profitability
    # sell * (1 - fee) > buy * (1 + fee)
    # sell > buy * (1 + fee) / (1 - fee)
    min_sell_continuous = our_buy * (1 + FEE_RATE) / (1 - FEE_RATE)
    min_sell_ticks = math.ceil(min_sell_continuous / tick_size)
    min_sell = min_sell_ticks * tick_size
    
    # Our sell price: must be at least min_sell, ideally best_ask - 1 tick
    ideal_sell = best_ask - tick_size
    our_sell = max(min_sell, ideal_sell)
    
    # CRITICAL: Our sell must be STRICTLY below best_ask to undercut
    if our_sell >= best_ask:
        return (0, 0, 0)  # Can't undercut - spread too tight
    
    # CRITICAL: Our buy must be STRICTLY above best_bid
    if our_buy <= best_bid:
        return (0, 0, 0)  # Something wrong
    
    # Calculate our spread
    our_spread = our_sell - our_buy
    our_spread_pct = our_spread / mid
    
    # Must exceed minimum spread
    if our_spread_pct < MIN_SPREAD_PCT:
        return (0, 0, 0)
    
    return (our_buy, our_sell, our_spread_pct)


def monitor_activity(product_id: str, our_buy: float, our_sell: float, 
                    duration: float = ACTIVITY_MONITOR_SECONDS) -> Tuple[int, int]:
    """
    Monitor order book for market orders that would fill at our prices.
    
    We watch for:
    - Aggressive BUYS: asks getting lifted at prices >= our_sell (would fill our sell)
    - Aggressive SELLS: bids getting hit at prices <= our_buy (would fill our buy)
    
    Returns: (buy_activity_count, sell_activity_count)
    """
    buy_activity = 0  # Takers buying at prices that would fill our SELL
    sell_activity = 0  # Takers selling at prices that would fill our BUY
    
    start = time.time()
    last_best_bid = None
    last_best_ask = None
    last_bid_size = None
    last_ask_size = None
    
    checks = 0
    
    while (time.time() - start) < duration:
        try:
            book_data = get_order_book(product_id)
            if not book_data:
                time.sleep(0.2)
                continue
            
            pricebook = book_data.get('pricebook', {})
            bids = pricebook.get('bids', [])
            asks = pricebook.get('asks', [])
            
            if not bids or not asks:
                time.sleep(0.2)
                continue
            
            best_bid = float(bids[0]['price'])
            best_ask = float(asks[0]['price'])
            bid_size = float(bids[0]['size'])
            ask_size = float(asks[0]['size'])
            
            checks += 1
            
            if last_best_bid is not None:
                # Detect aggressive BUYS (ask side activity)
                # If best_ask jumped up OR ask size decreased significantly, buyers are lifting
                if best_ask > last_best_ask:
                    # Ask price moved up - someone bought the ask
                    if last_best_ask >= our_sell:
                        # The filled ask was at or above our sell price - we would have filled!
                        buy_activity += 1
                elif best_ask == last_best_ask and ask_size < last_ask_size * 0.7:
                    # Same price but size dropped significantly - partial fills happening
                    if best_ask >= our_sell:
                        buy_activity += 1
                
                # Detect aggressive SELLS (bid side activity)
                # If best_bid dropped OR bid size decreased significantly, sellers are hitting
                if best_bid < last_best_bid:
                    # Bid price moved down - someone sold into the bid
                    if last_best_bid <= our_buy:
                        # The filled bid was at or below our buy price - we would have filled!
                        sell_activity += 1
                elif best_bid == last_best_bid and bid_size < last_bid_size * 0.7:
                    # Same price but size dropped - partial fills
                    if best_bid <= our_buy:
                        sell_activity += 1
            
            last_best_bid = best_bid
            last_best_ask = best_ask
            last_bid_size = bid_size
            last_ask_size = ask_size
            
            time.sleep(0.2)  # Check 5x per second
            
        except Exception as e:
            time.sleep(0.2)
            continue
    
    return (buy_activity, sell_activity)


def scan_token(product: Dict, verbose: bool = False) -> Optional[TokenCandidate]:
    """
    Full scan of a single token.
    
    Returns TokenCandidate if it passes all filters, None otherwise.
    """
    product_id = product.get('product_id', '')
    
    # Get volume
    vol_str = product.get('volume_24h', '') or '0'
    try:
        volume = float(vol_str)
    except:
        volume = 0
    
    # Skip low volume
    if volume < MIN_VOLUME_24H:
        if verbose:
            print(f"  {product_id}: Skip - volume ${volume:,.0f} < ${MIN_VOLUME_24H:,}")
        return None
    
    # Get order book
    book_data = get_order_book(product_id)
    if not book_data:
        return None
    
    pricebook = book_data.get('pricebook', {})
    bids = pricebook.get('bids', [])
    asks = pricebook.get('asks', [])
    
    if not bids or not asks:
        return None
    
    best_bid = float(bids[0]['price'])
    best_ask = float(asks[0]['price'])
    
    if best_bid <= 0 or best_ask <= 0 or best_bid >= best_ask:
        return None
    
    mid = (best_bid + best_ask) / 2
    spread = best_ask - best_bid
    spread_pct = spread / mid
    
    # Get tick size
    tick_size = float(product.get('quote_increment', '0.01'))
    ticks_in_spread = int(spread / tick_size) if tick_size > 0 else 0
    
    # Need at least 3 ticks to position inside
    if ticks_in_spread < 3:
        if verbose:
            print(f"  {product_id}: Skip - only {ticks_in_spread} ticks in spread")
        return None
    
    # Calculate our positions
    our_buy, our_sell, our_spread_pct = calculate_positions(best_bid, best_ask, tick_size)
    
    if our_buy == 0:
        if verbose:
            print(f"  {product_id}: Skip - spread {spread_pct*100:.4f}% too tight for profit")
        return None
    
    profit_margin = our_spread_pct - (2 * FEE_RATE)
    
    if verbose:
        print(f"  {product_id}: Spread {spread_pct*100:.3f}%, Our spread {our_spread_pct*100:.3f}%, Margin {profit_margin*100:.3f}%")
        print(f"    Positioning: BUY ${our_buy:.6f} (>{best_bid:.6f}) | SELL ${our_sell:.6f} (<{best_ask:.6f})")
        print(f"    Monitoring activity for {ACTIVITY_MONITOR_SECONDS}s...")
    
    # CRITICAL: Monitor for actual trading activity
    buy_activity, sell_activity = monitor_activity(product_id, our_buy, our_sell)
    
    if verbose:
        print(f"    Activity: {buy_activity} buys (would fill our sell), {sell_activity} sells (would fill our buy)")
    
    # Need activity on BOTH sides
    if buy_activity == 0 or sell_activity == 0:
        if verbose:
            print(f"    ❌ Insufficient activity - skipping")
        return None
    
    # Success! This token has spread AND activity
    return TokenCandidate(
        product_id=product_id,
        mid_price=mid,
        best_bid=best_bid,
        best_ask=best_ask,
        our_buy_price=our_buy,
        our_sell_price=our_sell,
        spread_pct=spread_pct,
        our_spread_pct=our_spread_pct,
        profit_margin_pct=profit_margin,
        tick_size=tick_size,
        ticks_in_spread=ticks_in_spread,
        base_increment=product.get('base_increment', '?'),
        volume_24h=volume,
        buy_activity=buy_activity,
        sell_activity=sell_activity,
        activity_duration=ACTIVITY_MONITOR_SECONDS
    )


def quick_filter(products: List[Dict]) -> List[Dict]:
    """Quick pre-filter based on volume and basic spread check."""
    filtered = []
    
    for p in products:
        # Volume check
        vol_str = p.get('volume_24h', '') or '0'
        try:
            volume = float(vol_str)
        except:
            continue
        
        if volume < MIN_VOLUME_24H:
            continue
        
        filtered.append(p)
    
    return filtered


def main():
    print("=" * 80)
    print("SOPHISTICATED TOKEN SCANNER - SPREAD + ACTIVITY VALIDATION")
    print("=" * 80)
    print()
    print(f"Requirements:")
    print(f"  • Spread > {MIN_SPREAD_PCT*100:.2f}% (covers 2x {FEE_RATE*100:.3f}% fee)")
    print(f"  • Volume > ${MIN_VOLUME_24H:,}/day")
    print(f"  • Can position STRICTLY inside both bid and ask")
    print(f"  • See market orders on BOTH sides within {ACTIVITY_MONITOR_SECONDS}s")
    print()
    
    # Get all products
    print("Fetching all USD pairs...")
    products = get_all_usd_products()
    print(f"Found {len(products)} USD pairs")
    
    # Quick filter
    print("Quick filtering by volume...")
    candidates_pool = quick_filter(products)
    print(f"Volume filter: {len(candidates_pool)} pairs have >${MIN_VOLUME_24H/1000:.0f}k volume")
    print()
    
    # Check spreads first (fast)
    print("Checking spreads...")
    spread_candidates = []
    
    for p in candidates_pool:
        pid = p.get('product_id', '')
        
        book_data = get_order_book(pid)
        if not book_data:
            continue
        
        pricebook = book_data.get('pricebook', {})
        bids = pricebook.get('bids', [])
        asks = pricebook.get('asks', [])
        
        if not bids or not asks:
            continue
        
        best_bid = float(bids[0]['price'])
        best_ask = float(asks[0]['price'])
        
        if best_bid <= 0 or best_ask <= 0:
            continue
        
        mid = (best_bid + best_ask) / 2
        tick_size = float(p.get('quote_increment', '0.01'))
        
        our_buy, our_sell, our_spread_pct = calculate_positions(best_bid, best_ask, tick_size)
        
        if our_buy > 0:
            profit_margin = our_spread_pct - (2 * FEE_RATE)
            vol_str = p.get('volume_24h', '') or '0'
            volume = float(vol_str) if vol_str else 0
            
            spread_candidates.append({
                'product': p,
                'our_buy': our_buy,
                'our_sell': our_sell,
                'our_spread_pct': our_spread_pct,
                'profit_margin': profit_margin,
                'volume': volume
            })
        
        time.sleep(0.05)  # Rate limit
    
    # Sort by volume (prioritize liquid markets)
    spread_candidates.sort(key=lambda x: x['volume'], reverse=True)
    
    print(f"Found {len(spread_candidates)} pairs with sufficient spread")
    print()
    
    if not spread_candidates:
        print("No candidates found with sufficient spread!")
        return
    
    # Now do deep activity scan on top candidates
    print("=" * 80)
    print(f"DEEP ACTIVITY SCAN (top {min(20, len(spread_candidates))} by volume)")
    print(f"Monitoring each for {ACTIVITY_MONITOR_SECONDS}s...")
    print("=" * 80)
    print()
    
    final_candidates: List[TokenCandidate] = []
    
    for i, sc in enumerate(spread_candidates[:20]):
        product = sc['product']
        pid = product.get('product_id', '')
        
        print(f"[{i+1}/{min(20, len(spread_candidates))}] {pid}")
        print(f"  Volume: ${sc['volume']:,.0f}/day")
        print(f"  Our spread: {sc['our_spread_pct']*100:.3f}% (margin: {sc['profit_margin']*100:.3f}%)")
        
        candidate = scan_token(product, verbose=True)
        
        if candidate:
            print(f"  ✅ PASSED - Activity confirmed!")
            final_candidates.append(candidate)
        else:
            print(f"  ❌ Failed activity test")
        
        print()
    
    # Results
    print("=" * 80)
    print("FINAL CANDIDATES")
    print("=" * 80)
    print()
    
    if not final_candidates:
        print("❌ No tokens passed all filters!")
        print()
        print("This means no tokens currently have:")
        print("  1. Sufficient spread for profit")
        print("  2. Active market orders on BOTH sides")
        print()
        print("Try again later when markets are more active.")
        return
    
    # Sort by activity score
    final_candidates.sort(key=lambda x: (x.buy_activity + x.sell_activity, x.profit_margin_pct), reverse=True)
    
    print(f"{'Pair':15s} {'Margin':>8s} {'Vol 24h':>12s} {'Buys':>6s} {'Sells':>6s} {'Size Inc':>10s}")
    print("-" * 70)
    
    for c in final_candidates:
        if c.volume_24h >= 1_000_000:
            vol_str = f"${c.volume_24h/1_000_000:.2f}M"
        else:
            vol_str = f"${c.volume_24h/1_000:.1f}K"
        
        print(f"{c.product_id:15s} {c.profit_margin_pct*100:>7.3f}% {vol_str:>12s} {c.buy_activity:>6d} {c.sell_activity:>6d} {c.base_increment:>10s}")
    
    print()
    print("=" * 80)
    print("TOP RECOMMENDATION")
    print("=" * 80)
    
    best = final_candidates[0]
    print()
    print(f"  🏆 {best.product_id}")
    print(f"     Price: ${best.mid_price:.6f}")
    print(f"     Our BUY:  ${best.our_buy_price:.6f} (above best bid ${best.best_bid:.6f})")
    print(f"     Our SELL: ${best.our_sell_price:.6f} (below best ask ${best.best_ask:.6f})")
    print(f"     Profit Margin: {best.profit_margin_pct*100:.3f}%")
    print(f"     Activity: {best.buy_activity} buys, {best.sell_activity} sells in {best.activity_duration}s")
    print(f"     Volume: ${best.volume_24h:,.0f}/day")
    print(f"     Size Increment: {best.base_increment}")
    print()
    
    # Save results
    output = {
        "scan_time": datetime.now().isoformat(),
        "parameters": {
            "min_spread_pct": MIN_SPREAD_PCT,
            "min_volume_24h": MIN_VOLUME_24H,
            "activity_monitor_seconds": ACTIVITY_MONITOR_SECONDS,
            "fee_rate": FEE_RATE
        },
        "candidates": [
            {
                "product_id": c.product_id,
                "mid_price": c.mid_price,
                "our_buy_price": c.our_buy_price,
                "our_sell_price": c.our_sell_price,
                "profit_margin_pct": c.profit_margin_pct,
                "volume_24h": c.volume_24h,
                "buy_activity": c.buy_activity,
                "sell_activity": c.sell_activity,
                "base_increment": c.base_increment,
                "tick_size": c.tick_size
            }
            for c in final_candidates
        ]
    }
    
    with open("token_scan_results.json", "w") as f:
        json.dump(output, f, indent=2)
    
    print(f"Results saved to token_scan_results.json")


if __name__ == "__main__":
    main()
