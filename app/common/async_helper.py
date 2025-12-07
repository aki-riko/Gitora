# coding:utf-8
"""
异步操作辅助类
简化QThread的使用，参考pyqt5-concurrent思想
"""
from typing import Callable, Any
from PySide6.QtCore import QThread, Signal, Qt
from qfluentwidgetspro import ProgressInfoBar
from qfluentwidgets import InfoBar, InfoBarPosition

from .logger import get_logger

logger = get_logger("AsyncHelper")


class AsyncWorker(QThread):
    """通用异步工作线程"""
    finished = Signal(object)  # 返回结果
    error = Signal(str)  # 错误信息
    
    def __init__(self, func: Callable, *args, **kwargs):
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs
    
    def run(self):
        logger.debug(f"[AsyncWorker] 开始执行异步任务: {self.func.__name__}")
        try:
            result = self.func(*self.args, **self.kwargs)
            logger.debug(f"[AsyncWorker] 异步任务执行成功: {self.func.__name__}")
            self.finished.emit(result)
        except Exception as e:
            logger.exception(f"[AsyncWorker] 异步任务执行失败: {self.func.__name__}, error: {e}")
            self.error.emit(str(e))


class AsyncTask:
    """异步任务管理器（带进度环）"""
    
    @staticmethod
    def run(
        func: Callable,
        on_success: Callable[[Any], None] = None,
        on_error: Callable[[str], None] = None,
        progress_title: str = "请稍候",
        progress_content: str = "正在处理...",
        success_title: str = "成功",
        success_content: str = "操作完成",
        error_title: str = "错误",
        error_content: str = None,
        show_progress: bool = True,
        parent=None,
        *args,
        **kwargs
    ):
        """
        异步执行任务，自动显示进度环
        
        Args:
            func: 要执行的函数
            on_success: 成功回调
            on_error: 失败回调
            progress_title: 进度环标题
            progress_content: 进度环内容
            success_title: 成功标题
            success_content: 成功内容
            error_title: 错误标题
            error_content: 错误内容
            show_progress: 是否显示进度环
            parent: 父窗口
            *args, **kwargs: 传递给func的参数
        
        Returns:
            AsyncWorker实例
        """
        # 显示进度环
        progress_bar = None
        if show_progress and parent:
            progress_bar = ProgressInfoBar.create(
                title=progress_title,
                content=progress_content,
                orient=Qt.Orientation.Horizontal,
                isClosable=False,
                position=InfoBarPosition.BOTTOM_RIGHT,
                parent=parent
            )
        
        # 创建工作线程
        worker = AsyncWorker(func, *args, **kwargs)
        
        # 成功回调 - 不自动判断，由on_success回调处理
        def on_finished(result):
            # 关闭进度环，由on_success自己控制显示
            if progress_bar:
                progress_bar.close()
            
            if on_success:
                on_success(result)
        
        # 错误回调 - 处理异常
        def on_failed(error_msg):
            logger.error(f"[AsyncTask] 异步任务失败: {progress_title}, error: {error_msg}")
            # 关闭进度环，不显示错误状态（因为 .error() 会显示通知）
            if progress_bar:
                progress_bar.close()
            
            # 错误通知完全由调用者的 on_error 回调处理
            # 这样避免重复通知，并且让调用者有更多控制权
            
            if on_error:
                on_error(error_msg)
        
        worker.finished.connect(on_finished)
        worker.error.connect(on_failed)
        
        # 保存worker引用到parent，防止被过早销毁
        if parent and hasattr(parent, '__dict__'):
            if not hasattr(parent, '_async_workers'):
                parent._async_workers = []
            parent._async_workers.append(worker)
            # 线程完成后移除引用
            worker.finished.connect(lambda: parent._async_workers.remove(worker) if worker in parent._async_workers else None)
            worker.error.connect(lambda: parent._async_workers.remove(worker) if worker in parent._async_workers else None)
        
        logger.info(f"[AsyncTask] 启动异步任务: {progress_title} - {progress_content}")
        worker.start()
        return worker


class SimpleAsyncTask:
    """简化的异步任务（无进度环）"""
    
    @staticmethod
    def run(func: Callable, on_finished: Callable[[Any], None] = None, *args, **kwargs):
        """
        简单异步执行，无进度环
        
        Args:
            func: 要执行的函数
            on_finished: 完成回调（接收结果）
            *args, **kwargs: 传递给func的参数
        
        Returns:
            AsyncWorker实例
        """
        logger.debug(f"[SimpleAsyncTask] 启动简单异步任务: {func.__name__}")
        worker = AsyncWorker(func, *args, **kwargs)
        
        if on_finished:
            worker.finished.connect(on_finished)
        
        # 保存引用防止被销毁（使用全局列表）
        if not hasattr(SimpleAsyncTask, '_workers'):
            SimpleAsyncTask._workers = []
        SimpleAsyncTask._workers.append(worker)
        worker.finished.connect(lambda: SimpleAsyncTask._workers.remove(worker) if worker in SimpleAsyncTask._workers else None)
        worker.error.connect(lambda: SimpleAsyncTask._workers.remove(worker) if worker in SimpleAsyncTask._workers else None)
        
        worker.start()
        return worker
