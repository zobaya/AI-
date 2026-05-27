# 标签管理系统完整文档

## 概览

标签系统采用**严格二级树形结构**（一级分类 + 二级标签），用于对知识库文档进行分类管理。系统贯穿三个服务：

```
Frontend（标签管理页面 + 知识库文档标签分配）
    ↓ HTTP/REST
Backend（标签 CRUD + 文档关联 + 内部注册表）
    ↓ Service Token
AI Service（ES 索引 + 分类检索 + 缓存）
```

**权限控制**：标签的增删改查仅 `sys_admin` 可操作；`dept_admin` 和普通用户可在文档上传/编辑时选择已有标签。

---

## 一、数据模型

### 1.1 Tag 模型（backend/tags/models.py）

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | BigAutoField | 主键 |
| `name` | CharField(100) | 标签名称 |
| `description` | TextField | 描述，可空，默认空字符串 |
| `parent` | ForeignKey("self") | 自引用外键，`on_delete=CASCADE`，`null=True`。一级标签无 parent，二级标签指向一级标签 |
| `level` | PositiveSmallIntegerField | 层级：`1`=一级分类，`2`=二级标签。由 `clean()` 自动校验 |
| `sort_order` | IntegerField | 排序权重，默认 0 |
| `created_by` | ForeignKey("users.User") | 创建者，`on_delete=SET_NULL` |
| `created_at` | DateTimeField | `auto_now_add` |
| `updated_at` | DateTimeField | `auto_now` |

**约束**：
- `unique_together = [("parent", "name")]` — 同一父标签下名称唯一
- `ordering = ["sort_order", "id"]`
- `clean()` 校验：最多两级，父标签必须是一级

### 1.2 Document 模型上的标签字段（backend/knowledge/models.py）

| 字段 | 类型 | on_delete | 说明 |
|------|------|-----------|------|
| `category_l1` | ForeignKey("tags.Tag", null=True) | `SET_NULL` | 一级分类 |
| `category_l2` | ForeignKey("tags.Tag", null=True) | `SET_NULL` | 二级标签 |

`SET_NULL` 意味着：**标签被删除时，文档不会被删除，标签字段被置为 NULL**。

### 1.3 ES 索引中的标签字段

存储在 `metadata` 对象内，类型为 **integer**（存储标签 ID，非标签名称）：

```json
{
  "metadata": {
    "category_l1": {"type": "integer"},
    "category_l2": {"type": "integer"}
  }
}
```

---

## 二、Backend API

所有标签端点挂载在 `api/tags/`（由 `mybackend/urls.py` 注册）。

### 2.1 标签 CRUD 端点

| 端点 | 方法 | 视图 | 权限 | 说明 |
|------|------|------|------|------|
| `/api/tags/` | GET | `TagTreeView` | `IsAuthenticated + IsSysAdmin` | 获取完整二级标签树（含文档计数） |
| `/api/tags/create/` | POST | `TagCreateView` | `IsAuthenticated + IsSysAdmin` | 创建标签（一级或二级） |
| `/api/tags/<int:pk>/` | PUT | `TagDetailView` | `IsAuthenticated + IsSysAdmin` | 更新标签（名称/描述/排序） |
| `/api/tags/<int:pk>/` | DELETE | `TagDetailView` | `IsAuthenticated + IsSysAdmin` | 删除标签（级联处理） |
| `/api/tags/<int:pk>/documents/` | GET | `TagDocumentsView` | `IsAuthenticated + IsSysAdmin` | 查看标签下的文档列表（最多50条） |
| `/api/tags/internal/registry/` | GET | `TagRegistryInternalView` | Service Token 认证 | AI Service 拉取标签分类树 |

### 2.2 标签创建（POST /api/tags/create/）

**请求体**：
```json
{
  "name": "标签名称",
  "description": "描述（可选）",
  "parent_id": 1  // 可选，不传则创建一级标签，传则创建该一级标签下的二级标签
}
```

