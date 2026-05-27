# -*- coding: utf-8 -*-
"""
计算引擎 - 核心计算逻辑

职责：
1. 提供统一的计算接口
2. 管理全局参数池
3. 执行计算链
4. 记录计算日志

不包含：
- MCP 协议相关代码
- LangGraph 相关代码
- 数据库查询实现（通过回调函数注入）
"""
import json
from typing import Dict, Any, Callable, Optional
from datetime import datetime
from pathlib import Path

# 配置目录
CONFIG_DIR = Path(__file__).parent
LOG_FILE = CONFIG_DIR / "calc_log.json"

# 加载配置
with open(CONFIG_DIR / "formula_config.json", "r", encoding="utf-8") as f:
    FORMULA_CONFIG = json.load(f)


def write_log(log_entry: Dict[str, Any]):
    """追加写入日志"""
    try:
        if LOG_FILE.exists():
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                logs = json.load(f)
        else:
            logs = []
        
        log_entry["timestamp"] = datetime.now().isoformat()
        logs.append(log_entry)
        
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[日志] 写入失败: {e}")


def calculate_parameter(
    target: str,
    params: Dict[str, Any],
    query_callback: Callable[[str, Dict[str, Any]], Dict[str, Any]]
) -> Dict[str, Any]:
    """
    计算参数（完整流程，使用全局参数池）
    
    Args:
        target: 目标参数
        params: 输入参数
        query_callback: 查询回调函数，签名为 (query_type, query_args) -> result
        
    Returns:
        计算结果
    """
    from .dependency_analysis import (
        analyze_dependencies,
        validate_calculation_chain,
        get_missing_param_info
    )
    
    log_entry = {
        "type": "calculation",
        "target": target,
        "input_params": params.copy()
    }
    
    try:
        # 创建全局参数池
        param_pool = params.copy()
        
        # 应用默认值
        for key, default_info in FORMULA_CONFIG["default_values"].items():
            if key not in param_pool:
                param_pool[key] = default_info["value"]
        
        # 依赖分析
        can_calc, missing, chain = analyze_dependencies(target, param_pool)
        
        if not can_calc:
            # 缺少参数
            missing_info = get_missing_param_info(missing)
            log_entry["status"] = "missing_params"
            log_entry["missing_params"] = missing_info
            write_log(log_entry)
            
            # 区分参数类型：known（已知参数，需要用户提供）vs target（待求参数，可以查询或计算）
            user_input_params = [info for info in missing_info if info["type"] == "known"]
            queryable_params = [info for info in missing_info if info["type"] == "target"]
            
            # 生成错误信息
            error_parts = []
            if user_input_params:
                user_param_names = [f"{info['name']}({info['unit']})" if info['unit'] else info['name'] 
                                   for info in user_input_params]
                error_parts.append(f"需要用户提供：{', '.join(user_param_names)}")
            
            if queryable_params:
                query_param_names = [f"{info['name']}({info['unit']})" if info['unit'] else info['name'] 
                                    for info in queryable_params]
                error_parts.append(f"可以查询或计算：{', '.join(query_param_names)}")
            
            error_msg = "无法计算，缺少必要参数。" + "；".join(error_parts) + "。"
            
            return {
                "success": False,
                "error": error_msg,
                "missing_params": missing_info,
                "requires_user_input": len(user_input_params) > 0,
                "user_input_params": [p["param"] for p in user_input_params],
                "queryable_params": [p["param"] for p in queryable_params]
            }
        
        # 验证计算链
        is_valid, error_msg = validate_calculation_chain(chain, param_pool)
        if not is_valid:
            log_entry["status"] = "invalid_chain"
            log_entry["error"] = error_msg
            write_log(log_entry)
            
            return {
                "success": False,
                "error": f"计算链验证失败: {error_msg}"
            }
        
        # 执行计算链
        chain_log = []
        
        for step in chain:
            param = step["param"]
            step_type = step["type"]
            
            if step_type == "query":
                # 查询步骤
                query_type = FORMULA_CONFIG["query_mappings"][param]["query_type"]
                
                # 从参数池中获取依赖参数
                query_args = {dep: param_pool[dep] for dep in step["dependencies"] if dep in param_pool}
                
                # 额外传递可能有用的参数
                optional_params = ["resistivity", "specific_gravity", "alloy_shape"]
                for opt_param in optional_params:
                    if opt_param in param_pool and opt_param not in query_args:
                        query_args[opt_param] = param_pool[opt_param]
                
                # 调用查询回调
                query_result = query_callback(query_type, query_args)
                
                if not query_result["success"]:
                    log_entry["status"] = "query_failed"
                    log_entry["failed_step"] = step
                    log_entry["error"] = query_result["error"]
                    write_log(log_entry)
                    
                    return {
                        "success": False,
                        "error": f"查询失败: {query_result['error']}",
                        "failed_step": step["name"]
                    }
                
                # 将查询结果添加到参数池
                param_pool[param] = query_result["value"]
                
                step_log = {
                    "step": step["name"],
                    "type": "query",
                    "result": query_result["value"],
                    "unit": query_result["unit"],
                    "source": query_result.get("source", "database")
                }
                
                # 添加降级信息
                if query_result.get("fallback"):
                    step_log["fallback"] = True
                    step_log["fallback_reason"] = query_result.get("fallback_reason")
                    step_log["formula"] = query_result.get("formula")
                    step_log["message"] = query_result.get("message")
                
                # 添加默认值信息
                if query_result.get("is_default"):
                    step_log["is_default"] = True
                    step_log["message"] = query_result.get("message")
                
                chain_log.append(step_log)
            
            else:
                # 计算步骤
                formula = FORMULA_CONFIG["calculation_formulas"][param]
                expression = formula["expression"]
                
                # 从参数池中准备计算环境
                calc_env = {dep: param_pool[dep] for dep in step["dependencies"] if dep in param_pool}
                
                # 检查依赖
                missing_deps = [dep for dep in step["dependencies"] if dep not in param_pool]
                if missing_deps:
                    log_entry["status"] = "missing_dependencies"
                    log_entry["failed_step"] = step
                    log_entry["missing_deps"] = missing_deps
                    write_log(log_entry)
                    
                    return {
                        "success": False,
                        "error": f"计算步骤 '{step['name']}' 缺少依赖: {missing_deps}",
                        "failed_step": step["name"]
                    }
                
                # 执行计算
                try:
                    # 检查是否是特殊计算（需要自定义逻辑）
                    if expression.startswith("special:"):
                        special_type = expression.split(":")[1]
                        value = _execute_special_calculation(special_type, calc_env, param_pool, query_callback)
                    else:
                        # 普通表达式计算
                        value = eval(expression, {"__builtins__": {}}, calc_env)
                    
                    param_pool[param] = value
                    
                    chain_log.append({
                        "step": step["name"],
                        "type": "calculation",
                        "formula": expression if not expression.startswith("special:") else f"特殊计算: {special_type}",
                        "result": round(value, 6) if isinstance(value, float) else value,
                        "unit": step["unit"]
                    })
                except Exception as e:
                    log_entry["status"] = "calculation_failed"
                    log_entry["failed_step"] = step
                    log_entry["error"] = str(e)
                    write_log(log_entry)
                    
                    return {
                        "success": False,
                        "error": f"计算失败: {str(e)}",
                        "failed_step": step["name"],
                        "expression": expression,
                        "available_params": list(calc_env.keys())
                    }
        
        # 成功
        final_result = param_pool.get(target)
        if final_result is None:
            return {
                "success": False,
                "error": f"计算完成但未找到目标参数 '{target}' 的值"
            }
        
        log_entry["status"] = "success"
        log_entry["calculation_chain"] = chain_log
        log_entry["result"] = final_result
        log_entry["param_pool_size"] = len(param_pool)
        write_log(log_entry)
        
        return {
            "success": True,
            "result": final_result,
            "unit": chain[-1]["unit"] if chain else "",
            "calculation_chain": chain_log,
            "param_pool": {k: v for k, v in param_pool.items() if k != target}
        }
    
    except Exception as e:
        log_entry["status"] = "error"
        log_entry["error"] = str(e)
        write_log(log_entry)
        
        return {
            "success": False,
            "error": f"执行失败: {str(e)}"
        }



