#!/usr/bin/env python3
"""
Spread Scanner - Find Trading Pairs with Wide Spreads

Scans Coinbase trading pairs to find those with spreads wide enough
for profitable market making.

Usage:
    python -m market_making.spread_scanner [options]
    
Options:
    --min_spread PCT      Minimum spread % to show (default: 0.06)
    --fee_rate PCT        Fee rate % for profitability calc (default: 0.025)
    --quote USD           Quote currency to filter by (default: USD)
    --top N               Show top N pairs by spread (default: 20)
    --all                 Scan all pairs (not just USD pairs)
    --volume              Sort by volume instead of spread
"""

import argparse
import requests
import time
from dataclasses import dataclass
from typing import List, Optional, Dict
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from .order_book import CoinbaseOrderBook


@dataclass
class SpreadResult:
    """Result of spread analysis for a trading pair"""
    product_id: str
    best_bid: float
    best_ask: float
    mid_price: float
    spread: float
    spread_pct: float
    bid_size: float
    ask_size: float
    is_profitable: bool
    expected_profit_pct: float
    volume_24h: float = 0.0
    volume_24h_usd: float = 0.0
    
    def __str__(self) -> str:
        profit_indicator = "✅" if self.is_profitable else "❌"
        vol_str = self._format_volume(self.volume_24h_usd)
        return (f"{profit_indicator} {self.product_id:12} | "
                f"Spread: {self.spread_pct:7.4f}% | "
                f"Vol24h: {vol_str:>10} | "
                f"Profit: {self.expected_profit_pct:+7.4f}%")
    
    def _format_volume(self, vol: float) -> str:
        """Format volume in human-readable format"""
        if vol >= 1_000_000:
            return f"${vol/1_000_000:.2f}M"
        elif vol >= 1_000:
            return f"${vol/1_000:.1f}K"
        else:
            return f"${vol:.0f}"


