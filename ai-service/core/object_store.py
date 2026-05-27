"""📦 (MinIO) 只管"取"（从Java后端上传的文件路径读取）"""
from minio import Minio
from minio.error import S3Error
from core.config import settings


class ObjectStore:
    """MinIO 对象存储客户端"""
    
    def __init__(self):
        """初始化 MinIO 客户端"""
        self.client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
    
    def _parse_path(self, minio_path: str) -> tuple[str, str]:
        """
        解析 MinIO 路径，提取 bucket 和 object 路径
        
        Args:
            minio_path: MinIO 路径，格式为 "bucket/kb_id/doc_id/filename"
                       例如: "knowledge-base/test_kb_001/test_doc_001/合金优点.txt"
            
        Returns:
            (bucket_name, object_path) 元组
        """
        # 路径格式：bucket/kb_id/doc_id/filename
        # 第一个斜杠前的部分作为 bucket，剩余部分作为 object_path
        if "/" in minio_path:
            parts = minio_path.split("/", 1)
            return parts[0], parts[1]
        # 如果没有斜杠，抛出错误（路径必须包含 bucket 名称）
        raise ValueError(f"路径格式错误：'{minio_path}'，应为 'bucket/path/to/file' 格式")
    
    def get_object(self, minio_path: str) -> bytes:
        """
        从 MinIO 获取对象

        Args:
            minio_path: MinIO 路径，格式为 "bucket/kb_id/doc_id/filename"
                       例如: "knowledge-base/test_kb_001/test_doc_001/合金优点.txt"

        Returns:
            对象内容（字节）
        """
        try:
            bucket_name, object_path = self._parse_path(minio_path)
            response = self.client.get_object(bucket_name, object_path)
            data = response.read()
            response.close()
            response.release_conn()
            return data
        except S3Error as e:
            # WORKAROUND: If the object wasn't found, try with bucket name prepended to object path
            # This handles cases where files were incorrectly stored with bucket prefix in object name
            try:
                bucket_name, object_path = self._parse_path(minio_path)
                object_path_with_bucket = f"{bucket_name}/{object_path}"
                print(f"[ObjectStore] Retrying with bucket prefix: {object_path_with_bucket}")
                response = self.client.get_object(bucket_name, object_path_with_bucket)
                data = response.read()
                response.close()
                response.release_conn()
                return data
            except S3Error:
                raise Exception(f"获取对象失败: {e}")
    
    def object_exists(self, minio_path: str) -> bool:
        """
        检查对象是否存在
        
        Args:
            minio_path: MinIO 路径，格式为 "bucket/kb_id/doc_id/filename"
                       例如: "knowledge-base/test_kb_001/test_doc_001/合金优点.txt"
            
        Returns:
            是否存在
        """
        try:
            bucket_name, object_path = self._parse_path(minio_path)
            self.client.stat_object(bucket_name, object_path)
            return True
        except S3Error:
            return False
    
    def put_object(self, object_name: str, data: bytes,
                   content_type: str = "application/octet-stream",
                   bucket: str | None = None) -> str:
        """
        上传对象到 MinIO。

        Args:
            object_name: 对象路径，格式为 "images/filename.jpg"
            data: 对象内容（字节）
            content_type: 内容类型，例如 "image/jpeg"
            bucket: 桶名，默认使用 settings.MINIO_BUCKET

        Returns:
            minio_path，格式为 "bucket/object_name"
        """
        try:
            from io import BytesIO

            bucket_name = bucket or settings.MINIO_BUCKET

            # 确保bucket存在
            if not self.client.bucket_exists(bucket_name):
                self.client.make_bucket(bucket_name)

            # FIX: 如果object_name包含bucket名称前缀，则移除它
            if object_name.startswith(f"{bucket_name}/"):
                object_name = object_name[len(bucket_name)+1:]
                print(f"[ObjectStore] Removed bucket prefix, new object_name: {object_name}")

            # 上传对象
            self.client.put_object(
                bucket_name,
                object_name,
                BytesIO(data),
                length=len(data),
                content_type=content_type
            )

            return f"{bucket_name}/{object_name}"

        except S3Error as e:
            raise Exception(f"上传对象失败: {e}")

    def put_markdown(self, kb_id: str, doc_id: str, doc_name: str, markdown_content: str) -> str:
        """
        上传 Markdown 文件到 MinIO

        Args:
            kb_id: 知识库 ID
            doc_id: 文档 ID
            doc_name: 文档名称（不含扩展名）
            markdown_content: Markdown 内容

        Returns:
            MinIO 中 md 文件的完整路径，格式: "knowledge-base/{kb_id}/{doc_id}/{doc_name}.md"
        """
        md_filename = f"{doc_name}.md"
        object_name = f"{kb_id}/{doc_id}/{md_filename}"
        md_bytes = markdown_content.encode('utf-8')

        url = self.put_object(
            object_name=object_name,
            data=md_bytes,
            content_type="text/markdown"
        )

        return url

    def get_markdown(self, kb_id: str, doc_id: str, doc_name: str) -> str:
        """
        从 MinIO 获取 Markdown 文件内容

        Args:
            kb_id: 知识库 ID
            doc_id: 文档 ID
            doc_name: 文档名称（不含扩展名）

        Returns:
            Markdown 内容（字符串）
        """
        md_filename = f"{doc_name}.md"
        minio_path = f"knowledge-base/{kb_id}/{doc_id}/{md_filename}"
        data = self.get_object(minio_path)
        return data.decode('utf-8')

    def delete_object(self, minio_path: str) -> bool:
        """
        从 MinIO 删除对象

        Args:
            minio_path: MinIO 路径，格式为 "knowledge-base/path/to/file.jpg"
                       完整URL格式：http://endpoint/bucket/path/to/file.jpg

        Returns:
            是否删除成功
        """
        try:
            # 如果是完整URL，提取路径部分
            if minio_path.startswith("http://") or minio_path.startswith("https://"):
                # 解析URL，提取路径部分（去除协议和域名）
                # 例如: http://10.199.195.21:9000/knowledge-base/alloy_handbook/image.jpg
                #       -> knowledge-base/alloy_handbook/image.jpg
                from urllib.parse import urlparse
                parsed = urlparse(minio_path)
                minio_path = parsed.path.lstrip('/')  # 移除开头的 '/'

            bucket_name, object_path = self._parse_path(minio_path)

            # 删除对象
            self.client.remove_object(bucket_name, object_path)
            print(f"[ObjectStore] Deleted object: {bucket_name}/{object_path}")
            return True

        except S3Error as e:
            print(f"[ObjectStore] Failed to delete object: {e}")
            return False


# 全局对象存储实例
object_store = ObjectStore()
