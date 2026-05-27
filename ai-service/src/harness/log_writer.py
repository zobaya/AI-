"""
Agent 日志写入模块 - 记录每次对话的完整工作流程

日志格式：JSONL（每行一个 JSON），存储在 logs/ 目录下。
每次对话生成一个 {workflow_id}.jsonl 文件。
"""
import json
import logging
import os
from datetime import datetime
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# 日志目录
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")

# 结果截断阈值
MAX_RESULT_LENGTH = 2000


def _truncate(text: str, max_len: int = MAX_RESULT_LENGTH) -> str:
    """截断过长文本，保留前后部分"""
    if not text or len(text) <= max_len:
        return text
    half = max_len // 2
    return text[:half] + f"\n...[截断，原文 {len(text)} 字]...\n" + text[-half:]


def _ts() -> str:
    """当前时间 ISO 格式"""
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


class AgentLogger:
    """收集和持久化 Agent 日志"""

    def __init__(self):
        self._entries: List[Dict[str, Any]] = []
        self._workflow_id: str = ""
        self._think_buffer: str = ""  # 累积思考内容，结束时一次性写入
        self._output_buffer: str = ""  # 累积输出内容
        self._flushed: bool = False

    def start(self, workflow_id: str, user_query: str, minio_paths: Optional[List[str]] = None):
        """记录对话开始"""
        self._workflow_id = workflow_id
        entry = {
            "ts": _ts(),
            "type": "start",
            "workflow_id": workflow_id,
            "user_query": user_query,
        }
        if minio_paths:
            entry["minio_paths"] = minio_paths
        self._append(entry)

    def node_start(self, node_name: str):
        """记录节点开始执行"""
        self._append({"ts": _ts(), "type": "node_start", "node": node_name})

    def node_end(self, node_name: str, output: Any = None):
        """记录节点结束，提取关键输出摘要"""
        entry: Dict[str, Any] = {"ts": _ts(), "type": "node_end", "node": node_name}

        if output and isinstance(output, dict):
            # 只记录关键字段，不存完整 state
            summary = {}
            for key in ("standalone_query", "tool_calls_count", "output"):
                if key in output:
                    val = output[key]
                    if isinstance(val, str):
                        summary[key] = val
                    else:
                        summary[key] = val

            # 提取 tool_calls 信息
            messages = output.get("messages", [])
            for msg in messages:
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    summary["tool_calls"] = [
                        {"id": tc.get("id"), "name": tc.get("name"), "args": tc.get("args")}
                        for tc in msg.tool_calls
                    ]

            if summary:
                entry["summary"] = summary

        self._append(entry)

    def think(self, content: str):
        """累积思考内容"""
        self._think_buffer += content

    def flush_think(self):
        """将累积的思考内容写入日志"""
        if self._think_buffer.strip():
            self._append({
                "ts": _ts(),
                "type": "think",
                "content": self._think_buffer,
                "length": len(self._think_buffer),
            })
            self._think_buffer = ""

    def progress(self, node: str, message: str):
        """记录进度事件"""
        self._append({"ts": _ts(), "type": "progress", "node": node, "message": message})

    def node_event(self, event_type: str, data: Dict[str, Any]):
        """记录节点输出事件（如标题、推荐问题）"""
        entry: Dict[str, Any] = {"ts": _ts(), "type": event_type}
        entry.update(data)
        self._append(entry)

    def tool_call(self, tool_name: str, args: Dict[str, Any]):
        """记录工具调用"""
        self.flush_think()  # 工具调用前刷出思考内容
        self._append({
            "ts": _ts(),
            "type": "tool_call",
            "tool": tool_name,
            "args": {k: str(v) for k, v in args.items()},
        })

    def tool_result(self, tool_name: str, result: str):
        """记录工具执行结果"""
        self._append({
            "ts": _ts(),
            "type": "tool_result",
            "tool": tool_name,
            "result": result,
            "result_length": len(result),
        })

    def output(self, content: str):
        """累积输出内容"""
        self._output_buffer += content

    def end(self, tool_calls_count: int = 0):
        """记录对话结束"""
        self.flush_think()

        # 刷出输出内容
        if self._output_buffer.strip():
            self._append({
                "ts": _ts(),
                "type": "output",
                "content": self._output_buffer,
                "length": len(self._output_buffer),
            })
            self._output_buffer = ""

        self._append({
            "ts": _ts(),
            "type": "end",
            "workflow_id": self._workflow_id,
            "tool_calls_count": tool_calls_count,
        })

    def flush(self):
        """将所有日志写入 JSONL 文件"""
        if self._flushed:
            return
        self._flushed = True

        os.makedirs(LOG_DIR, exist_ok=True)
        log_file = os.path.join(LOG_DIR, f"{self._workflow_id}.jsonl")

        try:
            with open(log_file, "w", encoding="utf-8") as f:
                for entry in self._entries:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            logger.info(f"[log] Written {len(self._entries)} entries to {log_file}")
        except Exception as e:
            logger.error(f"[log] Failed to write log: {e}")

    def _append(self, entry: Dict[str, Any]):
        self._entries.append(entry)

    # ========== 静态方法：读取日志 ==========

    @staticmethod
    def list_logs() -> List[Dict[str, Any]]:
        """返回日志文件列表，按时间倒序"""
        if not os.path.isdir(LOG_DIR):
            return []

        logs = []
        for fname in os.listdir(LOG_DIR):
            if not fname.endswith(".jsonl"):
                continue
            filepath = os.path.join(LOG_DIR, fname)
            try:
                stat = os.stat(filepath)
                workflow_id = fname[:-6]  # 去掉 .jsonl

                # 读取第一行获取 user_query
                user_query = ""
                with open(filepath, "r", encoding="utf-8") as f:
                    first_line = f.readline().strip()
                    if first_line:
                        data = json.loads(first_line)
                        user_query = data.get("user_query", "")

                logs.append({
                    "workflow_id": workflow_id,
                    "user_query": user_query,
                    "file_size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                })
            except Exception:
                continue

        logs.sort(key=lambda x: x["modified"], reverse=True)
        return logs

    @staticmethod
    def read_log(workflow_id: str) -> List[Dict[str, Any]]:
        """读取单个 workflow 的完整日志"""
        # 安全检查：防止路径遍历
        safe_id = workflow_id.replace("/", "").replace("\\", "").replace("..", "")
        filepath = os.path.join(LOG_DIR, f"{safe_id}.jsonl")

        if not os.path.isfile(filepath):
            return []

        entries = []
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        entries.append(json.loads(line))
        except Exception as e:
            logger.error(f"[log] Failed to read log {workflow_id}: {e}")

        return entries
