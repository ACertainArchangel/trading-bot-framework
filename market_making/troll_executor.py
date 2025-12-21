"""
TROLL-USD Aggressive Market Maker

Optimized for TROLL-USD's wide spread (~0.4%) and fine tick size ($0.00001).
With 14 ticks in the spread, we can undercut aggressively by 2-3 ticks.

Uses secrets3.json for credentials.
"""

import os
import sys
import json
import time
import math
import signal
import argparse
import requests
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, ROUND_DOWN
from typing import Optional, Dict, Tuple, Callable, List

try:
    from .order_book import CoinbaseOrderBook, OrderBook
except ImportError:
    from order_book import CoinbaseOrderBook, OrderBook


# =============================================================================
# CONFIGURATION - TROLL-USD SPECIFIC
# =============================================================================

PRODUCT_ID = "TROLL-USD"
SECRETS_FILE = "secrets/secrets3.json"

# TROLL-USD has:
# - Quote increment (tick): $0.00001 (5 decimals)
# - Base increment (size): 0.1 TROLL (1 decimal)
# - Typical spread: ~0.4% (14 ticks)

SIZE_DECIMALS = 1        # 0.1 TROLL minimum
PRICE_DECIMALS = 5       # $0.00001 tick
MIN_TICK = 0.00001

# AGGRESSIVE SETTINGS - undercut by more than 1 tick since we have room
UNDERCUT_TICKS = 2       # Jump 2 ticks inside spread (still leaving 10+ ticks margin)
FEE_RATE = 0.00025       # 0.025% maker fee


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class Balance:
    currency: str
    available: float
    hold: float = 0.0


@dataclass
class OrderFill:
    order_id: str
    side: str
    product_id: str
    filled_size: float
    filled_value: float
    average_price: float
    fee_amount: float
    fee_rate: float
    timestamp: datetime
    raw_response: Dict = field(default_factory=dict)
    
    def validate_fee(self, expected_rate: float = FEE_RATE, tolerance: float = 0.0001):
        """Validate fee rate is within expected bounds."""
        if abs(self.fee_rate - expected_rate) > tolerance:
            raise Exception(
                f"Fee validation failed for {self.side}: "
                f"expected {expected_rate*100:.4f}% ± {tolerance*100:.4f}%, "
                f"got {self.fee_rate*100:.4f}%"
            )


@dataclass
class TradeResult:
    round_id: str
    buy_fill: OrderFill
    sell_fill: OrderFill
    gross_profit: float
    total_fees: float
    net_profit: float
    net_profit_pct: float
    duration_seconds: float


# =============================================================================
# COINBASE CLIENT
# =============================================================================

