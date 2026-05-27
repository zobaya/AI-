# -*- coding: utf-8 -*-
"""
计算子图 - 可嵌入主工作流的 MCP 计算模块
"""
from typing import Dict, Any
from langgraph.graph import StateGraph, END
from .state import CalculateState
from .nodes import (
    initial_decision_node,
    query_node,
    calculate_node,
    answer_node
)


def create_calculation_mcp_subgraph():
    """
    创建 MCP 计算子图 - 可嵌入主工作流

    输入：CalculateState
    输出：CalculateState

    流程：
    1. parse (initial_decision): 参数解析
    2. query: 查询数据库
    3. calculate: 执行计算
    4. answer: 流式生成答案（async，需要 config）

    注意：
    - answer_node 是 async 函数，需要传递 config 参数
    - 其他节点是同步函数
    """
    workflow = StateGraph(CalculateState)

    # 添加节点（answer_node 是 async）
    workflow.add_node("parse", initial_decision_node)
    workflow.add_node("query", query_node)
    workflow.add_node("calculate", calculate_node)
    workflow.add_node("answer", answer_node)  # async 函数

    # 设置固定流程
    workflow.set_entry_point("parse")
    workflow.add_edge("parse", "query")
    workflow.add_edge("query", "calculate")
    workflow.add_edge("calculate", "answer")
    workflow.add_edge("answer", END)

    return workflow.compile()


# 创建全局子图实例
calculation_mcp_subgraph = create_calculation_mcp_subgraph()


async def invoke_calculation_mcp_subgraph(user_input: str, config=None) -> Dict[str, Any]:
    """
    调用 MCP 计算子图的便捷函数（异步）

    注意：answer_node 是 async 函数，必须使用 ainvoke() 异步调用。

    Args:
        user_input: 用户输入的计算问题

    Returns:
        计算结果字典（与 calculate 子图格式兼容），包含：
        - error: 错误信息（如果有）
        - calculated_results: 计算结果（合并所有问题的结果）
        - known_parameters: 已知参数（合并所有问题的参数）
        - used_defaults: 使用的默认值
        - missing_parameters: 缺失参数
        - query_results: 查询结果（合并所有问题的查询）
        - query_success: 查询是否成功
        - debug_logs: 调试日志

        额外字段（MCP 特有）：
        - questions: 问题列表
        - question_results: 每个问题的详细结果
        - context_data: 上下文数据（供 LLM 生成答案）
    """
    # 构建初始状态
    initial_state = CalculateState(
        user_input=user_input,
        questions=[],
        query_results={},
        question_results={},
        context_data=None,
        debug_logs=[],
        error=None
    )

    # 异步调用子图（answer_node 是 async，必须用 ainvoke）
    invoke_config = {"configurable": {}} if config is None else config
    final_state = await calculation_mcp_subgraph.ainvoke(initial_state, config=invoke_config)
    
    # 提取原始结果
    error = final_state.get("error")
    questions = final_state.get("questions", [])
    question_results = final_state.get("question_results", {})
    query_results_raw = final_state.get("query_results", {})
    context_data = final_state.get("context_data")
    debug_logs = final_state.get("debug_logs", [])
    
    # 转换为与 calculate 子图兼容的格式
    calculated_results = {}
    known_parameters = {}
    query_results = {}
    used_defaults = {}
    missing_parameters = None
    query_success = False
    
    # 合并所有问题的结果
    for q_id, q_data in question_results.items():
        question = q_data.get("question", {})
        result = q_data.get("result", {})
        
        # 合并已知参数
        known_parameters.update(question.get("known_parameters", {}))
        
        # 合并查询结果
        if q_id in query_results_raw:
            query_results.update(query_results_raw[q_id])
            query_success = True
        
        # 合并计算结果
        if result.get("success"):
            if result.get("type") == "query":
                # 查询问题：直接合并数据
                calculated_results.update(result.get("data", {}))
            elif result.get("type") == "multi_calculate":
                # 多目标计算：提取每个目标的结果
                for target, target_result in result.get("results", {}).items():
                    if target_result.get("success"):
                        calculated_results[target] = target_result.get("result")
            else:
                # 单目标计算：提取结果
                target_params = question.get("target_parameters", [])
                if target_params:
                    calculated_results[target_params[0]] = result.get("result")
        else:
            # 记录失败的参数
            if result.get("missing_params"):
                # 处理 missing_params（可能是字典列表或字符串列表）
                missing_list = result.get("missing_params", [])
                missing_param_names = []
                for item in missing_list:
                    if isinstance(item, str):
                        missing_param_names.append(item)
                    elif isinstance(item, dict):
                        # 提取 param 字段（参数名）
                        param = item.get('param', item.get('name', str(item)))
                        missing_param_names.append(param)
                    else:
                        missing_param_names.append(str(item))

                missing_parameters = ", ".join(missing_param_names)
    
    # 返回兼容格式
    return {
        # 标准字段（与 calculate 子图兼容）
        "error": error,
        "calculated_results": calculated_results,
        "known_parameters": known_parameters,
        "used_defaults": used_defaults,
        "missing_parameters": missing_parameters,
        "query_results": query_results,
        "query_success": query_success,
        "debug_logs": debug_logs,
        
        # MCP 特有字段（额外信息）
        "questions": questions,
        "question_results": question_results,
        "context_data": context_data
    }