**处理流程**：
1. 校验 name 非空
2. 若提供 `parent_id`：验证父标签存在且为一级、同级名称不重复 → 创建二级标签
3. 若无 `parent_id`：验证一级标签名称不重复 → 创建一级标签
4. 设置 `created_by = request.user`
5. 调用 `_invalidate_tag_cache()` 通知 AI Service 清除缓存

### 2.3 标签更新（PUT /api/tags/<pk>/）

**请求体**：
```json
{
  "name": "新名称（可选）",
  "description": "新描述（可选）",
  "sort_order": 0  // 可选
}
```

**处理流程**：
1. 若修改名称，验证同级不重名
2. 保存后调用 `_invalidate_tag_cache()`

### 2.4 标签删除（DELETE /api/tags/<pk>/）— 关键流程

删除操作是最复杂的，涉及多处联动：

```
1. 获取目标标签
2. 若是一级标签：收集所有子标签 ID → child_ids
3. 构建 tag_ids_to_clean = [pk] + child_ids
4. 执行 tag.delete()
   → Django CASCADE：一级标签删除时，其下所有二级标签也被删除
   → Document 的 SET_NULL：相关文档的 category_l1/category_l2 被置为 NULL
5. 调用 _cleanup_es_tags(tag_ids_to_clean)
   → POST {AI_SERVICE}/api/kb/internal/tags/cleanup
   → AI Service 将 ES 中匹配 tag ID 的 metadata.category_l1/category_l2 置为 null
6. 调用 _invalidate_tag_cache()
   → POST {AI_SERVICE}/api/kb/internal/cache/invalidate
   → AI Service 清除标签注册表缓存
7. 返回 {"message": "已删除", "child_count": N}
```

### 2.5 标签树查询（GET /api/tags/）

**响应格式**：
```json
{
  "tags": [
    {
      "id": 1,
      "name": "材料科学",
      "description": "...",
      "parent": null,
      "level": 1,
      "sort_order": 0,
      "created_by": "admin",
      "doc_count": 15,
      "created_at": "2026-01-01T00:00:00Z",
      "updated_at": "2026-01-01T00:00:00Z",
      "children": [
        {
          "id": 2,
          "name": "合金材料",
          "description": "...",
          "parent": 1,
          "level": 2,
          "sort_order": 0,
          "created_by": "admin",
          "doc_count": 8,
          "created_at": "...",
          "updated_at": "...",
          "children": []
        }
      ]
    }
  ]
}
```

`doc_count` 统计文档数 = `documents_l1.count() + documents_l2.count()`。

### 2.6 内部注册表端点（GET /api/tags/internal/registry/）

**专供 AI Service 调用**，不走 JWT 认证，手动验证 Service Token：

- 请求头：`Authorization: Service <SERVICE_AUTH_TOKEN>`
- `authentication_classes = []`，`permission_classes = []`

**响应格式**（带 ID 的分类树）：

```json
{
  "categories": [
    {
      "id": 1,
      "category_l1": "材料科学",
      "description": "...",
      "category_l2": [
        {"id": 2, "name": "合金材料", "description": "..."},
        {"id": 3, "name": "高分子材料", "description": "..."}
      ]
    }
  ]
}
```

### 2.7 文档标签修改接口

#### 上传时指定标签（POST /api/knowledge/documents/upload/）

前端在 FormData 中传递：
- `category_l1_id`: 一级标签 ID（可选）
- `category_l2_id`: 二级标签 ID（可选）

后端解析后存储为 Document FK，同时转发给 AI Service 进行 ES 索引。

#### 编辑文档元数据（PUT /api/knowledge/documents/<id>/metadata/）

**请求体**：
```json
{
  "file_name": "新文件名（可选）",
  "category_l1_id": 1,   // 可选，传 null 清除
  "category_l2_id": 2    // 可选，传 null 清除
}
```

**处理流程**：
1. 更新 Document 的 category_l1/category_l2 FK
2. 代理到 AI Service 的 ES 元数据更新接口，同步更新 ES 中的 `metadata.category_l1`/`metadata.category_l2`

---

## 三、Frontend

### 3.1 文件清单

