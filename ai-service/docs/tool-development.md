# 工具开发指南

本文档说明如何开发新的 Agent 工具，集成到动态工具注册系统中。

## 工具系统架构

```
BaseTool (抽象基类)
  ├── get_schema()       → 返回 OpenAI Function Calling 格式的 JSON Schema
  ├── execute(**kwargs)  → 异步执行工具逻辑
  └── should_activate(context) → 可选，判断工具是否应该在当前上下文中激活

ToolRegistry (全局注册表)
  ├── register(tool)     → 注册工具实例
  ├── get_schemas()      → 获取工具 Schema 列表（供 LLM 使用）
  ├── get_executor(name) → 获取工具执行函数
  └── get_available_tools() → 按条件过滤可用工具
```

## 开发步骤

### 1. 创建工具类

在 `src/harness/tools/` 下创建新文件，继承 `BaseTool`：

```python
# src/harness/tools/my_tool.py
from src.harness.tools.base import BaseTool


class MyTool(BaseTool):
    """自定义工具示例"""

    name = "my_tool"          # 工具名（全局唯一）
    description = "工具描述，告诉 LLM 何时使用此工具"
    group = "custom"           # 分组名

    def get_schema(self) -> dict:
        """返回 OpenAI Function Calling 格式的 Schema"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "查询参数",
                        },
                    },
                    "required": ["query"],
                },
            },
        }

    async def execute(self, **kwargs) -> str:
        """
        执行工具逻辑，返回文本结果。

        Args:
            **kwargs: LLM 传递的参数（与 Schema 定义一致）

        Returns:
            str: 工具执行结果文本（会作为 ToolMessage 返回给 LLM）
        """
        query = kwargs.get("query", "")
        # ... 实际执行逻辑 ...
        return f"查询 '{query}' 的结果"

    def should_activate(self, context: dict) -> bool:
        """
        可选：判断工具是否应该在当前上下文中激活。

        Args:
            context: 包含 state 信息的上下文字典

        Returns:
            bool: True 表示激活
        """
        return True  # 默认始终激活
```

### 2. 注册工具

在 `src/harness/tools/__init__.py` 中添加注册：

```python
from .my_tool import MyTool

_BUILTIN_TOOLS = [
    ESSearchTool,
    FileParseTool,
    CalculateTool,
    MyTool,         # 添加到这里
]
```

### 3. 完成

工具会在服务启动时通过 `register_all_tools()` 自动注册到 `ToolRegistry`。LLM 会根据工具的 Schema 和描述自动决定何时调用。

## 工具参数说明

### execute() 的特殊参数

LLM 传递的参数取决于 Schema 定义。但 `tool_node`（`src/harness/nodes/tools.py`）会在调用 `execute()` 前注入一些额外的状态参数：

| 参数 | 来源 | 说明 |
|------|------|------|
| `query` | LLM tool_call args | 用户查询（Schema 定义） |
| `kb_ids` | state | 知识库权限 ID 列表（由 tool_node 从 state 注入） |
| `config` | LangGraph config | 用于发送进度事件 |

### 条件激活示例

```python
def should_activate(self, context: dict) -> bool:
    """只在有文件路径时激活文件解析工具"""
    return bool(context.get("minio_paths"))
```

## 子图开发

如果工具需要复杂的多步推理，可以创建 LangGraph 子图：

### 1. 创建子图目录

```
src/harness/subgraphs/my_subgraph/
├── __init__.py
├── state.py        # 子图状态定义（TypedDict）
├── subgraph.py     # 子图构建 + 入口函数
└── nodes.py        # 子图节点实现
```

### 2. 定义子图状态

```python
# state.py
from typing import TypedDict, List, Optional


class MySubgraphState(TypedDict):
    query: str
    results: List[dict]
    error: Optional[str]
```

### 3. 构建子图

