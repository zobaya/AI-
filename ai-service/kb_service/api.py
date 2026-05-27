"""知识库服务 API - 上传/删除（v2 架构）

支持新的分层架构和 v2 ES 索引结构：
- Parser Layer → Chunker Layer → Enhancer Layer → Vector Layer → Storage Layer
- v2 索引：metadata 嵌套结构
"""
from fastapi import APIRouter, HTTPException, Query, Body, UploadFile, File, Form
from typing import List, Optional
from kb_service.tasks import process_document_task_v2, celery_app
from kb_service.worker_health import worker_health_checker  # Worker 健康检查
from .es_store import es_service_store  # 使用 v2 知识库专用ESStore实例
from core.object_store import object_store
from core.config import settings
import uuid

router = APIRouter()


@router.post("/upload-file")
async def upload_file(
    file: UploadFile = File(..., description="要上传的文件"),
    kb_id: str = Form("general", description="知识库ID"),
    department: str = Form(None, description="部门"),
    category_l1: Optional[int] = Form(None, description="一级分类ID"),
    category_l2: Optional[int] = Form(None, description="二级分类ID")
):
    """
    上传文件到 MinIO

    返回 MinIO 路径，供后续调用 /upload 接口使用

    参数说明：
    - department: 部门（如：安全部、技术部）
    - category_l1: 一级分类
    - category_l2: 二级分类
    """
    import uuid

    # 生成唯一的 doc_id 和文件名
    doc_id = f"doc-{uuid.uuid4()}"
    file_extension = file.filename.split('.')[-1] if '.' in file.filename else ''
    unique_filename = f"{uuid.uuid4()}.{file_extension}" if file_extension else str(uuid.uuid4())

    # 构建 MinIO 对象名称: {kb_id}/{doc_id}/{filename}
    object_name = f"{kb_id}/{doc_id}/{unique_filename}"

    try:
        # 读取文件内容
        file_content = await file.read()

        # 上传到 MinIO
        minio_path = object_store.put_object(
            object_name=object_name,
            data=file_content,
            content_type=file.content_type or 'application/octet-stream'
        )

        return {
            "minio_path": f"source-documents/{object_name}",
            "doc_id": doc_id,
            "file_name": file.filename,
            "minio_url": minio_path,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件上传失败: {str(e)}")


@router.post("/upload")
async def upload_document(
    minio_path: str = Body(..., description="MinIO中的文件路径，格式: source-documents/{kb_id}/{doc_id}/{uuid}"),
    file_name: str = Body(..., description="真实文件名"),
    department: str = Body(None, description="部门"),
    category_l1: Optional[int] = Body(None, description="一级分类ID"),
    category_l2: Optional[int] = Body(None, description="二级分类ID"),
):
    """
    上传文档到知识库 - 使用 DocumentOrchestrator 分层架构

    流程：
    1. 接收 minio_path、file_name 和宏观管理字段
    2. 提交到 Celery Worker 队列
    3. Worker 执行 DocumentOrchestrator 分层架构：
       - Parser Layer: 文件 → Markdown（支持 PDF, DOCX）
       - Chunker Layer: Markdown → 父子分块
       - Enhancer Layer: 填充宏观管理字段
       - Vector Layer: 生成嵌入向量
       - Storage Layer: 写入 kb_service 索引（v2 格式）

    参数说明：
    - minio_path: MinIO路径（文件名部分是UUID），格式: source-documents/{kb_id}/{doc_id}/{uuid}
    - file_name: 真实文件名，用于显示和搜索
    - department: 部门（如：安全部、技术部）→ metadata.department
    - category_l1: 一级分类ID（整数）→ metadata.category_l1
    - category_l2: 二级分类ID（整数）→ metadata.category_l2
    """
    # 从 minio_path 解析 kb_id 和 doc_id
    path_parts = minio_path.split('/')
    if len(path_parts) < 4:
        raise HTTPException(
            status_code=400,
            detail=f"minio_path 格式错误，应为: source-documents/{{kb_id}}/{{doc_id}}/{{uuid}}，实际: {minio_path}"
        )
    kb_id = path_parts[1]
    doc_id = path_parts[2]

    # ========== 红绿灯机制：检查 Worker 健康状态 ==========
    # 目的：防止任务进入"黑洞"（未启动或冷启动中的 Worker）
    # worker_health_checker.require_worker_health()  # 临时禁用，用于调试

    # 调试：打印接收到的参数
    print(f"[API /upload] Received parameters:")
    print(f"  minio_path: {minio_path}")
    print(f"  file_name: {file_name}")

    # 提交异步任务到 Celery（统一走 Orchestrator）
    task = process_document_task_v2.delay(
        minio_path=minio_path,
        file_name=file_name,
        department=department,
        category_l1=category_l1,
        category_l2=category_l2
    )

    return {
        "task_id": task.id,
        "kb_id": kb_id,
        "doc_id": doc_id,
        "file_name": file_name,
        "minio_path": minio_path,
        "status": "pending",
        "message": "任务已提交，正在处理中",
        "metadata": {
            "department": department,
            "category_l1": category_l1,
            "category_l2": category_l2,
        }
    }


@router.get("/tasks/{task_id}")
async def get_task_status(
    task_id: str,
):
    """
    查询Celery任务状态

    用于轮询上传任务的处理进度
    """
    try:
        task = celery_app.AsyncResult(task_id)

        print(f"[DEBUG] Task {task_id}: state={task.state}, info={task.info}")

        result = {
            "task_id": task_id,
            "status": task.state,  # PENDING, STARTED, PROGRESS, SUCCESS, FAILURE, RETRY
        }

        if task.state == "PENDING":
            result["message"] = "任务等待中..."
            result["progress"] = 0
        elif task.state == "STARTED":
            # STARTED 状态（task_track_started=True 时会触发）
            info = task.info or {}
            result["message"] = "任务已开始处理..."
            result["progress"] = 5
            result["logs"] = info.get("logs", [])  # 添加日志字段
            result["log_count"] = info.get("log_count", 0)
        elif task.state == "PROGRESS":
            # PROGRESS 状态（自定义状态，包含详细进度信息）
            info = task.info or {}
            print(f"[DEBUG] PROGRESS info: {info}")
            result.update({
                "current_step": info.get("current_step", ""),
                "progress": info.get("progress", 0),
                "message": info.get("message", "处理中..."),
                "logs": info.get("logs", []),  # 添加日志字段
                "log_count": info.get("log_count", 0)
            })
            print(f"[DEBUG] Returning PROGRESS result: {result}")
        elif task.state == "SUCCESS":
            result["message"] = "任务完成"
            result["progress"] = 100
            result["result"] = task.result
        elif task.state == "FAILURE":
            result["message"] = "任务失败"
            result["progress"] = 0
            result["error"] = str(task.info)
        elif task.state == "RETRY":
            result["message"] = "任务重试中..."
            result["progress"] = 25
        else:
            # 其他未知状态，尝试从 info 中获取信息
            info = task.info if task.state != "PENDING" else {}
            result["message"] = f"任务状态: {task.state}"
            result["progress"] = 0
            if isinstance(info, dict):
                result["current_step"] = info.get("current_step", "")
                result["progress"] = info.get("progress", 0)
                result["message"] = info.get("message", result["message"])

        print(f"[DEBUG] Final result: {result}")
        return result
    except Exception as e:
        print(f"[ERROR] get_task_status failed: {e}")
        raise HTTPException(status_code=500, detail=f"查询任务状态失败: {str(e)}")


@router.delete("/documents/{doc_id}")
async def delete_document(
    doc_id: str,
    kb_id: str = Query("", description="知识库ID（可选，为空则只通过doc_id删除）"),
    hard: bool = Query(False, description="是否硬删除"),
):
    """
    删除文档及其所有分块（v2 格式）

    流程：
    1. 接收 doc_id 和可选的 kb_id
    2. 如果 hard=false：软删除所有分块（将 metadata.is_active 设为 false）
    3. 如果 hard=true：硬删除所有分块（从 ES 永久删除）

    注意：
    - kb_id 为可选参数，通用知识库可以省略（只通过 doc_id 删除）
    - 删除文档会删除该文档的所有分块
    - 软删除后可通过恢复接口还原
    """
    try:
        if hard:
            # 硬删除：真正从 ES 删除所有分块
            es_service_store.delete_document(kb_id, doc_id)
            message = f"文档已硬删除（所有分块已从数据库永久删除）"
        else:
            # 软删除：将所有分块的 metadata.is_active 字段设为 false
            es_service_store.soft_delete_document(kb_id, doc_id)
            message = f"文档已禁用（所有分块已标记为未激活状态）"

        return {
            "doc_id": doc_id,
            "kb_id": kb_id,
            "deleted": True,
            "hard_delete": hard,
            "message": message,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除文档失败: {str(e)}")


@router.post("/documents/{doc_id}/disable")
async def disable_document(
    doc_id: str,
    kb_id: str = Query("", description="知识库ID（可选）"),
):
    """
    禁用文档：将文档及其所有分块的 metadata.is_active 设置为 false（v2 格式）

    级联操作：
    - 禁用文档的所有分块（包括父块和子块）
    - 设置删除时间戳
    - 禁用后，所有分块不可被单独启用

    Args:
        doc_id: 文档ID
        kb_id: 知识库ID（可选）
    """
    try:
        es_service_store.disable_document(kb_id, doc_id)
        return {
            "doc_id": doc_id,
            "kb_id": kb_id,
            "disabled": True,
            "message": "文档已禁用（所有分块已禁用）",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"禁用文档失败: {str(e)}")


@router.post("/documents/{doc_id}/enable")
async def enable_document(
    doc_id: str,
    kb_id: str = Query("", description="知识库ID（可选）"),
):
    """
    启用文档：将文档及其所有分块的 metadata.is_active 设置为 true（v2 格式）

    级联操作：
    - 启用文档的所有分块（包括父块和子块）
    - 清除删除时间戳

    Args:
        doc_id: 文档ID
        kb_id: 知识库ID（可选）
    """
    try:
        es_service_store.enable_document(kb_id, doc_id)
        return {
            "doc_id": doc_id,
            "kb_id": kb_id,
            "enabled": True,
            "message": "文档已启用（所有分块已启用）",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"启用文档失败: {str(e)}")


@router.post("/documents/{doc_id}/restore")
async def restore_document(
    doc_id: str,
    kb_id: str = Query("", description="知识库ID（可选，为空则只通过doc_id恢复）"),
):
    """
    恢复已禁用的文档：将所有分块的 metadata.is_active 恢复为 true（v2 格式）

    注意：
    - kb_id 为可选参数，通用知识库可以省略（只通过 doc_id 恢复）
    - 恢复文档会恢复该文档的所有分块
    """
    try:
        es_service_store.restore_document(kb_id, doc_id)
        return {
            "doc_id": doc_id,
            "kb_id": kb_id,
            "restored": True,
            "message": "文档已启用（所有分块已恢复为激活状态）",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"恢复文档失败: {str(e)}")


@router.get("/documents")
async def get_documents(
    kb_id: str = Query("", description="知识库ID（可选，默认为通用知识库）"),
    include_inactive: bool = Query(True, description="是否包含已删除的文档"),
):
    """
    获取文档列表（v2 格式）

    返回指定知识库的所有文档及其分块统计信息
    """
    try:
        # v2 索引字段路径：metadata.doc_id, metadata.is_active, metadata.file_name
        query = {
            "size": 0,  # 不需要返回文档详情，只要聚合结果
            "aggs": {
                "docs": {
                    "terms": {
                        "field": "metadata.doc_id",  # v2: keyword 类型不需要 .keyword 后缀
                        "size": 10000
                    },
                    "aggs": {
                        "active_chunks": {
                            "filter": {
                                "term": {"metadata.is_active": True}  # v2: metadata.is_active
                            },
                            "aggs": {
                                "chunks": {
                                    "value_count": {
                                        "field": "metadata.chunk_id"  # v2: metadata.chunk_id
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        try:
            response = es_service_store.client.search(index=es_service_store.index_name, body=query)
        except TypeError:
            response = es_service_store.client.search(index=es_service_store.index_name, **query)

        print(f"[DEBUG] ES 查询状态: {response.get('hits', {}).get('total', 0)} total hits")

        # 处理聚合结果
        documents = []
        aggregations = response.get("aggregations", {})
        print(f"[DEBUG] 聚合结果: {list(aggregations.keys())}")
        buckets = aggregations.get("docs", {}).get("buckets", [])

        print(f"[DEBUG] 找到 {len(buckets)} 个文档桶")

        for bucket in buckets:
            doc_id = bucket["key"]
            # 从 active_chunks 聚合中获取激活的分块数
            active_chunks = bucket.get("active_chunks", {})
            active_chunk_count = active_chunks.get("chunks", {}).get("value", 0)

            # 获取总分块数（包括已禁用的）
            total_chunk_count = bucket.get("doc_count", 0)

            # 文档状态：如果有任何激活的分块，则文档为激活状态
            is_active = active_chunk_count > 0

            print(f"[DEBUG] doc_id={doc_id}, active_chunks={active_chunk_count}, total_chunks={total_chunk_count}, is_active={is_active}")

            # 查询父子分块统计（统计所有分块，包括禁用的）
            chunk_stats_query = {
                "query": {
                    "bool": {
                        "must": [
                            {"term": {"metadata.doc_id": doc_id}}  # v2: keyword 类型不需要 .keyword 后缀
                        ]
                    }
                },
                "size": 0,
                "aggs": {
                    "by_level": {
                        "terms": {
                            "field": "metadata.chunk_level",  # v2: metadata.chunk_level 是 long 类型，可以直接聚合
                            "size": 10
                        }
                    }
                }
            }

            try:
                stats_response = es_service_store.client.search(index=es_service_store.index_name, body=chunk_stats_query)
            except TypeError:
                stats_response = es_service_store.client.search(index=es_service_store.index_name, **chunk_stats_query)

            # 统计父子分块数量
            # 父块：chunk_level=1，子块：chunk_level=2
            level_buckets = stats_response.get("aggregations", {}).get("by_level", {}).get("buckets", [])

            parent_count = 0
            child_count = 0

            for level_bucket in level_buckets:
                level = level_bucket.get("key", 0)
                count = level_bucket.get("doc_count", 0)

                if level == 1:
                    parent_count += count
                elif level == 2:
                    child_count += count

            # 获取第一个分块的其他元数据（优先查询未删除的分块，如果没有则查询所有分块）
            doc_query = {
                "query": {
                    "bool": {
                        "must": [{"term": {"metadata.doc_id": doc_id}}]  # v2: keyword 类型不需要 .keyword 后缀
                    }
                },
                "size": 1,
                "sort": [
                    {"metadata.is_active": {"order": "desc"}},  # v2: metadata.is_active
                    {"metadata.chunk_id": {"order": "asc"}}  # v2: metadata.chunk_id
                ]
            }

            try:
                doc_response = es_service_store.client.search(index=es_service_store.index_name, body=doc_query)
            except TypeError:
                doc_response = es_service_store.client.search(index=es_service_store.index_name, **doc_query)

            hits = doc_response.get("hits", {}).get("hits", [])
            first_chunk = hits[0]["_source"] if hits else {}
            metadata = first_chunk.get("metadata", {})  # v2: metadata 嵌套

            documents.append({
                "doc_id": doc_id,
                "file_name": metadata.get("file_name", ""),  # v2: metadata.file_name
                "chunk_count": active_chunk_count if is_active else parent_count + child_count,  # 激活文档显示激活数，禁用文档显示总数
                "total_chunks": total_chunk_count,  # 总分块数
                "parent_count": parent_count,  # 父块数量（所有）
                "child_count": child_count,  # 子块数量（所有）
                "is_active": is_active,
                "department": metadata.get("department"),  # v2: metadata.department
                "category_l1": metadata.get("category_l1"),  # v2: metadata.category_l1
                "category_l2": metadata.get("category_l2"),  # v2: metadata.category_l2
                "upload_time": metadata.get("upload_time"),  # v2: metadata.upload_time
                "update_time": metadata.get("update_time"),  # v2: metadata.update_time
                "delete_time": metadata.get("delete_time"),  # v2: metadata.delete_time
            })

        # 返回所有文档（包括已禁用的文档）
        # 已禁用的文档：is_active = false（所有分块都被禁用）
        # 已启用的文档：is_active = true（至少有一个激活的分块）

        return {
            "kb_id": kb_id or "general",
            "total": len(documents),
            "documents": documents,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取文档列表失败: {str(e)}")


@router.get("/chunks")
async def get_chunks(
    minio_path: str = Query(None, description="MinIO文件路径（与 kb_id/doc_id 二选一）"),
    kb_id: str = Query(None, description="知识库ID（与 minio_path 二选一）"),
    doc_id: str = Query(None, description="文档ID（可选，需要与 kb_id 配合使用）"),
    parent_id: str = Query(None, description="父块ID（获取子块）"),
    chunk_level: int = Query(None, description="分块级别（1=父块，2=子块）", ge=1, le=2),
    size: int = Query(1000, description="返回数量", ge=1, le=10000),
    include_vector: bool = Query(False, description="是否包含向量数据"),
    include_inactive: bool = Query(False, description="是否包含已禁用的分块"),
):
    """
    获取分块列表（v2 格式）

    支持多种查询方式：
    1. 通过 minio_path 查询指定文件的分块
    2. 通过 kb_id 查询指定知识库的分块（可加 doc_id 过滤）
    3. 通过 parent_id 查询指定父块的所有子块
    4. 通过 chunk_level 过滤分块级别（1=父块，2=子块）
    5. 如果都不提供，查询所有分块

    优先级：minio_path > parent_id > (kb_id + doc_id + chunk_level) > 全部
    """
    try:
        # 方式1：通过 minio_path 查询
        if minio_path:
            # 从 minio_path 解析出 kb_id 和 doc_id
            path_parts = minio_path.split('/')
            if len(path_parts) < 4:
                raise HTTPException(
                    status_code=400,
                    detail=f"minio_path 格式错误，应为: source-documents/{{kb_id}}/{{doc_id}}/{{filename}}"
                )
            parsed_kb_id = path_parts[1]
            parsed_doc_id = path_parts[2]

            chunks = es_service_store.get_chunks_by_minio_path(minio_path, None)

            # 移除 content_vector 字段（如果不需要）
            if not include_vector:
                for chunk in chunks:
                    chunk.pop('content_vector', None)

            return {
                "minio_path": minio_path,
                "kb_id": parsed_kb_id,
                "doc_id": parsed_doc_id,
                "total": len(chunks),
                "chunks": chunks,
            }

        # 方式2：通过 kb_id 和可选的 doc_id、parent_id、chunk_level 查询
        # 构建查询条件（v2: metadata 嵌套）
        must_conditions = []

        # 优先处理 parent_id（查询子块）
        if parent_id:
            must_conditions.append({"term": {"metadata.parent_id": parent_id}})

        # kb_id 条件
        if kb_id:
            must_conditions.append({"term": {"metadata.kb_id": kb_id}})  # v2: keyword 类型不需要 .keyword 后缀

        # doc_id 条件
        if doc_id:
            must_conditions.append({"term": {"metadata.doc_id": doc_id}})  # v2: keyword 类型不需要 .keyword 后缀

        # chunk_level 条件
        if chunk_level is not None:
            must_conditions.append({"term": {"metadata.chunk_level": chunk_level}})

        query = {
            "query": {
                "bool": {
                    "must": must_conditions if must_conditions else [{"match_all": {}}],
                    "filter": [
                        {"term": {"metadata.is_active": True}}  # 只返回激活的分块
                    ] if not include_inactive else []  # 如果 include_inactive=True，则不过滤
                }
            },
            "size": size
        }

        try:
            response = es_service_store.client.search(index=es_service_store.index_name, body=query)
        except TypeError:
            response = es_service_store.client.search(index=es_service_store.index_name, **query)

        chunks = []
        for hit in response.get("hits", {}).get("hits", []):
            source = hit["_source"]
            metadata = source.get("metadata", {})  # v2: metadata 嵌套

            chunk_data = {
                # 核心字段
                "chunk_id": metadata.get("chunk_id"),
                "kb_id": metadata.get("kb_id"),
                "doc_id": metadata.get("doc_id"),
                "is_active": metadata.get("is_active", True),
                "content": source.get("content"),
                # 宏观管理字段
                "department": metadata.get("department"),
                "category_l1": metadata.get("category_l1"),
                "category_l2": metadata.get("category_l2"),
                # 父子分块信息
                "parent_id": metadata.get("parent_id"),
                "chunk_level": metadata.get("chunk_level"),
                "chunk_length": metadata.get("chunk_length"),
                # 元数据
                "file_name": metadata.get("file_name"),
                "headers": source.get("headers", ""),
                # 时间字段
                "upload_time": metadata.get("upload_time"),
                "update_time": metadata.get("update_time"),
                "delete_time": metadata.get("delete_time"),
            }

            if include_vector:
                chunk_data["content_vector"] = source.get("content_vector")

            chunks.append(chunk_data)

        return {
            "kb_id": kb_id or "general",
            "doc_id": doc_id,
            "total": len(chunks),
            "chunks": chunks,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取分块列表失败: {str(e)}")


@router.get("/chunks/{chunk_id}")
async def get_chunk(
    chunk_id: str,
    include_vector: bool = Query(False, description="是否包含向量数据"),
):
    """
    获取单个分块详情（v2 格式）

    Args:
        chunk_id: 分块ID
        include_vector: 是否包含向量数据

    Returns:
        分块详情
    """
    try:
        # 使用 metadata.chunk_id 查询，与前端传递的 chunk_id 保持一致
        query = {
            "query": {
                "term": {"metadata.chunk_id": chunk_id}
            }
        }

        try:
            response = es_service_store.client.search(index=es_service_store.index_name, body=query)
        except TypeError:
            response = es_service_store.client.search(index=es_service_store.index_name, **query)

        hits = response.get("hits", {}).get("hits", [])
        if not hits:
            raise HTTPException(status_code=404, detail=f"分块不存在: {chunk_id}")

        source = hits[0]["_source"]
        metadata = source.get("metadata", {})  # v2: metadata 嵌套

        chunk_data = {
            # 核心字段
            "chunk_id": metadata.get("chunk_id"),
            "kb_id": metadata.get("kb_id"),
            "doc_id": metadata.get("doc_id"),
            "is_active": metadata.get("is_active", True),
            "content": source.get("content"),
            # 宏观管理字段
            "department": metadata.get("department"),
            "category_l1": metadata.get("category_l1"),
            "category_l2": metadata.get("category_l2"),
            # 父子分块信息
            "parent_id": metadata.get("parent_id"),
            "chunk_level": metadata.get("chunk_level"),
            "chunk_length": metadata.get("chunk_length"),
            # 元数据
            "file_name": metadata.get("file_name"),
            "headers": source.get("headers", ""),
            # 时间字段
            "upload_time": metadata.get("upload_time"),
            "update_time": metadata.get("update_time"),
            "delete_time": metadata.get("delete_time"),
        }

        if include_vector:
            chunk_data["content_vector"] = source.get("content_vector")

        return chunk_data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取分块详情失败: {str(e)}")


@router.put("/chunks/{chunk_id}")
async def update_chunk(
    chunk_id: str,
    content: Optional[str] = Body(None, description="文本内容（仅父块可修改）"),
    department: Optional[str] = Body(None, description="部门"),
    category_l1: Optional[str] = Body(None, description="一级分类"),
    category_l2: Optional[str] = Body(None, description="二级分类"),
    is_active: Optional[bool] = Body(None, description="是否激活"),
):
    """
    更新单个分块（v2 格式，子块连坐重构）

    规范：
    - 只有父块（chunk_level=1）允许修改 content
    - 子块修改 content 返回 403 Forbidden
    - 父块修改 content 时会：
      1. 检查内容长度是否超过上限（3000字符）
      2. 更新父块内容和向量
      3. 删除所有旧子块
      4. 重新切分子块
      5. 生成新子块向量并写入

    支持更新：
    - content: 文本内容（仅父块，会触发子块重建）
    - department: 部门（父块+子块都允许）
    - category_l1: 一级分类（父块+子块都允许）
    - category_l2: 二级分类（父块+子块都允许）
    - is_active: 状态（父块+子块都允许）
    """
    try:
        # 1. 获取原始分块数据（使用 metadata.chunk_id 查询）
        query = {"query": {"term": {"metadata.chunk_id": chunk_id}}}
        try:
            get_result = es_service_store.client.search(index=es_service_store.index_name, body=query)
        except TypeError:
            get_result = es_service_store.client.search(index=es_service_store.index_name, **query)

        hits = get_result.get("hits", {}).get("hits", [])
        if not hits:
            raise HTTPException(status_code=404, detail=f"分块不存在: {chunk_id}")

        source = hits[0]["_source"]
        es_doc_id = hits[0]["_id"]  # 获取ES文档的_id，用于后续更新
        metadata = source.get("metadata", {})
        chunk_level = metadata.get("chunk_level", 1)

        updates = {}
        metadata_updates = {}
        updated_fields = []
        new_child_ids = []  # 记录新创建的子块 ID

        # 2. 如果更新内容，检查 chunk_level 并执行子块连坐重构
        if content is not None:
            # 检查是否为子块
            if chunk_level == 2:
                raise HTTPException(
                    status_code=403,
                    detail="子块不可被人工修改，请修改关联的父块"
                )

            # 检查内容长度是否超过上限
            MAX_PARENT_CONTENT_LENGTH = 3000  # parent_chunk_size * 1.5
            if len(content) > MAX_PARENT_CONTENT_LENGTH:
                raise HTTPException(
                    status_code=400,
                    detail=f"父块内容超过上限长度 {MAX_PARENT_CONTENT_LENGTH} 字符（当前 {len(content)} 字符）"
                )

            # 生成父块向量
            import requests
            response = requests.post(
                settings.OLLAMA_EMBED_URL,
                json={
                    "model": settings.OLLAMA_BGE_M3_MODEL,
                    "input": content,
                },
                timeout=settings.OLLAMA_TIMEOUT,
            )
            response.raise_for_status()
            result = response.json()
            embeddings = result.get("embeddings", [])
            if not embeddings or len(embeddings) == 0:
                raise ValueError("Ollama 返回的 embeddings 为空")

            content_vector = embeddings[0]
            if len(content_vector) != 1024:
                raise ValueError(f"向量维度错误: 期望 1024 维，实际 {len(content_vector)} 维")

            # 更新父块内容和向量
            updates["content"] = content
            updates["content_vector"] = content_vector
            updated_fields.extend(["content", "content_vector"])

            # 重新切分子块（先创建新子块，成功后再删除旧子块，避免失败时数据丢失）
            # 对于父块，使用它自己的 chunk_id 作为 parent_id
            parent_id = metadata.get("chunk_id")
            parent_is_active = metadata.get("is_active", True)
            parent_delete_time = metadata.get("delete_time", None)
            from langchain_text_splitters import RecursiveCharacterTextSplitter

            child_splitter = RecursiveCharacterTextSplitter(
                chunk_size=settings.PARENT_CHILD_CHILD_CHUNK_SIZE,
                chunk_overlap=settings.PARENT_CHILD_CHILD_CHUNK_OVERLAP,
                length_function=len,
                separators=["\n\n", "\n", "。", "！", "？", "，", " ", ""]
            )

            child_docs = child_splitter.split_text(content)

            # 生成新子块并写入 ES
            from datetime import datetime, timedelta
            current_time = (datetime.utcnow() + timedelta(hours=8)).strftime("%Y-%m-%dT%H:%M:%S")

            for k, child_content in enumerate(child_docs):
                # 生成子块向量
                try:
                    child_response = requests.post(
                        settings.OLLAMA_EMBED_URL,
                        json={
                            "model": settings.OLLAMA_BGE_M3_MODEL,
                            "input": child_content,
                        },
                        timeout=settings.OLLAMA_TIMEOUT,
                    )
                    child_response.raise_for_status()
                    child_result = child_response.json()
                    child_embeddings = child_result.get("embeddings", [])
                    if not child_embeddings or len(child_embeddings) == 0:
                        print(f"[WARNING] 子块 {k} 向量化失败：embeddings 为空")
                        continue

                    child_vector = child_embeddings[0]
                    if len(child_vector) != 1024:
                        print(f"[WARNING] 子块 {k} 向量维度错误：{len(child_vector)} 维")
                        continue
                except Exception as e:
                    print(f"[WARNING] 子块 {k} 向量化异常：{str(e)}")
                    continue

                child_id = f"{parent_id}_C_{k:03d}"

                # 在创建新子块之前，先删除同ID的旧子块（避免版本冲突）
                try:
                    es_service_store.client.delete(
                        index=es_service_store.index_name,
                        id=child_id,
                        ignore=[404]
                    )
                except Exception:
                    pass  # 忽略删除失败（可能不存在）

                # 构建子块文档
                child_doc = {
                    "content": child_content,
                    "content_vector": child_vector,
                    "headers": source.get("headers", ""),
                    "metadata": {
                        "doc_id": metadata.get("doc_id"),
                        "chunk_id": child_id,
                        "parent_id": parent_id,
                        "chunk_level": 2,
                        "chunk_length": len(child_content),
                        "file_name": metadata.get("file_name"),
                        "kb_id": metadata.get("kb_id"),
                        "department": metadata.get("department"),
                        "category_l1": metadata.get("category_l1"),
                        "category_l2": metadata.get("category_l2"),
                        "is_active": parent_is_active,
                        "upload_time": metadata.get("upload_time"),
                        "update_time": current_time,
                        "delete_time": parent_delete_time if not parent_is_active else None,
                    }
                }

                # 写入子块
                try:
                    es_service_store.client.index(
                        index=es_service_store.index_name,
                        id=child_id,
                        body=child_doc
                    )
                except TypeError:
                    es_service_store.client.index(
                        index=es_service_store.index_name,
                        id=child_id,
                        document=child_doc
                    )
                print(f"[INFO] 已创建子块 {child_id} ({len(child_content)} 字)")
                new_child_ids.append(child_id)

            print(f"[INFO] 父块 {parent_id} 共创建了 {len(new_child_ids)} 个子块")
            updated_fields.append("rebuilt_children")

        # 3. 更新其他字段（父块+子块都允许）
        if department is not None:
            metadata_updates["department"] = department
            updated_fields.append("department")

        if category_l1 is not None:
            metadata_updates["category_l1"] = category_l1
            updated_fields.append("category_l1")

        if category_l2 is not None:
            metadata_updates["category_l2"] = category_l2
            updated_fields.append("category_l2")

        if is_active is not None:
            metadata_updates["is_active"] = is_active
            if not is_active:
                # 设置删除时间
                from datetime import datetime, timedelta
                metadata_updates["delete_time"] = (datetime.utcnow() + timedelta(hours=8)).strftime("%Y-%m-%dT%H:%M:%S")
                updated_fields.append("delete_time")
            else:
                # 清除删除时间
                metadata_updates["delete_time"] = None
            updated_fields.append("is_active")

        # 4. 如果没有更新项，返回错误
        if not updates and not metadata_updates:
            raise HTTPException(status_code=400, detail="没有提供任何更新字段")

        # 5. 更新时间戳
        from datetime import datetime, timedelta
        metadata_updates["update_time"] = (datetime.utcnow() + timedelta(hours=8)).strftime("%Y-%m-%dT%H:%M:%S")
        updated_fields.append("update_time")

        # 6. 合并更新（根级别字段和 metadata 嵌套字段）
        if metadata_updates:
            updates["metadata"] = metadata_updates

        # 7. 执行更新（使用ES文档的_id）
        update_doc = {"doc": updates}
        try:
            es_service_store.client.update(
                index=es_service_store.index_name,
                id=es_doc_id,
                refresh=True,  # 立即刷新索引
                body=update_doc,
            )
        except TypeError:
            es_service_store.client.update(
                index=es_service_store.index_name,
                id=es_doc_id,
                refresh=True,  # 立即刷新索引
                document=updates,
            )

        # 8. 同步过滤字段到所有子块（确保父子块过滤字段一致）
        # 过滤字段包括：department, category_l1, category_l2, file_name
        if chunk_level == 1 and parent_id:
            # 准备需要同步的字段
            sync_updates = {}
            if metadata_updates.get("department") is not None:
                sync_updates["department"] = metadata_updates["department"]
            if metadata_updates.get("category_l1") is not None:
                sync_updates["category_l1"] = metadata_updates["category_l1"]
            if metadata_updates.get("category_l2") is not None:
                sync_updates["category_l2"] = metadata_updates["category_l2"]

            # 如果有过滤字段更新，同步到所有子块
            if sync_updates:
                # 查询所有子块（排除刚创建的新子块）
                child_query_dict = {
                    "term": {"metadata.parent_id": parent_id}
                }

                # 如果有新创建的子块，排除它们（因为它们已经有了正确的字段）
                if new_child_ids:
                    child_query_dict = {
                        "bool": {
                            "must": [
                                {"term": {"metadata.parent_id": parent_id}}
                            ],
                            "must_not": [
                                {"ids": {"values": new_child_ids}}
                            ]
                        }
                    }

                try:
                    # 使用 update_by_query 批量更新子块
                    child_result = es_service_store.client.update_by_query(
                        index=es_service_store.index_name,
                        body={
                            "query": child_query_dict,
                            "script": {
                                "lang": "painless",
                                "source": "; ".join([
                                    f"ctx._source.metadata.{k} = params.{k}"
                                    for k in sync_updates.keys()
                                ]),
                                "params": sync_updates
                            }
                        },
                        refresh=True
                    )
                    updated_children = child_result.get('updated', 0)
                    if updated_children > 0:
                        print(f"[INFO] 已同步过滤字段到 {updated_children} 个子块")
                except Exception as e:
                    print(f"[WARNING] 同步子块过滤字段失败: {str(e)}")

        # 9. 父块更新成功后，删除所有旧子块（子块连坐）
        # 注意：必须在父块更新成功后才删除旧子块，确保数据一致性
        # 排除刚创建的新子块，避免版本冲突
        if content is not None and parent_id and new_child_ids:
            delete_query = {
                "query": {
                    "bool": {
                        "must": [
                            {"term": {"metadata.parent_id": parent_id}}
                        ],
                        "must_not": [
                            {"ids": {"values": new_child_ids}}
                        ]
                    }
                }
            }
            try:
                result = es_service_store.client.delete_by_query(
                    index=es_service_store.index_name,
                    body=delete_query,
                    refresh=True,  # 立即刷新索引
                    ignore=[404]
                )
                deleted = result.get('deleted', 0)
                print(f"[INFO] 已删除父块 {parent_id} 的 {deleted} 个旧子块")
            except Exception as e:
                # 记录错误但不中断流程（父块已更新，新子块已创建）
                print(f"[WARNING] 删除旧子块失败: {str(e)}")

        return {
            "success": True,
            "chunk_id": chunk_id,
            "chunk_level": chunk_level,
            "updated_fields": updated_fields,
            "message": f"已更新 {len(updated_fields)} 个字段"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新分块失败: {str(e)}")


@router.delete("/chunks/{chunk_id}")
async def delete_chunk(
    chunk_id: str,
    hard: bool = Query(False, description="是否硬删除"),
):
    """
    删除单个分块（v2 格式，父子级联删除）

    规范：
    - 子块（chunk_level=2）不可被单独删除，返回 403 Forbidden
    - 父块（chunk_level=1）删除时会级联删除所有子块

    - hard=false: 软删除（设置 metadata.is_active=false）
    - hard=true: 硬删除（从 ES 真正删除）
    """
    try:
        # 1. 获取分块数据
        query = {"query": {"term": {"_id": chunk_id}}}
        try:
            get_result = es_service_store.client.search(index=es_service_store.index_name, body=query)
        except TypeError:
            get_result = es_service_store.client.search(index=es_service_store.index_name, **query)

        hits = get_result.get("hits", {}).get("hits", [])
        if not hits:
            raise HTTPException(status_code=404, detail=f"分块不存在: {chunk_id}")

        source = hits[0]["_source"]
        metadata = source.get("metadata", {})
        chunk_level = metadata.get("chunk_level", 1)

        # 2. 检查是否为子块
        if chunk_level == 2:
            raise HTTPException(
                status_code=403,
                detail="子块不可被单独删除，请删除关联的父块"
            )

        # 3. 获取 parent_id（用于级联删除子块）
        parent_id = metadata.get("parent_id") or metadata.get("chunk_id")

        index_name = es_service_store.index_name
        from datetime import datetime, timedelta
        current_time = (datetime.utcnow() + timedelta(hours=8)).strftime("%Y-%m-%dT%H:%M:%S")

        if hard:
            # 硬删除：删除父块 + 级联删除所有子块
            # 删除父块
            try:
                es_service_store.client.delete(
                    index=index_name,
                    id=chunk_id,
                    refresh=True,  # 立即刷新索引
                    ignore=[404]
                )
            except TypeError:
                es_service_store.client.delete(
                    index=index_name,
                    id=chunk_id,
                    refresh=True  # 立即刷新索引
                )

            # 级联删除所有子块
            if parent_id:
                delete_children_query = {
                    "query": {
                        "term": {"metadata.parent_id": parent_id}
                    }
                }
                try:
                    es_service_store.client.delete_by_query(
                        index=index_name,
                        body=delete_children_query,
                        refresh=True,  # 立即刷新索引
                        ignore=[404]
                    )
                except Exception as e:
                    print(f"[WARNING] 级联删除子块失败: {str(e)}")

            message = f"父块及其子块已硬删除"

        else:
            # 软删除：更新父块 + 级联软删除所有子块
            # 软删除父块（v2: metadata.is_active）
            try:
                es_service_store.client.update(
                    index=index_name,
                    id=chunk_id,
                    refresh=True,  # 立即刷新索引
                    body={"doc": {"metadata": {"is_active": False, "delete_time": current_time}}},
                )
            except TypeError:
                es_service_store.client.update(
                    index=index_name,
                    id=chunk_id,
                    refresh=True,  # 立即刷新索引
                    document={"metadata": {"is_active": False, "delete_time": current_time}},
                )

            # 级联软删除所有子块
            if parent_id:
                update_children_query = {
                    "query": {
                        "term": {"metadata.parent_id": parent_id}
                    },
                    "script": {
                        "source": "ctx._source.metadata.is_active = false; ctx._source.metadata.delete_time = params.time;",
                        "lang": "painless",
                        "params": {
                            "time": current_time
                        }
                    }
                }
                try:
                    es_service_store.client.update_by_query(
                        index=index_name,
                        body=update_children_query,
                        refresh=True,  # 立即刷新索引
                        ignore=[404]
                    )
                except Exception as e:
                    print(f"[WARNING] 级联软删除子块失败: {str(e)}")

            message = f"父块及其子块已软删除"

        return {
            "success": True,
            "chunk_id": chunk_id,
            "parent_id": parent_id,
            "chunk_level": chunk_level,
            "hard_delete": hard,
            "message": message,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除分块失败: {str(e)}")


@router.post("/chunks/{chunk_id}/disable")
async def disable_chunk(
    chunk_id: str,
):
    """
    软禁用分块：将分块及其子块的 is_active 字段设置为 false

    规范：
    - 父块（chunk_level=1）禁用时会级联禁用所有子块
    - 子块（chunk_level=2）不可被单独禁用，返回 403 Forbidden
    """
    try:
        # 1. 获取分块数据（使用 metadata.chunk_id 查询）
        query = {"query": {"term": {"metadata.chunk_id": chunk_id}}}
        try:
            get_result = es_service_store.client.search(index=es_service_store.index_name, body=query)
        except TypeError:
            get_result = es_service_store.client.search(index=es_service_store.index_name, **query)

        hits = get_result.get("hits", {}).get("hits", [])
        if not hits:
            raise HTTPException(status_code=404, detail=f"分块不存在: {chunk_id}")

        source = hits[0]["_source"]
        es_doc_id = hits[0]["_id"]  # 获取ES文档的_id
        metadata = source.get("metadata", {})
        chunk_level = metadata.get("chunk_level", 1)

        # 2. 检查是否为子块
        if chunk_level == 2:
            raise HTTPException(
                status_code=403,
                detail="子块不可被单独禁用，请禁用关联的父块"
            )

        # 3. 执行软禁用（使用ES文档的_id）
        es_service_store.soft_disable_chunk(es_doc_id)

        return {
            "success": True,
            "chunk_id": chunk_id,
            "chunk_level": chunk_level,
            "message": "分块已禁用"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"禁用分块失败: {str(e)}")


@router.post("/chunks/{chunk_id}/enable")
async def enable_chunk(
    chunk_id: str,
):
    """
    恢复已禁用的分块：将分块及其子块的 is_active 字段设置为 true

    规范：
    - 父块（chunk_level=1）恢复时会级联恢复所有子块
    - 子块（chunk_level=2）不可被单独恢复，返回 403 Forbidden
    """
    try:
        # 1. 获取分块数据（使用 metadata.chunk_id 查询）
        query = {"query": {"term": {"metadata.chunk_id": chunk_id}}}
        try:
            get_result = es_service_store.client.search(index=es_service_store.index_name, body=query)
        except TypeError:
            get_result = es_service_store.client.search(index=es_service_store.index_name, **query)

        hits = get_result.get("hits", {}).get("hits", [])
        if not hits:
            raise HTTPException(status_code=404, detail=f"分块不存在: {chunk_id}")

        source = hits[0]["_source"]
        es_doc_id = hits[0]["_id"]  # 获取ES文档的_id
        metadata = source.get("metadata", {})
        chunk_level = metadata.get("chunk_level", 1)
        doc_id = metadata.get("doc_id")

        # 2. 子块需要检查文档（父块）是否被禁用
        if chunk_level == 2 and doc_id:
            # 查询文档的任意一个父块状态来代表文档状态
            doc_query = {
                "query": {
                    "bool": {
                        "must": [
                            {"term": {"metadata.doc_id": doc_id}},
                            {"term": {"metadata.chunk_level": 1}},
                            {"term": {"metadata.is_active": True}},
                        ]
                    }
                },
                "size": 1,
                "_source": ["metadata.is_active"]
            }
            try:
                doc_result = es_service_store.client.search(
                    index=es_service_store.index_name, body=doc_query
                )
            except TypeError:
                doc_result = es_service_store.client.search(
                    index=es_service_store.index_name, **doc_query
                )

            doc_hits = doc_result.get("hits", {}).get("hits", [])
            if not doc_hits:
                raise HTTPException(
                    status_code=403,
                    detail="文档已被禁用，无法启用分块。请先启用文档。"
                )

        # 3. 检查是否为子块
        if chunk_level == 2:
            raise HTTPException(
                status_code=403,
                detail="子块不可被单独恢复，请恢复关联的父块"
            )

        # 4. 执行恢复（使用ES文档的_id）
        es_service_store.restore_chunk(es_doc_id)

        return {
            "success": True,
            "chunk_id": chunk_id,
            "chunk_level": chunk_level,
            "message": "分块已恢复"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"恢复分块失败: {str(e)}")


@router.get("/documents/{doc_id}/chunks")
async def get_document_chunks(
    doc_id: str,
    kb_id: str = Query("", description="知识库ID（可选）"),
    include_inactive: bool = Query(False, description="是否包含已禁用的父块"),
):
    """
    获取指定文档的所有父块（不包括子块）

    返回该文档下所有 chunk_level=1 的父块
    """
    try:
        # 构建查询条件（v2: metadata 嵌套）
        must_conditions = [
            {"term": {"metadata.doc_id": doc_id}},
            {"term": {"metadata.chunk_level": 1}}  # 只返回父块
        ]

        if kb_id:
            must_conditions.append({"term": {"metadata.kb_id": kb_id}})

        query = {
            "query": {
                "bool": {
                    "must": must_conditions,
                    "filter": [
                        {"term": {"metadata.is_active": True}}
                    ] if not include_inactive else []
                }
            },
            "size": 10000,  # 父块数量不会太多
            "sort": [{"metadata.chunk_id": "asc"}]  # 按 chunk_id 排序
        }

        try:
            response = es_service_store.client.search(index=es_service_store.index_name, body=query)
        except TypeError:
            response = es_service_store.client.search(index=es_service_store.index_name, **query)

        chunks = []
        for hit in response.get("hits", {}).get("hits", []):
            source = hit["_source"]
            metadata = source.get("metadata", {})

            chunk_data = {
                "chunk_id": metadata.get("chunk_id"),
                "kb_id": metadata.get("kb_id"),
                "doc_id": metadata.get("doc_id"),
                "is_active": metadata.get("is_active", True),
                "content": source.get("content"),
                "department": metadata.get("department"),
                "category_l1": metadata.get("category_l1"),
                "category_l2": metadata.get("category_l2"),
                "parent_id": metadata.get("parent_id"),
                "chunk_level": metadata.get("chunk_level"),
                "chunk_length": metadata.get("chunk_length"),
                "file_name": metadata.get("file_name"),
                "headers": source.get("headers", ""),
                "upload_time": metadata.get("upload_time"),
                "update_time": metadata.get("update_time"),
                "delete_time": metadata.get("delete_time"),
            }

            chunks.append(chunk_data)

        return {
            "doc_id": doc_id,
            "kb_id": kb_id or "general",
            "total": len(chunks),
            "chunks": chunks,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取文档父块失败: {str(e)}")


@router.put("/documents/{doc_id}/metadata")
async def update_document_metadata(
    doc_id: str,
    kb_id: str = Query("", description="知识库ID（可选）"),
    department: Optional[str] = Body(None, description="部门"),
    category_l1: Optional[int] = Body(None, description="一级分类ID"),
    category_l2: Optional[int] = Body(None, description="二级分类ID"),
    file_name: Optional[str] = Body(None, description="文件名"),
):
    """
    更新文档的宏观管理字段，并批量更新该文档的所有分块（v2 格式）

    支持更新：
    - department: 部门
    - category_l1: 一级分类/资料形态
    - category_l2: 二级分类/系统标签
    - file_name: 文件名

    注意：此操作会更新文档的所有分块
    """
    try:
        # 构建更新字段
        updates = {}
        metadata_updates = {}
        updated_fields = []

        if department is not None:
            metadata_updates["department"] = department
            updated_fields.append("department")

        if category_l1 is not None:
            metadata_updates["category_l1"] = category_l1
            updated_fields.append("category_l1")

        if category_l2 is not None:
            metadata_updates["category_l2"] = category_l2
            updated_fields.append("category_l2")

        if file_name is not None:
            metadata_updates["file_name"] = file_name
            updated_fields.append("file_name")

        # 如果没有更新项，返回错误
        if not metadata_updates:
            raise HTTPException(status_code=400, detail="没有提供任何更新字段")

        # 更新时间戳
        from datetime import datetime, timedelta
        metadata_updates["update_time"] = (datetime.utcnow() + timedelta(hours=8)).isoformat()
        updated_fields.append("update_time")

        # 构建查询条件（v2: metadata 嵌套）
        must_conditions = [{"term": {"metadata.doc_id": doc_id}}]  # v2: keyword 类型不需要 .keyword 后缀
        if kb_id:
            must_conditions.append({"term": {"metadata.kb_id": kb_id}})  # v2: keyword 类型不需要 .keyword 后缀

        # 批量更新所有分块
        query = {
            "query": {
                "bool": {
                    "must": must_conditions
                }
            },
            "script": {
                "source": "",
                "lang": "painless"
            }
        }

        # 构建更新脚本（v2: metadata 嵌套）
        script_lines = []
        for field, value in metadata_updates.items():
            if field == "update_time":
                script_lines.append(f"ctx._source.metadata.update_time = '{value}';")
            elif field in ["category_l1", "category_l2"]:
                # integer 字段（可能为 None）
                if value is None:
                    script_lines.append(f"ctx._source.metadata.{field} = null;")
                else:
                    script_lines.append(
                        f"ctx._source.metadata.{field} = {int(value)};"
                    )
            elif field in ["file_name", "department"]:
                # 字符串字段（可能为 None）
                if value is None:
                    script_lines.append(f"ctx._source.metadata.{field} = null;")
                else:
                    script_lines.append(f"ctx._source.metadata.{field} = '{value}';")
            else:
                # 其他字符串字段
                script_lines.append(f"ctx._source.metadata.{field} = '{value}';")

        query["script"]["source"] = "\n".join(script_lines)

        # 执行更新（refresh=True 确保更新立即生效）
        es_service_store.client.update_by_query(
            index=es_service_store.index_name,
            body=query,
            ignore=[404],
            refresh=True  # 立即刷新索引，使更新对后续搜索可见
        )

        return {
            "success": True,
            "doc_id": doc_id,
            "kb_id": kb_id,
            "updated_fields": updated_fields,
            "message": f"已更新文档及其所有分块的 {len(updated_fields)} 个字段"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新文档失败: {str(e)}")


# ══════════════════════════════════════════════════════════════════
#  内部接口（Service Token 认证，供 Django 后端调用）
# ══════════════════════════════════════════════════════════════════


@router.post("/internal/cache/invalidate")
async def invalidate_cache(
    scope: str = Body(..., description="缓存范围，如 tag_registry"),
):
    """
    清除 AI Service 内部缓存。

    由 Django 在标签 CUD 操作后调用，确保标签注册表及时刷新。
    认证由 Service Token 中间件处理。
    """
    if scope == "tag_registry":
        from src.harness.subgraphs.es_search.classify import invalidate_cache as _invalidate
        _invalidate()
        return {"status": "ok", "invalidated": "tag_registry"}

    return {"status": "ok", "invalidated": "none"}


@router.post("/internal/tags/cleanup")
async def cleanup_deleted_tags(
    tag_ids: list[int] = Body(..., description="需要从 ES 中清除的标签 ID 列表"),
):
    """
    标签删除后清洗 ES 数据。

    将引用了指定标签 ID 的所有 chunk 的对应字段置 null。
    由 Django 在标签删除后调用。
    """
    cleaned = []
    for tag_id in tag_ids:
        # 清除 category_l1 匹配的 chunk
        try:
            es_service_store.client.update_by_query(
                index=es_service_store.index_name,
                body={
                    "query": {"term": {"metadata.category_l1": tag_id}},
                    "script": {
                        "source": "ctx._source.metadata.category_l1 = null;",
                        "lang": "painless",
                    },
                },
                refresh=True,
                ignore=[404],
            )
        except Exception as e:
            print(f"[ES] 清理 category_l1={tag_id} 失败: {e}")

        # 清除 category_l2 匹配的 chunk
        try:
            es_service_store.client.update_by_query(
                index=es_service_store.index_name,
                body={
                    "query": {"term": {"metadata.category_l2": tag_id}},
                    "script": {
                        "source": "ctx._source.metadata.category_l2 = null;",
                        "lang": "painless",
                    },
                },
                refresh=True,
                ignore=[404],
            )
        except Exception as e:
            print(f"[ES] 清理 category_l2={tag_id} 失败: {e}")

        cleaned.append(tag_id)

    return {"status": "ok", "cleaned_tag_ids": cleaned}
