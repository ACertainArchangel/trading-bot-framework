"""
Spread vs Precision Scanner

Scans all Coinbase USD pairs to find coins where:
- The tick size (minimum price increment) is FINER than the typical spread
- This indicates market making opportunity (can undercut within the spread)

Example: If price is $45.7234 (4 decimal precision) but spread is $0.01,
there's room for 100 price levels within the spread!
"""

import requests
import time
import json
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from decimal import Decimal


@dataclass
class PairAnalysis:
    """Analysis results for a trading pair"""
    product_id: str
    mid_price: float
    best_bid: float
    best_ask: float
    spread: float
    spread_pct: float
    tick_size: float  # Minimum price increment (quote_increment)
    ticks_in_spread: int  # How many tick levels fit in the spread
    base_increment: float  # Minimum size increment
    volume_24h: float
    status: str
    profitable_for_mm: bool  # spread > 2 * fee (0.05%)


def get_all_usd_products() -> List[Dict]:
    """Fetch all USD trading pairs from Coinbase."""
    url = "https://api.coinbase.com/api/v3/brokerage/market/products"
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Filter for USD pairs that are trading
        usd_products = [
            p for p in data.get('products', [])
            if p.get('quote_currency_id') == 'USD' 
            and p.get('status') == 'online'
            and not p.get('is_disabled', False)
            and not p.get('trading_disabled', False)
        ]
        
        return usd_products
    except Exception as e:
        print(f"Error fetching products: {e}")
        return []


def get_order_book(product_id: str) -> Optional[Dict]:
    """Fetch order book for a product."""
    url = f"https://api.coinbase.com/api/v3/brokerage/market/product_book"
    params = {"product_id": product_id, "limit": 5}
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return None


def analyze_precision(price_str: str) -> int:
    """Get decimal precision from a price string."""
    if '.' not in price_str:
        return 0
    return len(price_str.split('.')[-1].rstrip('0')) or 0


def analyze_pair(product: Dict) -> Optional[PairAnalysis]:
    """Analyze a single trading pair."""
    product_id = product.get('product_id', '')
    
    # Get order book
    book_data = get_order_book(product_id)
    if not book_data:
        return None
    
    pricebook = book_data.get('pricebook', {})
    bids = pricebook.get('bids', [])
    asks = pricebook.get('asks', [])
    
    if not bids or not asks:
        return None
    
    best_bid = float(bids[0].get('price', 0))
    best_ask = float(asks[0].get('price', 0))
    
    if best_bid <= 0 or best_ask <= 0:
        return None
    
    mid_price = (best_bid + best_ask) / 2
    spread = best_ask - best_bid
    spread_pct = spread / mid_price if mid_price > 0 else 0
    
    # Get tick size (quote_increment) from product info
    quote_increment = float(product.get('quote_increment', '0.01'))
    base_increment = float(product.get('base_increment', '0.0001'))
    
    # Calculate how many ticks fit in the spread
    ticks_in_spread = int(spread / quote_increment) if quote_increment > 0 else 0
    
    # Get 24h volume (handle empty strings)
    vol_str = product.get('volume_24h', '0') or '0'
    volume_24h = float(vol_str) if vol_str else 0
    
    # Is it profitable for market making? (spread > 2 * maker fee of 0.025%)
    min_spread_for_profit = 0.0005  # 0.05% (double the 0.025% fee)
    profitable = spread_pct > min_spread_for_profit and ticks_in_spread >= 2
    
    return PairAnalysis(
        product_id=product_id,
        mid_price=mid_price,
        best_bid=best_bid,
        best_ask=best_ask,
        spread=spread,
        spread_pct=spread_pct,
        tick_size=quote_increment,
        ticks_in_spread=ticks_in_spread,
        base_increment=base_increment,
        volume_24h=volume_24h,
        status=product.get('status', 'unknown'),
        profitable_for_mm=profitable
    )


