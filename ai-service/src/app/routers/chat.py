"""
App 层 — Chat/Upload/Logs 路由

从 tool_calling_agent/main.py 迁移，使用新的 AgentRunner。
保持所有 API 端点和 SSE 事件格式完全兼容。
"""
import asyncio
import json
import logging
import uuid
from typing import Optional, List

from fastapi import APIRouter, Request, UploadFile, File
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from langchain_core.messages import HumanMessage
from pathlib import Path

from src.harness.factory import create_agent_graph, RuntimeFeatures
from src.harness.state import AgentState

logger = logging.getLogger(__name__)

# ========== 路由定义 ==========

router = APIRouter()

PAGES_DIR = Path(__file__).parent.parent / "pages"

# ========== 全局 AgentRunner（启动时创建一次） ==========

agent_runner = create_agent_graph(RuntimeFeatures(
    progress=True,
    loop_detection=True,
    token_tracker=True,
    memory=True,
    sandbox=False,
))


# ========== 页面路由 ==========


@router.get("/", response_class=HTMLResponse)
async def index():
    """测试页面"""
    html_path = PAGES_DIR / "index.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Test page not found</h1>")


@router.get("/logs", response_class=HTMLResponse)
async def logs_page():
    """日志查看页面"""
    html_path = PAGES_DIR / "logs.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Logs page not found</h1>")


# ========== 文件上传 ==========


@router.post("/api/upload")
async def upload_files(files: List[UploadFile] = File(...)):
    """
    上传文件到 MinIO，返回路径列表供后续 /api/chat 使用。

    返回：
    {
        "paths": ["chat-uploads/xxx.pdf", ...],
        "names": ["xxx.pdf", ...]
    }
    """
    from core.object_store import object_store
    from core.config import settings

    paths = []
    names = []

    for f in files:
        filename = f.filename or "unknown"
        object_name = f"{uuid.uuid4().hex[:8]}_{filename}"

        try:
            data = await f.read()
            minio_path = object_store.put_object(
                object_name=object_name,
                data=data,
                content_type=f.content_type or "application/octet-stream",
                bucket=settings.MINIO_CHAT_UPLOAD_BUCKET,
            )
            paths.append(minio_path)
            names.append(filename)
            logger.info(f"[upload] {filename} -> {minio_path}")
        except Exception as e:
            logger.error(f"[upload] Failed: {filename}, {e}")
            return JSONResponse(
                status_code=500,
                content={"error": f"上传 {filename} 失败: {str(e)}"},
            )

    return {"paths": paths, "names": names}


# ========== Chat SSE Endpoint ==========


