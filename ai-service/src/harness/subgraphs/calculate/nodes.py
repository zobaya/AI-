# -*- coding: utf-8 -*-
"""
节点定义 - 基于questions结构（查询/计算分离）

新架构：
- 用户输入 → 解析为多个独立的question
- 每个question包含：类型(query/calculate) + 已知参数 + 待求参数
- 查询问题：直接查询数据库，返回结构化数据
- 计算问题：依赖分析 → 查询缺失参数 → 执行计算
"""
from typing import Dict, Any, List
from .state import CalculateState
from core.config import settings
from openai import OpenAI
from langchain_core.callbacks.manager import adispatch_custom_event
import json
import re


def get_llm_client():
    """获取LLM客户端（每次调用创建新实例）"""
    return OpenAI(
        api_key="none",
        base_url=settings.VLLM_BASE_URL + "/v1",
        timeout=60.0
    )


async def _progress(message: str, config):
    """发送进度事件"""
    if config:
        try:
            await adispatch_custom_event(
                "progress",
                {"node": "calculate", "message": message},
                config=config,
            )
        except Exception:
            pass


async def initial_decision_node(state: CalculateState, config=None) -> CalculateState:
    """
    参数解析节点 - 提取问题列表
    
    职责：
    1. 将用户输入解析为多个独立的问题
    2. 每个问题包含：已知参数 + 待求参数
    3. 避免参数冲突（每个question的参数值唯一）
    """
    debug_logs = state.get("debug_logs", [])
    debug_logs.append("[参数解析] 开始")

    await _progress("📋 正在解析计算参数...", config)

    user_input = state["user_input"]
    
    # 定义可选参数列表
    available_params = {
        # 输入参数
        "power": "功率 (W)",
        "voltage": "电压 (V)",
        "current": "电流 (A)",
        "resistance": "电阻 (Ω)",
        "temperature": "温度 (℃)",
        "material": "合金材料名称（如Cr20Ni80、0Cr25Al5等）",
        "diameter": "直径 (mm) - 用于合金丝",
        "thickness": "厚度 (mm) - 用于扁丝/扁带",
        "width": "宽度 (mm) - 用于扁丝/扁带",
        "length": "长度 (m)",
        "surface_load": "表面负荷 (W/cm²)",
        "alloy_shape": "合金形状（可选值：'合金丝'、'扁丝'、'扁带'）",
        "aspect_ratio": "宽厚比（默认10）",
        # 输出参数（可作为计算目标）
        "specific_gravity": "比重 (g/cm³)",
        "resistivity": "电阻率-常温20℃ (10⁻⁶Ω·m) - 【仅用于查询常温基准值，不用于计算】",
        "resistivity_at_temperature": "指定温度下的电阻率 (10⁻⁶Ω·m) - 【当问题涉及特定温度时使用此参数】",
        "resistance_per_meter": "每米电阻 (Ω/m)",
        "weight_per_meter": "每米重量 (g/m)",
        "surface_area_per_ohm": "每欧表面积 (cm²/Ω)",
        "surface_area_per_meter": "每米表面积 (cm²/m)",
        "cross_section_area": "截面积 (mm²)",
        "ct_value": "温度系数Ct",
        # 合金带参数
        "ripple_depth": "波纹深度H (mm)",
        "ripple_pitch": "波纹节距S (mm)",
        "curvature_radius": "曲率半径r (mm)",
        "strip_length": "合金带长度系数L"
    }
    
    # 使用LLM分析问题
    parse_prompt = f"""将用户问题解析为多个独立的子问题，并区分查询问题和计算问题。

用户问题：{user_input}

【可选参数列表】：
{json.dumps(available_params, indent=2, ensure_ascii=False)}

【问题类型分类标准】（重要！不要被用户的动词误导）：
1. query（查询问题）：仅用于查询常温下的基础静态物理属性。目标参数只能是：`specific_gravity`（比重）、`resistivity`（常温电阻率）、`ct_value`（温度系数）等不随业务场景变化的基础常量。
2. calculate（计算问题）：需要推导、公式计算或随条件变化的参数。目标参数如：`resistivity_at_temperature`（指定温度下的电阻率）、电流、电压、长宽厚、截面积等。

输出JSON（严格格式，不要注释，不要思考过程）：
{{
    "questions": [
        {{
            "id": "q1",
            "type": "query或calculate",
            "description": "问题描述",
            "known_parameters": {{}},
            "target_parameters": ["待求参数名列表"]
        }}
    ]
}}

【重要规则】：
1. **只提取用户明确要求的问题**，不要拆分计算的中间步骤
2. 例如：用户问"求厚度和宽度"，只生成一个问题，target_parameters: ["thickness", "width"]
3. 不要生成"求电流"、"求电阻率"等中间步骤的问题，系统会自动处理依赖关系
4. 每个question的known_parameters中，每个参数只能有一个值
5. 如果用户问多个情况（如不同温度、不同电压），才拆分成多个question
6. 参数名必须从【可选参数列表】中选择
7. 数值必须转换单位后返回纯数字（不带单位）
8. 单位转换：kW→W(*1000), kV→V(*1000), mA→A(/1000)
9. 'material' 只返回合金名称，不添加"合金"等描述词
10. **'alloy_shape' 自动识别规则**（可选值：'合金丝'、'扁丝'、'扁带'）：
    - 如果用户明确提到"扁带"或"合金带" → alloy_shape: "扁带"
    - 如果用户明确提到"扁丝" → alloy_shape: "扁丝"
    - 如果用户明确提到"合金丝"或"直径" → alloy_shape: "合金丝"
    - 如果用户没有明确指明形状，不添加 alloy_shape 参数（使用默认值"合金丝"）
    - 注意：不要根据"厚度"、"宽度"等参数自动判断，必须用户明确提到形状名称
11. **无关问题过滤**（重要）：
    - 如果用户问题是问候语（如"你好"、"您好"、"hi"、"hello"）、闲聊、感谢等与合金材料计算/查询无关的内容
    - 或者用户问题没有提到任何合金材料、计算参数、查询目标
    - 必须返回空的questions列表：{{"questions": []}}
    - 不要强行将无关问题解析为查询或计算问题
    - 例如：用户问"你好"，应返回 {{"questions": []}}，而不是查询HRE合金的属性

【示例1】：计算问题（单个目标）
问题：功率10kW，电压220V，求电流
输出：
{{
    "questions": [
        {{
            "id": "q1",
            "type": "calculate",
            "description": "功率10kW、电压220V时的电流",
            "known_parameters": {{"power": 10000, "voltage": 220}},
            "target_parameters": ["current"]
        }}
    ]
}}

【示例2】：计算问题（多个目标，自动识别 alloy_shape）
问题：HRE合金，功率10kW，电压220V，表面负荷1.5W/cm²，求合金带的厚度和宽度
输出：
{{
    "questions": [
        {{
            "id": "q1",
            "type": "calculate",
            "description": "根据功率、电压、表面负荷计算合金带的厚度和宽度",
            "known_parameters": {{"material": "HRE", "power": 10000, "voltage": 220, "surface_load": 1.5, "alloy_shape": "扁带"}},
            "target_parameters": ["thickness", "width"]
        }}
    ]
}}
注意：
1. 不要拆分成"求电流"、"求电阻率"等中间步骤！
2. 因为用户明确提到"合金带"，添加 alloy_shape: "扁带"

【示例3】：计算问题（不同温度）
问题：HRE合金在800℃和600℃下的电阻率
输出：
{{
    "questions": [
        {{
            "id": "q1",
            "type": "calculate",
            "description": "HRE合金在800℃下的电阻率",
            "known_parameters": {{"material": "HRE", "temperature": 800}},
            "target_parameters": ["resistivity_at_temperature"]
        }},
        {{
            "id": "q2",
            "type": "calculate",
            "description": "HRE合金在600℃下的电阻率",
            "known_parameters": {{"material": "HRE", "temperature": 600}},
            "target_parameters": ["resistivity_at_temperature"]
        }}
    ]
}}

【示例4】：查询问题
问题：查询HRE合金的比重和电阻率
输出：
{{
    "questions": [
        {{
            "id": "q1",
            "type": "query",
            "description": "查询HRE合金的比重和电阻率",
            "known_parameters": {{"material": "HRE"}},
            "target_parameters": ["specific_gravity", "resistivity"]
        }}
    ]
}}

【示例5】：无关问题（问候、闲聊等）
问题：你好
输出：
{{
    "questions": []
}}
说明：这是问候语，与合金材料计算/查询无关，返回空列表

问题：谢谢
输出：
{{
    "questions": []
}}
说明：这是感谢语，与合金材料计算/查询无关，返回空列表

只返回JSON，不要解释，不要思考过程："""
    
    try:
        client = get_llm_client()
        
        response = client.chat.completions.create(
            model=settings.VLLM_MODEL_NAME,
            messages=[
                {"role": "system", "content": "你是参数提取专家。只返回JSON格式，不要思考过程，不要其他内容。"},
                {"role": "user", "content": parse_prompt}
            ],
            temperature=0.1,
            max_tokens=1500,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}}
        )
        
        content = response.choices[0].message.content.strip()
        debug_logs.append(f"[参数解析] LLM返回: {content[:500]}")
        
        # 清理并解析JSON
        # 1. 移除 <think> 标签
        content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
        
        # 2. 尝试多种方式提取JSON
        result = None
        
        # 方法1：直接解析
        try:
            result = json.loads(content)
        except:
            pass
        
        # 方法2：提取完整的JSON对象（支持嵌套）
        if not result:
            # 找到第一个 { 和最后一个 }
            start = content.find('{')
            end = content.rfind('}')
            if start != -1 and end != -1 and end > start:
                json_str = content[start:end+1]
                # 清理
                json_str = re.sub(r'//.*?(?=\n|$)', '', json_str)
                json_str = re.sub(r'/\*.*?\*/', '', json_str, flags=re.DOTALL)
                json_str = re.sub(r',\s*}', '}', json_str)
                json_str = re.sub(r',\s*]', ']', json_str)
                try:
                    result = json.loads(json_str)
                except:
                    pass
        
        # 方法3：修复不完整的JSON
        if not result:
            # 如果JSON被截断，尝试补全
            if '"questions"' in content and content.count('[') > content.count(']'):
                # 补全缺失的括号
                content = content + ']}'
                try:
                    result = json.loads(content)
                except:
                    pass
        
        if not result:
            debug_logs.append(f"[参数解析] JSON解析失败")
            raise ValueError("无法解析JSON")
        
        questions = result.get("questions", [])
        
        # 验证questions格式并标准化
        if not isinstance(questions, list):
            debug_logs.append(f"[参数解析] questions不是列表")
            questions = []
        
        # 标准化：确保target_parameters是列表
        for q in questions:
            if "target_parameter" in q and "target_parameters" not in q:
                q["target_parameters"] = [q["target_parameter"]]
            elif "target_parameters" not in q:
                q["target_parameters"] = []
            
            # 确保有type字段
            if "type" not in q:
                # 默认为calculate
                q["type"] = "calculate"
        
        debug_logs.append(f"[参数解析] 解析出 {len(questions)} 个问题")
        if not questions:
            await _progress("⚠️ 未识别到计算或查询问题", config)
        else:
            q_desc = "、".join(q.get("description", "")[:20] for q in questions[:3])
            await _progress(f"✅ 解析完成，{len(questions)} 个问题：{q_desc}", config)
        for q in questions:
            debug_logs.append(f"[参数解析] {q['id']}: [{q['type']}] {q['description']}")
            debug_logs.append(f"[参数解析]   待求: {q['target_parameters']}")
        
    except Exception as e:
        debug_logs.append(f"[参数解析] LLM失败，使用降级策略: {str(e)}")
        
        # 降级：生成单个问题
        questions = [{
            "id": "q1",
            "description": user_input[:50],
            "known_parameters": {},
            "target_parameter": "unknown"
        }]
    
    return {
        **state,
        "questions": questions,
        "question_results": {},
        "debug_logs": debug_logs
    }


