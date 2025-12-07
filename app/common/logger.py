# coding:utf-8
"""
日志系统配置
提供统一的日志记录功能
"""
import logging
import os
import sys
from pathlib import Path
from datetime import datetime
from logging.handlers import RotatingFileHandler


class Logger:
    """日志管理器"""
    
    _initialized = False
    _loggers = {}
    
    @classmethod
    def setup(cls):
        """初始化日志系统（只执行一次）"""
        if cls._initialized:
            return
        
        # 创建日志目录
        log_dir = Path.home() / "AppData" / "Local" / "Gitess" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # 日志文件路径
        log_file = log_dir / f"gitess_{datetime.now().strftime('%Y%m%d')}.log"
        
        # 配置根日志器
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)
        
        # 清除已有的处理器
        root_logger.handlers.clear()
        
        # 1. 文件处理器（所有级别）
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            '[%(asctime)s] [%(levelname)s] [%(name)s:%(lineno)d] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)
        
        # 2. 控制台处理器（WARNING及以上）
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.WARNING)
        console_formatter = logging.Formatter(
            '[%(levelname)s] %(name)s: %(message)s'
        )
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)
        
        cls._initialized = True
        
        # 记录启动日志
        logger = cls.get_logger("Gitess")
        logger.info("=" * 60)
        logger.info("Gitess 启动")
        logger.info(f"日志文件: {log_file}")
        logger.info("=" * 60)
    
    @classmethod
    def get_logger(cls, name: str) -> logging.Logger:
        """获取指定名称的日志器"""
        if not cls._initialized:
            cls.setup()
        
        if name not in cls._loggers:
            cls._loggers[name] = logging.getLogger(name)
        
        return cls._loggers[name]


# 便捷函数
def get_logger(name: str) -> logging.Logger:
    """获取日志器"""
    return Logger.get_logger(name)
