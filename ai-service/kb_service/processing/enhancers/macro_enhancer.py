"""
宏观管理字段增强器 - 为文档块添加部门、分类等宏观管理字段
"""
from typing import List, Dict
from datetime import datetime, timedelta


class MacroEnhancer:
    """
    宏观管理字段增强器

    为文档块添加：
    - department: 部门
    - category_l1: 一级分类
    - category_l2: 二级分类
    - upload_time: 上传时间
    - update_time: 更新时间
    """

    @staticmethod
    def enhance(
        chunks: List[Dict],
        department: str = None,
        category_l1: int = None,
        category_l2: int = None
    ) -> List[Dict]:
        """
        为文档块列表添加宏观管理字段

        Args:
            chunks: 文档块列表
            department: 部门
            category_l1: 一级分类ID
            category_l2: 二级分类ID

        Returns:
            List[Dict]: 添加了宏观管理字段的文档块列表
        """
        if not chunks:
            return []

        print(f"[MacroEnhancer] Adding macro fields to {len(chunks)} chunks")
        print(f"[MacroEnhancer] department={department}, category_l1={category_l1}, category_l2={category_l2}")

        # 北京时间（UTC+8），去掉微秒
        current_time = (datetime.utcnow() + timedelta(hours=8)).strftime("%Y-%m-%dT%H:%M:%S")

        enhanced_chunks = []
        for idx, chunk in enumerate(chunks):
            enhanced_chunk = chunk.copy()

            # 确保 metadata 存在
            if "metadata" not in enhanced_chunk:
                enhanced_chunk["metadata"] = {}

            # 调试：检查 file_name
            if idx == 0:
                print(f"[MacroEnhancer] First chunk metadata before enhance: {list(enhanced_chunk.get('metadata', {}).keys())}")
                print(f"[MacroEnhancer] file_name in metadata: {enhanced_chunk.get('metadata', {}).get('file_name')}")

            # 添加宏观管理字段
            enhanced_chunk["metadata"]["department"] = department
            enhanced_chunk["metadata"]["category_l1"] = category_l1
            enhanced_chunk["metadata"]["category_l2"] = category_l2
            enhanced_chunk["metadata"]["upload_time"] = current_time
            enhanced_chunk["metadata"]["update_time"] = current_time

            # 调试：验证 file_name 仍然存在
            if idx == 0:
                print(f"[MacroEnhancer] First chunk metadata after enhance: {list(enhanced_chunk.get('metadata', {}).keys())}")
                print(f"[MacroEnhancer] file_name after enhance: {enhanced_chunk.get('metadata', {}).get('file_name')}")

            enhanced_chunks.append(enhanced_chunk)

        print(f"[MacroEnhancer] Complete")
        return enhanced_chunks
