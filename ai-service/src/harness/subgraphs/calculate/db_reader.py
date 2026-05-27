# -*- coding: utf-8 -*-
"""
数据库读取模块 - calculate_mcp 专用版本
"""
import pandas as pd
import sys
import io
import os
from typing import Optional, Dict, Any
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# 导入配置（从 __init__.py）
from . import DB_CONFIG

# 禁用输出缓冲
os.environ['PYTHONUNBUFFERED'] = '1'

# 修复 Windows 控制台编码问题
# 使用 reconfigure 原地修改编码，避免 io.TextIOWrapper 接管 buffer 导致原 stdout 被 GC 关闭
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
    except AttributeError:
        pass  # Python < 3.7 不支持 reconfigure，跳过

# 重写print函数，强制flush
_original_print = print
def print(*args, **kwargs):
    kwargs.setdefault('flush', True)
    _original_print(*args, **kwargs)

# 数据库连接初始化
db_url = f"mysql+pymysql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG.get('port', 3306)}/{DB_CONFIG['database']}?charset=utf8mb4"
engine = create_engine(
    db_url,
    pool_size=5,
    max_overflow=10,
    pool_recycle=3600
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    """获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ==================== 基础查询函数 ====================

def get_code(alloy_name: str, alloy_shape: str) -> Optional[int]:
    """
    从 hejincode 表获取合金代码

    Args:
        alloy_name: 合金名称，如 "Cr20Ni80"
        alloy_shape: 合金形状，如 "合金丝"、"扁丝"、"扁带"

    Returns:
        code: 合金代码，如果未找到返回 None
    """
    # 检查必需参数
    if not alloy_name:
        print(f"[DB查询] 获取code失败: alloy_name为空")
        return None

    if not alloy_shape:
        print(f"[DB查询] 获取code失败: alloy_shape为空")
        return None

    with next(get_db()) as db:
        sql = text("SELECT code FROM hejincode WHERE alloy_name=:alloy_name AND type=:alloy_shape LIMIT 1")
        print(f"[DB查询] 获取code: alloy_name={alloy_name}, alloy_shape={alloy_shape}")
        result = db.execute(sql, {"alloy_name": alloy_name, "alloy_shape": alloy_shape})
        row = result.fetchone()
        code = int(row.code) if row else None
        print(f"[DB结果] code={code}")
        return code


def get_data_by_code(code: int) -> Optional[pd.DataFrame]:
    """
    从 data 表获取指定 code 的所有数据

    Args:
        code: 合金代码

    Returns:
        DataFrame: 包含该合金所有规格的数据
    """
    with next(get_db()) as db:
        sql = text("SELECT * FROM data WHERE code=:code")
        print(f"[DB查询] 获取data表数据: code={code}")
        df = pd.read_sql(sql, db.bind, params={"code": code})
        print(f"[DB结果] 查询到 {len(df)} 条数据")
        return df if not df.empty else None


def get_base_data(alloy_name: str) -> Optional[Dict[str, Any]]:
    """
    从 basedata 表获取合金基础数据

    Args:
        alloy_name: 合金名称

    Returns:
        dict: 包含 name, 比重, 电阻率
    """
    # 检查必需参数
    if not alloy_name:
        print(f"[DB查询] 获取basedata失败: alloy_name为空")
        return None

    with next(get_db()) as db:
        sql = text("SELECT name, 比重, 电阻率 FROM basedata WHERE name=:alloy_name LIMIT 1")
        print(f"[DB查询] 获取basedata: alloy_name={alloy_name}")
        result = db.execute(sql, {"alloy_name": alloy_name})
        row = result.fetchone()
        if row:
            data = {
                "name": row[0],
                "比重": float(row[1]) if row[1] is not None else None,
                "电阻率": float(row[2]) if row[2] is not None else None
            }
            print(f"[DB结果] basedata={data}")
            return data
        print(f"[DB结果] 未找到basedata")
        return None


def get_ct_value(alloy_name: str, temperature: float) -> float:
    """
    从 ctvalue 表获取温度系数

    Args:
        alloy_name: 合金名称
        temperature: 温度（℃）

    Returns:
        Ct值: 温度系数，未找到或参数缺失返回 1.0
    """
    # 检查必需参数
    if not alloy_name:
        print(f"[DB查询] 获取Ct值失败: alloy_name为空")
        return 1.0

    if temperature is None:
        print(f"[DB查询] 获取Ct值失败: temperature为空")
        return 1.0

    with next(get_db()) as db:
        # 查找最接近的温度
        sql = text("""
            SELECT `Ct 值`, ABS(`温度（℃）` - :temp) as diff
            FROM ctvalue
            WHERE 合金名称=:alloy_name
            ORDER BY diff ASC
            LIMIT 1
        """)
        print(f"[DB查询] 获取Ct值: alloy_name={alloy_name}, temperature={temperature}")
        result = db.execute(sql, {"alloy_name": alloy_name, "temp": temperature})
        row = result.fetchone()
        ct_value = float(row[0]) if row else 1.0
        print(f"[DB结果] Ct值={ct_value}")
        return ct_value


# ==================== 数据库字段获取函数（仅查询） ====================

def get_specific_gravity(alloy_name: str) -> Optional[float]:
    """
    获取比重（g/cm³）- 仅从数据库查询

    数据库字段: basedata.比重
    """
    print(f"[get_specific_gravity] 查询材料: {alloy_name}")
    base_data = get_base_data(alloy_name)
    if base_data:
        print(f"[get_specific_gravity] 找到basedata: {base_data}")
        if base_data["比重"] is not None:
            print(f"[get_specific_gravity] 返回比重: {base_data['比重']}")
            return base_data["比重"]
        else:
            print(f"[get_specific_gravity] 比重字段为空")
    else:
        print(f"[get_specific_gravity] 未找到basedata")
    return None


def get_resistivity(alloy_name: str) -> Optional[float]:
    """
    获取电阻率（10⁻⁶Ω·m）- 仅从数据库查询

    数据库字段: basedata.电阻率
    """
    base_data = get_base_data(alloy_name)
    if base_data and base_data["电阻率"] is not None:
        print(f"[DB] 从basedata获取电阻率: {base_data['电阻率']}")
        return base_data["电阻率"]
    return None


def _get_spec_field(alloy_name: str, alloy_shape: str, field_name: str,
                    diameter: float = None, thickness: float = None,
                    width: float = None) -> Optional[float]:
    """
    通用的规格字段查询函数 - 统一处理所有字段查询

    Args:
        alloy_name: 合金名称
        alloy_shape: 合金形状
        field_name: 数据库字段名
        diameter: 直径（mm），用于合金丝
        thickness: 厚度（mm），用于合金带
        width: 宽度（mm），用于合金带

    Returns:
        字段值，未找到返回 None
    """
    code = get_code(alloy_name, alloy_shape)
    if not code:
        return None

    df = get_data_by_code(code)
    if df is None or df.empty or field_name not in df.columns:
        return None

    # 合金丝：根据直径查找
    if diameter is not None:
        df_filtered = df[df["直径   mm"].notna()]
        for idx, row in df_filtered.iterrows():
            try:
                db_diameter = float(str(row["直径   mm"]).strip())
                if abs(db_diameter - diameter) < 0.01:
                    value = row.get(field_name)
                    return float(value) if value is not None else None
            except:
                continue

    # 合金带：根据厚度和宽度查找
    elif thickness is not None and width is not None:
        df_filtered = df[df["厚×宽mm"].notna()]
        for idx, row in df_filtered.iterrows():
            spec = str(row["厚×宽mm"])
            if "*" in spec:
                try:
                    t, w = spec.split("*")
                    if abs(float(t) - thickness) < 0.01 and abs(float(w) - width) < 0.01:
                        value = row.get(field_name)
                        return float(value) if value is not None else None
                except:
                    continue

    return None


def get_resistance_per_meter(alloy_name: str, alloy_shape: str, diameter: float = None,
                             thickness: float = None, width: float = None) -> Optional[float]:
    """
    获取每米电阻（Ω/m）- 仅从数据库查询

    数据库字段: data.每米电阻（20℃）Ω/m
    """
    return _get_spec_field(alloy_name, alloy_shape, "每米电阻（20℃）Ω/m",
                          diameter, thickness, width)


def get_weight_per_meter(alloy_name: str, alloy_shape: str, diameter: float = None,
                         thickness: float = None, width: float = None) -> Optional[float]:
    """
    获取每米重量（g/m）- 仅从数据库查询

    数据库字段: data.每米重量g/m
    """
    return _get_spec_field(alloy_name, alloy_shape, "每米重量g/m",
                          diameter, thickness, width)


def get_surface_area_per_ohm(alloy_name: str, alloy_shape: str, diameter: float = None,
                             thickness: float = None, width: float = None) -> Optional[float]:
    """
    获取每欧表面积（cm²/Ω）- 仅从数据库查询

    数据库字段: data.每欧表面积（20℃）cm2/Ω
    """
    return _get_spec_field(alloy_name, alloy_shape, "每欧表面积（20℃）cm2/Ω",
                          diameter, thickness, width)


def get_surface_area_per_meter(alloy_name: str, alloy_shape: str, diameter: float = None,
                               thickness: float = None, width: float = None) -> Optional[float]:
    """
    获取每米表面积（cm²/m）- 仅从数据库查询

    数据库字段: data.每米表面积cm2/m
    """
    return _get_spec_field(alloy_name, alloy_shape, "每米表面积cm2/m",
                          diameter, thickness, width)


def get_cross_section_area(alloy_name: str, alloy_shape: str, diameter: float = None,
                           thickness: float = None, width: float = None) -> Optional[float]:
    """
    获取截面积（mm²）- 仅从数据库查询

    数据库字段: data.截面积mm²
    """
    return _get_spec_field(alloy_name, alloy_shape, "截面积mm²",
                          diameter, thickness, width)


# ==================== 高级查询函数 ====================

def find_spec_by_surface_area(alloy_name: str, target_surface_area: float,
                              alloy_shape: str, tolerance: float = 0.1) -> Optional[Dict[str, Any]]:
    """
    根据目标表面积查找最接近的规格

    Args:
        alloy_name: 合金名称
        target_surface_area: 目标表面积（cm²/Ω）
        alloy_shape: 合金形状
        tolerance: 容差（未使用，保留兼容性）

    Returns:
        dict: 包含规格信息的字典
    """
    code = get_code(alloy_name, alloy_shape)
    if not code:
        print(f"[DB错误] 未找到code")
        return None

    df = get_data_by_code(code)
    if df is None or df.empty:
        print(f"[DB错误] 未找到data数据")
        return None

    if "每欧表面积（20℃）cm2/Ω" not in df.columns:
        print(f"[DB错误] 缺少'每欧表面积（20℃）cm2/Ω'列")
        return None

    # 过滤有效数据
    df = df.dropna(subset=["每欧表面积（20℃）cm2/Ω"])
    if df.empty:
        print(f"[DB错误] 过滤后数据为空")
        return None

    # 计算差值并找到最接近的
    df["diff"] = (df["每欧表面积（20℃）cm2/Ω"] - target_surface_area).abs()
    row = df.loc[df["diff"].idxmin()]

    print(f"[DB] 找到最接近的表面积: {row['每欧表面积（20℃）cm2/Ω']}, 差值: {row['diff']}")

    # 提取直径
    diameter = None
    if pd.notna(row.get("直径   mm")):
        try:
            diameter = float(str(row["直径   mm"]).strip())
        except:
            pass

    return {
        "Resistance_per_meter": row.get("每米电阻（20℃）Ω/m"),
        "diameter": diameter,
        "G_per_meter": row.get("每米重量g/m"),
        "surface_area_per_ohm": row["每欧表面积（20℃）cm2/Ω"],
        "diff": row["diff"]
    }


def find_standard_spec(alloy_name: str, thickness: float, width: float,
                      alloy_shape: str) -> Dict[str, bool]:
    """
    检查是否存在标准规格（全局函数）

    Args:
        alloy_name: 合金名称
        thickness: 厚度（mm）
        width: 宽度（mm）
        alloy_shape: 合金形状

    Returns:
        dict: {"found": True/False}
    """
    code = get_code(alloy_name, alloy_shape)
    if not code:
        return {"found": False}

    df = get_data_by_code(code)
    if df is None or "厚×宽mm" not in df.columns:
        return {"found": False}

    # 解析厚×宽格式
    for idx, row in df.iterrows():
        spec = str(row["厚×宽mm"])
        if "*" in spec:
            try:
                t, w = spec.split("*")
                if abs(float(t) - thickness) < 0.01 and abs(float(w) - width) < 0.01:
                    return {"found": True}
            except:
                continue

    return {"found": False}


# ==================== 查询服务（为计算引擎提供统一接口）====================

class QueryService:
    """查询服务类 - 为计算引擎提供数据查询接口

    职责：
    1. 为 calc_engine 提供统一的查询接口
    2. 支持查询失败时的降级计算（使用公式计算）
    3. 封装数据库访问细节，使 calc_engine 保持独立

    使用场景：
    - 只在计算节点中使用
    - 作为 calc_engine.calculate_parameter 的 query_callback 参数
    """

    @staticmethod
    def query_specific_gravity(material: str) -> Dict[str, Any]:
        """查询材料比重"""
        if not material:
            return {
                "success": False,
                "error": "材料名称不能为空",
                "missing_params": ["material"]
            }

        try:
            result = get_specific_gravity(material)
            if result is None:
                return {
                    "success": False,
                    "error": f"未找到材料 '{material}' 的比重数据",
                    "query_type": "specific_gravity",
                    "params": {"material": material}
                }

            return {
                "success": True,
                "value": result,
                "unit": "g/cm³",
                "source": "database"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"查询失败: {str(e)}",
                "query_type": "specific_gravity"
            }

    @staticmethod
    def query_resistivity(material: str) -> Dict[str, Any]:
        """查询材料电阻率（20℃）"""
        if not material:
            return {
                "success": False,
                "error": "材料名称不能为空",
                "missing_params": ["material"]
            }

        try:
            result = get_resistivity(material)
            if result is None:
                return {
                    "success": False,
                    "error": f"未找到材料 '{material}' 的电阻率数据",
                    "query_type": "resistivity",
                    "params": {"material": material}
                }

            return {
                "success": True,
                "value": result,
                "unit": "10⁻⁶Ω·m",
                "source": "database"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"查询失败: {str(e)}",
                "query_type": "resistivity"
            }

    @staticmethod
    def query_temperature_coefficient(material: str, temperature: float) -> Dict[str, Any]:
        """查询温度系数Ct"""
        if not material:
            return {
                "success": False,
                "error": "材料名称不能为空",
                "missing_params": ["material"]
            }

        if temperature is None:
            return {
                "success": False,
                "error": "温度不能为空",
                "missing_params": ["temperature"]
            }

        try:
            result = get_ct_value(material, temperature)
            return {
                "success": True,
                "value": result,
                "unit": "无量纲",
                "source": "database" if result != 1.0 else "default",
                "is_default": result == 1.0,
                "message": f"⚠️ 数据库中未找到 {material} 在 {temperature}℃ 的温度系数数据，使用默认值1.0" if result == 1.0 else None
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"查询失败: {str(e)}",
                "query_type": "ct_value"
            }

    @staticmethod
    def query_resistance_per_meter(
        material: str,
        diameter: float,
        alloy_shape: str = "合金丝",
        fallback_to_calculation: bool = True,
        resistivity: Optional[float] = None
    ) -> Dict[str, Any]:
        """查询每米电阻，支持降级到公式计算"""
        if not material:
            return {
                "success": False,
                "error": "材料名称不能为空",
                "missing_params": ["material"]
            }

        if diameter is None:
            return {
                "success": False,
                "error": "直径不能为空",
                "missing_params": ["diameter"]
            }

        try:
            # 先尝试从数据库查询
            result = get_resistance_per_meter(material, alloy_shape, diameter=diameter)

            if result is not None:
                return {
                    "success": True,
                    "value": result,
                    "unit": "Ω/m",
                    "source": "database"
                }

            # 查询失败，尝试降级到公式计算
            if fallback_to_calculation:
                # 如果没有提供电阻率，先查询
                if resistivity is None:
                    resistivity_result = QueryService.query_resistivity(material)
                    if not resistivity_result["success"]:
                        return {
                            "success": False,
                            "error": f"数据库无规格数据，且无法获取电阻率进行计算: {resistivity_result['error']}",
                            "query_type": "resistance_per_meter",
                            "params": {"material": material, "diameter": diameter, "alloy_shape": alloy_shape}
                        }
                    resistivity = resistivity_result["value"]

                # 使用公式计算: Rm = ρ × 4 / (π × d²)
                calculated_value = (resistivity * 4) / (3.14 * (diameter ** 2))

                return {
                    "success": True,
                    "value": round(calculated_value, 6),
                    "unit": "Ω/m",
                    "source": "calculated",
                    "fallback": True,
                    "fallback_reason": "数据库无规格数据",
                    "formula": "Rm = ρ × 4 / (π × d²)",
                    "calculation_details": {
                        "resistivity": resistivity,
                        "diameter": diameter,
                        "formula_used": "Rm = ρ × 4 / (π × d²)"
                    },
                    "message": f"⚠️ 数据库中未找到 {material} 直径{diameter}mm 的规格数据，已使用公式计算"
                }
            else:
                return {
                    "success": False,
                    "error": f"未找到规格数据: 材料={material}, 直径={diameter}mm, 形状={alloy_shape}",
                    "query_type": "resistance_per_meter",
                    "params": {"material": material, "diameter": diameter, "alloy_shape": alloy_shape}
                }

        except Exception as e:
            return {
                "success": False,
                "error": f"查询失败: {str(e)}",
                "query_type": "resistance_per_meter"
            }

    @staticmethod
    def query_weight_per_meter(
        material: str,
        diameter: float,
        alloy_shape: str = "合金丝",
        fallback_to_calculation: bool = True,
        specific_gravity: Optional[float] = None
    ) -> Dict[str, Any]:
        """查询每米重量，支持降级到公式计算"""
        if not material:
            return {
                "success": False,
                "error": "材料名称不能为空",
                "missing_params": ["material"]
            }

        if diameter is None:
            return {
                "success": False,
                "error": "直径不能为空",
                "missing_params": ["diameter"]
            }

        try:
            # 先尝试从数据库查询
            result = get_weight_per_meter(material, alloy_shape, diameter=diameter)

            if result is not None:
                return {
                    "success": True,
                    "value": result,
                    "unit": "g/m",
                    "source": "database"
                }

            # 查询失败，尝试降级到公式计算
            if fallback_to_calculation:
                # 如果没有提供比重，先查询
                if specific_gravity is None:
                    sg_result = QueryService.query_specific_gravity(material)
                    if not sg_result["success"]:
                        return {
                            "success": False,
                            "error": f"数据库无规格数据，且无法获取比重进行计算: {sg_result['error']}",
                            "query_type": "weight_per_meter",
                            "params": {"material": material, "diameter": diameter, "alloy_shape": alloy_shape}
                        }
                    specific_gravity = sg_result["value"]

                # 使用公式计算: Gm = (π × d² / 4) × ρg
                calculated_value = (3.14 * (diameter ** 2) / 4) * specific_gravity

                return {
                    "success": True,
                    "value": round(calculated_value, 3),
                    "unit": "g/m",
                    "source": "calculated",
                    "fallback": True,
                    "fallback_reason": "数据库无规格数据",
                    "formula": "Gm = (π × d² / 4) × ρg",
                    "calculation_details": {
                        "specific_gravity": specific_gravity,
                        "diameter": diameter,
                        "formula_used": "Gm = (π × d² / 4) × ρg"
                    },
                    "message": f"⚠️ 数据库中未找到 {material} 直径{diameter}mm 的规格数据，已使用公式计算"
                }
            else:
                return {
                    "success": False,
                    "error": f"未找到规格数据: 材料={material}, 直径={diameter}mm, 形状={alloy_shape}",
                    "query_type": "weight_per_meter",
                    "params": {"material": material, "diameter": diameter, "alloy_shape": alloy_shape}
                }

        except Exception as e:
            return {
                "success": False,
                "error": f"查询失败: {str(e)}",
                "query_type": "weight_per_meter"
            }

    @staticmethod
    def find_diameter_by_surface_area(
        material: str,
        surface_area: float,
        alloy_shape: str = "合金丝"
    ) -> Dict[str, Any]:
        """根据表面积查找匹配的直径"""
        if not material:
            return {
                "success": False,
                "error": "材料名称不能为空",
                "missing_params": ["material"]
            }

        if surface_area is None:
            return {
                "success": False,
                "error": "表面积不能为空",
                "missing_params": ["surface_area"]
            }

        try:
            result = find_spec_by_surface_area(material, surface_area, alloy_shape)

            if not result or result.get("diameter") is None:
                return {
                    "success": False,
                    "error": f"未找到匹配的规格: 材料={material}, 表面积={surface_area}cm²/Ω, 形状={alloy_shape}",
                    "query_type": "find_diameter",
                    "params": {"material": material, "surface_area": surface_area, "alloy_shape": alloy_shape}
                }

            return {
                "success": True,
                "value": result["diameter"],
                "unit": "mm",
                "source": "database",
                "extra_data": {
                    "resistance_per_meter": result.get("Resistance_per_meter"),
                    "weight_per_meter": result.get("G_per_meter"),
                    "surface_area_per_ohm": result.get("surface_area_per_ohm")
                }
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"查询失败: {str(e)}",
                "query_type": "find_diameter"
            }

    @staticmethod
    def find_standard_spec(
        material: str,
        thickness: float,
        width: float,
        alloy_shape: str = "扁带"
    ) -> Dict[str, Any]:
        """检查是否存在标准规格"""
        if not material:
            return {
                "success": False,
                "error": "材料名称不能为空",
                "missing_params": ["material"]
            }

        if thickness is None or width is None:
            return {
                "success": False,
                "error": "厚度和宽度不能为空",
                "missing_params": ["thickness", "width"]
            }

        try:
            result = find_standard_spec(material, thickness, width, alloy_shape)

            return {
                "success": True,
                "found": result.get("found", False),
                "source": "database"
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"查询失败: {str(e)}",
                "query_type": "find_standard_spec"
            }


# 创建全局实例
query_service = QueryService()