async def query_node(state: CalculateState, config=None) -> CalculateState:
    """
    查询节点 - 处理查询问题和为计算问题补充参数

    策略：
    1. 对于query类型的问题：根据target_parameters查询对应的数据库字段
    2. 对于calculate类型的问题：通过依赖分析找出缺失参数，然后查询
    3. 如果questions为空，说明这不是计算/查询问题，设置is_irrelevant标志
    """
    debug_logs = state.get("debug_logs", [])
    debug_logs.append("[查询节点] 开始")

    questions = state.get("questions", [])

    # 检查是否为无关问题（如问候、闲聊等）
    if not questions or len(questions) == 0:
        debug_logs.append("[查询节点] 没有问题需要处理，标记为无关问题")
        return {
            **state,
            "is_irrelevant": True,  # 标记为无关问题
            "query_results": {},
            "question_results": {},
            "debug_logs": debug_logs
        }

    await _progress(f"🔍 正在查询材料属性（{len(questions)} 个问题）...", config)

    try:
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        from . import db_reader
        from .core.dependency_analysis import analyze_dependencies
        
        query_results = {}
        
        for question in questions:
            q_id = question["id"]
            q_type = question.get("type", "calculate")
            known_params = question["known_parameters"]
            target_params = question.get("target_parameters", [])
            material = known_params.get("material")
            
            debug_logs.append(f"[查询节点] {q_id}: 类型={q_type}, 待求={target_params}")
            
            q_results = {}
            
            if q_type == "query":
                # 查询问题：直接查询target_parameters中的所有参数
                if not material:
                    debug_logs.append(f"[查询节点] {q_id}: 查询问题缺少material参数")
                    # 标记为失败，需要材料参数
                    q_results['_query_failed'] = True
                    q_results['_missing_params'] = ['material']
                    q_results['_error'] = "缺少必要参数：材料名称"
                    query_results[q_id] = q_results
                    continue
                
                debug_logs.append(f"[查询节点] {q_id}: 查询材料 {material} 的属性: {target_params}")
                
                # 检查是否需要规格参数
                spec_params = ["resistance_per_meter", "weight_per_meter", "surface_area_per_ohm", 
                              "surface_area_per_meter", "cross_section_area"]
                needs_spec = any(param in spec_params for param in target_params)
                
                if needs_spec:
                    diameter = known_params.get("diameter")
                    thickness = known_params.get("thickness")
                    width = known_params.get("width")
                    
                    # 检查是否有规格参数
                    has_spec = diameter or (thickness and width)
                    
                    if not has_spec:
                        debug_logs.append(f"[查询节点] {q_id}: 查询规格相关参数，但缺少规格信息")
                        missing = []
                        if not diameter:
                            missing.append("直径(diameter)")
                        if not thickness or not width:
                            missing.append("厚度和宽度(thickness, width)")
                        
                        q_results['_query_failed'] = True
                        q_results['_missing_params'] = missing
                        q_results['_error'] = f"缺少必要参数：{' 或 '.join(missing)}"
                        query_results[q_id] = q_results
                        continue
                
                for param in target_params:
                    if param == "specific_gravity":
                        value = db_reader.get_specific_gravity(material)
                        if value:
                            q_results[param] = value
                            debug_logs.append(f"[查询节点] {q_id}: {param} = {value}")
                    
                    elif param == "resistivity":
                        value = db_reader.get_resistivity(material)
                        if value:
                            q_results[param] = value
                            debug_logs.append(f"[查询节点] {q_id}: {param} = {value}")
                    
                    elif param == "ct_value" or param == "temperature_coeff":
                        temp = known_params.get("temperature")
                        if temp:
                            value = db_reader.get_ct_value(material, temp)
                            if value:
                                q_results["ct_value"] = value
                                q_results["temperature_coeff"] = value
                                debug_logs.append(f"[查询节点] {q_id}: ct_value({temp}℃) = {value}")
                    
                    elif param == "resistance_per_meter":
                        diameter = known_params.get("diameter")
                        thickness = known_params.get("thickness")
                        width = known_params.get("width")
                        alloy_shape = known_params.get("alloy_shape", "合金丝")
                        
                        if diameter or (thickness and width):
                            value = db_reader.get_resistance_per_meter(
                                material, alloy_shape, 
                                diameter=diameter, 
                                thickness=thickness, 
                                width=width
                            )
                            if value:
                                q_results[param] = value
                                debug_logs.append(f"[查询节点] {q_id}: {param} = {value}")
                    
                    elif param == "weight_per_meter":
                        diameter = known_params.get("diameter")
                        thickness = known_params.get("thickness")
                        width = known_params.get("width")
                        alloy_shape = known_params.get("alloy_shape", "合金丝")
                        
                        if diameter or (thickness and width):
                            value = db_reader.get_weight_per_meter(
                                material, alloy_shape, 
                                diameter=diameter, 
                                thickness=thickness, 
                                width=width
                            )
                            if value:
                                q_results[param] = value
                                debug_logs.append(f"[查询节点] {q_id}: {param} = {value}")
            
            else:
                # 计算问题：先尝试直接查询待求参数，查不到再准备计算所需的依赖参数
                if not material:
                    debug_logs.append(f"[查询节点] {q_id}: 计算问题缺少material参数，跳过查询")
                    query_results[q_id] = q_results
                    continue
                
                # 1. 先尝试直接查询待求参数（优先数据库）
                debug_logs.append(f"[查询节点] {q_id}: 尝试直接查询待求参数: {target_params}")
                
                for target in target_params:
                    # 尝试直接查询
                    if target == "specific_gravity":
                        value = db_reader.get_specific_gravity(material)
                        if value:
                            q_results[target] = value
                            debug_logs.append(f"[查询节点] {q_id}: 直接查询到 {target} = {value}")
                    
                    elif target == "resistivity":
                        value = db_reader.get_resistivity(material)
                        if value:
                            q_results[target] = value
                            debug_logs.append(f"[查询节点] {q_id}: 直接查询到 {target} = {value}")
                    
                    elif target == "ct_value" or target == "temperature_coeff":
                        temp = known_params.get("temperature")
                        if temp:
                            value = db_reader.get_ct_value(material, temp)
                            if value:
                                q_results[target] = value
                                q_results['ct_value'] = value
                                q_results['temperature_coeff'] = value
                                debug_logs.append(f"[查询节点] {q_id}: 直接查询到 {target}({temp}℃) = {value}")
                    
                    elif target == "resistance_per_meter":
                        diameter = known_params.get("diameter")
                        thickness = known_params.get("thickness")
                        width = known_params.get("width")
                        alloy_shape = known_params.get("alloy_shape", "合金丝")
                        
                        if diameter or (thickness and width):
                            value = db_reader.get_resistance_per_meter(
                                material, alloy_shape, 
                                diameter=diameter, 
                                thickness=thickness, 
                                width=width
                            )
                            if value:
                                q_results[target] = value
                                debug_logs.append(f"[查询节点] {q_id}: 直接查询到 {target} = {value}")
                    
                    elif target == "weight_per_meter":
                        diameter = known_params.get("diameter")
                        thickness = known_params.get("thickness")
                        width = known_params.get("width")
                        alloy_shape = known_params.get("alloy_shape", "合金丝")
                        
                        if diameter or (thickness and width):
                            value = db_reader.get_weight_per_meter(
                                material, alloy_shape, 
                                diameter=diameter, 
                                thickness=thickness, 
                                width=width
                            )
                            if value:
                                q_results[target] = value
                                debug_logs.append(f"[查询节点] {q_id}: 直接查询到 {target} = {value}")
                    
                    elif target == "surface_area_per_ohm":
                        diameter = known_params.get("diameter")
                        thickness = known_params.get("thickness")
                        width = known_params.get("width")
                        alloy_shape = known_params.get("alloy_shape", "合金丝")
                        
                        if diameter or (thickness and width):
                            try:
                                value = db_reader.get_surface_area_per_ohm(
                                    material, alloy_shape, 
                                    diameter=diameter, 
                                    thickness=thickness, 
                                    width=width
                                )
                                if value:
                                    q_results[target] = value
                                    debug_logs.append(f"[查询节点] {q_id}: 直接查询到 {target} = {value}")
                            except:
                                pass
                    
                    elif target == "surface_area_per_meter":
                        diameter = known_params.get("diameter")
                        thickness = known_params.get("thickness")
                        width = known_params.get("width")
                        alloy_shape = known_params.get("alloy_shape", "合金丝")
                        
                        if diameter or (thickness and width):
                            try:
                                value = db_reader.get_surface_area_per_meter(
                                    material, alloy_shape, 
                                    diameter=diameter, 
                                    thickness=thickness, 
                                    width=width
                                )
                                if value:
                                    q_results[target] = value
                                    debug_logs.append(f"[查询节点] {q_id}: 直接查询到 {target} = {value}")
                            except:
                                pass
                
                # 2. 如果所有待求参数都查询到了，标记为已完成
                all_found = all(target in q_results for target in target_params)
                if all_found:
                    debug_logs.append(f"[查询节点] {q_id}: 所有待求参数都已查询到，无需计算")
                    q_results['_direct_query'] = True  # 标记为直接查询
                else:
                    # 3. 有参数查不到，需要计算，查询计算所需的依赖参数
                    debug_logs.append(f"[查询节点] {q_id}: 部分参数需要计算，查询依赖参数")
                    
                    # 应用默认值到 known_params（用于依赖分析）
                    from .core.calc_engine import FORMULA_CONFIG
                    params_with_defaults = known_params.copy()
                    for key, default_info in FORMULA_CONFIG["default_values"].items():
                        if key not in params_with_defaults:
                            params_with_defaults[key] = default_info["value"]
                    
                    # 对每个target进行依赖分析
                    all_missing_params = set()
                    for target in target_params:
                        if target in q_results:
                            continue  # 已经查询到的跳过
                        
                        can_calc, missing, chain = analyze_dependencies(target, params_with_defaults)
                        if not can_calc:
                            all_missing_params.update(missing)
                            debug_logs.append(f"[查询节点] {q_id}: {target} 缺少参数: {missing}")
                    
                    # 查询缺失的参数
                    debug_logs.append(f"[查询节点] {q_id}: 需要查询的依赖参数: {list(all_missing_params)}")
                    
                    # 基础属性（总是查询）
                    if 'specific_gravity' not in q_results:
                        sg = db_reader.get_specific_gravity(material)
                        if sg:
                            q_results['specific_gravity'] = sg
                            debug_logs.append(f"[查询节点] {q_id}: specific_gravity = {sg}")
                    
                    if 'resistivity' not in q_results:
                        res = db_reader.get_resistivity(material)
                        if res:
                            q_results['resistivity'] = res
                            debug_logs.append(f"[查询节点] {q_id}: resistivity = {res}")
                    
                    # 温度相关
                    temp = known_params.get("temperature")
                    if temp or "temperature_coeff" in all_missing_params or "ct_value" in all_missing_params:
                        if temp and 'temperature_coeff' not in q_results:
                            ct = db_reader.get_ct_value(material, temp)
                            if ct:
                                q_results['ct_value'] = ct
                                q_results['temperature_coeff'] = ct
                                debug_logs.append(f"[查询节点] {q_id}: temperature_coeff({temp}℃) = {ct}")
                    
                    # 规格相关
                    diameter = known_params.get("diameter")
                    thickness = known_params.get("thickness")
                    width = known_params.get("width")
                    
                    if diameter or (thickness and width) or "resistance_per_meter" in all_missing_params or "weight_per_meter" in all_missing_params:
                        alloy_shape = known_params.get("alloy_shape", "合金丝")
                        
                        if 'resistance_per_meter' not in q_results:
                            rm = db_reader.get_resistance_per_meter(
                                material, alloy_shape, 
                                diameter=diameter, 
                                thickness=thickness, 
                                width=width
                            )
                            if rm:
                                q_results['resistance_per_meter'] = rm
                                debug_logs.append(f"[查询节点] {q_id}: resistance_per_meter = {rm}")
                        
                        if 'weight_per_meter' not in q_results:
                            gm = db_reader.get_weight_per_meter(
                                material, alloy_shape, 
                                diameter=diameter, 
                                thickness=thickness, 
                                width=width
                            )
                            if gm:
                                q_results['weight_per_meter'] = gm
                                debug_logs.append(f"[查询节点] {q_id}: weight_per_meter = {gm}")
            
            query_results[q_id] = q_results
            debug_logs.append(f"[查询节点] {q_id}: 共查询到 {len(q_results)} 个属性")
        
        debug_logs.append(f"[查询节点] 查询完成，共处理 {len(query_results)} 个问题")
        await _progress(f"✅ 查询完成，已获取 {len(query_results)} 个问题的数据", config)

        return {
            **state,
            "query_results": query_results,
            "debug_logs": debug_logs
        }
    
    except Exception as e:
        debug_logs.append(f"[查询节点] 错误: {str(e)}")
        import traceback
        debug_logs.append(f"[查询节点] 堆栈: {traceback.format_exc()}")
        return {
            **state,
            "query_results": {},
            "debug_logs": debug_logs
        }