class TrollClient:
    """Coinbase client optimized for TROLL-USD."""
    
    def __init__(self, api_key_name: str, api_private_key: str, logger: Callable[[str], None]):
        self.api_key_name = api_key_name
        self.api_private_key = api_private_key
        self.base_url = "https://api.coinbase.com"
        self._log = logger
    
    def _generate_jwt_token(self, method: str, request_path: str) -> str:
        from coinbase import jwt_generator
        jwt_uri = jwt_generator.format_jwt_uri(method, request_path)
        return jwt_generator.build_rest_jwt(jwt_uri, self.api_key_name, self.api_private_key)
    
    def _make_request(self, method: str, endpoint: str, body: dict = None, retries: int = 3) -> Dict:
        last_error = None
        for attempt in range(retries):
            try:
                token = self._generate_jwt_token(method, endpoint)
                headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
                url = f"{self.base_url}{endpoint}"
                
                if method == 'GET':
                    resp = requests.get(url, headers=headers, timeout=10)
                else:
                    resp = requests.post(url, headers=headers, json=body, timeout=10)
                
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                last_error = e
                if attempt < retries - 1:
                    time.sleep(0.5)
        raise Exception(f"Request failed after {retries} attempts: {last_error}")
    
    def get_balances(self) -> Tuple[Balance, Balance]:
        """Get USD and TROLL balances."""
        result = self._make_request('GET', '/api/v3/brokerage/accounts')
        
        usd_bal = None
        troll_bal = None
        
        for account in result.get('accounts', []):
            currency = account['currency']
            available = float(account['available_balance']['value'])
            hold = float(account.get('hold', {}).get('value', 0))
            
            if currency == 'USD':
                usd_bal = Balance('USD', available, hold)
            elif currency == 'TROLL':
                troll_bal = Balance('TROLL', available, hold)
        
        if not usd_bal:
            raise Exception("No USD account found")
        if not troll_bal:
            raise Exception("No TROLL account found")
        
        return (usd_bal, troll_bal)
    
    def place_limit_order(self, side: str, size: float, price: float, post_only: bool = True) -> str:
        """Place a limit order with TROLL-specific precision."""
        # Round size to 1 decimal (0.1 TROLL increments)
        size_decimal = Decimal(str(size))
        size_rounded = float(size_decimal.quantize(Decimal('0.1'), rounding=ROUND_DOWN))
        
        size_str = f"{size_rounded:.1f}"
        price_str = f"{price:.5f}"
        
        order_data = {
            "client_order_id": f"troll_{side.lower()}_{int(time.time()*1000)}",
            "product_id": PRODUCT_ID,
            "side": side.upper(),
            "order_configuration": {
                "limit_limit_gtc": {
                    "base_size": size_str,
                    "limit_price": price_str,
                    "post_only": post_only
                }
            }
        }
        
        self._log(f"📤 {side}: {size_str} TROLL @ ${price_str}")
        
        result = self._make_request('POST', '/api/v3/brokerage/orders', order_data)
        
        if 'error_response' in result:
            error = result['error_response']
            raise Exception(f"Order rejected: {error.get('message', error)}")
        
        order_id = result['success_response']['order_id']
        return order_id
    
    def get_order_status(self, order_id: str) -> Dict:
        result = self._make_request('GET', f'/api/v3/brokerage/orders/historical/{order_id}')
        return result.get('order', {})
    
    def cancel_order(self, order_id: str) -> bool:
        try:
            self._make_request('POST', '/api/v3/brokerage/orders/batch_cancel', {"order_ids": [order_id]})
            return True
        except:
            return False


# =============================================================================
# TROLL MARKET MAKER
# =============================================================================

