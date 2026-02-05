"""
Dashboard - Web-based visualization for trading.

Provides real-time charts, indicators, and trade monitoring.
"""

from typing import Optional, Type
import threading
import webbrowser

from ..strategies.base import Strategy


def launch_dashboard(
    strategy: Optional[Type[Strategy]] = None,
    product_id: str = "BTC-USD",
    granularity: str = '1m',
    port: int = 5002,
    open_browser: bool = True
):
    """
    Launch the web dashboard for monitoring and visualization.
    
    Args:
        strategy: Optional strategy to monitor
        product_id: Trading pair
        granularity: Candle size
        port: Web server port
        open_browser: Automatically open browser
    
    Example:
        >>> from framework import launch_dashboard
        >>> launch_dashboard(product_id="ETH-USD")
    """
    try:
        from ..dashboard.app import create_app
        app, socketio = create_app(
            product_id=product_id,
            granularity=granularity,
            strategy=strategy
        )
        
        if open_browser:
            threading.Timer(1.5, lambda: webbrowser.open(f'http://localhost:{port}')).start()
        
        print(f"🌐 Dashboard running at http://localhost:{port}")
        socketio.run(app, host='0.0.0.0', port=port, debug=False)
    
    except ImportError as e:
        print(f"⚠️  Dashboard dependencies not installed: {e}")
        print("   Install with: pip install flask flask-socketio flask-cors")
