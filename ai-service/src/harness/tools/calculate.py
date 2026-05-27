"""
计算工具

包装 calculate subgraph，提供 BaseTool 接口。
"""
import logging
from typing import Any, Dict

from .base import BaseTool

logger = logging.getLogger(__name__)


class CalculateTool(BaseTool):
    """合金材料参数计算工具"""

    name = "calculate"
    description = "执行合金材料的参数计算与查询"
    group = "calculate"

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "calculate",
                "description": (
                    "执行合金材料的参数计算与查询。"
                    "支持电阻、功率、电流、尺寸（直径/厚度/宽度）、表面负荷等参数的计算。"
                    "也能查询合金的基础物性（比重、电阻率、温度系数等）。"
                    "当用户问题涉及合金材料数值计算、参数查询时使用此工具。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "user_input": {
                            "type": "string",
                            "description": "用户的原始计算问题描述，保持完整语义",
                        },
                    },
                    "required": ["user_input"],
                },
            },
        }

    async def execute(self, user_input: str, config=None, **kwargs) -> str:
        """
        执行计算。

        Args:
            user_input: 用户原始计算问题描述
            config: LangGraph config
        """
        from src.harness.subgraphs.calculate.subgraph import invoke_calculation_mcp_subgraph

        try:
            result = await invoke_calculation_mcp_subgraph(user_input, config=config)

            if result.get("error"):
                return f"计算失败：{result['error']}"

            parts = []

            # 1. 已知参数
            known = result.get("known_parameters", {})
            if known:
                parts.append("## 已知参数")
                for k, v in known.items():
                    parts.append(f"- {k}: {v}")

            # 2. 每个问题的详细过程和结果
            question_results = result.get("question_results", {})
            calculated = result.get("calculated_results", {})

            for q_id, q_data in question_results.items():
                question = q_data.get("question", {})
                desc = question.get("description", q_id)
                target_params = question.get("target_parameters", [])
                res = q_data.get("result", {})

                parts.append(f"\n## {desc}")

                if res.get("type") == "multi_calculate":
                    results_map = res.get("results", {})
                else:
                    results_map = {target_params[0]: res} if target_params else {"result": res}

                for target, target_res in results_map.items():
                    if not isinstance(target_res, dict):
                        continue

                    chain = target_res.get("calculation_chain", [])
                    if chain:
                        parts.append(f"\n### 计算 {target}")
                        for i, step in enumerate(chain, 1):
                            step_type = step.get("type", "")
                            if step_type == "query":
                                parts.append(
                                    f"{i}. 查询 {step.get('step', '')}"
                                    f" → {step.get('result', '')} {step.get('unit', '')}"
                                )
                            elif step_type == "calculation":
                                formula = step.get("formula", "")
                                parts.append(
                                    f"{i}. 计算: {step.get('step', '')}"
                                    f"（公式: {formula}）"
                                    f" → {step.get('result', '')} {step.get('unit', '')}"
                                )
                            else:
                                parts.append(f"{i}. {step.get('step', '')}")

            # 3. 汇总最终结果
            if calculated:
                parts.append("\n## 最终结果")
                for k, v in calculated.items():
                    parts.append(f"- **{k}**: {v}")
            else:
                parts.append("\n计算完成，但未得到有效结果。")

            missing = result.get("missing_parameters")
            if missing:
                parts.append(f"\n缺少参数：{missing}")

            return "\n".join(parts)

        except Exception as e:
            logger.error(f"[calculate] Execute error: {e}")
            return f"计算服务异常：{str(e)}"