def _execute_special_calculation(
    special_type: str, 
    calc_env: Dict[str, Any], 
    param_pool: Dict[str, Any],
    query_callback: Optional[Callable[[str, Dict[str, Any]], Dict[str, Any]]] = None
) -> float:
    """
    执行特殊计算逻辑
    
    Args:
        special_type: 特殊计算类型
        calc_env: 计算环境（当前步骤的依赖参数）
        param_pool: 全局参数池
        query_callback: 查询回调函数（可选，用于数据库查询）
        
    Returns:
        计算结果（对于 belt_dimensions 返回 thickness，width 会自动添加到 param_pool）
    """
    if special_type == "belt_thickness_width":
        # 合金带厚度和宽度计算（统一处理，不管目标是什么）
        # 逻辑：
        # 1. 尝试多个宽厚比 [10, 8, 12, 15, 5]（除非用户指定）
        # 2. 对每个宽厚比，计算厚度和宽度
        # 3. 查询数据库是否有标准规格
        # 4. 找到标准规格或尝试完所有比例后，返回结果
        # 5. 同时设置 param_pool['thickness'] 和 param_pool['width']
        
        current = calc_env["current"]
        resistivity = calc_env["resistivity_at_temperature"]  # 使用指定温度下的电阻率
        surface_load = calc_env["surface_load"]
        aspect_ratio = calc_env.get("aspect_ratio", 10)
        material = calc_env.get("material", "")
        
        # 合金带计算必须使用 alloy_shape = "扁带"（数据库中的存储值）
        alloy_shape = "扁带"
        
        # 定义宽厚比尝试顺序（优先使用第一个）
        ratios = [10, 8, 12, 15, 5]
        
        # 计算基础因子
        factor = (current ** 2 * resistivity / surface_load) ** (1 / 3)
        
        # 尝试不同的宽厚比
        best_thickness = None
        best_width = None
        used_ratio = ratios[0]
        found_any_spec = False  # 标记是否找到任何标准规格
        
        for ratio in ratios:
            # 计算 k_t
            k_t = (1 / (20 * ratio * (ratio + 1))) ** (1 / 3)
            
            # 计算厚度和宽度
            thickness = round(k_t * factor, 1)
            width = round(thickness * ratio, 1)
            
            print(f'[合金带计算] 尝试宽厚比={ratio}, 厚度={thickness}mm, 宽度={width}mm')
            
            # 如果是第一个比例，先保存结果（作为默认值）
            if ratio == ratios[0]:
                best_thickness = thickness
                best_width = width
                used_ratio = ratio
            
            # 检查是否有标准规格（如果有查询回调）
            found_spec = False
            if query_callback and material:
                try:
                    spec_result = query_callback("find_standard_spec", {
                        "material": material,
                        "thickness": thickness,
                        "width": width,
                        "alloy_shape": alloy_shape
                    })
                    if spec_result.get("success", False):
                        found_spec = spec_result.get("found", False)
                        if found_spec:
                            print(f'[合金带计算] 找到标准规格！')
                            found_any_spec = True
                            best_thickness = thickness
                            best_width = width
                            used_ratio = ratio
                            break
                except Exception as e:
                    print(f'[合金带计算] 规格查询失败: {e}')
        
        # 如果没有找到任何标准规格，使用第一个宽厚比的结果（已经保存在 best_thickness/best_width 中）
        if not found_any_spec:
            print(f'[合金带计算] 未找到标准规格，使用默认宽厚比={ratios[0]}的结果')
        
        # 同时设置厚度和宽度到参数池
        param_pool["thickness"] = best_thickness
        param_pool["width"] = best_width
        param_pool["aspect_ratio"] = used_ratio
        
        print(f'[合金带计算] 最终结果: 厚度={best_thickness}mm, 宽度={best_width}mm, 宽厚比={used_ratio}')
        
        # 返回厚度（作为主要返回值，宽度已在参数池中）
        return best_thickness
    
    elif special_type == "ripple_depth_by_alloy":
        # 波纹深度计算：根据合金类型判断系数
        # 铁铬铝：H = 2.5 × b
        # 镍铬：H = 3.5 × b
        width = calc_env["width"]
        material = calc_env.get("material", "")
        
        # 判断合金类型（与 calculate 逻辑一致）
        if material and (material[0].isdigit() or material[0] == "H" or "铁铬铝" in material):
            # 铁铬铝合金
            coefficient = 2.5
            alloy_type = "铁铬铝"
        else:
            # 镍铬合金
            coefficient = 3.5
            alloy_type = "镍铬"
        
        ripple_depth = round(coefficient * width, 2)
        print(f'[波纹深度计算] 材料={material}, 合金类型={alloy_type}, 系数={coefficient}, 宽度={width}mm, 波纹深度={ripple_depth}mm')
        
        return ripple_depth
    
    else:
        raise ValueError(f"未知的特殊计算类型: {special_type}")
