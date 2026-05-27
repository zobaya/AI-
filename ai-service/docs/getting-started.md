# 快速开始

## 环境要求

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) 包管理器
- MySQL、Redis、Elasticsearch、MinIO（本地或远程）
- vLLM 服务（Qwen3.5-9B）
- Ollama（bge-m3 嵌入模型）
- BGE Reranker 服务

## 安装

```bash
cd ai-service
uv sync
```

## 配置

复制 `.env.example`（如有）为 `.env`，或直接编辑 `core/config.py` 中的默认值。

关键配置项：

```env
# LLM 服务
VLLM_BASE_URL=http://10.199.194.246:3001
VLLM_MODEL_NAME=/models/Qwen3.5-9B

# Elasticsearch
ES_HOST=localhost
ES_PORT=9200

# MinIO
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=admin
MINIO_SECRET_KEY=password123

# Redis（Celery Broker）
REDIS_HOST=localhost
REDIS_PORT=6379

# Django 后端（记忆系统）
DJANGO_API_BASE_URL=http://localhost:8000

# 合金计算数据库
CALC_DB_HOST=localhost
CALC_DB_DATABASE=hejinshuju
```

## 启动

### 1. 启动 AI 服务

```bash
uv run python main.py
```

服务运行在 `http://0.0.0.0:7729`，提供以下端点：

| 端点 | 方法 | 说明 |
|------|------|------|
| `/agent/api/chat` | POST | SSE 流式对话（核心端点） |
| `/agent/api/upload` | POST | 文件上传到 MinIO |
| `/agent/api/agent-logs` | GET | 日志文件列表 |
| `/agent/api/agent-logs/{id}` | GET | 单个日志详情 |
| `/agent/` | GET | 聊天测试页面 |
| `/agent/logs` | GET | 日志查看页面 |
| `/api/kb/upload` | POST | 知识库文档上传 |
| `/api/kb/upload-file` | POST | 文件上传到 MinIO |

### 2. 启动 Celery Worker（知识库文档处理）

```bash
uv run python worker.py
```

### 3. 启动 Django 后端

```bash
cd E:\AI_Project\backend
.venv/Scripts/python manage.py runserver 8000
```

### 4. 启动前端

```bash
cd E:\AI_Project\frontend
npm run dev
```

## 快速验证

### 测试对话（通过测试页面）

访问 `http://localhost:7729/agent/`，在聊天界面输入问题。

### 测试对话（通过 curl）

```bash
curl -X POST http://localhost:7729/agent/api/chat \
  -H "Content-Type: application/json" \
  -d '{"user_query": "你好"}'
```

### 测试知识库检索

```bash
curl -X POST http://localhost:7729/agent/api/chat \
  -H "Content-Type: application/json" \
  -d '{"user_query": "高处坠落应急处置流程", "allowed_tools": ["es_search"]}'
```

### 测试文件解析

先上传文件：
```bash
curl -X POST http://localhost:7729/agent/api/upload \
  -F "files=@test.pdf"
```

然后带着返回的 `paths` 发起对话：
```bash
curl -X POST http://localhost:7729/agent/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "user_query": "这个文件讲了什么？",
    "minio_paths": ["chat-uploads/xxx_test.pdf"],
    "file_names": ["test.pdf"]
  }'
```

## 代码质量

```bash
# 格式化
uv run black . --line-length 100

# 静态检查
uv run ruff check . --line-length 100

# 类型检查
uv run mypy .

# 测试
uv run pytest
```

## 完整请求流程

```
用户提问
  → Django(:8000) POST /api/chat/send/
    → AI Service(:7729) POST /agent/api/chat
      → rewrite 节点（查询改写）
      → agent 节点（LLM 推理）
        → tools 节点（工具执行，可能多轮循环）
      → maybe 节点（标题 + 推荐问题）
    ← SSE 事件流
  ← StreamingHttpResponse
← 前端渲染
```