async def calculate_node(state: CalculateState, config=None) -> CalculateState:
    """
    计算节点 - 处理所有问题（查询问题直接返回，计算问题执行计算）

    如果is_irrelevant=True，直接返回，不执行计算
    """
    debug_logs = state.get("debug_logs", [])
    debug_logs.append("[计算节点] 开始")

    # 检查是否为无关问题
    if state.get("is_irrelevant"):
        debug_logs.append("[计算节点] 检测到无关问题，跳过计算")
        return {
            **state,
            "calculated_results": {},
            "missing_parameters": None,
            "error": None,
            "debug_logs": debug_logs
        }

    questions = state.get("questions", [])
    calc_questions = [q for q in questions if q.get("type") == "calculate"]
    if calc_questions:
        targets = []
        for q in calc_questions:
            targets.extend(q.get("target_parameters", []))
        await _progress(f"🧮 正在计算：{'、'.join(targets[:5])}...", config)
    
    questions = state.get("questions", [])
    query_results = state.get("query_results", {})
    
    try:
        from .core.calc_engine import calculate_parameter
        from . import db_reader

        query_service = db_reader.query_service
        
        def query_callback(query_type: str, query_args: Dict[str, Any]) -> Dict[str, Any]:
            """查询回调"""
            if query_type == "specific_gravity":
                return query_service.query_specific_gravity(query_args["material"])
            elif query_type == "resistivity":
                return query_service.query_resistivity(query_args["material"])
            elif query_type == "temperature_coefficient":
                return query_service.query_temperature_coefficient(
                    query_args["material"], query_args["temperature"]
                )
            elif query_type == "resistance_per_meter":
                return query_service.query_resistance_per_meter(
                    query_args["material"], query_args["diameter"],
                    query_args.get("alloy_shape", "合金丝"),
                    fallback_to_calculation=True
                )
            elif query_type == "weight_per_meter":
                return query_service.query_weight_per_meter(
                    query_args["material"], query_args["diameter"],
                    query_args.get("alloy_shape", "合金丝"),
                    fallback_to_calculation=True
                )
            elif query_type == "find_diameter":
                return query_service.find_diameter_by_surface_area(
                    query_args["material"],
                    query_args["surface_area"],
                    query_args.get("alloy_shape", "合金丝")
                )
            elif query_type == "find_standard_spec":
                return query_service.find_standard_spec(
                    query_args["material"],
                    query_args["thickness"],
                    query_args["width"],
                    query_args.get("alloy_shape", "扁带")
                )
            else:
                return {"success": False, "error": f"未知查询类型: {query_type}"}
        
        question_results = {}
        
        for question in questions:
            q_id = question["id"]
            q_type = question.get("type", "calculate")
            known_params = question["known_parameters"]
            target_params = question.get("target_parameters", [])
            
            debug_logs.append(f"[计算节点] {q_id}: 类型={q_type}")
            
            if q_type == "query":
                # 查询问题：直接返回查询结果
                q_results = query_results.get(q_id, {})
                
                # 检查是否查询失败（缺少参数）
                if q_results.get('_query_failed'):
                    missing_params = q_results.get('_missing_params', [])
                    error_msg = q_results.get('_error', '查询失败')
                    
                    question_results[q_id] = {
                        "question": question,
                        "result": {
                            "success": False,
                            "error": error_msg,
                            "missing_params": missing_params,
                            "type": "query"
                        }
                    }
                    debug_logs.append(f"[计算节点] {q_id}: 查询失败 - {error_msg}")
                else:
                    question_results[q_id] = {
                        "question": question,
                        "result": {
                            "success": True,
                            "type": "query",
                            "data": q_results,
                            "message": f"查询到 {len(q_results)} 个属性"
                        }
                    }
                    debug_logs.append(f"[计算节点] {q_id}: 查询问题，返回 {len(q_results)} 个属性")
            
            else:
                # 计算问题：执行计算
                # 构建计算上下文（合并已知参数和查询结果）
                calc_context = known_params.copy()
                if q_id in query_results:
                    calc_context.update(query_results[q_id])
                
                # 辅助函数：获取参数单位（与param_meta.json保持一致）
                def get_unit(param_name):
                    unit_map = {
                        # 输入参数
                        "power": "W",
                        "voltage": "V",
                        "material": "",
                        "temperature": "℃",
                        "surface_load": "W/cm²",
                        "alloy_shape": "",
                        "application_scenario": "",
                        "thickness": "mm",
                        "width": "mm",
                        "aspect_ratio": "无量纲",
                        # 输出参数
                        "diameter": "mm",
                        "current": "A",
                        "resistance": "Ω",
                        "temperature_coeff": "无量纲",
                        "ct_value": "无量纲",
                        "surface_area": "cm²/Ω",
                        "resistance_per_meter": "Ω/m",
                        "weight_per_meter": "g/m",
                        "length": "m",
                        "weight": "g",
                        "specific_gravity": "g/cm³",
                        "resistivity": "10⁻⁶Ω·m",
                        "resistivity_at_temperature": "10⁻⁶Ω·m",
                        "surface_area_per_meter": "cm²/m",
                        "surface_area_per_ohm": "cm²/Ω",
                        "cross_section_area": "mm²",
                        # 合金带参数
                        "ripple_depth": "mm",
                        "ripple_pitch": "mm",
                        "curvature_radius": "mm",
                        "strip_length": "无量纲"
                    }
                    return unit_map.get(param_name, "")
                
                # 检查是否所有待求参数都已通过直接查询获得
                if calc_context.get('_direct_query'):
                    debug_logs.append(f"[计算节点] {q_id}: 所有参数已通过直接查询获得，跳过计算")
                    
                    # 构建查询结果（模拟计算结果格式）
                    results = {}
                    for target in target_params:
                        if target in calc_context:
                            results[target] = {
                                "success": True,
                                "result": calc_context[target],
                                "unit": get_unit(target),
                                "source": "database",
                                "calculation_chain": [{
                                    "step": f"数据库查询 {target}",
                                    "type": "query",
                                    "result": calc_context[target],
                                    "unit": get_unit(target)
                                }]
                            }
                    
                    # 如果只有一个target，简化结果
                    if len(target_params) == 1:
                        question_results[q_id] = {
                            "question": question,
                            "result": results[target_params[0]]
                        }
                    else:
                        question_results[q_id] = {
                            "question": question,
                            "result": {
                                "success": all(r.get("success") for r in results.values()),
                                "type": "multi_calculate",
                                "results": results
                            }
                        }
                    
                    debug_logs.append(f"[计算节点] {q_id}: 直接返回查询结果")
                    continue
                
                debug_logs.append(f"[计算节点] {q_id}: 计算上下文包含 {len(calc_context)} 个参数")
                
                # 对每个target执行计算
                results = {}
                calculated_params = {}  # 记录已计算的参数（用于 belt_dimensions 等特殊计算）
                
                for target in target_params:
                    # 如果已经通过查询获得，直接使用
                    if target in calc_context and target in query_results.get(q_id, {}):
                        debug_logs.append(f"[计算节点] {q_id}: {target} 已通过查询获得，跳过计算")
                        results[target] = {
                            "success": True,
                            "result": calc_context[target],
                            "unit": get_unit(target),
                            "source": "database",
                            "calculation_chain": [{
                                "step": f"数据库查询 {target}",
                                "type": "query",
                                "result": calc_context[target],
                                "unit": get_unit(target)
                            }]
                        }
                        continue
                    
                    # 如果已经通过之前的计算获得（如 belt_dimensions 同时计算 thickness 和 width）
                    if target in calculated_params:
                        debug_logs.append(f"[计算节点] {q_id}: {target} 已通过之前的计算获得")
                        results[target] = calculated_params[target]
                        continue
                    
                    debug_logs.append(f"[计算节点] {q_id}: 计算 {target}")
                    result = calculate_parameter(target, calc_context, query_callback)
                    results[target] = result
                    
                    if result.get("success"):
                        debug_logs.append(f"[计算节点] {q_id}: {target} = {result.get('result')} {result.get('unit', '')}")
                        
                        # 检查 param_pool 中是否有其他参数被同时计算（如 belt_dimensions）
                        param_pool = result.get("param_pool", {})
                        for other_target in target_params:
                            if other_target != target and other_target in param_pool and other_target not in results:
                                # 其他目标参数也被计算出来了
                                calculated_params[other_target] = {
                                    "success": True,
                                    "result": param_pool[other_target],
                                    "unit": get_unit(other_target),
                                    "source": "calculated",
                                    "calculation_chain": result.get("calculation_chain", []),
                                    "note": f"与 {target} 一起计算"
                                }
                                debug_logs.append(f"[计算节点] {q_id}: {other_target} = {param_pool[other_target]} {get_unit(other_target)} (与 {target} 一起计算)")
                    else:
                        debug_logs.append(f"[计算节点] {q_id}: {target} 计算失败: {result.get('error')}")
                
                # 如果只有一个target，简化结果
                if len(target_params) == 1:
                    question_results[q_id] = {
                        "question": question,
                        "result": results[target_params[0]]
                    }
                else:
                    question_results[q_id] = {
                        "question": question,
                        "result": {
                            "success": all(r.get("success") for r in results.values()),
                            "type": "multi_calculate",
                            "results": results
                        }
                    }
        
        # 统计计算结果
        success_count = sum(1 for q in question_results.values() if q.get("result", {}).get("success"))
        total_count = len(question_results)
        await _progress(f"✅ 计算完成（{success_count}/{total_count} 成功）", config)

        return {
            **state,
            "question_results": question_results,
            "debug_logs": debug_logs
        }

    except Exception as e:
        debug_logs.append(f"[计算节点] 错误: {str(e)}")
        import traceback
        debug_logs.append(f"[计算节点] 堆栈: {traceback.format_exc()}")
        return {
            **state,
            "question_results": {},
            "debug_logs": debug_logs
        }


