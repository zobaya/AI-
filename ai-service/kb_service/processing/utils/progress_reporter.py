# -*- coding: utf-8 -*-
"""
任务进度报告器 - 将详细的处理步骤传递给前端
"""
from typing import Optional
from datetime import datetime


class TaskProgressReporter:
    """
    任务进度报告器

    功能：
    1. 收集详细的处理步骤信息
    2. 通过 task.update_state() 更新进度
    3. 前端通过 /tasks/{task_id} 获取实时进度
    """

    def __init__(self, task):
        """
        初始化进度报告器

        Args:
            task: Celery task 实例（用于 update_state）
        """
        self.task = task
        self.logs = []  # 日志列表
        self.start_time = datetime.now()

    def log(self, level: str, message: str, progress: Optional[int] = None):
        """
        记录日志并更新任务状态

        Args:
            level: 日志级别 (INFO, WARNING, ERROR)
            message: 日志消息
            progress: 当前进度 (0-100)
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = {
            "timestamp": timestamp,
            "level": level,
            "message": message
        }
        self.logs.append(log_entry)

        # 打印到控制台
        print(f"[{level}] {message}")

        # 更新任务状态（传递最新的日志）
        self.update(progress=progress, latest_log=log_entry)

    def info(self, message: str, progress: Optional[int] = None):
        """记录 INFO 日志"""
        self.log("INFO", message, progress)

    def warning(self, message: str, progress: Optional[int] = None):
        """记录 WARNING 日志"""
        self.log("WARNING", message, progress)

    def error(self, message: str, progress: Optional[int] = None):
        """记录 ERROR 日志"""
        self.log("ERROR", message, progress)

    def update(self, **meta):
        """
        更新任务状态

        Args:
            **meta: 要传递给前端的元数据
        """
        state = "PROGRESS"

        # 构建更新数据
        update_data = {
            "logs": self.logs[-20:],  # 只传递最近 20 条日志
            "log_count": len(self.logs),
        }

        # 添加进度信息
        if "progress" in meta and meta["progress"] is not None:
            update_data["progress"] = meta["progress"]

        if "current_step" in meta:
            update_data["current_step"] = meta["current_step"]

        if "message" in meta:
            update_data["message"] = meta["message"]

        if "latest_log" in meta:
            update_data["latest_log"] = meta["latest_log"]

        # 添加任何额外的元数据
        for key, value in meta.items():
            if key not in ["progress", "current_step", "message", "latest_log"]:
                update_data[key] = value

        self.task.update_state(state=state, meta=update_data)

    def report_step(self, step_name: str, message: str, progress: int):
        """
        报告处理步骤

        Args:
            step_name: 步骤名称
            message: 步骤消息
            progress: 进度 (0-100)
        """
        self.info(message, progress)
        self.update(
            current_step=step_name,
            message=message,
            progress=progress
        )

    def report_substep(self, substep_name: str, message: str, parent_progress: int, sub_progress: int):
        """
        报告子步骤

        Args:
            substep_name: 子步骤名称
            message: 子步骤消息
            parent_progress: 父步骤的基础进度
            sub_progress: 子步骤的相对进度 (0-100)
        """
        # 计算总进度：父进度 + 子进度的一小部分
        total_progress = parent_progress + int(sub_progress * 0.1)
        self.info(f"  {message}", total_progress)
        self.update(
            current_step=substep_name,
            message=message,
            progress=total_progress
        )

    def report_count(self, step_name: str, message: str, progress: int, count: int, total: int):
        """
        报告带计数的进度（如"已处理 5/10 个分块"）

        Args:
            step_name: 步骤名称
            message: 消息模板（会添加计数）
            progress: 当前进度
            count: 当前计数
            total: 总数
        """
        message_with_count = f"{message} ({count}/{total})"
        self.info(message_with_count, progress)
        self.update(
            current_step=step_name,
            message=message_with_count,
            progress=progress,
            count=count,
            total=total
        )
