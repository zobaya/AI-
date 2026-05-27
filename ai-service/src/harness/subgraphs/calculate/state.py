# -*- coding: utf-8 -*-
"""
State定义 - 基于questions结构
"""
from typing import TypedDict, Dict, Any, List, Optional


class CalculateState(TypedDict, total=False):
    """计算状态"""
    # 输入
    user_input: str
    
    # 问题列表（新架构核心）
    questions: List[Dict[str, Any]]  # [{"id": "q1", "type": "query/calculate", "description": "...", "known_parameters": {}, "target_parameters": [...]}]
    
    # 查询结果（按问题ID组织）
    query_results: Dict[str, Dict[str, Any]]  # {question_id: {param: value}}
    
    # 计算结果（按问题ID组织）
    question_results: Dict[str, Dict[str, Any]]  # {question_id: {"question": {...}, "result": {...}}}
    
    # 上下文数据（供API层使用）
    context_data: Optional[Dict[str, Any]]  # {"user_input": "...", "questions": [...]}
    
    # 调试信息
    debug_logs: List[str]
    error: Optional[str]