@router.post("/api/chat")
async def chat(request: Request):
    """
    SSE 流式对话端点。

    请求体：
    {
        "user_query": "用户问题",
        "minio_paths": ["chat-uploads/xxx.pdf"],
        "history": [{"role": "user", "content": "..."}],
        "workflow_id": "xxx",
        "allowed_tools": ["es_search", "calculate"]
    }

    SSE 事件类型：
    - progress: 进度更新
    - think: 思考内容
    - output: 流式输出
    - title: 对话标题
    - maybe: 推荐问题
    - final: 最终结果
    - error: 错误
    """
    body = await request.json()

    user_query = body.get("user_query", "")
    minio_paths = body.get("minio_paths")
    file_names = body.get("file_names")
    history = body.get("history", [])
    allowed_tools = body.get("allowed_tools")
    workflow_id = body.get("workflow_id") or str(uuid.uuid4())
    user_id = body.get("user_id")
    conversation_id = body.get("conversation_id")

    if not user_query:
        return StreamingResponse(
            _error_stream("user_query 不能为空"),
            media_type="text/event-stream",
        )

    # 构建初始 state
    initial_state = AgentState(
        messages=[HumanMessage(content=user_query)],
        user_query=user_query,
        workflow_id=workflow_id,
        kb_ids=body.get("kb_ids"),
        minio_paths=minio_paths,
        file_names=file_names,
        allowed_tools=allowed_tools,
        tool_calls_count=0,
        last_tool_name=None,
        last_tool_args=None,
        repeated_calls=0,
        think=[],
        output=None,
        standalone_query=None,
        history=history,
        memory_facts=None,
        token_usage=None,
    )

    # LangGraph config
    config = {
        "configurable": {
            "thread_id": workflow_id,
            "user_id": user_id,
            "conversation_id": conversation_id,
        },
        "recursion_limit": 25,
    }

    return StreamingResponse(
        _run_graph_stream(initial_state, config, workflow_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _run_graph_stream(
    initial_state: AgentState,
    config: dict,
    workflow_id: str,
):
    """遍历 agent_runner.astream_events()，将事件转为 SSE 格式推送，同时记录日志。"""
    from src.harness.log_writer import AgentLogger

    final_output = ""
    has_real_output = False
    tool_call_map = {}
    final_tool_calls_count = 0
    token_usage = {"prompt_tokens": 0, "completion_tokens": 0}
    agent_log = AgentLogger()
    agent_log.start(
        workflow_id,
        initial_state.get("user_query", ""),
        initial_state.get("minio_paths"),
    )

    try:
        yield f"event: workflow_id\ndata: {json.dumps({'workflow_id': workflow_id})}\n\n"

        async for event in agent_runner.astream_events(
            initial_state,
            config=config,
            version="v2",
        ):
            event_type = event.get("event", "")

            if event_type == "on_custom_event":
                event_name = event.get("name", "")
                event_data = event.get("data", {})

                if event_name == "progress":
                    message = event_data.get("message", "")
                    node = event_data.get("node", "")
                    agent_log.progress(node, message)
                    yield f"event: progress\ndata: {json.dumps({'node': node, 'message': message}, ensure_ascii=False)}\n\n"

                elif event_name == "output":
                    content = event_data.get("content", "")
                    if not has_real_output:
                        content = content.lstrip('\n')
                        if not content:
                            continue
                    if content.strip():
                        has_real_output = True
                    final_output += content
                    agent_log.output(content)
                    yield f"event: output\ndata: {json.dumps({'content': content}, ensure_ascii=False)}\n\n"

                elif event_name == "think":
                    agent_log.think(event_data.get("content", ""))
                    yield f"event: think\ndata: {json.dumps(event_data, ensure_ascii=False)}\n\n"

                elif event_name == "title":
                    agent_log.node_event("title", {"title": event_data.get("content", "")})
                    yield f"event: title\ndata: {json.dumps(event_data, ensure_ascii=False)}\n\n"

                elif event_name == "maybe":
                    questions = event_data.get("questions", [])
                    agent_log.node_event("maybe", {"questions": questions})
                    yield f"event: maybe\ndata: {json.dumps(event_data, ensure_ascii=False)}\n\n"

                elif event_name == "error":
                    yield f"event: error\ndata: {json.dumps(event_data, ensure_ascii=False)}\n\n"

                else:
                    yield f"event: {event_name}\ndata: {json.dumps(event_data, ensure_ascii=False)}\n\n"

            elif event_type == "on_chain_start":
                node_name = event.get("name", "")
                if node_name:
                    agent_log.node_start(node_name)

            elif event_type == "on_chain_end":
                node_name = event.get("name", "")
                output = event.get("data", {}).get("output")
                if node_name:
                    agent_log.node_end(node_name, output)

                if output and isinstance(output, dict):
                    if "tool_calls_count" in output:
                        final_tool_calls_count = output["tool_calls_count"]
                    if "token_usage" in output and output["token_usage"]:
                        tu = output["token_usage"]
                        token_usage["prompt_tokens"] = tu.get("prompt_tokens", 0)
                        token_usage["completion_tokens"] = tu.get("completion_tokens", 0)
                    messages = output.get("messages", [])
                    for msg in messages:
                        if hasattr(msg, "tool_calls") and msg.tool_calls:
                            for tc in msg.tool_calls:
                                tool_call_map[tc.get("id", "")] = tc.get("name", "")
                                agent_log.tool_call(
                                    tc.get("name", ""),
                                    tc.get("args", {}),
                                )
                        if hasattr(msg, "content") and hasattr(msg, "tool_call_id") and msg.tool_call_id:
                            tool_name = tool_call_map.get(msg.tool_call_id, "")
                            agent_log.tool_result(tool_name or "unknown", msg.content or "")

        # token_usage 事件（在 final 之前发送）
        total_tokens = token_usage["prompt_tokens"] + token_usage["completion_tokens"]
        if total_tokens > 0:
            yield f"event: token_usage\ndata: {json.dumps(token_usage)}\n\n"

        # final 带完整内容
        yield f"event: final\ndata: {json.dumps({'workflow_id': workflow_id, 'output': final_output}, ensure_ascii=False)}\n\n"

    except Exception as e:
        logger.error(f"[SSE] Stream error: {e}", exc_info=True)
        yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"
    finally:
        agent_log.end(
            tool_calls_count=final_tool_calls_count,
        )
        agent_log.flush()


async def _error_stream(message: str):
    """生成错误 SSE 流"""
    yield f"event: error\ndata: {json.dumps({'message': message})}\n\n"


# ========== 日志 API ==========


@router.get("/api/agent-logs")
async def list_agent_logs():
    """返回日志文件列表"""
    from src.harness.log_writer import AgentLogger

    logs = AgentLogger.list_logs()
    return {"logs": logs, "total": len(logs)}


@router.get("/api/agent-logs/{workflow_id}")
async def get_agent_log(workflow_id: str):
    """返回单个 workflow 的完整日志"""
    from src.harness.log_writer import AgentLogger

    entries = AgentLogger.read_log(workflow_id)
    if not entries:
        return JSONResponse(status_code=404, content={"error": "日志不存在"})
    return {"workflow_id": workflow_id, "entries": entries}