async def answer_node(state: CalculateState, config) -> CalculateState:
    """
    回答节点 - 构建计算结果数据（不生成答案）

    负责将计算结果整理为主图 answer_node 需要的格式，
    实际的答案生成由主图的 answer_node 完成。

    如果is_irrelevant=True，返回错误提示，说明这不是计算问题
    """
    from langchain_core.callbacks.manager import adispatch_custom_event

    debug_logs = state.get("debug_logs", [])
    debug_logs.append("[回答节点] 构建计算结果数据")

    # 检查是否为无关问题
    if state.get("is_irrelevant"):
        debug_logs.append("[回答节点] 检测到无关问题，返回提示")
        # 发送提示消息
        await adispatch_custom_event(
            "progress",
            {"node": "answer", "message": "⚠️ 这不是计算或查询问题，请尝试其他模式"},
            config=config
        )
        return {
            **state,
            "context_data": {
                "error": "这不是合金材料计算或查询问题",
                "user_input": state["user_input"],
                "suggestion": "如果是问候或闲聊，请使用通用问答模式；如果是计算问题，请提供具体的计算参数"
            },
            "debug_logs": debug_logs
        }

    user_input = state["user_input"]
    question_results = state.get("question_results", {})
    query_results = state.get("query_results", {})

    try:
        # 构建 calculation_result 格式（与主图兼容）
        calculated_results = {}
        known_parameters = {}
        target_parameters = []
        used_defaults = {}
        missing_parameters = None
        merged_query_results = {}  # 修复：使用局部变量而非直接修改 state 的 query_results
        query_success = False
        has_error = False

        # 合并所有问题的结果
        for q_id, q_data in question_results.items():
            question = q_data.get("question", {})
            result = q_data.get("result", {})

            # 合并已知参数
            if question.get("known_parameters"):
                known_parameters.update(question["known_parameters"])

            # 合并查询结果（安全处理，确保是字典）
            if q_id in query_results:
                q_result = query_results[q_id]
                if isinstance(q_result, dict):
                    merged_query_results.update(q_result)
                    query_success = True
                else:
                    debug_logs.append(f"[回答节点] 警告: q_id={q_id} 的查询结果不是字典: {type(q_result)}")

            # 合并计算结果
            if result.get("success"):
                if result.get("type") == "query":
                    calculated_results.update(result.get("data", {}))
                elif result.get("type") == "multi_calculate":
                    for target, target_result in result.get("results", {}).items():
                        if target_result.get("success"):
                            calculated_results[target] = target_result.get("result")
                else:
                    target_params = question.get("target_parameters", [])
                    if target_params:
                        target_parameters.extend(target_params)
                        calculated_results[target_params[0]] = result.get("result")
            else:
                # 检查是否缺少参数
                if result.get("missing_params"):
                    missing_list = result.get("missing_params", [])
                    if missing_list:
                        # 将字典列表转换为参数名列表
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

                        # 拼接参数名列表
                        missing_str = ", ".join(missing_param_names)
                        if missing_parameters:
                            missing_parameters += ", " + missing_str
                        else:
                            missing_parameters = missing_str
                        has_error = True
                        debug_logs.append(f"[回答节点] 缺少必要参数: {missing_parameters}")

        # 如果缺少参数，标记为错误状态
        if has_error or missing_parameters:
            # 构建友好的错误消息
            if missing_parameters:
                error_msg = f"计算无法完成：缺少必要参数（{missing_parameters}）"
            else:
                error_msg = "计算无法完成：缺少必要的参数信息"

            debug_logs.append(f"[回答节点] {error_msg}")

            # 发送错误事件
            await adispatch_custom_event(
                "error",
                {"node": "calculate", "message": error_msg},
                config=config
            )

            # 返回带错误信息的 calculation_result
            calculation_result = {
                "known_parameters": known_parameters,
                "calculated_results": {},  # 空结果
                "target_parameters": target_parameters,
                "used_defaults": used_defaults,
                "missing_parameters": missing_parameters,
                "query_results": merged_query_results,
                "query_success": query_success,
                "error": error_msg,  # 明确标记错误
                "debug_logs": debug_logs,
                # 额外字段（保留详细信息）
                "questions": state.get("questions", []),
                "question_results": question_results,
                "context_data": state.get("context_data")
            }

            return {
                **state,
                "calculation_result": calculation_result,
                "debug_logs": debug_logs
            }

        # 构建符合主图格式的 calculation_result
        calculation_result = {
            "known_parameters": known_parameters,
            "calculated_results": calculated_results,
            "target_parameters": target_parameters,
            "used_defaults": used_defaults,
            "missing_parameters": missing_parameters,
            "query_results": merged_query_results,
            "query_success": query_success,
            "debug_logs": debug_logs,
            # 额外字段（保留详细信息）
            "questions": state.get("questions", []),
            "question_results": question_results,
            "context_data": state.get("context_data")
        }

        debug_logs.append(f"[回答节点] 计算结果构建完成: {len(calculated_results)} 个结果")

        # 将结果保存到 state 中，供主图的 answer_node 使用
        # 注意：这里不发送 thinking/title/output 事件，由主图的 answer_node 发送
        return {
            **state,
            "calculation_result": calculation_result,
            "debug_logs": debug_logs
        }

    except Exception as e:
        import traceback
        # 构建计算结果失败（系统级错误）
        error_str = str(e)
        error_msg = f"构建计算结果失败: {error_str}"

        debug_logs.append(f"[回答节点] 错误: {error_msg}")
        debug_logs.append(f"[回答节点] 堆栈: {traceback.format_exc()}")

        # 发送错误事件（保留原始错误信息）
        await adispatch_custom_event(
            "error",
            {"node": "calculate", "message": error_msg},
            config=config
        )

        # 返回包含完整错误信息的 calculation_result
        return {
            **state,
            "calculation_result": {
                "error": error_msg,
                "debug_logs": debug_logs
            },
            "debug_logs": debug_logs
        }
