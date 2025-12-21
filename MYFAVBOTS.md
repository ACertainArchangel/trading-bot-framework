WET maker: ABANDONED
cd "/Users/gabrieljordaan/Desktop/Coding/Artificial Inteligence/Algorithmic Trading/market_making" && "/Users/gabrieljordaan/Desktop/Coding/Artificial Inteligence/Algorithmic Trading/venv/bin/python" production_executor.py --product_id WET-USD --no-confirm --secrets ../secrets/secrets2.json

Grumpy Mom:
python3 live_bot.py greedy_momentum --period 14 --patience_candles 1440 --profit_margin 1.0 --loss_tolerance 0.00 --granularity 1m --sell_threshold -1.0 --buy_threshold 1.0