class TrollMarketMaker:
    """
    Aggressive market maker for TROLL-USD.
    
    Strategy:
    - Undercut by 2 ticks (aggressive since we have 14 ticks room)
    - Place both orders simultaneously
    - Continuously requote if undercut
    - Break-even requote after timeout
    """
    
    def __init__(self, api_key_name: str, api_private_key: str, 
                 min_trade_usd: float = 10.0, max_trade_usd: float = 100.0,
                 logger: Optional[Callable[[str], None]] = None):
        
        self._log = logger or self._default_logger
        self.min_trade_usd = min_trade_usd
        self.max_trade_usd = max_trade_usd
        
        self.client = TrollClient(api_key_name, api_private_key, self._log)
        self.order_book = CoinbaseOrderBook(product_id=PRODUCT_ID)
        
        # Stats
        self.total_profit = 0.0
        self.total_fees = 0.0
        self.rounds_completed = 0
        
        self._log("=" * 60)
        self._log("🧌 TROLL-USD AGGRESSIVE MARKET MAKER")
        self._log("=" * 60)
        self._log(f"Undercut: {UNDERCUT_TICKS} ticks (${UNDERCUT_TICKS * MIN_TICK:.5f})")
        self._log(f"Trade size: ${min_trade_usd:.2f} - ${max_trade_usd:.2f}")
        self._log("=" * 60)
    
    @staticmethod
    def _default_logger(msg: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {msg}")
    
    def get_trade_size(self, mid_price: float) -> Tuple[float, float, float]:
        """Calculate trade size based on portfolio."""
        usd_bal, troll_bal = self.client.get_balances()
        
        usd_available = usd_bal.available
        troll_value = troll_bal.available * mid_price
        
        # Use minimum of USD and TROLL value
        trade_size_usd = min(usd_available, troll_value)
        trade_size_usd = max(trade_size_usd, self.min_trade_usd)
        trade_size_usd = min(trade_size_usd, self.max_trade_usd)
        
        self._log(f"💰 ${usd_available:.2f} USD | {troll_bal.available:.1f} TROLL (${troll_value:.2f})")
        
        return (trade_size_usd, usd_available, troll_value)
    
    def execute_round(self, monitor_timeout: float = 60.0) -> Optional[TradeResult]:
        """Execute one market making round."""
        round_id = f"troll_{int(time.time())}"
        start_time = time.time()
        
        self._log("")
        self._log("=" * 60)
        self._log(f"🚀 ROUND: {round_id}")
        self._log("=" * 60)
        
        # Monitor for opportunity
        analysis = self._find_opportunity(timeout=monitor_timeout)
        if not analysis:
            return None
        
        # Get balances and calculate size
        usd_bal, troll_bal = self.client.get_balances()
        
        buy_size_raw = analysis['trade_size_usd'] / analysis['buy_price']
        # Use min of calculated and available TROLL
        trade_size_raw = min(buy_size_raw, troll_bal.available)
        trade_size = float(Decimal(str(trade_size_raw)).quantize(Decimal('0.1'), rounding=ROUND_DOWN))
        
        if trade_size < 0.1:
            self._log("⚠️  Trade size too small after rounding")
            return None
        
        buy_price = analysis['buy_price']
        sell_price = analysis['sell_price']
        
        self._log(f"📊 Size: {trade_size:.1f} TROLL")
        self._log(f"   BUY  @ ${buy_price:.5f}")
        self._log(f"   SELL @ ${sell_price:.5f}")
        
        # Place both orders
        buy_order_id = None
        sell_order_id = None
        
        try:
            buy_order_id = self.client.place_limit_order("BUY", trade_size, buy_price)
            sell_order_id = self.client.place_limit_order("SELL", trade_size, sell_price)
        except Exception as e:
            self._log(f"❌ Order placement failed: {e}")
            if buy_order_id:
                self.client.cancel_order(buy_order_id)
            if sell_order_id:
                self.client.cancel_order(sell_order_id)
            return None
        
        self._log("✅ Both orders placed!")
        
        # Wait for fills with requoting
        buy_fill, sell_fill = self._wait_for_fills(
            buy_order_id, sell_order_id,
            buy_price, sell_price,
            trade_size
        )
        
        if not buy_fill or not sell_fill:
            self._log("❌ Failed to complete round")
            return None
        
        # VALIDATE FEES
        self._log("")
        self._log("🔍 Validating fees...")
        self._log(f"   BUY:  ${buy_fill.filled_value:.4f}, Fee: ${buy_fill.fee_amount:.6f} ({buy_fill.fee_rate*100:.4f}%)")
        self._log(f"   SELL: ${sell_fill.filled_value:.4f}, Fee: ${sell_fill.fee_amount:.6f} ({sell_fill.fee_rate*100:.4f}%)")
        
        try:
            buy_fill.validate_fee()
            sell_fill.validate_fee()
            self._log("✅ Fees validated")
        except Exception as e:
            self._log(f"⚠️  Fee validation warning: {e}")
            # Continue anyway - fee variance is usually minor
        
        # Calculate results
        gross_profit = sell_fill.filled_value - buy_fill.filled_value
        total_fees = buy_fill.fee_amount + sell_fill.fee_amount
        net_profit = gross_profit - total_fees
        net_profit_pct = net_profit / buy_fill.filled_value * 100
        
        duration = time.time() - start_time
        
        result = TradeResult(
            round_id=round_id,
            buy_fill=buy_fill,
            sell_fill=sell_fill,
            gross_profit=gross_profit,
            total_fees=total_fees,
            net_profit=net_profit,
            net_profit_pct=net_profit_pct,
            duration_seconds=duration
        )
        
        self.total_profit += net_profit
        self.total_fees += total_fees
        self.rounds_completed += 1
        
        # PROFIT VERIFICATION
        if net_profit <= 0:
            self._log("")
            self._log("🚨" * 20)
            self._log("❌ LOSS DETECTED!")
            self._log(f"   Buy:  {buy_fill.filled_size:.1f} @ ${buy_fill.average_price:.5f} = ${buy_fill.filled_value:.4f}")
            self._log(f"   Sell: {sell_fill.filled_size:.1f} @ ${sell_fill.average_price:.5f} = ${sell_fill.filled_value:.4f}")
            self._log(f"   Gross: ${gross_profit:.6f}")
            self._log(f"   Fees:  ${total_fees:.6f}")
            self._log(f"   Net:   ${net_profit:.6f}")
            self._log("🚨" * 20)
            # Don't halt - record the loss and continue
        
        self._log("")
        self._log("=" * 60)
        profit_emoji = "✅" if net_profit > 0 else "❌"
        self._log(f"{profit_emoji} ROUND COMPLETE")
        self._log(f"   Net Profit: ${net_profit:.6f} ({net_profit_pct:.4f}%)")
        self._log(f"   Duration: {duration:.1f}s")
        self._log(f"   Session Total: ${self.total_profit:.4f} ({self.rounds_completed} rounds)")
        self._log("=" * 60)
        
        return result
    
    def _find_opportunity(self, timeout: float) -> Optional[Dict]:
        """Monitor for profitable spread opportunity."""
        start = time.time()
        
        self._log(f"🔍 Monitoring spread (timeout: {timeout}s)...")
        
        while (time.time() - start) < timeout:
            try:
                book = self.order_book.fetch_order_book(limit=5)
                
                if not book.best_bid or not book.best_ask:
                    time.sleep(0.5)
                    continue
                
                best_bid = book.best_bid.price
                best_ask = book.best_ask.price
                mid = book.mid_price
                spread = best_ask - best_bid
                spread_pct = spread / mid
                
                # Aggressive undercut: jump UNDERCUT_TICKS inside
                buy_price = best_bid + (UNDERCUT_TICKS * MIN_TICK)
                
                # Calculate minimum profitable sell price
                min_sell_continuous = buy_price * (1 + FEE_RATE) / (1 - FEE_RATE)
                min_sell_ticks = math.ceil(min_sell_continuous / MIN_TICK)
                min_sell_price = min_sell_ticks * MIN_TICK
                
                # Our sell: best_ask - UNDERCUT_TICKS, but at least min_sell_price
                sell_price = max(best_ask - (UNDERCUT_TICKS * MIN_TICK), min_sell_price)
                
                # Must be below best_ask to be competitive
                if sell_price >= best_ask:
                    time.sleep(0.5)
                    continue
                
                # Calculate profit
                trade_size_usd, _, _ = self.get_trade_size(mid)
                buy_size = trade_size_usd / buy_price
                buy_size_rounded = float(Decimal(str(buy_size)).quantize(Decimal('0.1'), rounding=ROUND_DOWN))
                
                if buy_size_rounded < 0.1:
                    time.sleep(0.5)
                    continue
                
                buy_value = buy_size_rounded * buy_price
                sell_value = buy_size_rounded * sell_price
                buy_fee = buy_value * FEE_RATE
                sell_fee = sell_value * FEE_RATE
                net_profit = (sell_value - buy_value) - (buy_fee + sell_fee)
                net_profit_pct = net_profit / buy_value
                
                # Log spread
                self._log(f"   Spread: {spread_pct*100:.4f}% | Our: BUY ${buy_price:.5f} → SELL ${sell_price:.5f} | Net: {net_profit_pct*100:.4f}%")
                
                if net_profit > 0 and net_profit_pct >= 0.0001:  # At least 0.01%
                    self._log(f"✨ OPPORTUNITY! Expected profit: ${net_profit:.6f}")
                    return {
                        'buy_price': buy_price,
                        'sell_price': sell_price,
                        'min_sell_price': min_sell_price,
                        'trade_size_usd': trade_size_usd,
                        'spread_pct': spread_pct,
                        'expected_profit': net_profit
                    }
                
                time.sleep(1.0)
                
            except Exception as e:
                self._log(f"⚠️  Error: {e}")
                time.sleep(1.0)
        
        self._log("⏰ Timeout - no opportunity found")
        return None
    
    def _wait_for_fills(self, buy_order_id: str, sell_order_id: str,
                        buy_price: float, sell_price: float,
                        trade_size: float) -> Tuple[Optional[OrderFill], Optional[OrderFill]]:
        """Wait for both orders to fill with aggressive requoting.
        
        CRITICAL: This function will NOT exit until BOTH orders are filled.
        One-legged fills will keep requoting until closed out.
        """
        
        buy_fill = None
        sell_fill = None
        current_buy_price = buy_price
        current_sell_price = sell_price
        current_buy_order_id = buy_order_id
        current_sell_order_id = sell_order_id
        
        buy_requotes = 0
        sell_requotes = 0
        MAX_REQUOTES = 15
        REQUOTE_COOLDOWN = 0.5  # Faster requoting for TROLL
        last_buy_requote = 0.0
        last_sell_requote = 0.0
        
        elapsed = 0.0
        BREAKEVEN_TIMEOUT = 15.0  # Drop to break-even after 15s
        breakeven_applied_buy = False
        breakeven_applied_sell = False
        
        while True:
            loop_start = time.time()
            
            # Get current book
            try:
                book = self.order_book.fetch_order_book(limit=5)
                best_bid = book.best_bid.price if book.best_bid else 0
                best_ask = book.best_ask.price if book.best_ask else float('inf')
            except:
                best_bid = 0
                best_ask = float('inf')
            
            # Check BUY status
            if buy_fill is None and current_buy_order_id:
                order = self.client.get_order_status(current_buy_order_id)
                status = order.get('status', 'UNKNOWN')
                
                if status == 'FILLED':
                    filled_size = float(order.get('filled_size', 0))
                    avg_price = float(order.get('average_filled_price', 0))
                    fees = float(order.get('total_fees', 0))
                    fill_value = filled_size * avg_price
                    
                    buy_fill = OrderFill(
                        order_id=current_buy_order_id, side="BUY", product_id=PRODUCT_ID,
                        filled_size=filled_size, filled_value=fill_value,
                        average_price=avg_price, fee_amount=fees,
                        fee_rate=fees/fill_value if fill_value > 0 else 0,
                        timestamp=datetime.utcnow(), raw_response=order
                    )
                    self._log(f"✅ BUY filled: {filled_size:.1f} @ ${avg_price:.5f}")
                    
                elif status in ['CANCELLED', 'EXPIRED', 'FAILED']:
                    # Order is gone - need to replace it!
                    # This can happen if our cancel-for-requote succeeded but new order failed
                    self._log(f"⚠️  BUY order {status} - will replace")
                    current_buy_order_id = None  # Mark as needing replacement
            
            # Check SELL status
            if sell_fill is None and current_sell_order_id:
                order = self.client.get_order_status(current_sell_order_id)
                status = order.get('status', 'UNKNOWN')
                
                if status == 'FILLED':
                    filled_size = float(order.get('filled_size', 0))
                    avg_price = float(order.get('average_filled_price', 0))
                    fees = float(order.get('total_fees', 0))
                    fill_value = filled_size * avg_price
                    
                    sell_fill = OrderFill(
                        order_id=current_sell_order_id, side="SELL", product_id=PRODUCT_ID,
                        filled_size=filled_size, filled_value=fill_value,
                        average_price=avg_price, fee_amount=fees,
                        fee_rate=fees/fill_value if fill_value > 0 else 0,
                        timestamp=datetime.utcnow(), raw_response=order
                    )
                    self._log(f"✅ SELL filled: {filled_size:.1f} @ ${avg_price:.5f}")
                    
                elif status in ['CANCELLED', 'EXPIRED', 'FAILED']:
                    # Order is gone - need to replace it!
                    self._log(f"⚠️  SELL order {status} - will replace")
                    current_sell_order_id = None  # Mark as needing replacement
            
            # Both filled?
            if buy_fill and sell_fill:
                return (buy_fill, sell_fill)
            
            # REQUOTE LOGIC
            
            # BUY: Replace if missing OR requote if undercut
            if buy_fill is None:
                # If order is missing (cancelled/failed), must replace immediately
                if current_buy_order_id is None:
                    # Calculate appropriate price
                    if sell_fill:
                        # SELL filled - use break-even max
                        proceeds = sell_fill.filled_value - sell_fill.fee_amount
                        max_buy = proceeds / (trade_size * (1 + FEE_RATE))
                        new_buy = math.floor(max_buy / MIN_TICK) * MIN_TICK
                    else:
                        # Use current price
                        new_buy = current_buy_price
                    
                    self._log(f"🔄 BUY order missing - replacing @ ${new_buy:.5f}")
                    try:
                        current_buy_order_id = self.client.place_limit_order("BUY", trade_size, new_buy)
                        current_buy_price = new_buy
                    except Exception as e:
                        self._log(f"⚠️  BUY replacement failed: {e}")
                
                # Normal requote logic
                elif (elapsed - last_buy_requote) > REQUOTE_COOLDOWN and buy_requotes < MAX_REQUOTES:
                    if sell_fill:
                        # SELL filled - calculate max buy for break-even
                        proceeds = sell_fill.filled_value - sell_fill.fee_amount
                        max_buy = proceeds / (trade_size * (1 + FEE_RATE))
                        max_buy_price = math.floor(max_buy / MIN_TICK) * MIN_TICK
                        
                        if best_bid > current_buy_price + MIN_TICK:
                            new_buy = min(best_bid + UNDERCUT_TICKS * MIN_TICK, max_buy_price)
                            if new_buy > current_buy_price:
                                self._log(f"🔄 BUY: ${current_buy_price:.5f} → ${new_buy:.5f} (max: ${max_buy_price:.5f})")
                                self.client.cancel_order(current_buy_order_id)
                                try:
                                    current_buy_order_id = self.client.place_limit_order("BUY", trade_size, new_buy)
                                    current_buy_price = new_buy
                                    buy_requotes += 1
                                    last_buy_requote = elapsed
                                except Exception as e:
                                    self._log(f"⚠️  BUY requote failed: {e}")
                                    current_buy_order_id = None  # Will be replaced next loop
                    else:
                        # SELL not filled - check if we can safely requote
                        if best_bid > current_buy_price + MIN_TICK:
                            new_buy = best_bid + UNDERCUT_TICKS * MIN_TICK
                            
                            # Calculate required sell price for this buy
                            min_sell = new_buy * (1 + FEE_RATE) / (1 - FEE_RATE)
                            min_sell_price = math.ceil(min_sell / MIN_TICK) * MIN_TICK
                            
                            # Block if our pending sell is too low
                            if current_sell_price < min_sell_price:
                                self._log(f"⚠️  BUY blocked: need SELL @ ${min_sell_price:.5f}, have ${current_sell_price:.5f}")
                            elif min_sell_price >= best_ask:
                                pass  # No room in market
                            else:
                                self._log(f"🔄 BUY: ${current_buy_price:.5f} → ${new_buy:.5f}")
                                self.client.cancel_order(current_buy_order_id)
                                try:
                                    current_buy_order_id = self.client.place_limit_order("BUY", trade_size, new_buy)
                                    current_buy_price = new_buy
                                    buy_requotes += 1
                                    last_buy_requote = elapsed
                                except Exception as e:
                                    self._log(f"⚠️  BUY requote failed: {e}")
                                    current_buy_order_id = None
            
            # SELL: Replace if missing OR requote if undercut
            if sell_fill is None:
                # If order is missing, must replace immediately
                if current_sell_order_id is None:
                    # Calculate appropriate price
                    if buy_fill:
                        # BUY filled - use break-even min
                        total_cost = buy_fill.filled_value + buy_fill.fee_amount
                        min_sell = total_cost / (trade_size * (1 - FEE_RATE))
                        new_sell = math.ceil(min_sell / MIN_TICK) * MIN_TICK
                    else:
                        # Use current price
                        new_sell = current_sell_price
                    
                    self._log(f"🔄 SELL order missing - replacing @ ${new_sell:.5f}")
                    try:
                        current_sell_order_id = self.client.place_limit_order("SELL", trade_size, new_sell)
                        current_sell_price = new_sell
                    except Exception as e:
                        self._log(f"⚠️  SELL replacement failed: {e}")
                
                # Normal requote logic
                elif (elapsed - last_sell_requote) > REQUOTE_COOLDOWN and sell_requotes < MAX_REQUOTES:
                    if best_ask < current_sell_price - MIN_TICK:
                        # Calculate min sell price
                        if buy_fill:
                            total_cost = buy_fill.filled_value + buy_fill.fee_amount
                            min_sell = total_cost / (trade_size * (1 - FEE_RATE))
                        else:
                            min_sell = current_buy_price * (1 + FEE_RATE) / (1 - FEE_RATE)
                        
                        min_sell_price = math.ceil(min_sell / MIN_TICK) * MIN_TICK
                        new_sell = max(best_ask - UNDERCUT_TICKS * MIN_TICK, min_sell_price)
                        
                        if new_sell < current_sell_price:
                            self._log(f"🔄 SELL: ${current_sell_price:.5f} → ${new_sell:.5f} (min: ${min_sell_price:.5f})")
                            self.client.cancel_order(current_sell_order_id)
                            try:
                                current_sell_order_id = self.client.place_limit_order("SELL", trade_size, new_sell)
                                current_sell_price = new_sell
                                sell_requotes += 1
                                last_sell_requote = elapsed
                            except Exception as e:
                                self._log(f"⚠️  SELL requote failed: {e}")
                                current_sell_order_id = None
            
            # Break-even timeout (only apply ONCE per side)
            if elapsed >= BREAKEVEN_TIMEOUT:
                if buy_fill and not sell_fill and not breakeven_applied_sell:
                    total_cost = buy_fill.filled_value + buy_fill.fee_amount
                    breakeven = total_cost / (trade_size * (1 - FEE_RATE))
                    breakeven_price = math.ceil(breakeven / MIN_TICK) * MIN_TICK
                    
                    if current_sell_price > breakeven_price + MIN_TICK:
                        self._log(f"⏰ SELL → break-even: ${breakeven_price:.5f}")
                        if current_sell_order_id:
                            self.client.cancel_order(current_sell_order_id)
                        try:
                            current_sell_order_id = self.client.place_limit_order("SELL", trade_size, breakeven_price)
                            current_sell_price = breakeven_price
                            breakeven_applied_sell = True
                        except Exception as e:
                            self._log(f"⚠️  Break-even SELL failed: {e}")
                            current_sell_order_id = None
                
                elif sell_fill and not buy_fill and not breakeven_applied_buy:
                    proceeds = sell_fill.filled_value - sell_fill.fee_amount
                    breakeven = proceeds / (trade_size * (1 + FEE_RATE))
                    breakeven_price = math.floor(breakeven / MIN_TICK) * MIN_TICK
                    
                    if current_buy_price < breakeven_price - MIN_TICK:
                        self._log(f"⏰ BUY → break-even: ${breakeven_price:.5f}")
                        if current_buy_order_id:
                            self.client.cancel_order(current_buy_order_id)
                        try:
                            current_buy_order_id = self.client.place_limit_order("BUY", trade_size, breakeven_price)
                            current_buy_price = breakeven_price
                            breakeven_applied_buy = True
                        except Exception as e:
                            self._log(f"⚠️  Break-even BUY failed: {e}")
                            current_buy_order_id = None
            
            time.sleep(1.0)
            elapsed += time.time() - loop_start
            
            # Progress log every 30s
            if int(elapsed) % 30 == 0 and elapsed > 0:
                buy_stat = "FILLED" if buy_fill else f"@ ${current_buy_price:.5f}"
                sell_stat = "FILLED" if sell_fill else f"@ ${current_sell_price:.5f}"
                self._log(f"⏳ [{int(elapsed)}s] BUY: {buy_stat}, SELL: {sell_stat}")


# =============================================================================
# MAIN
# =============================================================================

def load_credentials():
    """Load from secrets3.json"""
    if not os.path.exists(SECRETS_FILE):
        raise FileNotFoundError(f"Secrets file not found: {SECRETS_FILE}")
    
    with open(SECRETS_FILE, 'r') as f:
        secrets = json.load(f)
    
    return (secrets['coinbase_api_key_name'], secrets['coinbase_api_private_key'])


def main():
    parser = argparse.ArgumentParser(description="TROLL-USD Aggressive Market Maker")
    parser.add_argument("--min_trade", type=float, default=10.0)
    parser.add_argument("--max_trade", type=float, default=100.0)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--max_rounds", type=int, default=None)
    parser.add_argument("--no-confirm", action="store_true")
    
    args = parser.parse_args()
    
    api_key, api_secret = load_credentials()
    
    if not args.no_confirm:
        print()
        print("=" * 60)
        print("🧌 TROLL-USD AGGRESSIVE MARKET MAKER")
        print("⚠️  REAL MONEY - USE WITH CAUTION")
        print("=" * 60)
        print(f"Undercut: {UNDERCUT_TICKS} ticks")
        print(f"Trade size: ${args.min_trade:.2f} - ${args.max_trade:.2f}")
        print(f"Secrets: {SECRETS_FILE}")
        print()
        confirm = input("Type 'TROLL' to start: ")
        if confirm != "TROLL":
            print("Aborted.")
            return
    
    mm = TrollMarketMaker(
        api_key_name=api_key,
        api_private_key=api_secret,
        min_trade_usd=args.min_trade,
        max_trade_usd=args.max_trade
    )
    
    running = True
    def signal_handler(sig, frame):
        nonlocal running
        print("\n⚠️  Stopping...")
        running = False
    
    signal.signal(signal.SIGINT, signal_handler)
    
    rounds = 0
    while running:
        try:
            result = mm.execute_round(monitor_timeout=args.timeout)
            if result:
                rounds += 1
                if args.max_rounds and rounds >= args.max_rounds:
                    print(f"\n✅ Completed {rounds} rounds")
                    break
            else:
                time.sleep(5)  # Brief pause before retry
        except Exception as e:
            print(f"\n❌ Error: {e}")
            time.sleep(10)
    
    print()
    print("=" * 60)
    print("📊 SESSION SUMMARY")
    print("=" * 60)
    print(f"Rounds: {mm.rounds_completed}")
    print(f"Total Profit: ${mm.total_profit:.6f}")
    print(f"Total Fees: ${mm.total_fees:.6f}")
    print("=" * 60)


if __name__ == "__main__":
    main()
