""" (启动) Celery Worker 总入口 """
# 先导入配置，确保 settings 对象正确初始化
from core.config import settings
# 再导入 celery_app（tasks.py 会再次导入 settings，但应该是同一个实例）
from kb_service.tasks import celery_app
from kombu import Queue, Exchange
import logging

logger = logging.getLogger(__name__)

# 配置 Celery（完整配置：基础配置已在 tasks.py 中设置，这里补充 worker 特定配置）
celery_app.conf.update(
    # ========== 任务路由配置 ==========
    task_routes={
        "kb_service.tasks.*": {"queue": "kb_queue"},
    },
    # ========== 任务队列配置 ==========
    task_queues=[
        Queue("celery", Exchange("celery"), routing_key="celery"),
        Queue("kb_queue", Exchange("celery"), routing_key="kb_queue"),
    ],
    # ========== 任务创建配置 ==========
    task_default_queue="kb_queue",
    task_default_exchange="celery",  # 默认使用 celery exchange
    # ========== 任务结果过期时间（秒）- 确保 Redis 中的键带 TTL ==========
    # 修复序列化问题：直接使用硬编码值避免 Pydantic 属性访问问题
    task_result_expires=3600,  # 3600秒=1小时
    result_extended=False,  # 禁用扩展结果格式，避免序列化冲突
    result_compression='gzip',  # 启用结果压缩
    # 忽略结果无法解析的错误
    result_backend_transport_options={'retry_policy': {'max_retries': 0}},
    # ========== 任务超时时间（秒） ==========
    task_time_limit=3600,
    task_soft_time_limit=3300,
    # ========== Worker 预取和并发配置 ==========
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
    # ========== 状态跟踪配置（实时进度更新） ==========
    task_track_started=True,  # 跟踪任务开始状态
    task_send_sent_event=True,  # 发送任务状态事件
    worker_send_task_events=True,  # worker 发送任务事件
    task_ignore_result=False,  # 不忽略任务结果
    # ========== 任务确认配置 ==========
    task_acks_late=True,  # 任务完成后才确认（更好的错误处理）
    task_reject_on_worker_lost=True,  # worker 丢失时拒绝任务
    # ========== Broker 传输选项 - 为消息设置 TTL ==========
    broker_transport_options={
        "visibility_timeout": 3600,  # 消息可见性超时（秒）
        "fanout_prefix": True,
        "fanout_patterns": True,
    },
)

# 自动发现任务
celery_app.autodiscover_tasks(["kb_service"])


# ========== 第二道防线：Worker 启动前主动预热 ==========
def warmup_worker():
    """
    Worker 启动前的预热逻辑

    功能：
    1. 在 worker_main 之前执行
    2. 直接建立与 Redis、Elasticsearch 的连接
    3. 确保所有外部依赖已就绪

    目的：就像冬天开车前的"热车"，实现"无感就绪"
    """
    print("")
    print("[Warmup] ========== Worker Warmup Started ==========")
    print(f"[Warmup] Timestamp: {__import__('datetime').datetime.now()}")

    try:
        # 步骤 1：触发 Celery 控制通道初始化
        print("[Warmup] [1/3] Initializing Celery control channel...")
        inspect = celery_app.control.inspect(timeout=2.0)
        pong = inspect.ping()
        if pong:
            worker_names = list(pong.keys())
            print(f"[Warmup] [1/3] Control channel: OK (responded: {worker_names})")
            print(f"[Warmup] [1/3] WARNING: Found {len(worker_names)} worker(s) already running!")
            # 尝试获取更多信息
            try:
                stats = inspect.stats()
                if stats:
                    for worker_name, worker_stats in stats.items():
                        print(f"[Warmup] [1/3]   - {worker_name}")
                        pool = worker_stats.get('pool', {})
                        print(f"[Warmup] [1/3]     Pool: {pool.get('max-concurrency', 'unknown')} concurrency")
            except Exception as e:
                print(f"[Warmup] [1/3] Could not get worker stats: {e}")
        else:
            print("[Warmup] [1/3] Control channel: No active workers (expected during startup)")

        # 步骤 2：触发 Redis 连接（访问 backend）
        print("[Warmup] [2/3] Establishing Redis connection...")
        try:
            backend = celery_app.backend
            if backend:
                # 强制访问 backend，触发连接建立
                _ = backend
                print("[Warmup] [2/3] Redis connection: OK")
            else:
                print("[Warmup] [2/3] Redis: No backend configured")
        except Exception as e:
            print(f"[Warmup] [2/3] Redis warning: {e}")

        # 步骤 3：触发 Elasticsearch 连接
        print("[Warmup] [3/3] Establishing Elasticsearch connection...")
        try:
            from kb_service.es_store import es_service_store
            health = es_service_store.client.cluster.health()
            cluster_status = health.get("status", "unknown")
            print(f"[Warmup] [3/3] Elasticsearch cluster: {cluster_status}")
        except Exception as e:
            print(f"[Warmup] [3/3] Elasticsearch warning: {e}")

        # 完成
        print("[Warmup] ========== Worker Warmup Finished ==========")
        print("[Warmup] Worker is ready to accept tasks!")
        print("")

    except Exception as e:
        print(f"[Warmup] ERROR: {e}")
        # 预热失败不影响 Worker 运行


if __name__ == "__main__":
    # ========== 在启动 Worker 之前执行预热 ==========
    warmup_worker()

    import platform
    is_windows = platform.system() == "Windows"

    worker_args = [
        "worker",
        "-l", "info",
        "-Q", "celery,kb_queue",
    ]

    if is_windows:
        # Windows 使用 solo 池以获得更好的兼容性
        worker_args.extend(["-P", "solo"])
    else:
        # Linux 使用 prefork 池，并发数默认 4（可通过环境变量 CELERY_CONCURRENCY 调整）
        import os
        concurrency = os.environ.get("CELERY_CONCURRENCY", "4")
        worker_args.extend(["-P", "prefork", "-c", concurrency])

    celery_app.worker_main(worker_args)
