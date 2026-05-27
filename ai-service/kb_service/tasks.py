"""
kb_service 任务处理模块 - 统一走 DocumentOrchestrator

所有文档处理统一使用 DocumentOrchestrator 分层架构：
  Parser Layer → Chunker Layer (Parent-Child) → Enhancer Layer → Vector Layer → Storage Layer

目前支持的文件类型：
  - PDF：MinerU 解析 → Markdown
  - DOCX：HybridConverter 解析 → Markdown
  - TXT/Excel 等：后续补全 parser

Celery 任务：
  - process_document_task_v2：唯一的文档处理任务
"""
from celery import Celery
from kombu import Queue, Exchange
from core.config import settings
from kb_service.es_store import es_service_store
import traceback


# 创建 Celery 应用实例（与 worker.py 中的配置保持一致）
celery_app = Celery(
    "ai_service",
    broker=settings.CELERY_BROKER,
    backend=settings.CELERY_RESULT_BACKEND or settings.REDIS_URL,
)

# 配置 Celery
celery_app.conf.update(
    # ========== 序列化配置 ==========
    task_serializer=settings.CELERY_TASK_SERIALIZER,
    accept_content=settings.CELERY_ACCEPT_CONTENT,
    result_serializer=settings.CELERY_RESULT_SERIALIZER,
    timezone=settings.CELERY_TIMEZONE,
    enable_utc=settings.CELERY_ENABLE_UTC,
    # ========== 任务队列配置 ==========
    task_queues=[
        Queue("celery", Exchange("celery"), routing_key="celery"),
        Queue("kb_queue", Exchange("celery"), routing_key="kb_queue"),
    ],
    task_routes={
        "kb_service.tasks.*": {"queue": "kb_queue"},
    },
    task_default_queue="kb_queue",
    task_default_exchange="celery",
    # ========== 状态跟踪配置 ==========
    task_track_started=True,
    task_send_sent_event=True,
    worker_send_task_events=True,
    task_ignore_result=False,
    task_eager_propagates=False,
    # ========== 结果后端配置 ==========
    result_backend=settings.CELERY_RESULT_BACKEND or settings.REDIS_URL,
    task_result_expires=3600,
    result_extended=False,
    result_compression='gzip',
    result_backend_transport_options={'retry_policy': {'max_retries': 0}},
    # ========== Worker 预取和任务确认配置 ==========
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # ========== Broker 连接重试配置 ==========
    broker_connection_retry_on_startup=True,
    broker_connection_retry=True,
    broker_connection_max_retries=5,
)


def parse_minio_path(minio_path: str) -> tuple:
    """
    从 minio_path 解析出 kb_id、doc_id 和 file_name

    Args:
        minio_path: MinIO中的文件路径，格式: source-documents/{kb_id}/{doc_id}/{filename}

    Returns:
        (kb_id, doc_id, file_name) 元组
    """
    path_parts = minio_path.split('/')
    if len(path_parts) < 4:
        raise ValueError(
            f"minio_path 格式错误，应为: source-documents/{{kb_id}}/{{doc_id}}/{{filename}}，实际: {minio_path}"
        )
    kb_id = path_parts[1]
    doc_id = path_parts[2]
    file_name = path_parts[3]
    return kb_id, doc_id, file_name


def get_es_store(kb_id: str):
    """
    根据知识库ID获取对应的ESStore实例

    Args:
        kb_id: 知识库ID

    Returns:
        对应的ESStore实例
    """
    return es_service_store


def _notify_django_status(minio_path: str, status: str):
    """处理完成后回调 Django 更新文档状态"""
    try:
        path_parts = minio_path.split('/')
        if len(path_parts) < 3:
            return
        doc_id = path_parts[2]
        import requests
        requests.post(
            f"{settings.DJANGO_API_BASE_URL}/api/knowledge/documents/{doc_id}/status-callback/",
            json={"status": status},
            timeout=5,
        )
    except Exception as e:
        print(f"[Task] 回调 Django 状态更新失败: {e}")


# ==========================================
# 文档处理任务（DocumentOrchestrator）
# ==========================================

@celery_app.task(bind=True, name="kb_service.tasks.process_document_v2")
def process_document_task_v2(
    self,
    minio_path: str,
    file_name: str,
    department: str = None,
    category_l1: int = None,
    category_l2: int = None
):
    """
    文档处理任务 - 统一走 DocumentOrchestrator

    Args:
        minio_path: MinIO中的文件路径，格式: source-documents/{kb_id}/{doc_id}/{uuid}
        file_name: 真实文件名（如：操作规程.docx）
        department: 部门（宏观管理字段）→ metadata.department
        category_l1: 一级分类ID（宏观管理字段）→ metadata.category_l1
        category_l2: 二级分类ID（宏观管理字段）→ metadata.category_l2
    """
    from kb_service.processing.orchestrator import DocumentOrchestrator
    from kb_service.processing.utils.progress_reporter import TaskProgressReporter

    try:
        # 创建进度报告器
        reporter = TaskProgressReporter(self)
        reporter.info(f"开始处理文档: {file_name}", 1)
        reporter.info(f"文件路径: {minio_path}", 2)

        # 创建编排器并处理文档
        orchestrator = DocumentOrchestrator()
        result = orchestrator.process_document(
            minio_path=minio_path,
            file_name=file_name,
            department=department,
            category_l1=category_l1,
            category_l2=category_l2,
            reporter=reporter
        )

        reporter.info("========== SUCCESS ==========", 100)

        # 回调 Django 更新文档状态为 completed
        _notify_django_status(minio_path, "completed")

        return result

    except Exception as e:
        error_msg = str(e)
        traceback_str = traceback.format_exc()
        print(f"[Task] ERROR: {error_msg}")
        print(traceback_str)

        # 回调 Django 更新文档状态为 failed
        _notify_django_status(minio_path, "failed")

        self.update_state(
            state="FAILURE",
            meta={
                "error": error_msg,
                "message": f"处理失败: {error_msg}"
            }
        )

        raise self.retry(exc=e, countdown=60, max_retries=3)