| 文件 | 职责 |
|------|------|
| `api/tags.ts` | TagItem/RelatedDoc 类型定义 + tagsApi（getTree/create/update/delete/getDocuments） |
| `api/knowledge.ts` | TagRef 类型 + 文档上传/编辑中的标签字段 |
| `pages/Tags.tsx` | 标签管理页面（主从布局：左侧标签树 + 右侧详情面板） |
| `pages/Knowledge.tsx` | 知识库页面中的标签分配（UploadModal + DocEditModal） |
| `pages/ChunkDetail.tsx` | 分块详情中的标签只读展示 |
| `components/Layout/Sidebar.tsx` | 侧边栏导航入口（sysAdminOnly） |
| `App.tsx` | 路由 `/admin/tags` |

### 3.2 TypeScript 类型

**TagItem**（`api/tags.ts`）— 完整标签对象：

```typescript
interface TagItem {
  id: number
  name: string
  description: string
  parent: number | null    // null=一级，有值=二级
  level: 1 | 2
  sort_order: number
  children?: TagItem[]     // 仅一级标签有此字段
  created_by: string | null
  doc_count: number
  created_at: string
  updated_at: string
}
```

**TagRef**（`api/knowledge.ts`）— 文档上的轻量标签引用：
```typescript
interface TagRef {
  id: number
  name: string
}
```

### 3.3 标签管理页面（pages/Tags.tsx，约 960 行）

**路由**：`/admin/tags`，仅 `sys_admin` 可访问。

**布局**：左右主从分栏
- **左侧面板**（w-72，灰底 `var(--bg)`）：标签树
- **右侧面板**（flex-1，白底 `var(--surface)`）：标签详情

**左侧标签树功能**：
- 顶部"添加一级标签"虚线按钮
- 一级标签行：`FolderOutlined` + 粗体名称 + 子标签数量徽章 + 展开/折叠箭头
- 二级标签行（缩进 `pl-8`）：`TagOutlined` + 浅色文本
- 点击选中标签，自动展开一级节点
- Hover 显示 `...` 菜单按钮
- 右键菜单：
  - 一级标签：添加子标签 / 编辑 / 删除
  - 二级标签：编辑 / 删除

**右侧详情面板**：

- 空状态：提示"选择左侧标签查看详情"
- 选中标签时显示：
  - 头部：层级图标 + 标签名 + 元数据（层级标签、子标签数、文档数）
  - 操作按钮：
    - 一级标签："添加二级标签"（蓝色主按钮）+ "编辑" + "删除"
    - 二级标签："编辑" + "删除"
  - 描述卡片（flex-1）+ 文档计数卡片（w-36）
  - 关联文档列表：通过 `tagsApi.getDocuments()` 加载，显示文件名 + 知识库名
  - 底部：创建者 + 创建时间

**统一弹窗**：一个 Modal 组件处理三种模式：

- `createL1`：名称 + 描述输入
- `createL2`：只读父标签 + 名称 + 描述输入
- `edit`：预填充名称 + 描述

**删除流程**：使用 `useUIStore.confirm()` 弹窗确认，提示包含子标签数和受影响文档数。

### 3.4 知识库页面中的标签使用（pages/Knowledge.tsx）

#### UploadModal（上传弹窗，776-933 行）

- 组件挂载时加载完整标签树 `tagsApi.getTree()`
- 二级级联下拉选择器：
  - "一级分类"：`<select>` 从顶级标签填充
  - "二级标签"：`<select>` 从 `tags.find(t => t.id === selectedL1)?.children` 填充
  - 选择新一级标签时重置二级选择
  - 未选一级标签时二级下拉禁用
- 选中的 `categoryL1Id` 和 `categoryL2Id` 通过 `knowledgeApi.uploadDocument()` 上传

#### DocEditModal（文档编辑弹窗，939-1042 行）

- 挂载时加载标签树
- 从文档现有的 `category_l1?.id` 和 `category_l2?.id` 初始化选择状态
- 同样的级联下拉模式
- 保存时调用 `knowledgeApi.updateDocumentMetadata(docId, { file_name, category_l1_id, category_l2_id })`

#### 文档列表展示（548-559 行）

