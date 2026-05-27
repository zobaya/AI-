# -*- coding: utf-8 -*-
"""
Calculate MCP 子图模块

采用"问题分解 + 查询/计算分离"的架构：
1. 参数解析：将用户输入解析为多个独立的问题
2. 查询节点：查询数据库补充信息
3. 计算节点：执行计算
4. 回答节点：构建上下文数据
"""
from core.config import settings
from .subgraph import calculation_mcp_subgraph, invoke_calculation_mcp_subgraph
from .state import CalculateState
from .nodes import (
    initial_decision_node,
    query_node,
    calculate_node,
    answer_node
)

# ================= 数据库配置（从 core.config 统一管理） =================
DB_CONFIG = {
    "host": settings.CALC_DB_HOST,
    "port": settings.CALC_DB_PORT,
    "user": settings.CALC_DB_USER,
    "password": settings.CALC_DB_PASSWORD,
    "database": settings.CALC_DB_DATABASE,
    "charset": settings.CALC_DB_CHARSET,
}
