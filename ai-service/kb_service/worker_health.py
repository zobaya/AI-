# -*- coding: utf-8 -*-
"""Worker 健康检查 - API 入口"红绿灯"机制"""
from kb_service.tasks import celery_app
from typing import Optional, Dict
import logging

logger = logging.getLogger(__name__)


class WorkerHealthChecker:
    """
    Worker 健康检查器

    功能：
    1. 在 API 入口处检查 Worker 是否存活
    2. 防止任务进入"黑洞"（未启动或冷启动中的 Worker）
    3. 极短超时（1-2秒），快速失败
    """

    def __init__(self, timeout: float = 2.0):
        """
        初始化健康检查器

        Args:
            timeout: 超时时间（秒），默认 2 秒
        """
        self.timeout = timeout
        self.inspect = celery_app.control.inspect(timeout=timeout)

    def check_worker_health(self) -> Dict[str, any]:
        """
        检查 Worker 健康状态

        Returns:
            {
                "healthy": bool,        # Worker 是否健康
                "workers": list,        # 存活的 worker 列表
                "message": str          # 状态消息
            }
        """
        try:
            # 使用 ping() 检查 worker 存活状态
            # ping() 会向所有 worker 发送 ping 命令，等待响应
            pong = self.inspect.ping()

            if pong and isinstance(pong, dict) and len(pong) > 0:
                # 有 worker 响应
                worker_names = list(pong.keys())
                logger.info(f"[HealthCheck] Worker healthy: {worker_names}")

                return {
                    "healthy": True,
                    "workers": worker_names,
                    "message": "Worker 正常运行"
                }
            else:
                # 没有 worker 响应
                logger.warning(f"[HealthCheck] No workers responded")

                return {
                    "healthy": False,
                    "workers": [],
                    "message": "Worker 未启动或冷启动中，请稍候"
                }

        except Exception as e:
            # 异常情况（连接超时、Redis 未启动等）
            logger.error(f"[HealthCheck] Health check failed: {e}")

            return {
                "healthy": False,
                "workers": [],
                "message": f"Worker 健康检查失败: {str(e)}"
            }

    def require_worker_health(self) -> None:
        """
        要求 Worker 必须健康，否则抛出异常

        Raises:
            HTTPException: 当 Worker 不健康时

        Usage:
            checker.require_worker_health()  # 如果不健康会抛出异常
            # 继续处理上传逻辑...
        """
        result = self.check_worker_health()

        if not result["healthy"]:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=503,  # Service Unavailable
                detail={
                    "error": "service_unavailable",
                    "message": result["message"],
                    "suggestion": "请稍候重试，或联系管理员检查 Worker 状态"
                }
            )

    def get_worker_stats(self) -> Optional[Dict]:
        """
        获取 Worker 统计信息（用于监控）

        Returns:
            Worker 统计信息字典，失败时返回 None
        """
        try:
            stats = self.inspect.stats()

            if stats and isinstance(stats, dict) and len(stats) > 0:
                # 汇总所有 worker 的统计信息
                total_tasks = 0
                worker_info = []

                for worker_name, worker_stats in stats.items():
                    total_tasks += worker_stats.get('total', {}).values()

                    worker_info.append({
                        "name": worker_name,
                        "pool": worker_stats.get('pool', {}).get('max-concurrency', 'unknown'),
                        "broker": worker_stats.get('broker', {}).get('url', 'unknown'),
                    })

                return {
                    "worker_count": len(stats),
                    "total_tasks": total_tasks,
                    "workers": worker_info
                }

            return None

        except Exception as e:
            logger.error(f"[HealthCheck] Failed to get worker stats: {e}")
            return None


# 全局实例（使用 2 秒超时）
worker_health_checker = WorkerHealthChecker(timeout=2.0)
