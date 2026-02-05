# Contributing to Trading Framework

Thank you for your interest in contributing! Copilot mostly wrote this from my readme section but with a few edits it perfectly describes what I am looking for in contributions. 

This project started as a messy collection of ad-hoc scripts (check out `_old/` if you're curious) and evolved into a reusable framework with Copilot's help for documentation and organization. 

The framework exists to help develop, backtest, and deploy trading strategies quickly. While I haven't cracked the code on consistently beating Coinbase fees without getting stuck in positions, **that's exactly where you come in!** I'd love to see what strategies and improvements the community can contribute.

## What We're Looking For

### Cool Strategies

This is the big one! If you've developed a strategy that:
- Beats market returns after fees
- Doesn't get stuck holding positions for 200 days (looking at you, "never take a loss" strategies...)
- Uses creative technical indicators or combinations
- Implements novel risk management approaches
- Works well in specific market conditions

**Please share it!** Even strategies that don't consistently win can teach us something valuable.

Some ideas to explore:
- **Adaptive "Grumpy" Strategy**: Like the "never take a loss" approach but with a gradually lowering threshold over time to escape those 200-day holding periods
- **Volatility-aware strategies**: Adjust behavior based on market volatility (ATR, Bollinger bandwidth, etc.)
- **Multi-timeframe approaches**: Combine signals from different granularities
- **Machine learning integrations**: Neural networks, ensemble methods, reinforcement learning
- **Sentiment analysis**: Incorporate news, social media, or on-chain data
- **Market regime detection**: Different strategies for trending vs ranging markets
- **Portfolio strategies**: Multi-asset allocation and rebalancing

### Framework Improvements

We welcome contributions that make the framework better:

- **New technical indicators**: More TA-Lib equivalents, custom indicators
- **Better backtesting features**: Walk-forward analysis, Monte Carlo simulations, parameter optimization
- **Risk management tools**: Position sizing, stop-loss enhancements, drawdown protection
- **Dashboard improvements**: Better visualizations, real-time analytics, performance metrics
- **Data sources**: Additional exchanges, alternative data feeds
- **Testing**: Unit tests, integration tests, strategy validation tools
- **Documentation**: Tutorials, strategy guides, API references
- **Performance optimizations**: Faster backtesting, efficient data handling
- **Bug fixes**: Anything broken or not working as expected

## How to Contribute

### 1. Fork and Clone

```bash
git clone https://github.com/yourusername/trading-framework.git
cd trading-framework/framework
pip install -r requirements.txt
```

### 2. Create a Branch

```bash
git checkout -b feature/my-awesome-strategy
# or
git checkout -b fix/some-bug
```

### 3. Make Your Changes

#### Contributing a Strategy

Create your strategy in `framework/strategies/examples/`:

```python
from framework.strategies.base import Strategy
from framework.indicators import ema, rsi, macd

class YourAwesomeStrategy(Strategy):
    """
    Brief description of what makes this strategy special.
    
    Parameters:
        param1 (int): Description of parameter 1
        param2 (float): Description of parameter 2
    
    Performance notes:
        - Tested on: BTC-USD, 6 months
        - Return: XX%
        - Win rate: XX%
        - Max drawdown: XX%
    """
    
    def __init__(self, param1=10, param2=0.02):
        super().__init__()
        self.param1 = param1
        self.param2 = param2
    
    def buy_signal(self, candles):
        """Explain your buy logic."""
        # Your implementation
        return False
    
    def sell_signal(self, candles):
        """Explain your sell logic."""
        # Your implementation
        return False
```

Don't forget to add your strategy to `framework/strategies/__init__.py`:

```python
from .examples.your_strategy import YourAwesomeStrategy
```

#### Contributing an Indicator

Add new indicators to `framework/indicators/__init__.py`:

```python
def your_indicator(candles, period=14):
    """
    Calculate your custom indicator.
    
    Args:
        candles (list[Candle]): Price history
        period (int): Lookback period
    
    Returns:
        list[float]: Indicator values
    """
    # Your implementation
    return []
```

#### Contributing Framework Improvements

- Follow existing code style and patterns
- Add docstrings to all public functions and classes
- Update relevant documentation in README.md or create new docs
- Test your changes thoroughly

### 4. Test Your Changes

**For Strategies:**

```python
from framework import backtest, simulate
from framework.strategies.examples import YourAwesomeStrategy

# Backtest it
result = backtest(YourAwesomeStrategy, months=6)
print(result)

# Test on different timeframes and products
backtest(YourAwesomeStrategy, months=12, product_id="ETH-USD")

# Visualize performance
simulate(YourAwesomeStrategy, months=6)
```

**For Framework Changes:**

- Ensure existing examples in `quickstart/` still work
- Test with multiple strategies and market conditions
- Check for edge cases and error handling

### 5. Document Your Work

Include in your pull request:

- **What**: Clear description of what you're adding/fixing
- **Why**: The problem you're solving or opportunity you're exploiting
- **How**: Brief explanation of your approach
- **Results**: For strategies, include backtest results (returns, win rate, drawdown)
- **Trade-offs**: Any limitations or conditions where it doesn't work well

### 6. Submit a Pull Request

```bash
git add .
git commit -m "Add YourAwesomeStrategy: momentum-based approach with adaptive stops"
git push origin feature/my-awesome-strategy
```

Then open a pull request on GitHub with:
- Clear title describing the contribution
- Detailed description of changes
- Backtest results (if applicable)
- Any breaking changes or dependencies added

## Strategy Contribution Guidelines

### What Makes a Good Strategy Contribution?

✅ **DO:**
- Include clear documentation and comments
- Provide backtest results on BTC-USD (6-12 months minimum)
- Explain the market hypothesis/edge you're exploiting
- Note any specific market conditions where it works best
- Include parameter descriptions and sensible defaults
- Test on multiple timeframes/products when possible

❌ **DON'T:**
- Submit overfitted strategies (tested on one coin, one period only)
- Claim guaranteed profits or unrealistic returns
- Submit strategies without proper documentation
- Include hardcoded secrets or API keys
- Ignore fee impact in your analysis

### Strategy Documentation Template

When submitting a strategy, please include:

```markdown
## [Strategy Name]

**Description**: Brief overview of the strategy's approach

**Market Hypothesis**: What edge or inefficiency does this exploit?

**Parameters**:
- `param1`: Description (default: X)
- `param2`: Description (default: Y)

**Backtest Results**:
- Period: 6 months on BTC-USD, 1hr candles
- Starting balance: $1,000
- Final balance: $XXX
- Return: XX%
- Trades: XX (XX% win rate)
- Max drawdown: XX%
- Sharpe ratio: X.XX

**Strengths**:
- Works well in trending markets
- Low drawdown
- etc.

**Weaknesses**:
- Struggles in ranging markets
- Requires specific volatility conditions
- etc.

**Usage**:
```python
from framework import backtest
from framework.strategies.examples import YourStrategy

result = backtest(YourStrategy, months=6)
```

## Code Style

I really don't care what style you use. If you read my code you'll see it's a mess stylistically, but makes sense organizationally. You can use PEP8, Google style, Gangnam Style, or whatever you prefer.
- Keep functions focused and single-purpose
- Use descriptive variable names
- Add comments for complex logic
- Type hints are something I really do like but not mandatory. They can be a pain sometimes to write with.

Example:

## Areas Where We Need Help

### High Priority

1. **Strategies that beat fees**: The holy grail. Simple or complex, we want them all
2. **Solutions for position holding**: Strategies that avoid getting stuck for months
3. **Risk management improvements**: Better stop-loss, position sizing, drawdown protection
4. **Comprehensive testing suite**: Unit tests, integration tests, strategy validators
5. **Machine learning integration**: Framework-compatible ML strategy templates

### Medium Priority

1. **Additional exchange support**: Binance, Kraken, etc.
2. **More technical indicators**: Volume-based, advanced oscillators, custom composites
3. **Multi-asset support**: Portfolio strategies, correlation analysis
4. **Performance optimization**: Faster backtesting, parallel processing
5. **Strategy optimizer**: Grid search, genetic algorithms for parameter tuning

### Nice to Have

1. **Advanced visualizations**: Equity curves, drawdown charts, heat maps
2. **Educational content**: Tutorials, strategy breakdowns, best practices guide

## The Story So Far

This framework emerged from frustration with:
- **20x boilerplate** in every script (look at `_old/` for the nightmare)
- **Slow iteration** when testing new ideas
- **Repeated code** across multiple bot implementations

The goal was fast strategy development and deployment. We've achieved that. Now the challenge is finding strategies that consistently work.

### What I've Learned

1. **"Never take a loss" strategies** work great... until they hold a position for 200 days. Not ideal.
2. **Coinbase fees are brutal**: ~0.6% round-trip eats into profits fast
3. **Simple strategies often beat complex ones**: But they need an edge
4. **Position clarity matters**: Being fully in or fully out simplifies everything
5. **Backtesting isn't reality**: But it's essential for filtering bad ideas

### What's Next

- Deep learning strategies (future project)
- Adaptive "grumpy" strategy to solve the stuck-position problem
- Your contributions!

## Questions?

Feel free to:
- Open an issue for questions or discussions
- Start a discussion in the repository
- Submit a draft PR if you want early feedback

## Recognition

Contributors will be:
- Listed in the main README
- Credited in strategy documentation
- Appreciated by everyone trying to beat the market :p

## Final Notes

**Remember**: Trading involves serious risk. All strategies in this repository are for educational purposes. Never trade money you can't afford to lose.

That said, if you discover something that works, the community (only me at the time of writing this) would love to learn from it. Even "failed" strategies teach valuable lessons.

Looking forward to your contributions.

---

**License**: All contributions will be under the MIT License.
