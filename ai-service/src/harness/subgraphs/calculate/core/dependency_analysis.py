# -*- coding: utf-8 -*-
"""
依赖分析模块 - 根据公式配置生成计算链
"""
import json
from typing import Dict, List, Set, Tuple, Any
from pathlib import Path

# 加载配置
CONFIG_DIR = Path(__file__).parent
with open(CONFIG_DIR / "formula_config.json", "r", encoding="utf-8") as f:
    FORMULA_CONFIG = json.load(f)


def analyze_dependencies(target: str, available_params: Dict[str, Any]) -> Tuple[bool, List[str], List[Dict]]:
    """
    分析目标参数的依赖并生成计算链
    
    Args:
        target: 目标参数名
        available_params: 当前可用的参数字典
        
    Returns:
        (can_calculate, missing_params, calculation_chain)
        - can_calculate: 是否可以计算
        - missing_params: 缺失的输入参数列表
        - calculation_chain: 计算链（按执行顺序）
    """
    # 合并计算公式和查询映射
    all_formulas = {
        **FORMULA_CONFIG["calculation_formulas"],
        **FORMULA_CONFIG["query_mappings"]
    }
    
    # 如果目标已经在可用参数中，直接返回
    if target in available_params:
        return True, [], []
    
    # 如果目标不在公式中，无法计算
    if target not in all_formulas:
        return False, [target], []
    
    # 递归分析依赖
    calculation_chain = []
    visited = set()
    missing = set()
    
    def dfs(param: str) -> bool:
        """深度优先搜索依赖"""
        # 已访问过
        if param in visited:
            return True
        
        # 已经有值
        if param in available_params:
            visited.add(param)
            return True
        
        # 不在公式中，是缺失的输入参数
        if param not in all_formulas:
            missing.add(param)
            return False
        
        # 获取依赖
        formula = all_formulas[param]
        deps = formula["dependencies"]
        
        # 递归处理所有依赖
        all_deps_satisfied = True
        for dep in deps:
            if not dfs(dep):
                all_deps_satisfied = False
        
        # 如果所有依赖都满足，添加到计算链
        if all_deps_satisfied:
            visited.add(param)
            
            # 特殊处理：如果是 belt_thickness_width，同时标记 thickness 和 width 为已访问
            # 因为 belt_thickness_width 会同时计算两者
            if formula.get("expression", "").startswith("special:belt_thickness_width"):
                visited.add("thickness")
                visited.add("width")
            
            calculation_chain.append({
                "param": param,
                "name": formula["name"],
                "unit": formula["unit"],
                "dependencies": deps,
                "type": "query" if param in FORMULA_CONFIG["query_mappings"] else "calculation"
            })
            return True
        else:
            return False
    
    # 执行依赖分析
    can_calc = dfs(target)
    
    return can_calc, list(missing), calculation_chain


def validate_calculation_chain(chain: List[Dict], available_params: Dict[str, Any]) -> Tuple[bool, str]:
    """
    验证计算链的正确性
    
    Args:
        chain: 计算链
        available_params: 初始可用参数
        
    Returns:
        (is_valid, error_message)
    """
    current_params = set(available_params.keys())
    
    for step in chain:
        param = step["param"]
        deps = step["dependencies"]
        
        # 检查所有依赖是否都已满足
        missing_deps = [d for d in deps if d not in current_params]
        if missing_deps:
            return False, f"步骤 '{step['name']}' 缺少依赖: {missing_deps}"
        
        # 添加当前参数到已知参数集
        current_params.add(param)
    
    return True, ""


def get_missing_param_info(missing_params: List[str]) -> List[Dict]:
    """
    获取缺失参数的详细信息
    
    Args:
        missing_params: 缺失参数列表
        
    Returns:
        参数信息列表
    """
    # 加载参数元数据
    with open(CONFIG_DIR / "param_meta.json", "r", encoding="utf-8") as f:
        param_meta = json.load(f)
    
    result = []
    for param in missing_params:
        if param in param_meta["parameters"]:
            meta = param_meta["parameters"][param]
            result.append({
                "param": param,
                "name": meta["name"],
                "unit": meta["unit"],
                "type": meta.get("type", "unknown"),
                "description": meta["description"]
            })
        else:
            result.append({
                "param": param,
                "name": param,
                "unit": "未知",
                "type": "unknown",
                "description": "未知参数"
            })
    
    return result