每行文档显示"分类"列（w-28）：
- 一级标签名（`--text-secondary`）
- 二级标签名（`--text-muted`）
- 无标签时显示 "-"

### 3.5 分块详情中的标签展示（pages/ChunkDetail.tsx）

仅做只读展示：
```tsx
{selectedChunk.category_l1 && (
  <span>分类: {[selectedChunk.category_l1, selectedChunk.category_l2].filter(Boolean).join(' / ')}</span>
)}
```

分块中的 `category_l1`/`category_l2` 为字符串类型（标签名称），非引用对象。

---

## 四、AI Service 集成

### 4.1 标签注册表拉取与缓存

**文件**：`ai-service/src/harness/subgraphs/es_search/classify.py`

**拉取方式**：从 Django 内部端点获取带 ID 的分类树

- URL：`{DJANGO_API_BASE_URL}/api/tags/internal/registry/`
- 认证：`Authorization: Service {token}`

**缓存机制**（模块级全局变量，5 分钟 TTL）：

```python
_cache_text: str       # 格式化后的分类树文本（给 LLM prompt 用）
_cache_time: float     # 上次缓存时间戳
_cache_id_to_name: Dict[int, str]  # ID→名称映射（用于进度消息）
_CACHE_TTL = 300.0     # 5 分钟
```

**Fallback**：Django API 调用失败时，读取本地静态文件 `categories.json`（不含 ID 字段，功能不完整）。

**缓存失效**：`invalidate_cache()` 清除所有全局变量。Django 在标签增删改后调用 AI Service 的缓存失效接口。

### 4.2 文档处理流水线中的标签注入

**文件**：`ai-service/kb_service/processing/enhancers/macro_enhancer.py`

文档上传时，标签 ID 经以下路径注入到每个分块的 ES 元数据中：

```
Django upload (category_l1_id, category_l2_id)
  → AI Service API (kb_service/api.py)
    → Celery task (kb_service/tasks.py)
      → DocumentOrchestrator (processing/orchestrator.py)
        → MacroEnhancer (processing/enhancers/macro_enhancer.py)
          → 每个 chunk 的 metadata:
              {"category_l1": int, "category_l2": int, ...}
            → ESStore.add_document() 写入 ES
```

### 4.3 ES 搜索中的标签分类与过滤

**文件**：`ai-service/src/harness/subgraphs/es_search/`

#### 分类子图流程

```
classify(查询分类) → search(ES检索) → evaluate(评估反思) → 路由决策
                                                                ↓
                                                    sufficient → END
                                                    insufficient → retry_query / retry_tags / retry_broad
```

#### classify 节点（classify.py）

1. 检查 `tag_retry_count`，若 >= 2 次，设置 `broaden_search=True`（放弃标签过滤，全量搜索）
2. 拉取标签注册表（带缓存）
3. 格式化为带 ID 的文本给 LLM prompt，如 `[5] 材料科学: 描述`
4. 调用 LLM（Qwen，no_think 模式，temperature=0.1）输出 JSON：
   ```json
   {"category_l1": 5, "category_l2": [12, 13], "reason": "..."}
   ```
5. 解析 ID 为整数，记录已尝试的标签组合（`tried_tags`）

#### search 节点（nodes.py）

构建 ES 过滤条件：
```python
if category_l1:
    filters["category_l1"] = category_l1    # 单个 int
if category_l2:
    filters["category_l2"] = category_l2    # int 列表
```

当 `broaden_search=True` 时，不应用任何标签过滤。

#### ES 查询构建（general_kb_retriever.py）

```python
# category_l1: 精确匹配单个值
{"term": {"metadata.category_l1": value}}

# category_l2: 匹配多个值
{"terms": {"metadata.category_l2": [value1, value2]}}
```

这些过滤条件同时应用于 BM25 和 KNN 双路召回。

#### evaluate 节点（nodes.py）

LLM 评估检索结果是否充分：
- `sufficient`：结束
- `retry_query`：保持标签不变，调整查询词
- `retry_tags`：更换标签组合，重新分类
- `retry_broad`：放弃标签过滤，全量搜索

### 4.4 缓存失效接口

