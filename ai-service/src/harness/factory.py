"""
Agent 工厂 + AgentRunner

参考 DeerFlow 的 create_deerflow_agent() + RuntimeFeatures 模式。

职责：
1. RuntimeFeatures 声明式控制功能开关
2. 根据功能开关组装中间件链
3. 构建 LangGraph 图并用中间件包装节点
4. AgentRunner 封装图的执行，自动注入中间件到 config
"""
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, AsyncGenerator

from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.memory import MemorySaver

from .state import AgentState
from .tools import register_all_tools, ToolRegistry
from .middlewares.base import AgentMiddleware
from .middlewares.progress import ProgressMiddleware
from .middlewares.loop_detection import LoopDetectionMiddleware
from .middlewares.token_tracker import TokenTrackerMiddleware
from .middlewares.memory import MemoryMiddleware
from .nodes.rewrite import rewrite_node
from .nodes.agent import agent_node
from .nodes.tools import tool_node
from .nodes.maybe import maybe_node

logger = logging.getLogger(__name__)

# ========== 功能开关 ==========


@dataclass
class RuntimeFeatures:
    """
    功能开关 — 控制哪些中间件生效。

    使用方式：
        features = RuntimeFeatures(progress=True, loop_detection=True)
        runner = create_agent_graph(features=features)
    """

    progress: bool = True        # 工具执行进度推送 + 结果截断
    loop_detection: bool = True  # 死循环检测
    token_tracker: bool = True   # Token 统计（占位）
    memory: bool = False         # 长期记忆（Phase 2）
    sandbox: bool = False        # 沙盒（Phase 3）


# ========== 图节点包装器 ==========


def _wrap_node(
    node_func,
    node_name: str,
    middlewares: List[AgentMiddleware],
):
    """
    将中间件链包装到节点函数中。

    执行顺序：
    1. 按序调用所有中间件的 before_node
    2. 执行原节点函数
    3. 按序调用所有中间件的 after_node
    """

    async def wrapped(state, config):
        # 前置钩子
        for mw in middlewares:
            state = await mw.before_node(node_name, state, config)

        # 执行节点
        result = await node_func(state, config)

        # 后置钩子
        for mw in middlewares:
            result = await mw.after_node(node_name, state, result, config)

        return result

    # 保留原始函数名，方便调试和日志
    wrapped.__name__ = node_name
    wrapped.__qualname__ = node_name

    return wrapped


# ========== 条件路由 ==========


def _should_continue(state: AgentState) -> str:
    """
    条件路由：检查 agent_node 输出是否包含 tool_calls。

    返回值：
    - "tools": 有 tool_calls，继续执行工具
    - "end": 无 tool_calls，结束
    """
    messages = state.get("messages", [])
    last_ai_msg = None
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            last_ai_msg = msg
            break

    if not last_ai_msg or not last_ai_msg.tool_calls:
        return "end"

    # 安全检查：总调用次数上限（中间件也会检查，此处是兜底）
    tool_calls_count = state.get("tool_calls_count", 0)
    if tool_calls_count >= 10:
        logger.warning(f"[should_continue] Total tool calls ({tool_calls_count}) exceeded limit")
        return "end"

    # 重复调用检测（中间件也会检查，此处是兜底）
    repeated_calls = state.get("repeated_calls", 0)
    if repeated_calls >= 2:
        logger.warning(f"[should_continue] Repeated calls ({repeated_calls}), forcing end")
        return "end"

    return "tools"


# ========== 中间件组装 ==========


def _assemble_middlewares(
    features: RuntimeFeatures,
    extra_middlewares: List[AgentMiddleware] | None = None,
) -> List[AgentMiddleware]:
    """
    根据 RuntimeFeatures 组装中间件链。

    中间件执行顺序（固定）：
    1. ProgressMiddleware     — 工具进度 + 结果截断
    2. LoopDetectionMiddleware — 死循环检测
    3. TokenTrackerMiddleware  — Token 统计
    4. MemoryMiddleware        — 长期记忆（Phase 2）
    5. 用户自定义中间件        — extra_middlewares
    """
    middlewares: List[AgentMiddleware] = []

    if features.progress:
        middlewares.append(ProgressMiddleware())
    if features.loop_detection:
        middlewares.append(LoopDetectionMiddleware())
    if features.token_tracker:
        middlewares.append(TokenTrackerMiddleware())
    if features.memory:
        middlewares.append(MemoryMiddleware())

    if extra_middlewares:
        middlewares.extend(extra_middlewares)

    return middlewares


# ========== AgentRunner ==========


class AgentRunner:
    """
    Agent 执行器 — 封装 LangGraph 图 + 中间件注入。

    使用方式：
        runner = create_agent_graph(features=RuntimeFeatures())
        async for event in runner.astream_events(state, config, version="v2"):
            ...
    """

    def __init__(self, graph, middlewares: List[AgentMiddleware]):
        self.graph = graph
        self.middlewares = middlewares

    async def astream_events(
        self, initial_state: Dict[str, Any], config: Dict[str, Any], **kwargs
    ) -> AsyncGenerator:
        """
        流式执行 Agent，自动注入中间件到 config。

        中间件列表通过 config["configurable"]["_middlewares"] 传递给各节点。
        """
        # 注入中间件
        config.setdefault("configurable", {})
        config["configurable"]["_middlewares"] = self.middlewares

        async for event in self.graph.astream_events(
            initial_state, config=config, **kwargs
        ):
            yield event


# ========== 工厂函数 ==========


def create_agent_graph(
    features: RuntimeFeatures | None = None,
    extra_middlewares: List[AgentMiddleware] | None = None,
) -> AgentRunner:
    """
    创建 Agent 图（带中间件链）。

    图结构：
        START → rewrite → agent → (条件路由) → tools → agent → ... → maybe → END
                                    ↓ (无 tool_calls)
                                   maybe → END

    Args:
        features: 功能开关，None 使用默认值（全部开启）
        extra_middlewares: 额外的自定义中间件

    Returns:
        AgentRunner 实例
    """
    if features is None:
        features = RuntimeFeatures()

    # 注册所有内置工具（幂等操作）
    register_all_tools()

    # 组装中间件
    middlewares = _assemble_middlewares(features, extra_middlewares)

    # 用中间件包装节点
    wrapped_rewrite = _wrap_node(rewrite_node, "rewrite", middlewares)
    wrapped_agent = _wrap_node(agent_node, "agent", middlewares)
    wrapped_tools = _wrap_node(tool_node, "tools", middlewares)
    wrapped_maybe = _wrap_node(maybe_node, "maybe", middlewares)

    # 构建图
    wf = StateGraph(AgentState)

    wf.add_node("rewrite", wrapped_rewrite)
    wf.add_node("agent", wrapped_agent)
    wf.add_node("tools", wrapped_tools)
    wf.add_node("maybe", wrapped_maybe)

    # 入口 → rewrite
    wf.set_entry_point("rewrite")

    # rewrite → agent（固定边）
    wf.add_edge("rewrite", "agent")

    # 条件边：agent → tools 或 maybe
    wf.add_conditional_edges(
        "agent",
        _should_continue,
        {
            "tools": "tools",
            "end": "maybe",
        },
    )

    # 固定边：tools → agent（循环），maybe → END
    wf.add_edge("tools", "agent")
    wf.add_edge("maybe", END)

    graph = wf.compile(checkpointer=MemorySaver())

    logger.info(
        f"[factory] Agent graph created with middlewares: "
        f"{[mw.name for mw in middlewares]}"
    )

    return AgentRunner(graph, middlewares)
