from typing import Dict

class Interface:
    def __init__(self):
        pass

    def sync_with_bot(self, bot):
        self.bot = bot
        self.currency = bot.currency
        self.asset = bot.asset
        self.position = bot.position
        if self.asset > 0:
            assert self.position == "long"
        if self.currency > 0:
            assert self.position == "short"

    def assert_exchange_sync(self, bot):
        raise NotImplementedError("This method should be implemented by subclasses.")
    
    def connect_to_exchange(self):
        raise NotImplementedError("This method should be implemented by subclasses.")
    
    def fetch_exchange_balance_currency(self) -> Dict[str, float]:
        raise NotImplementedError("This method should be implemented by subclasses.")
    
    def fetch_exchange_balance_asset(self) -> Dict[str, float]:
        raise NotImplementedError("This method should be implemented by subclasses.")