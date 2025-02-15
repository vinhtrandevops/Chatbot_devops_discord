import logging
import colorlog
from ..config import LOG_LEVEL

class CustomFormatter(colorlog.ColoredFormatter):
    """Custom color formatter with better formatting"""
    def __init__(self):
        super().__init__(
            fmt='%(log_color)s%(asctime)s %(levelname)-8s %(name)s:%(lineno)d - %(message)s%(reset)s',
            datefmt='%Y-%m-%d %H:%M:%S',
            log_colors={
                'DEBUG': 'cyan',
                'INFO': 'green',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'red,bg_white',
            },
            secondary_log_colors={},
            style='%'
        )

def get_logger(name):
    """Tạo logger với cấu hình màu sắc và format chuẩn"""
    logger = logging.getLogger(name)
    
    if not logger.handlers:
        # Create console handler
        handler = logging.StreamHandler()
        
        # Set custom formatter
        handler.setFormatter(CustomFormatter())
        
        # Add handler to logger
        logger.addHandler(handler)
        
        # Set log level
        log_level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)
        logger.setLevel(log_level)
        
        # Prevent logging from propagating to the root logger
        logger.propagate = False
    
    return logger