def main():
    """Scan all USD pairs and rank by spread/tick opportunity."""
    print("=" * 80)
    print("COINBASE USD PAIRS - SPREAD vs TICK PRECISION SCANNER")
    print("=" * 80)
    print()
    print("Looking for pairs where tick_size << spread (many price levels to undercut)")
    print()
    
    # Get all USD products
    print("Fetching all USD trading pairs...")
    products = get_all_usd_products()
    print(f"Found {len(products)} USD pairs")
    print()
    
    # Analyze each pair
    results: List[PairAnalysis] = []
    
    for i, product in enumerate(products):
        product_id = product.get('product_id', '')
        print(f"\r  Analyzing {i+1}/{len(products)}: {product_id:20s}", end='', flush=True)
        
        analysis = analyze_pair(product)
        if analysis:
            results.append(analysis)
        
        # Rate limit - be nice to the API
        time.sleep(0.1)
    
    print("\r" + " " * 60)  # Clear line
    print()
    
    # Filter for pairs with multiple ticks in spread AND decent volume
    opportunities = [r for r in results if r.ticks_in_spread >= 3]
    
    # Sort by ticks_in_spread (more room to work = better)
    opportunities.sort(key=lambda x: (x.profitable_for_mm, x.ticks_in_spread, x.volume_24h), reverse=True)
    
    # Display results
    print("=" * 100)
    print("TOP OPPORTUNITIES: Pairs with tick_size << spread")
    print("(More ticks in spread = more room to undercut competitors)")
    print("=" * 100)
    print()
    print(f"{'Pair':15s} {'Price':>12s} {'Spread':>10s} {'Spread%':>8s} {'Tick':>10s} {'Ticks':>6s} {'Vol 24h':>14s} {'MM?':>4s}")
    print("-" * 100)
    
    for r in opportunities[:50]:  # Top 50
        mm_flag = "✓" if r.profitable_for_mm else ""
        
        # Format price based on magnitude
        if r.mid_price >= 1000:
            price_str = f"${r.mid_price:,.2f}"
        elif r.mid_price >= 1:
            price_str = f"${r.mid_price:.4f}"
        else:
            price_str = f"${r.mid_price:.6f}"
        
        # Format spread
        if r.spread >= 0.01:
            spread_str = f"${r.spread:.4f}"
        else:
            spread_str = f"${r.spread:.6f}"
        
        # Format tick
        tick_str = f"${r.tick_size:.6f}".rstrip('0').rstrip('.')
        
        # Format volume
        if r.volume_24h >= 1_000_000:
            vol_str = f"${r.volume_24h/1_000_000:.2f}M"
        elif r.volume_24h >= 1_000:
            vol_str = f"${r.volume_24h/1_000:.1f}K"
        else:
            vol_str = f"${r.volume_24h:.0f}"
        
        print(f"{r.product_id:15s} {price_str:>12s} {spread_str:>10s} {r.spread_pct*100:>7.3f}% {tick_str:>10s} {r.ticks_in_spread:>6d} {vol_str:>14s} {mm_flag:>4s}")
    
    print()
    print("=" * 100)
    print("SUMMARY")
    print("=" * 100)
    print(f"Total USD pairs analyzed: {len(results)}")
    print(f"Pairs with 3+ ticks in spread: {len(opportunities)}")
    print(f"Pairs profitable for MM (spread > 0.05%): {len([r for r in results if r.profitable_for_mm])}")
    print()
    
    # Show the BEST opportunities (high ticks + high volume + profitable)
    best = [r for r in opportunities if r.profitable_for_mm and r.volume_24h > 10000]
    best.sort(key=lambda x: x.ticks_in_spread * x.spread_pct, reverse=True)
    
    print("=" * 100)
    print("🏆 BEST MM CANDIDATES (profitable + volume + many ticks)")
    print("=" * 100)
    print()
    
    for r in best[:20]:
        print(f"  {r.product_id:15s}")
        print(f"      Price: ${r.mid_price:.6f}")
        print(f"      Spread: ${r.spread:.6f} ({r.spread_pct*100:.4f}%)")
        print(f"      Tick size: ${r.tick_size}")
        print(f"      Ticks in spread: {r.ticks_in_spread} (can undercut {r.ticks_in_spread-1}x before crossing)")
        print(f"      Volume 24h: ${r.volume_24h:,.2f}")
        print(f"      Base increment: {r.base_increment}")
        print()
    
    # Save full results to JSON
    output = {
        "scan_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_pairs": len(results),
        "opportunities": [
            {
                "product_id": r.product_id,
                "mid_price": r.mid_price,
                "spread": r.spread,
                "spread_pct": r.spread_pct,
                "tick_size": r.tick_size,
                "ticks_in_spread": r.ticks_in_spread,
                "base_increment": r.base_increment,
                "volume_24h": r.volume_24h,
                "profitable_for_mm": r.profitable_for_mm
            }
            for r in opportunities
        ]
    }
    
    with open("spread_precision_scan.json", "w") as f:
        json.dump(output, f, indent=2)
    print(f"Full results saved to spread_precision_scan.json")


if __name__ == "__main__":
    main()
