"""
统一 Agent 状态定义

核心设计：
- messages 使用 add_messages reducer，自动追加消息
- 保留所有现有字段（与原 tool_calling_agent/state.py 兼容）
- 新增中间件扩展字段（memory_facts, token_usage）
"""
from typing import List, Optional, Dict, Any, Annotated

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class AgentState(TypedDict):
    """ReAct Agent 状态"""

    # ===== 核心对话链 =====
    messages: Annotated[List[BaseMessage], add_messages]  # 对话消息链（自动追加）

    # ===== 输入参数 =====
    user_query: str                                       # 用户原始查询
    workflow_id: str                                      # 工作流 ID
    kb_ids: Optional[List[str]]                           # 知识库 ID 过滤
    minio_paths: Optional[List[str]]                      # MinIO 文件路径（用于 file_parse）
    file_names: Optional[List[str]]                       # 文件名列表（与 minio_paths 对应）
    allowed_tools: Optional[List[str]]                     # 允许使用的工具列表（None=全部）

    # ===== 死循环防护 =====
    tool_calls_count: int                                 # 累计工具调用次数
    last_tool_name: Optional[str]                         # 上一次调用的工具名
    last_tool_args: Optional[Dict[str, Any]]              # 上一次工具调用参数（检测重复）
    repeated_calls: int                                   # 连续重复调用次数

    # ===== 多轮对话 =====
    history: Optional[List[Dict[str, Any]]]               # 历史对话 [{"role":"user","content":"..."}]

    # ===== 查询改写 =====
    standalone_query: Optional[str]                       # 改写后的独立查询

    # ===== SSE 输出 =====
    think: List[str]                                      # 思考过程
    output: Optional[str]                                 # 最终输出

    # ===== 中间件扩展字段 =====
    memory_facts: Optional[List[dict]]                    # 记忆中间件注入的用户事实
    token_usage: Optional[Dict[str, int]]                 # Token 统计中间件写入