```python
# subgraph.py
from langgraph.graph import StateGraph, END
from .state import MySubgraphState
from .nodes import step1_node, step2_node


def create_my_subgraph():
    wf = StateGraph(MySubgraphState)
    wf.add_node("step1", step1_node)
    wf.add_node("step2", step2_node)
    wf.set_entry_point("step1")
    wf.add_edge("step1", "step2")
    wf.add_edge("step2", END)
    return wf.compile()


my_subgraph = create_my_subgraph()


async def run_my_subgraph(query: str, config=None) -> str:
    """入口函数，被工具的 execute() 调用"""
    initial_state = MySubgraphState(query=query, results=[], error=None)
    config = config or {"configurable": {}}
    final = await my_subgraph.ainvoke(initial_state, config=config)
    return format_result(final)
```

### 4. 在工具中调用子图

```python
# src/harness/tools/my_tool.py
async def execute(self, **kwargs) -> str:
    from src.harness.subgraphs.my_subgraph.subgraph import run_my_subgraph
    return await run_my_subgraph(query=kwargs["query"], config=kwargs.get("config"))
```

## 进度事件推送

在子图或工具执行中发送 SSE 进度事件：

```python
from langchain_core.callbacks.manager import adispatch_custom_event

await adispatch_custom_event(
    "progress",
    {"node": "my_tool", "message": "正在处理..."},
    config=config,
)
```

## 注意事项

- `execute()` 必须是 `async` 函数
- 返回值必须是 `str`（超过 16K 字符会被 ProgressMiddleware 截断）
- Schema 中的 `parameters` 必须符合 JSON Schema 格式
- `should_activate()` 是同步函数，不应有耗时操作
- 子图内部可以使用相对 import（`from .state import ...`）
- 子图内部引用 harness 模块使用绝对路径（`from src.harness.llm import ...`）

## 实例：PPT 生成工具

`ppt_generate` 工具是一个完整的文件生成工具示例，展示了从 LLM 内容规划到文件渲染、上传和记录创建的全流程。

### 架构

```
用户请求 "做一个关于 X 的 PPT"
  → LLM 调用 ppt_generate 工具（传入 topic + slides 数组）
    → build_slide_plan() 构建结构化幻灯片计划
    → render_presentation() 用 python-pptx 渲染为 .pptx bytes
    → object_store.put_object(bucket=settings.MINIO_GENERATED_BUCKET) 上传至 generated-files 桶
    → _create_file_record() 回调 Django 创建 GeneratedFile 记录
    → 返回 Markdown 文本 + <!--PPT_FILE:{json}--> 标记
  → 前端解析标记，渲染 PPTDownloadCard 下载卡片
```

### 文件结构

```
src/harness/tools/
├── ppt_generate.py    # PPTGenerateTool（BaseTool 子类）
├── ppt_renderer.py    # 纯渲染引擎（build_slide_plan + render_presentation）
└── ppt_themes.py      # 5 种主题配色定义（business_blue / dark_tech / minimal_white / academic_green / warm）
```

### 关键设计决策

1. **LLM 负责内容规划**：工具的 `slides` 参数接收 LLM 规划的结构化内容（`[{title, bullets}]`），而非工具自己生成泛化文本
2. **HTML 注释标记**：工具返回值中嵌入 `<!--PPT_FILE:{json}-->`，前端 `parsePPTFileMarkers()` 解析并渲染下载卡片
3. **Service Token 回调**：通过 `Authorization: Service {token}` 调用 Django `/api/chat/files/create/` 创建文件记录
4. **主题分离**：主题定义独立于渲染逻辑，方便扩展新主题

### Prompt 规则

在 `prompts.py` 中配置了 PPT 相关的提示词规则：

- `TOOL_PRIORITY_ORDER` — 工具优先级排序
- `TOOL_PRIORITY_ENTRIES["ppt_generate"]` — 触发条件
- `TOOL_SPECIFIC_RULES["ppt_generate"]` — 要求 LLM 必须填写 `slides` 参数、保留 HTML 注释标记、禁止自创下载链接
