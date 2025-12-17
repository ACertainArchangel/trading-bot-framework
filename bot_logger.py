"""
Centralized logging system for trading bots.
Supports multi-instance logging to both files and web interface.
"""

import os
from datetime import datetime
from typing import Optional, Callable


class BotLogger:
    """
    Logger that writes to both file and web interface.
    Supports multiple bot instances running in parallel.
    """
    
    def __init__(self, instance_id: int = 1, web_logger: Optional[Callable] = None):
        """
        Initialize logger for a specific bot instance.
        
        Args:
            instance_id: Bot instance number (default: 1)
            web_logger: Optional callback function for web interface logging
        """
        self.instance_id = instance_id
        self.web_logger = web_logger
        
        # Create logs directory if it doesn't exist
        os.makedirs('logs', exist_ok=True)
        
        # Set up log file paths
        self.main_log_file = f'logs/bot_{instance_id}_main.log'
        self.stream_log_file = f'logs/bot_{instance_id}_stream.log'
        
        # Write startup message
        startup_msg = f"{'=' * 80}\n"
        startup_msg += f"Bot Instance {instance_id} - Started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        startup_msg += f"{'=' * 80}\n"
        
        with open(self.main_log_file, 'a') as f:
            f.write(startup_msg)
    
    def log_main(self, msg: str):
        """
        Log to main application log (bot events, trades, etc).
        
        Args:
            msg: Message to log
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] {msg}\n"
        
        # Write to file
        with open(self.main_log_file, 'a') as f:
            f.write(log_line)
        
        # Send to web interface if available
        if self.web_logger:
            self.web_logger(msg)
    
    def log_stream(self, msg: str):
        """
        Log to stream log (price updates, candle data, etc).
        
        Args:
            msg: Message to log
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] {msg}\n"
        
        # Write to file
        with open(self.stream_log_file, 'a') as f:
            f.write(log_line)
        
        # Send to web interface if available (if different from main logger)
        if self.web_logger:
            self.web_logger(msg)
    
    def get_instance_id(self) -> int:
        """Get the instance ID for this logger."""
        return self.instance_id
    
    def get_log_files(self) -> dict:
        """Get paths to log files for this instance."""
        return {
            'main': self.main_log_file,
            'stream': self.stream_log_file
        }


# Global logger instances (one per bot instance)
_loggers = {}


def get_logger(instance_id: int = 1, web_main_logger: Optional[Callable] = None, 
               web_stream_logger: Optional[Callable] = None) -> tuple:
    """
    Get or create loggers for a bot instance.
    
    Args:
        instance_id: Bot instance number
        web_main_logger: Optional web logger for main events
        web_stream_logger: Optional web logger for stream events
    
    Returns:
        Tuple of (main_logger_func, stream_logger_func)
    """
    if instance_id not in _loggers:
        _loggers[instance_id] = {
            'main': BotLogger(instance_id, web_main_logger),
            'stream': BotLogger(instance_id, web_stream_logger)
        }
    
    main_logger = _loggers[instance_id]['main']
    stream_logger = _loggers[instance_id]['stream']
    
    return (main_logger.log_main, main_logger.log_stream)


def main_logger(msg: str, instance_id: int = 1):
    """
    Convenience function for main logging with default instance.
    
    Args:
        msg: Message to log
        instance_id: Bot instance number (default: 1)
    """
    if instance_id not in _loggers:
        _loggers[instance_id] = {
            'main': BotLogger(instance_id),
            'stream': BotLogger(instance_id)
        }
    
    _loggers[instance_id]['main'].log_main(msg)


def stream_logger(msg: str, instance_id: int = 1):
    """
    Convenience function for stream logging with default instance.
    
    Args:
        msg: Message to log
        instance_id: Bot instance number (default: 1)
    """
    if instance_id not in _loggers:
        _loggers[instance_id] = {
            'main': BotLogger(instance_id),
            'stream': BotLogger(instance_id)
        }
    
    _loggers[instance_id]['stream'].log_stream(msg)
