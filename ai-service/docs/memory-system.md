# 记忆系统

AI Service 实现了异步的长期记忆系统，能从对话中自动抽取用户相关的事实，在后续对话中注入到系统提示词。

## 架构总览

```
                    ┌─────────────────────────────────────────────────┐
                    │                 AI Service (:7729)              │
                    │                                                 │
  对话开始           │  MemoryMiddleware                               │
  ─────────→        │    before_node("agent"):                        │
                    │      DjangoMemoryStorage.load_facts()            │
                    │        ↓                                         │
                    │      build_system_prompt(memory_facts=...)       │
                    │        ↓                                         │
                    │      注入到 LLM messages                         │
                    │                                                 │
  对话结束           │  MemoryMiddleware                               │
  ─────────→        │    after_node("agent"):                         │
                    │      asyncio.create_task(_debounced_update)      │
                    │        ↓ 30 秒防抖                               │
                    │      MemoryUpdater.update_from_conversation()    │
                    │        ↓                                         │
                    │      LLM 抽取事实 (no_think)                     │
                    │        ↓                                         │
                    │      DjangoMemoryStorage.save_facts()            │
                    └──────────────────────┬──────────────────────────┘
                                           │ httpx
                                           ↓
                    ┌──────────────────────────────────────────────────┐
                    │            Django 后端 (:8000)                    │
                    │                                                  │
                    │  UserMemory 模型 (chat_memory 表)                │
                    │    ├─ user: FK → auth.User                       │
                    │    ├─ agent_name: str                            │
                    │    ├─ fact: str (事实内容)                        │
                    │    ├─ category: choice (偏好/知识/目标/背景/上下文) │
                    │    ├─ confidence: float (0-1)                     │
                    │    ├─ source_conv_id: int (来源会话)               │
                    │    └─ access_count: int (访问计数)                 │
                    │                                                  │
                    │  API 端点:                                       │
                    │    GET  /api/chat/memory/        读取记忆         │
                    │    POST /api/chat/memory/batch/  批量写入         │
                    │    DELETE /api/chat/memory/batch/ 批量删除        │
                    └──────────────────────────────────────────────────┘
```

## 数据流

### 1. 记忆注入（对话前）

```python
# MemoryMiddleware.before_node("agent")
# 1. 从 Django 加载用户记忆
facts = await storage.load_facts(user_id, agent_name="default", limit=15)

# 2. 注入到系统 Prompt
# build_system_prompt() 会在 Prompt 中添加：
# ## 关于用户的长期记忆
# - [偏好] 用户喜欢简洁的技术解释
# - [知识] 用户是金属材料领域的研究员
```

### 2. 事实抽取（对话后）

```python
# MemoryMiddleware.after_node("agent")
# 1. 异步触发（30 秒防抖，避免频繁调用 LLM）
asyncio.create_task(_debounced_update(user_id, messages, ...))

# 2. 过滤消息（只保留 user + 最终 assistant 回答，跳过中间工具调用）
filtered = filter_messages_for_memory(messages)

# 3. 调用 LLM 抽取事实（no_think 模式，低成本）
updates = await updater.update_from_conversation(user_id, filtered)

# 4. 持久化
# LLM 返回 JSON：{"add": [...], "delete": [...]}
# 新事实 → Django API 创建
# 过期事实 → Django API 删除
```

### 3. LLM 抽取 Prompt

系统使用 `src/harness/memory/prompt.py` 中的 `FACT_EXTRACTION_SYSTEM` 模板，要求 LLM：

- 分析对话中揭示的用户信息
- 与现有记忆去重
- 返回结构化 JSON：

```json
{
  "add": [
    {"fact": "用户主要从事合金材料研究", "category": "background", "confidence": 0.9}
  ],
  "delete": [1, 3]  // 过期事实的 ID
}
```

## 记忆分类

| 类别 | 说明 | 示例 |
|------|------|------|
| `preference` | 用户偏好 | "喜欢简洁的回答风格" |
| `knowledge` | 用户已有的知识 | "熟悉 Python 和 LangChain" |
| `goal` | 用户目标 | "正在搭建知识库问答系统" |
| `background` | 背景 | "金属材料领域研究员" |
| `context` | 上下文信息 | "当前项目使用 FastAPI" |

## 置信度机制

- 每条事实有 `confidence` 字段（0-1）
- 加载时只返回 `confidence >= 0.5` 的高置信度事实
- 按 `confidence` 降序 + `updated_at` 降序排列
- 默认加载最多 15 条

## 防抖机制

记忆更新使用 30 秒防抖，避免用户快速连续提问时频繁调用 LLM：

```python
# MemoryMiddleware 中的防抖实现
async def _debounced_update(self, user_id, messages, ...):
    await asyncio.sleep(30)  # 防抖延迟
    await self.updater.update_from_conversation(user_id, messages, ...)
```

使用 `asyncio.create_task()` 在后台异步执行，不阻塞对话响应。

## 存储接口

`MemoryStorage` 抽象基类定义三个操作：

```python
class MemoryStorage(ABC):
    async def load_facts(self, user_id, agent_name, limit) -> List[dict]
    async def save_facts(self, user_id, facts, agent_name, conversation_id) -> int
    async def delete_facts(self, user_id, fact_ids) -> int
```

当前实现：`DjangoMemoryStorage`，通过 httpx 调用 Django REST API。

## Django 端 API

### 读取记忆

```
GET /api/chat/memory/?limit=15&agent_name=default
Authorization: Bearer <JWT>

Response:
{
  "facts": [
    {"id": 1, "fact": "...", "category": "preference", "confidence": 0.9, ...}
  ]
}
```

### 批量写入

```
POST /api/chat/memory/batch/
Authorization: Bearer <JWT>

Body:
{
  "agent_name": "default",
  "conversation_id": 42,
  "facts": [
    {"fact": "...", "category": "background", "confidence": 0.8}
  ]
}
```

### 批量删除

```
DELETE /api/chat/memory/batch/
Authorization: Bearer <JWT>

Body:
{
  "ids": [1, 3, 5]
}
```

## 配置

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `DJANGO_API_BASE_URL` | Django API 地址 | `http://localhost:8000` |
| `SERVICE_AUTH_TOKEN` | 服务间认证 Token（可选） | `None` |

## 扩展点

- **存储层**：实现新的 `MemoryStorage` 子类可切换到其他后端（如 Redis、向量数据库）
- **抽取策略**：修改 `prompt.py` 中的模板可调整事实抽取行为
- **注入方式**：修改 `prompts.py` 中的 `build_system_prompt()` 可调整记忆注入格式
- **防抖时间**：`MemoryMiddleware` 构造函数的 `debounce_seconds` 参数