class SpreadScanner:
    """
    Scans Coinbase trading pairs for wide spreads.
    """
    
    def __init__(
        self,
        fee_rate: float = 0.00025,
        min_spread_pct: float = 0.0006,
        quote_currency: Optional[str] = "USD"
    ):
        """
        Initialize scanner.
        
        Args:
            fee_rate: Expected maker fee rate (0.00025 = 0.025%)
            min_spread_pct: Minimum spread to consider profitable
            quote_currency: Filter pairs by quote currency (None = all)
        """
        self.fee_rate = fee_rate
        self.min_spread_pct = min_spread_pct
        self.quote_currency = quote_currency
        self.base_url = "https://api.coinbase.com"
        
        # Minimum spread for breakeven = 2 * fee_rate
        self.breakeven_spread = 2 * fee_rate
        
        # Cache for product info (includes volume)
        self._product_info: Dict[str, Dict] = {}
    
    def get_all_products(self) -> List[Dict]:
        """Fetch all available trading pairs from Coinbase."""
        try:
            url = f"{self.base_url}/api/v3/brokerage/market/products"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            products = data.get('products', [])
            
            # Filter by quote currency if specified
            if self.quote_currency:
                products = [
                    p for p in products 
                    if p.get('quote_currency_id') == self.quote_currency
                    and p.get('status') == 'online'
                ]
            else:
                products = [p for p in products if p.get('status') == 'online']
            
            # Cache product info for volume lookup
            for p in products:
                self._product_info[p['product_id']] = p
            
            return products
            
        except Exception as e:
            print(f"❌ Failed to fetch products: {e}")
            return []
    
    def analyze_spread(self, product_id: str) -> Optional[SpreadResult]:
        """
        Analyze the spread for a single trading pair.
        
        Args:
            product_id: Trading pair (e.g., "ZEC-USD")
        
        Returns:
            SpreadResult or None if failed
        """
        try:
            fetcher = CoinbaseOrderBook(product_id=product_id)
            book = fetcher.fetch_order_book(limit=5)
            
            if not book.best_bid or not book.best_ask:
                return None
            
            spread_pct = book.spread_percent / 100  # Convert to decimal
            
            # Calculate expected profit (spread - 2*fees)
            expected_profit_pct = (spread_pct - self.breakeven_spread) * 100
            
            # Get volume from cached product info
            product_info = self._product_info.get(product_id, {})
            volume_24h = float(product_info.get('volume_24h', 0) or 0)
            volume_24h_usd = volume_24h * book.mid_price
            
            return SpreadResult(
                product_id=product_id,
                best_bid=book.best_bid.price,
                best_ask=book.best_ask.price,
                mid_price=book.mid_price,
                spread=book.spread,
                spread_pct=book.spread_percent,
                bid_size=book.best_bid.size,
                ask_size=book.best_ask.size,
                is_profitable=spread_pct > self.breakeven_spread,
                expected_profit_pct=expected_profit_pct,
                volume_24h=volume_24h,
                volume_24h_usd=volume_24h_usd
            )
            
        except Exception as e:
            # Silently skip failed pairs
            return None
    
    def scan_all(self, max_workers: int = 10, sort_by: str = "spread", min_volume_usd: float = 0) -> List[SpreadResult]:
        """
        Scan all trading pairs for spreads.
        
        Args:
            max_workers: Number of concurrent threads
            sort_by: "spread" or "volume" or "score" (spread * log(volume))
            min_volume_usd: Minimum 24h volume in USD to include
        
        Returns:
            List of SpreadResult sorted by specified criteria
        """
        products = self.get_all_products()
        
        if not products:
            print("❌ No products found")
            return []
        
        print(f"📊 Scanning {len(products)} trading pairs...")
        print()
        
        results = []
        failed = 0
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self.analyze_spread, p['product_id']): p['product_id']
                for p in products
            }
            
            for i, future in enumerate(as_completed(futures)):
                product_id = futures[future]
                try:
                    result = future.result()
                    if result:
                        results.append(result)
                except Exception:
                    failed += 1
                
                # Progress indicator
                if (i + 1) % 20 == 0:
                    print(f"  Scanned {i + 1}/{len(products)} pairs...", end='\r')
        
        print(f"  Scanned {len(products)} pairs, {len(results)} successful, {failed} failed")
        print()
        
        # Filter by minimum volume
        if min_volume_usd > 0:
            before = len(results)
            results = [r for r in results if r.volume_24h_usd >= min_volume_usd]
            print(f"  Filtered to {len(results)} pairs with volume >= ${min_volume_usd:,.0f}")
            print()
        
        # Sort results
        import math
        if sort_by == "volume":
            results.sort(key=lambda x: x.volume_24h_usd, reverse=True)
        elif sort_by == "spread":
            results.sort(key=lambda x: x.spread_pct, reverse=True)
        elif sort_by == "profit_volume":
            # Direct product: profit × volume (best balance)
            results.sort(key=lambda x: x.expected_profit_pct * x.volume_24h_usd, reverse=True)
        else:  # Default: score (profit × volume^1.5)
            # Volume exponent 1.5 weights toward higher liquidity, away from volatile low-volume pairs
            results.sort(key=lambda x: x.expected_profit_pct * (x.volume_24h_usd ** 1.5), reverse=True)
        
        return results
    
    def print_results(
        self,
        results: List[SpreadResult],
        top_n: int = 20,
        show_all: bool = False
    ):
        """Print formatted results."""
        if not results:
            print("❌ No results to display")
            return
        
        profitable = [r for r in results if r.is_profitable]
        
        print("=" * 70)
        print("📈 SPREAD SCANNER RESULTS")
        print("=" * 70)
        print(f"Fee Rate: {self.fee_rate * 100:.4f}%")
        print(f"Breakeven Spread: {self.breakeven_spread * 100:.4f}%")
        print(f"Total Pairs Scanned: {len(results)}")
        print(f"Profitable Pairs: {len(profitable)}")
        print("-" * 70)
        print()
        
        if profitable:
            print("✅ PROFITABLE PAIRS (spread > breakeven):")
            print("-" * 70)
            for result in profitable[:top_n]:
                print(result)
            
            if len(profitable) > top_n:
                print(f"  ... and {len(profitable) - top_n} more")
            print()
        else:
            print("⚠️  No pairs with spreads wide enough for profitability")
            print()
        
        if show_all or not profitable:
            print("📊 TOP SPREADS (may not be profitable):")
            print("-" * 70)
            for result in results[:top_n]:
                print(result)
            print()
        
        # Summary stats
        if profitable:
            import math
            best = profitable[0]
            avg_profit = sum(r.expected_profit_pct for r in profitable) / len(profitable)
            
            # Find best by different metrics
            best_by_vol = max(profitable, key=lambda x: x.volume_24h_usd)
            best_by_spread = max(profitable, key=lambda x: x.spread_pct)
            best_opportunity = max(profitable, key=lambda x: x.expected_profit_pct * (x.volume_24h_usd ** 1.5))
            
            print("=" * 70)
            print("📊 SUMMARY")
            print("=" * 70)
            print(f"🎯 BEST OPPORTUNITY (profit×volume^1.5): {best_opportunity.product_id}")
            print(f"  Spread: {best_opportunity.spread_pct:.4f}%")
            print(f"  Expected Profit: {best_opportunity.expected_profit_pct:+.4f}% per round")
            print(f"  24h Volume: ${best_opportunity.volume_24h_usd:,.0f}")
            print(f"  Mid Price: ${best_opportunity.mid_price:.4f}")
            print(f"  Opportunity Score: {best_opportunity.expected_profit_pct * (best_opportunity.volume_24h_usd ** 1.5) / 1e6:.2f}M")
            print()
            print(f"Best by Spread: {best_by_spread.product_id} ({best_by_spread.spread_pct:.4f}%, Vol: ${best_by_spread.volume_24h_usd:,.0f})")
            print(f"Best by Volume: {best_by_vol.product_id} (Vol: ${best_by_vol.volume_24h_usd:,.0f}, Profit: {best_by_vol.expected_profit_pct:+.4f}%)")
            print()
            print(f"Average Profit (profitable pairs): {avg_profit:+.4f}%")
            print("=" * 70)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Scan Coinbase pairs for wide spreads",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument("--min_spread", type=float, default=0.06,
                       help="Minimum spread %% to highlight (default: 0.06)")
    parser.add_argument("--fee_rate", type=float, default=0.025,
                       help="Fee rate %% (default: 0.025)")
    parser.add_argument("--quote", type=str, default="USD",
                       help="Quote currency filter (default: USD)")
    parser.add_argument("--top", type=int, default=20,
                       help="Show top N pairs (default: 20)")
    parser.add_argument("--all", action="store_true",
                       help="Scan all pairs (not just USD)")
    parser.add_argument("--show-all", action="store_true",
                       help="Show all results, not just profitable")
    parser.add_argument("--sort", type=str, default="score",
                       choices=["spread", "volume", "score", "profit_volume"],
                       help="Sort by: spread, volume, score (profit×vol^1.5), profit_volume (profit×vol) (default: score)")
    parser.add_argument("--min-volume", type=float, default=0,
                       help="Minimum 24h volume in USD (default: 0)")
    parser.add_argument("--min-precision", type=int, default=0,
                       help="Minimum price decimal places for market making (default: 0)")
    
    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()
    
    # Convert percentages to decimals
    fee_rate = args.fee_rate / 100
    min_spread = args.min_spread / 100
    
    quote = None if args.all else args.quote
    
    print()
    print("🔍 COINBASE SPREAD SCANNER")
    print("=" * 70)
    print(f"Quote Currency: {quote or 'ALL'}")
    print(f"Fee Rate: {args.fee_rate:.4f}%")
    print(f"Min Spread for Profit: {(2 * args.fee_rate):.4f}%")
    print("=" * 70)
    print()
    
    scanner = SpreadScanner(
        fee_rate=fee_rate,
        min_spread_pct=min_spread,
        quote_currency=quote
    )
    
    results = scanner.scan_all(sort_by=args.sort, min_volume_usd=args.min_volume)
    scanner.print_results(results, top_n=args.top, show_all=args.show_all)


if __name__ == "__main__":
    main()
