""" Pydantic 配置管理 """
import os

from dotenv import load_dotenv
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional

# 基于 config.py 所在目录定位 .env 文件，确保从任意工作目录启动都能加载
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Settings(BaseSettings):
    """应用配置"""
    
    # ========== 应用基础配置 ==========
    APP_NAME: str = "AI Service"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = True
    
    # ========== MySQL 配置 ==========
    MYSQL_HOST: str = Field(default="localhost", description="MySQL 主机地址")
    MYSQL_PORT: int = Field(default=3306, description="MySQL 端口")
    MYSQL_USER: str = Field(default="root", description="MySQL 用户名")
    MYSQL_PASSWORD: str = Field(default="123456", description="MySQL 密码")
    MYSQL_DATABASE: str = Field(default="ai_service", description="MySQL 数据库名")
    MYSQL_CHARSET: str = Field(default="utf8mb4", description="MySQL 字符集")

    # ========== 合金计算数据库配置 ==========
    CALC_DB_HOST: str = Field(default="localhost", description="合金计算 MySQL 主机地址")
    CALC_DB_PORT: int = Field(default=3306, description="合金计算 MySQL 端口")
    CALC_DB_USER: str = Field(default="root", description="合金计算 MySQL 用户名")
    CALC_DB_PASSWORD: str = Field(default="123456", description="合金计算 MySQL 密码")
    CALC_DB_DATABASE: str = Field(default="hejinshuju", description="合金计算 MySQL 数据库名")
    CALC_DB_CHARSET: str = Field(default="utf8mb4", description="合金计算 MySQL 字符集")
    
    @property
    def MYSQL_URL(self) -> str:
        """MySQL 连接 URL"""
        return (
            f"mysql+pymysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"
            f"?charset={self.MYSQL_CHARSET}"
        )
    
    # ========== MinIO 配置 ==========
    MINIO_ENDPOINT: str = Field(default="localhost:9000", description="MinIO 服务地址")
    MINIO_ACCESS_KEY: str = Field(default="admin", description="MinIO Access Key")
    MINIO_SECRET_KEY: str = Field(default="password123", description="MinIO Secret Key")
    MINIO_SECURE: bool = Field(default=False, description="是否使用 HTTPS")
    MINIO_BUCKET: str = Field(default="knowledge-base", description="MinIO 存储桶名称")
    MINIO_GENERATED_BUCKET: str = Field(default="generated-files", description="AI 生成文件桶")
    MINIO_CHAT_UPLOAD_BUCKET: str = Field(default="chat-uploads", description="聊天上传文件桶")
    
    # ========== Redis 配置 ==========
    REDIS_HOST: str = Field(default="localhost", description="Redis 主机地址")
    REDIS_PORT: int = Field(default=6379, description="Redis 端口")
    REDIS_PASSWORD: Optional[str] = Field(default=None, description="Redis 密码（本地无密码留空）")
    REDIS_DB: int = Field(default=0, description="Redis 数据库编号")
    
    @property
    def REDIS_URL(self) -> str:
        """Redis 连接 URL"""
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
    
    # ========== Celery 配置 ==========
    CELERY_BROKER_URL: Optional[str] = Field(default=None, description="Celery Broker URL（默认使用 Redis）")
    CELERY_RESULT_BACKEND: Optional[str] = Field(default=None, description="Celery Result Backend（默认使用 Redis）")
    CELERY_TASK_SERIALIZER: str = Field(default="json", description="任务序列化格式")
    CELERY_RESULT_SERIALIZER: str = Field(default="json", description="结果序列化格式")
    CELERY_ACCEPT_CONTENT: list = Field(default=["json"], description="接受的内容类型")
    CELERY_TIMEZONE: str = Field(default="Asia/Shanghai", description="时区")
    CELERY_ENABLE_UTC: bool = Field(default=True, description="启用 UTC")
    CELERY_TASK_RESULT_EXPIRES: int = Field(default=3600, description="任务结果过期时间（秒）")
    
    @property
    def CELERY_BROKER(self) -> str:
        """Celery Broker URL（自动使用 Redis）"""
        return self.CELERY_BROKER_URL or self.REDIS_URL
    
    # ========== Elasticsearch 配置 ==========
    ES_HOST: str = Field(default="localhost", description="Elasticsearch 主机地址")
    ES_PORT: int = Field(default=9200, description="Elasticsearch 端口")
    ES_USERNAME: Optional[str] = Field(default="elastic", description="Elasticsearch 用户名")
    ES_PASSWORD: Optional[str] = Field(default="keyanlou704", description="Elasticsearch 密码")
    ES_USE_SSL: bool = Field(default=False, description="是否使用 SSL")

    # ES 索引配置
    # 知识库索引
    KB_SERVICE_INDEX: str = Field(default="kb_service", description="通用知识库索引名称（v2 结构，metadata 嵌套）")

    @property
    def ES_URL(self) -> str:
        """Elasticsearch 连接 URL"""
        protocol = "https" if self.ES_USE_SSL else "http"
        if self.ES_USERNAME and self.ES_PASSWORD:
            return f"{protocol}://{self.ES_USERNAME}:{self.ES_PASSWORD}@{self.ES_HOST}:{self.ES_PORT}"
        return f"{protocol}://{self.ES_HOST}:{self.ES_PORT}"

    # ========== Ollama 配置 (bge-m3) ==========
    OLLAMA_BASE_URL: str = Field(default="http://10.199.194.246:11434", description="Ollama 服务地址")
    OLLAMA_BGE_M3_MODEL: str = Field(default="bge-m3", description="bge-m3 模型名称")
    OLLAMA_TIMEOUT: int = Field(default=900, description="请求超时时间（秒）")
    
    @property
    def OLLAMA_EMBED_URL(self) -> str:
        """Ollama Embedding API URL"""
        return f"{self.OLLAMA_BASE_URL}/api/embed"
    
    # ========== vLLM 语言模型配置 (Qwen3.5-9B) ==========
    VLLM_BASE_URL: str = Field(default="http://10.199.194.246:3001", description="vLLM 服务地址")
    VLLM_MODEL_NAME: str = Field(default="/models/Qwen3.5-9B", description="vLLM 模型名称")
    VLLM_TIMEOUT: int = Field(default=600, description="请求超时时间（秒）")
    VLLM_MAX_TOKENS: int = Field(default=16384, description="最大生成 token 数（16K，约 8000-12000 汉字，实际会根据输入大小动态调整）")
    VLLM_MAX_MODEL_LEN: int = Field(default=40960, description="vLLM max-model-len，即模型上下文窗口总大小（token 数）")
    VLLM_TEMPERATURE: float = Field(default=0.7, description="温度参数（从 0.3 提高到 0.7，增加输出多样性）")
    VLLM_STREAM: bool = Field(default=False, description="是否流式返回")

    # ========== vLLM 视觉模型配置 (qwen2.5-vl-7b-instruct) ==========
    VLLM_VLM_BASE_URL: str = Field(default="http://10.199.194.246:3002", description="vLLM VLM服务地址")
    VLLM_VLM_MODEL_NAME: str = Field(default="/models/Qwen2.5-VL-7B-Instruct", description="vLLM VLM模型名称")

    # ========== Django 后端配置 ==========
    DJANGO_API_BASE_URL: str = Field(default="http://localhost:8000", description="Django 后端 API 地址（记忆系统调用）")
    SERVICE_AUTH_TOKEN: Optional[str] = Field(default=None, description="服务间认证 Token（如需）")
    
    @property
    def VLLM_CHAT_URL(self) -> str:
        """vLLM Chat API URL"""
        return f"{self.VLLM_BASE_URL}/v1/chat/completions"
    
    @property
    def VLLM_COMPLETIONS_URL(self) -> str:
        """vLLM Completions API URL"""
        return f"{self.VLLM_BASE_URL}/v1/completions"
    
    # ========== 文件上传配置 ==========
    UPLOAD_MAX_SIZE: int = Field(default=100 * 1024 * 1024, description="最大上传文件大小（字节），默认 100MB")
    UPLOAD_ALLOWED_EXTENSIONS: list = Field(
        default=[".pdf", ".docx", ".xlsx", ".txt", ".png", ".jpg", ".jpeg"],
        description="允许的文件扩展名"
    )
    
    # ========== MinerU 配置 ==========
    MINERU_API_URL: str = Field(default="http://10.199.194.246:8010/file_parse", description="MinerU API 服务地址")
    MINERU_API_TIMEOUT: int = Field(default=600, description="MinerU API 超时时间（秒），用于 file_parse 接口")

    # ========== 解析层配置 ==========
    # Hybrid Converter 配置（MarkItDown + Mammoth + VLM）
    USE_HYBRID_CONVERTER: bool = Field(default=True, description="是否启用混合转换器（MarkItDown+Mammoth+VLM），False 则使用传统 python-docx")
    HYBRID_CONVERTER_IMAGE_MIN_SIZE: int = Field(default=50, description="图像最小尺寸（宽度和高度，像素），小于此值的图像会被过滤")
    HYBRID_CONVERTER_USE_VLM: bool = Field(default=True, description="是否使用 VLM 理解图像内容（需要 VLM 服务）")

    # ========== 分块层配置 ==========
    # 父子分块配置（LangChain + LCA 算法）
    USE_PARENT_CHILD_CHUNKING: bool = Field(default=True, description="是否启用父子分块（LangChain + LCA），False 则使用普通语义分块")
    PARENT_CHILD_SMALL_FILE_THRESHOLD: int = Field(default=2000, description="小文件阈值（字符），小于此值的文件作为单个父块")
    PARENT_CHILD_PARENT_TARGET_SIZE: int = Field(default=2000, description="父块目标大小（字符）")
    PARENT_CHILD_CHILD_CHUNK_SIZE: int = Field(default=350, description="子块大小（字符）")
    PARENT_CHILD_CHILD_CHUNK_OVERLAP: int = Field(default=50, description="子块重叠（字符）")
    PARENT_CHILD_FRAGMENT_MIN_SIZE: int = Field(default=500, description="碎片阈值（字符），小于此值的块会被视为碎片并尝试合并")

    # ========== QA Service 配置 ==========
    QA_ENABLE_LOG_AGENT: bool = Field(default=True, description="是否启用 QA 服务的日志记录")
    QA_DEFAULT_TOP_K: int = Field(default=10, description="QA 服务默认检索结果数量")
    QA_MAX_TOP_K: int = Field(default=50, description="QA 服务最大检索结果数量")

    # ========== 通用知识库检索配置（五步检索流程） ==========
    # 双路召回配置
    QA_RECALL_BM25_TOP_K: int = Field(default=100, description="BM25 召回返回前 K 条结果（子块）")
    QA_RECALL_KNN_TOP_K: int = Field(default=100, description="KNN 召回返回前 K 条结果（子块）")

    # RRF 融合配置
    QA_RRF_K: int = Field(default=60, description="RRF 融合参数 k（默认 60）")
    QA_RRF_TOP_K: int = Field(default=50, description="RRF 融合返回前 K 条结果（进入重排序）")

    # 父块溯源配置
    QA_PARENT_CHUNK_ENABLED: bool = Field(default=True, description="是否启用父块溯源（Small-to-Big）")
    QA_PARENT_CHUNK_MAX_SIZE: int = Field(default=5000, description="父块最大字符数（超过则截断）")

    # ========== Reranker 配置 ==========
    QA_ENABLE_RERANKER: bool = Field(default=True, description="是否启用重排序")
    QA_RERANKER_TOP_K: int = Field(default=10, description="重排序返回前 K 条结果")
    QA_RERANKER_SCORE_THRESHOLD: float = Field(
        default=0.3, description="重排序分数阈值，低于此值的结果将被过滤（0表示不过滤）"
    )
    RERANKER_BASE_URL: str = Field(default="http://10.199.194.246:9997/v1", description="Reranker 服务地址")
    RERANKER_MODEL_NAME: str = Field(default="bge-reranker-v2-m3", description="Reranker 模型名称")
    RERANKER_MODEL_UID: str = Field(default="bge-reranker-v2-m3", description="Reranker 模型 UID")
    RERANKER_API_KEY: str = Field(default="none", description="Reranker API 密钥")
    RERANKER_TIMEOUT: int = Field(default=30, description="Reranker 请求超时时间（秒）")

    class Config:
        env_file = os.path.join(_PROJECT_ROOT, ".env")
        env_file_encoding = "utf-8"
        case_sensitive = True


# 全局配置实例
load_dotenv(os.path.join(_PROJECT_ROOT, ".env"), override=False)
settings = Settings()