**Django → AI Service 调用**（两个内部端点）：

| 触发时机 | AI Service 端点 | 请求体 | 超时 |
|----------|----------------|--------|------|
| 标签增/删/改后 | `POST /api/kb/internal/cache/invalidate` | `{"scope": "tag_registry"}` | 5s |
| 标签删除后 | `POST /api/kb/internal/tags/cleanup` | `{"tag_ids": [1, 2, 3]}` | 30s |

- 两个调用均使用 `Authorization: Service {token}` 认证
- 调用失败仅记录警告日志，不阻塞标签操作
- ES cleanup 操作：遍历所有 ES 索引，将匹配被删除标签 ID 的 `metadata.category_l1`/`metadata.category_l2` 置为 null

---

## 五、完整数据流图

### 5.1 标签创建/更新流程

```
用户操作(Frontend Tags页面)
  → POST /api/tags/create/  或  PUT /api/tags/<id>/
    → Django 创建/更新 Tag 记录
    → POST {AI_SERVICE}/api/kb/internal/cache/invalidate
      → AI Service 清除标签注册表缓存
      → 下次搜索时 classify 节点重新拉取最新标签树
```

### 5.2 标签删除流程

```
用户点击删除(Frontend Tags页面)
  → DELETE /api/tags/<id>/
    → Django 删除 Tag（CASCADE 删除子标签）
    → Document FK 被 SET_NULL（文档保留，标签字段置空）
    → POST {AI_SERVICE}/api/kb/internal/tags/cleanup
      → AI Service 将 ES 中匹配 tag ID 的 metadata 字段置 null
    → POST {AI_SERVICE}/api/kb/internal/cache/invalidate
      → AI Service 清除标签注册表缓存
```

### 5.3 文档上传时的标签分配

```
用户上传文档(Frontend Knowledge页面 UploadModal)
  → POST /api/knowledge/documents/upload/ (FormData: category_l1_id, category_l2_id)
    → Django: Document.category_l1/category_l2 设为 Tag FK
    → 触发 AI Service Celery 任务 (传入 category_l1, category_l2 整数 ID)
      → MacroEnhancer 将标签 ID 写入每个 chunk 的 metadata
      → ESStore 索引到 Elasticsearch (metadata.category_l1: integer, category_l2: integer)
```

### 5.4 搜索时的标签分类

```
用户提问 "XXX合金的强度是多少"
  → AI Service classify 节点
    → 拉取标签注册表（5分钟缓存）
    → LLM 分析用户意图 → 输出 {"category_l1": 5, "category_l2": [12]}
    → ES 检索时应用 term/terms 过滤
    → 评估结果：
      → sufficient: 返回结果
      → insufficient + retry_tags: 重新分类（最多2次）
      → insufficient + retry_broad: 放弃标签过滤，全量搜索
```

### 5.5 文档元数据编辑时的标签更新

```
用户编辑文档标签(Frontend Knowledge页面 DocEditModal)
  → PUT /api/knowledge/documents/<id>/metadata/ (JSON: category_l1_id, category_l2_id)
    → Django: 更新 Document FK
    → 代理到 AI Service ES 元数据更新接口
      → 更新 ES 中该文档所有 chunk 的 metadata.category_l1/category_l2
```

---

## 六、关键设计决策

| 决策 | 原因 |
|------|------|
| ES 存储标签 ID（integer）而非名称 | 标签重命名时无需更新 ES 索引，只需清缓存 |
| Document FK 使用 SET_NULL | 标签删除不影响文档本身，文档保留 |
| Tag 父子关系使用 CASCADE | 一级标签删除时，其下二级标签失去意义，应一并删除 |
| 注册表缓存 5 分钟 TTL | 平衡实时性和性能，标签变更不频繁 |
| classify 最多重试 2 次后放弃标签 | 避免死循环，标签分类不准时 fallback 全量搜索 |
| 标签删除后主动清理 ES | 避免 ES 中残留已删除标签 ID 导致搜索过滤不到相关文档 |
| 内部端点使用 Service Token | 服务间通信不走用户 JWT，使用共享密钥认证 |
