"""MinIO 客户端 — Django 侧文件上传"""
from io import BytesIO
from minio import Minio
from django.conf import settings


def _get_client() -> Minio:
    return Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE,
    )


def get_minio_client() -> Minio:
    """公开方法：获取 MinIO 客户端实例"""
    return _get_client()


def ensure_bucket(bucket: str) -> None:
    """确保指定桶存在，不存在则创建"""
    client = _get_client()
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)


def upload_to_bucket(bucket: str, object_name: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    """
    上传文件到指定 MinIO 桶。

    Returns:
        对象名称
    """
    client = _get_client()
    ensure_bucket(bucket)
    client.put_object(
        bucket,
        object_name,
        BytesIO(data),
        length=len(data),
        content_type=content_type,
    )
    return object_name


def delete_from_bucket(bucket: str, object_name: str) -> bool:
    """从指定桶删除对象"""
    client = _get_client()
    try:
        client.remove_object(bucket, object_name)
        return True
    except Exception as e:
        print(f"[MinIO] 删除失败: {e}")
        return False


def upload_to_minio(object_name: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    """
    上传文件到 MinIO 的 knowledge-base 桶。

    Args:
        object_name: 对象路径，如 "kb_xxxx/doc-yyyy/uuid.pdf"
        data: 文件内容
        content_type: MIME 类型

    Returns:
        完整的 minio_path，如 "knowledge-base/kb_xxxx/doc-yyyy/uuid.pdf"
    """
    client = _get_client()
    bucket = settings.MINIO_BUCKET

    # 确保 bucket 存在
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)

    client.put_object(
        bucket,
        object_name,
        BytesIO(data),
        length=len(data),
        content_type=content_type,
    )

    return f"{bucket}/{object_name}"


def delete_from_minio(minio_path: str) -> bool:
    """
    从 MinIO 删除对象。

    Args:
        minio_path: 完整路径，如 "knowledge-base/kb_xxxx/doc-yyyy/uuid.pdf"

    Returns:
        是否删除成功
    """
    client = _get_client()
    bucket = settings.MINIO_BUCKET

    # 从 minio_path 提取 object_name（去掉 bucket 前缀）
    prefix = f"{bucket}/"
    object_name = minio_path[len(prefix):] if minio_path.startswith(prefix) else minio_path

    try:
        client.remove_object(bucket, object_name)
        return True
    except Exception as e:
        print(f"[MinIO] 删除失败: {e}")
        return False


def delete_doc_folder_from_minio(minio_path: str) -> bool:
    """
    删除文档在 MinIO 中的整个文件夹（包含原始文件、Markdown、图片等）。

    Args:
        minio_path: 文档中某个文件的完整路径，如 "knowledge-base/kb_xxx/doc-yyy/uuid.pdf"

    Returns:
        是否删除成功
    """
    client = _get_client()
    bucket = settings.MINIO_BUCKET

    # 提取文件夹路径: knowledge-base/kb_xxx/doc-yyy/uuid.pdf → kb_xxx/doc-yyy/
    prefix = f"{bucket}/"
    object_path = minio_path[len(prefix):] if minio_path.startswith(prefix) else minio_path
    # 取到 doc_id 这一级目录
    parts = object_path.split("/")
    if len(parts) >= 3:
        folder_prefix = "/".join(parts[:3]) + "/"
    else:
        folder_prefix = object_path

    try:
        # 列出该前缀下所有对象并逐一删除
        objects = client.list_objects(bucket, prefix=folder_prefix, recursive=True)
        for obj in objects:
            client.remove_object(bucket, obj.object_name)
        return True
    except Exception as e:
        print(f"[MinIO] 删除文件夹失败: {e}")
        return False
