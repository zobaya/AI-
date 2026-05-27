""" (ES) 只管增、删 """
from elasticsearch import Elasticsearch
from core.config import settings
from typing import List, Dict, Optional
import json
from datetime import datetime, timedelta
import time
import os

# 索引初始化状态缓存（避免重复检查）
_index_init_cache = set()


class ESStore:
    """Elasticsearch 存储客户端"""

    def __init__(self, index_name: str, ensure_index: bool = True):
        """
        初始化 Elasticsearch 客户端

        Args:
            index_name: 要使用的索引名称
            ensure_index: 是否自动检查/创建索引（默认 True，设为 False 可延迟初始化）
        """
        # 解析ES URL
        if settings.ES_USERNAME and settings.ES_PASSWORD:
            # 使用 basic_auth 时，hosts 只包含主机地址，不包含认证信息
            es_config = {
                "hosts": [f"http://{settings.ES_HOST}:{settings.ES_PORT}"],
                "basic_auth": (settings.ES_USERNAME, settings.ES_PASSWORD),
                "request_timeout": 30,
                "verify_certs": False,
                "ssl_show_warn": False,
            }
        else:
            es_config = {
                "hosts": [f"http://{settings.ES_HOST}:{settings.ES_PORT}"],
                "request_timeout": 30,
                "verify_certs": False,
                "ssl_show_warn": False,
            }

        self.client = Elasticsearch(**es_config)
        self.index_name = index_name

        # 只在需要时初始化索引（避免 reload 模式下的重复检查）
        if ensure_index:
            self._ensure_index()

    def _check_ik_plugin(self) -> bool:
        """检测 ES 是否安装了 IK 分词插件"""
        try:
            # 通过创建临时索引测试 IK 分词器是否可用
            test_index = f".ik_test_{int(time.time())}"
            test_mapping = {
                "settings": {
                    "analysis": {
                        "analyzer": {
                            "ik_test": {
                                "type": "custom",
                                "tokenizer": "ik_smart",
                                "filter": ["lowercase"]
                            }
                        }
                    }
                }
            }
            try:
                self.client.indices.create(index=test_index, body=test_mapping)
                self.client.indices.delete(index=test_index)
                return True
            except Exception:
                return False
        except Exception:
            return False

    def _get_index_mapping(self) -> Dict:
        """
        获取 ES 索引的 v2 版本 mapping 配置

        v2 结构特点：
        - 搜索字段在根级（content, headers, content_vector）
        - 元数据字段嵌套在 metadata 对象中
        - 不包含 modality、chunk_tags 字段（已废弃）
        - 支持父子分块（parent_id, chunk_level）
        - 自动检测 IK 分词插件，有则用 ik_max_word/ik_smart，无则用标准分词器
        """
        has_ik = self._check_ik_plugin()

        if has_ik:
            settings_section = {
                "analysis": {
                    "analyzer": {
                        "index_chinese_analyzer": {
                            "type": "custom",
                            "tokenizer": "ik_max_word",
                            "filter": ["lowercase"]
                        },
                        "search_chinese_analyzer": {
                            "type": "custom",
                            "tokenizer": "ik_smart",
                            "filter": ["lowercase"]
                        }
                    }
                }
            }
            content_field = {
                "type": "text",
                "analyzer": "index_chinese_analyzer",
                "search_analyzer": "search_chinese_analyzer"
            }
            headers_field = {
                "type": "text",
                "analyzer": "index_chinese_analyzer",
                "search_analyzer": "search_chinese_analyzer",
                "fields": {
                    "keyword": {"type": "keyword", "ignore_above": 256}
                }
            }
        else:
            settings_section = {}
            content_field = {"type": "text"}
            headers_field = {
                "type": "text",
                "fields": {
                    "keyword": {"type": "keyword", "ignore_above": 256}
                }
            }

        return {
            "settings": settings_section,
            "mappings": {
                "properties": {
                    # ================= 1. 核心检索大类 =================
                    "content": content_field,
                    "headers": headers_field,
                    "content_vector": {
                        "type": "dense_vector",
                        "dims": 1024,
                        "index": True,
                        "similarity": "cosine"
                    },

                    # ================= 2. 统一收口的所有元数据 =================
                    "metadata": {
                        "properties": {
                            # --- 文档级字段（同一文档的所有分块相同） ---
                            "doc_id": {"type": "keyword"},
                            "kb_id": {"type": "keyword"},
                            "file_name": {"type": "keyword"},
                            "department": {"type": "keyword"},
                            "category_l1": {"type": "integer"},
                            "category_l2": {"type": "integer"},

                            # --- 身份与层级 ---
                            "chunk_id": {"type": "keyword"},
                            "parent_id": {"type": "keyword"},
                            "chunk_level": {"type": "integer"},

                            # --- 大模型上下文辅助 ---
                            "chunk_length": {"type": "integer"},

                            # --- 状态字段 ---
                            "is_active": {"type": "boolean"},
                            "upload_time": {"type": "date"},
                            "update_time": {"type": "date"},
                            "delete_time": {"type": "date"}
                        }
                    }
                }
            }
        }

    def _ensure_index(self):
        """确保当前索引存在且映射正确"""
        # 使用缓存避免重复检查（特别是在 reload 模式下）
        global _index_init_cache
        if self.index_name in _index_init_cache:
            return

        try:
            # 使用超时参数检查索引是否存在
            if not self.client.indices.exists(index=self.index_name, request_timeout=5):
                # 创建索引的映射（使用 v2 mapping）
                index_config = self._get_index_mapping()
                print(f"[ES] 使用 v2 mapping 创建索引: {self.index_name}")

                # ES 8.x 使用 body 参数
                try:
                    self.client.indices.create(index=self.index_name, body=index_config, request_timeout=10)
                except TypeError:
                    # 如果 body 参数不支持，尝试直接传参
                    self.client.indices.create(index=self.index_name, **index_config, request_timeout=10)
                print(f"[ES] 索引创建成功: {self.index_name}")
            else:
                # 索引已存在，检查映射是否正确
                self._check_and_fix_mapping()
                if os.environ.get("UVICORN_WORKER_ID") is None:  # 只在主进程中打印
                    print(f"[ES] 索引已存在: {self.index_name}")

            # 标记为已初始化
            _index_init_cache.add(self.index_name)
        except Exception as e:
            # 即使 ES 连接失败，也允许服务启动
            print(f"[WARNING] ES 索引检查失败，服务继续运行: {e}")
            pass

    def _check_and_fix_mapping(self):
        """检查索引映射是否正确，如果不正确则通过重建索引修复"""
        try:
            mapping_response = self.client.indices.get_mapping(index=self.index_name)
            index_key = list(mapping_response.keys())[0]
            properties = mapping_response[index_key]["mappings"]["properties"]
            metadata_props = properties.get("metadata", {}).get("properties", {})

            need_reindex = False

            # 检查 keyword 字段是否被错误映射为 text 类型
            keyword_fields = [
                "kb_id", "doc_id", "chunk_id", "parent_id", "file_name", "department",
            ]
            wrong_text_fields = []
            for field in keyword_fields:
                field_type = metadata_props.get(field, {}).get("type", "")
                if field_type == "text":
                    wrong_text_fields.append(field)
            if wrong_text_fields:
                print(
                    f"[ES] ⚠️ 检测到映射错误: {wrong_text_fields} "
                    "字段为 text 类型（应为 keyword）"
                )
                need_reindex = True

            # 检查 integer 字段是否被错误映射为 keyword 或 text 类型
            integer_fields = ["category_l1", "category_l2"]
            wrong_type_fields = []
            for field in integer_fields:
                field_type = metadata_props.get(field, {}).get("type", "")
                if field_type in ("text", "keyword"):
                    wrong_type_fields.append(field)
            if wrong_type_fields:
                print(
                    f"[ES] ⚠️ 检测到映射错误: {wrong_type_fields} "
                    f"字段为 {metadata_props.get(wrong_type_fields[0], {}).get('type', '')} "
                    "类型（应为 integer）"
                )
                need_reindex = True

            if need_reindex:
                self._reindex_to_fix_mapping()
        except Exception as e:
            print(f"[ES] 映射检查失败: {e}")

    def _fix_doc_types(self, source: Dict) -> Dict:
        """修复文档字段类型：将 text 类型值转为映射期望的类型"""
        metadata = source.get("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}
            source["metadata"] = metadata

        # Boolean 字段：字符串 "true"/"false" → Python bool
        for field in ["is_active"]:
            if field in metadata and isinstance(metadata[field], str):
                metadata[field] = metadata[field].lower() in ("true", "1", "yes")

        # Integer 字段：字符串 → int
        for field in ["chunk_level", "chunk_length", "category_l1", "category_l2"]:
            if field in metadata and metadata[field] is not None:
                try:
                    metadata[field] = int(metadata[field])
                except (ValueError, TypeError):
                    metadata[field] = None

        # Keyword 字段：确保为字符串
        for field in ["kb_id", "doc_id", "chunk_id", "parent_id", "file_name",
                       "department"]:
            if field in metadata and metadata[field] is not None:
                metadata[field] = str(metadata[field])

        return source

    def _reindex_to_fix_mapping(self):
        """通过 Python 层迁移修复映射错误（保留所有数据）

        使用 scroll 读取旧索引 → Python 修正类型 → bulk 写入临时索引 → 交换
        """
        from elasticsearch.helpers import bulk

        temp_index = f"{self.index_name}_fix_temp"
        try:
            # 1. 创建临时索引（使用正确的 v2 mapping）
            if self.client.indices.exists(index=temp_index):
                self.client.indices.delete(index=temp_index)

            index_config = self._get_index_mapping()
            try:
                self.client.indices.create(index=temp_index, body=index_config, request_timeout=10)
            except TypeError:
                self.client.indices.create(index=temp_index, **index_config, request_timeout=10)

            # 2. 统计旧索引文档数
            old_count = self.client.count(index=self.index_name).get("count", 0)
            print(f"[ES] 开始重建索引: {self.index_name} 共 {old_count} 条文档")

            # 3. 使用 scroll API 逐批读取旧文档
            docs = []
            scroll_result = self.client.search(
                index=self.index_name,
                body={"query": {"match_all": {}}, "size": 500},
                scroll="2m"
            )
            scroll_id = scroll_result["_scroll_id"]
            hits = scroll_result["hits"]["hits"]

            while hits:
                for hit in hits:
                    fixed_source = self._fix_doc_types(hit["_source"])
                    docs.append({"_index": temp_index, "_id": hit["_id"], "_source": fixed_source})
                scroll_result = self.client.scroll(scroll_id=scroll_id, scroll="2m")
                scroll_id = scroll_result["_scroll_id"]
                hits = scroll_result["hits"]["hits"]

            try:
                self.client.clear_scroll(scroll_id=scroll_id)
            except Exception:
                pass

            # 4. 批量写入临时索引
            success_count, errors = bulk(self.client, docs, raise_on_error=False, request_timeout=120)
            error_items = [e for e in errors if isinstance(e, dict) and e.get("error")]
            if error_items:
                print(f"[ES] ⚠️ 批量写入有 {len(error_items)} 个错误，示例: {error_items[0]}")

            temp_count = self.client.count(index=temp_index).get("count", 0)
            print(f"[ES] 文档迁移: 旧 {old_count} → 临时 {temp_count}")

            # 5. 安全检查：临时索引必须有数据才继续
            if temp_count == 0 and old_count > 0:
                raise Exception(f"迁移失败：旧索引 {old_count} 条文档全部丢失，中止重建")

            # 6. 删除旧索引 → 用旧名称创建新索引
            self.client.indices.delete(index=self.index_name)
            try:
                self.client.indices.create(index=self.index_name, body=index_config, request_timeout=10)
            except TypeError:
                self.client.indices.create(index=self.index_name, **index_config, request_timeout=10)

            # 7. 从临时索引 reindex 回新索引（两边映射一致，不会失败）
            self.client.reindex(
                body={"source": {"index": temp_index}, "dest": {"index": self.index_name}},
                wait_for_completion=True,
                request_timeout=300
            )

            # 8. 删除临时索引
            self.client.indices.delete(index=temp_index)

            final_count = self.client.count(index=self.index_name).get("count", 0)
            print(f"[ES] ✅ 索引重建完成: {self.index_name}, 文档数: {old_count} → {final_count}")

        except Exception as e:
            print(f"[ES] ❌ 索引重建失败: {e}")
            # 清理临时索引
            try:
                if self.client.indices.exists(index=temp_index):
                    self.client.indices.delete(index=temp_index)
            except Exception:
                pass
            raise
    
    def add_document(self, kb_id: str, doc_id: str, chunks: List[Dict], category: str = None):
        """
        添加文档块到 ES（支持 v1 和 v2 格式）

        Args:
            kb_id: 知识库ID
            doc_id: 文档ID
            chunks: 文档块列表，支持两种格式：

            v2 格式（推荐，metadata 嵌套）:
                - content: 内容文本（必需）
                - content_vector: 1024维向量（必需）
                - headers: 标题路径（可选）
                - metadata: 嵌套元数据对象，包含：
                    - chunk_id: 分块ID（可选，自动生成）
                    - parent_id: 父块ID（可选）
                    - chunk_level: 分块层级（可选）
                    - chunk_index: 分块索引（可选）
                    - chunk_length: 分块长度（可选）
                    - kb_id: 知识库ID（可选，自动填充）
                    - doc_id: 文档ID（可选，自动填充）
                    - file_name: 文件名（可选）
                    - department: 部门（可选）
                    - category_l1: 一级分类（可选）
                    - category_l2: 二级分类（可选）
                    - is_active: 是否激活（可选，默认 True）
                    - page: 页码（可选）
                    - image_url: 图片URL（可选）
                    - upload_time: 上传时间（可选，自动填充）
                    - update_time: 更新时间（可选，自动填充）
                    - delete_time: 删除时间（可选）

            v1 格式（兼容，扁平化）:
                - content: 内容文本（必需）
                - content_vector: 1024维向量（必需）
                - modality: 模态（text/table/image，已废弃）
                - department: 部门（可选）
                - doc_type: 资料形态（可选）
                - sys_tags: 系统/内容标签（可选）
                - chunk_tags: 分块关键词（可选）
                - metadata: 元数据（包含 source_file, headers, page, image_url 等）

            category: 一级分类（已废弃，保留兼容性）

        注意：
            - chunk_id 格式：v1 为 {doc_id}_chunk_{idx}，v2 为 {doc_id}_L{level}_{idx}
            - chunk_id 在 add_document 方法中统一生成并写入 ES
            - chunk_id 同时作为 ES 文档的 id 和 document 中的 chunk_id 字段
        """
        try:
            # 获取当前时间戳（北京时间 = UTC + 8）
            current_time = (datetime.utcnow() + timedelta(hours=8)).strftime("%Y-%m-%dT%H:%M:%S")

            for idx, chunk in enumerate(chunks):
                # 检测格式：v2 格式有 metadata 字段
                is_v2_format = "metadata" in chunk

                if is_v2_format:
                    # ========== v2 格式处理 ==========
                    # 从 metadata 中提取 chunk_id，如果没有则生成
                    metadata = chunk.get("metadata", {})
                    chunk_id = metadata.get("chunk_id")

                    # 调试：检查第一个 chunk 的 metadata
                    if idx == 0:
                        print(f"[ES DEBUG] First chunk metadata keys: {list(metadata.keys())}")
                        print(f"[ES DEBUG] file_name in metadata: {repr(metadata.get('file_name'))}")

                    if not chunk_id:
                        # 生成 chunk_id（v2 格式）
                        chunk_level = metadata.get("chunk_level", 1)
                        chunk_id = f"{doc_id}_L{chunk_level}_{idx:03d}"

                    # 验证 content_vector 是否存在（必需）
                    if "content_vector" not in chunk or not chunk.get("content_vector"):
                        raise ValueError(f"chunk_id={chunk_id} 缺少必需的 content_vector 字段")

                    # 验证 content_vector 维度（必须是1024维）
                    content_vector = chunk["content_vector"]
                    if not isinstance(content_vector, list) or len(content_vector) != 1024:
                        raise ValueError(f"chunk_id={chunk_id} 的 content_vector 维度错误: 期望1024维，实际{len(content_vector) if isinstance(content_vector, list) else '非列表'}维")

                    # 补全 metadata 中的必需字段
                    metadata["doc_id"] = doc_id
                    metadata["kb_id"] = kb_id
                    metadata["chunk_id"] = chunk_id
                    if "upload_time" not in metadata or not metadata["upload_time"]:
                        metadata["upload_time"] = current_time
                    if "update_time" not in metadata or not metadata["update_time"]:
                        metadata["update_time"] = current_time
                    if "delete_time" not in metadata:
                        metadata["delete_time"] = None

                    # 构建 v2 文档数据（搜索字段在根级，元数据在 metadata 对象中）
                    # headers 支持字符串或数组格式
                    headers_value = chunk.get("headers", "")
                    if isinstance(headers_value, list):
                        # 数组格式：用 " > " 连接
                        headers_value = " > ".join(headers_value) if headers_value else ""

                    document = {
                        # 根级搜索字段
                        "content": chunk.get("content", ""),
                        "headers": headers_value,
                        "content_vector": content_vector,

                        # 嵌套元数据对象
                        "metadata": metadata
                    }

                else:
                    # ========== v1 格式处理（兼容旧代码）==========
                    # 生成chunk_id：统一格式为{doc_id}_chunk_{idx}
                    chunk_id = f"{doc_id}_chunk_{idx}"

                    # 验证 content_vector 是否存在（必需）
                    if "content_vector" not in chunk or not chunk.get("content_vector"):
                        raise ValueError(f"chunk_id={chunk_id} 缺少必需的 content_vector 字段")

                    # 验证 content_vector 维度（必须是1024维）
                    content_vector = chunk["content_vector"]
                    if not isinstance(content_vector, list) or len(content_vector) != 1024:
                        raise ValueError(f"chunk_id={chunk_id} 的 content_vector 维度错误: 期望1024维，实际{len(content_vector) if isinstance(content_vector, list) else '非列表'}维")

                    # 提取 metadata
                    chunk_metadata = chunk.get("metadata", {})

                    # 从 source_file 提取纯文件名（去除路径）
                    source_file = chunk_metadata.get("source_file", "")
                    file_name_only = os.path.basename(source_file) if source_file else ""

                    # 将 v1 格式转换为 v2 格式（写入 ES 时统一使用 v2 结构）
                    # v2 索引：转换为嵌套结构
                    document = {
                        # 根级搜索字段
                        "content": chunk.get("content", ""),
                        "headers": chunk_metadata.get("headers", ""),
                        "content_vector": content_vector,

                        # 嵌套元数据对象
                        "metadata": {
                            # 文档级字段
                            "doc_id": doc_id,
                            "kb_id": kb_id,
                            "chunk_id": chunk_id,
                            "file_name": file_name_only,
                            "department": chunk.get("department"),
                            "category_l1": chunk.get("doc_type"),  # v1 的 doc_type → v2 的 category_l1
                            "category_l2": (chunk.get("sys_tags", []) or [None])[0] if chunk.get("sys_tags") else None,  # v1 的 sys_tags → v2 的 category_l2

                            # 分块级字段
                            "parent_id": None,
                            "chunk_level": 1,
                            "chunk_length": len(chunk.get("content", "")),

                            # 其他字段
                            "is_active": chunk.get("is_active", True),
                            "page": chunk_metadata.get("page"),
                            "image_url": chunk_metadata.get("image_url"),

                            # 时间字段
                            "upload_time": current_time,
                            "update_time": current_time,
                            "delete_time": None,
                        }
                    }

                # 写入 ES：chunk_id 同时作为 ES 文档的 id 和 document 中的 chunk_id 字段
                # ES 8.x 使用 document 参数
                try:
                    self.client.index(
                        index=self.index_name,
                        id=chunk_id,  # chunk_id 作为 ES 文档的唯一标识
                        document=document,
                    )
                except TypeError:
                    # 兼容旧版本
                    self.client.index(
                        index=self.index_name,
                        id=chunk_id,  # chunk_id 作为 ES 文档的唯一标识
                        body=document,
                    )
        except Exception as e:
            raise Exception(f"添加文档到ES失败: {e}")
    
    def soft_delete_document(self, kb_id: str, doc_id: str):
        """
        软删除文档：将 is_active 字段设置为 false，并设置删除时间

        支持 v1 和 v2 格式

        Args:
            kb_id: 知识库ID（可选，为空则只通过 doc_id 删除）
            doc_id: 文档ID
        """
        try:
            # 获取当前时间戳（北京时间）
            current_time = (datetime.utcnow() + timedelta(hours=8)).strftime("%Y-%m-%dT%H:%M:%S")

            # 构建查询条件（v2 格式：字段在 metadata 对象中）
            must_conditions = [{"term": {"metadata.doc_id": doc_id}}]
            if kb_id:
                must_conditions.append({"term": {"metadata.kb_id": kb_id}})

            script_source = f"""
                ctx._source.metadata.is_active = false;
                ctx._source.metadata.delete_time = '{current_time}';
            """

            query = {
                "query": {
                    "bool": {
                        "must": must_conditions
                    }
                },
                "script": {
                    "source": script_source,
                    "lang": "painless"
                }
            }
            result = self.client.update_by_query(
                index=self.index_name,
                body=query,
                refresh=True,  # 立即刷新索引，确保后续查询能获取最新数据
                ignore=[404]
            )
            updated = result.get("updated", 0)
            print(f"[DEBUG] 软删除文档: doc_id={doc_id}, kb_id={kb_id}, 更新了 {updated} 个分块")
        except Exception as e:
            raise Exception(f"软删除文档失败: {e}")

    def disable_document(self, kb_id: str, doc_id: str):
        """
        禁用文档：将文档及其所有分块设置为禁用状态

        这是 soft_delete_document 的别名方法，用于API调用

        Args:
            kb_id: 知识库ID
            doc_id: 文档ID
        """
        return self.soft_delete_document(kb_id, doc_id)

    def enable_document(self, kb_id: str, doc_id: str):
        """
        启用文档：将文档及其所有分块设置为启用状态

        这是 restore_document 的别名方法，用于API调用

        Args:
            kb_id: 知识库ID
            doc_id: 文档ID
        """
        return self.restore_document(kb_id, doc_id)

    def restore_document(self, kb_id: str, doc_id: str):
        """
        撤销软删除：将 is_active 字段设置为 true，并清除删除时间

        支持 v1 和 v2 格式

        Args:
            kb_id: 知识库ID（可选，为空则只通过 doc_id 恢复）
            doc_id: 文档ID
        """
        try:
            # 获取当前时间戳（北京时间）
            current_time = (datetime.utcnow() + timedelta(hours=8)).strftime("%Y-%m-%dT%H:%M:%S")

            # 构建查询条件（v2 格式：字段在 metadata 对象中）
            must_conditions = [{"term": {"metadata.doc_id": doc_id}}]
            if kb_id:
                must_conditions.append({"term": {"metadata.kb_id": kb_id}})

            script_source = f"""
                ctx._source.metadata.is_active = true;
                ctx._source.metadata.delete_time = null;
                ctx._source.metadata.update_time = '{current_time}';
            """

            query = {
                "query": {
                    "bool": {
                        "must": must_conditions
                    }
                },
                "script": {
                    "source": script_source,
                    "lang": "painless"
                }
            }
            self.client.update_by_query(
                index=self.index_name,
                body=query,
                refresh=True,  # 立即刷新索引，确保后续查询能获取最新数据
                ignore=[404]
            )
        except Exception as e:
            raise Exception(f"撤销软删除失败: {e}")

    def soft_disable_chunk(self, chunk_id: str):
        """
        软禁用分块：将分块及其子块的 is_active 字段设置为 false

        Args:
            chunk_id: 分块ID（ES文档的_id）
        """
        try:
            # 获取当前时间戳（北京时间）
            current_time = (datetime.utcnow() + timedelta(hours=8)).strftime("%Y-%m-%dT%H:%M:%S")

            # 首先禁用父块本身（使用 update API，直接通过 _id 更新）
            try:
                self.client.update(
                    index=self.index_name,
                    id=chunk_id,
                    refresh=True,  # 立即刷新索引
                    body={
                        "script": {
                            "source": f"""
                                ctx._source.metadata.is_active = false;
                                ctx._source.metadata.delete_time = '{current_time}';
                            """,
                            "lang": "painless"
                        }
                    }
                )
                parent_updated = 1
            except Exception as e:
                print(f"[DEBUG] 更新父块失败: {e}")
                parent_updated = 0

            # 获取父块的 metadata.chunk_id，用于查找子块
            try:
                get_result = self.client.get(index=self.index_name, id=chunk_id, ignore=[404])
                parent_chunk_id = get_result["_source"]["metadata"]["chunk_id"]
            except:
                parent_chunk_id = None

            # 如果是父块，还需要级联禁用所有子块
            child_updated = 0
            if parent_chunk_id:
                child_query = {
                    "query": {
                        "bool": {
                            "must": [
                                {"term": {"metadata.parent_id": parent_chunk_id}}
                            ]
                        }
                    },
                    "script": {
                        "source": f"""
                            ctx._source.metadata.is_active = false;
                            ctx._source.metadata.delete_time = '{current_time}';
                        """,
                        "lang": "painless"
                    }
                }
                child_result = self.client.update_by_query(
                    index=self.index_name,
                    body=child_query,
                    refresh=True,  # 立即刷新索引
                    ignore=[404],
                    conflicts="proceed"  # 忽略版本冲突，继续执行
                )
                child_updated = child_result.get("updated", 0)

            total_updated = parent_updated + child_updated
            print(f"[DEBUG] 软禁用分块: chunk_id={chunk_id}, 更新了 {total_updated} 个分块（父块: {parent_updated}, 子块: {child_updated}）")
        except Exception as e:
            raise Exception(f"软禁用分块失败: {e}")

    def restore_chunk(self, chunk_id: str):
        """
        恢复已禁用的分块：将分块及其子块的 is_active 字段设置为 true

        Args:
            chunk_id: 分块ID（ES文档的_id）
        """
        try:
            # 获取当前时间戳（北京时间）
            current_time = (datetime.utcnow() + timedelta(hours=8)).strftime("%Y-%m-%dT%H:%M:%S")

            # 首先恢复父块本身（使用 update API，直接通过 _id 更新）
            try:
                self.client.update(
                    index=self.index_name,
                    id=chunk_id,
                    refresh=True,  # 立即刷新索引
                    body={
                        "script": {
                            "source": f"""
                                ctx._source.metadata.is_active = true;
                                ctx._source.metadata.delete_time = null;
                                ctx._source.metadata.update_time = '{current_time}';
                            """,
                            "lang": "painless"
                        }
                    }
                )
                parent_updated = 1
            except Exception as e:
                print(f"[DEBUG] 更新父块失败: {e}")
                parent_updated = 0

            # 获取父块的 metadata.chunk_id，用于查找子块
            try:
                get_result = self.client.get(index=self.index_name, id=chunk_id, ignore=[404])
                parent_chunk_id = get_result["_source"]["metadata"]["chunk_id"]
            except:
                parent_chunk_id = None

            # 如果是父块，还需要级联恢复所有子块
            child_updated = 0
            if parent_chunk_id:
                child_query = {
                    "query": {
                        "bool": {
                            "must": [
                                {"term": {"metadata.parent_id": parent_chunk_id}}
                            ]
                        }
                    },
                    "script": {
                        "source": f"""
                            ctx._source.metadata.is_active = true;
                            ctx._source.metadata.delete_time = null;
                            ctx._source.metadata.update_time = '{current_time}';
                        """,
                        "lang": "painless"
                    }
                }
                child_result = self.client.update_by_query(
                    index=self.index_name,
                    body=child_query,
                    refresh=True,  # 立即刷新索引
                    ignore=[404],
                    conflicts="proceed"  # 忽略版本冲突，继续执行
                )
                child_updated = child_result.get("updated", 0)

            total_updated = parent_updated + child_updated
            print(f"[DEBUG] 恢复分块: chunk_id={chunk_id}, 更新了 {total_updated} 个分块（父块: {parent_updated}, 子块: {child_updated}）")
        except Exception as e:
            raise Exception(f"恢复分块失败: {e}")

    def delete_document(self, kb_id: str, doc_id: str):
        """
        硬删除文档：从 ES 真正删除文档的所有块

        支持 v1 和 v2 格式

        Args:
            kb_id: 知识库ID（可选，为空则只通过 doc_id 删除）
            doc_id: 文档ID
        """
        try:
            # 构建查询条件（v2 格式：字段在 metadata 对象中）
            must_conditions = [{"term": {"metadata.doc_id": doc_id}}]
            if kb_id:
                must_conditions.append({"term": {"metadata.kb_id": kb_id}})

            query = {
                "query": {
                    "bool": {
                        "must": must_conditions
                    }
                }
            }
            result = self.client.delete_by_query(
                index=self.index_name,
                body=query,
                refresh=True,  # 立即刷新索引
                ignore=[404]
            )
            deleted = result.get("deleted", 0)
            print(f"[DEBUG] 硬删除文档: doc_id={doc_id}, kb_id={kb_id}, 删除了 {deleted} 个分块")
        except Exception as e:
            raise Exception(f"从ES删除文档失败: {e}")
    
    def get_chunks_by_minio_path(self, minio_path: str, kb_id: str = None) -> List[Dict]:
        """
        根据 minio_path 查询分块详情（v2 格式）

        Args:
            minio_path: MinIO 文件路径（存储在 metadata.file_name 字段中）
            kb_id: 知识库ID（可选，用于过滤）

        Returns:
            分块列表，每个块包含完整信息
        """
        def _extract_chunk_from_source(source: Dict) -> Dict:
            """从 ES source 提取分块数据（v2 格式）"""
            metadata = source.get("metadata", {})

            return {
                "chunk_id": source.get("chunk_id"),
                "kb_id": metadata.get("kb_id"),
                "doc_id": metadata.get("doc_id"),
                "is_active": metadata.get("is_active", True),
                "content": source.get("content"),
                "content_vector": source.get("content_vector"),
                # v2 格式字段
                "file_name": metadata.get("file_name"),
                "headers": metadata.get("headers"),
                "parent_id": metadata.get("parent_id"),
                "level": metadata.get("level"),
                "chunk_index": metadata.get("chunk_index"),
                "department": metadata.get("department"),
                "category_l1": metadata.get("category_l1"),
                "category_l2": metadata.get("category_l2"),
                # 时间字段
                "upload_time": metadata.get("upload_time"),
                "update_time": metadata.get("update_time"),
                "delete_time": metadata.get("delete_time"),
            }

        try:
            # 方案1: 使用 metadata.file_name 的 term 查询（精确匹配）
            query_conditions = [
                {"term": {"metadata.file_name": minio_path}}
            ]

            if kb_id:
                query_conditions.append({"term": {"metadata.kb_id": kb_id}})

            query = {
                "query": {
                    "bool": {
                        "must": query_conditions,
                        "filter": [
                            {"term": {"metadata.is_active": True}}  # 只返回激活的分块
                        ]
                    }
                },
                "sort": [
                    {"chunk_id": {"order": "asc"}}
                ],
                "size": 10000
            }

            # ES 8.x 兼容性处理
            try:
                response = self.client.search(index=self.index_name, body=query)
            except TypeError:
                response = self.client.search(index=self.index_name, **query)

            chunks = []
            for hit in response.get("hits", {}).get("hits", []):
                source = hit["_source"]
                chunks.append(_extract_chunk_from_source(source))

            # 方案1.1: 如果未命中，尝试基于文件名进行匹配（使用 wildcard 查询）
            if len(chunks) == 0:
                import os
                filename = os.path.basename(minio_path)
                if filename:
                    filename_query_conditions = [
                        {"wildcard": {"metadata.file_name": f"*{filename}*"}}
                    ]
                    if kb_id:
                        filename_query_conditions.append({"term": {"metadata.kb_id": kb_id}})
                    filename_query = {
                        "query": {
                            "bool": {
                                "must": filename_query_conditions
                            }
                        },
                        "sort": [
                            {"chunk_id": {"order": "asc"}}
                        ],
                        "size": 10000
                    }
                    try:
                        response = self.client.search(index=self.index_name, body=filename_query)
                    except TypeError:
                        response = self.client.search(index=self.index_name, **filename_query)
                    for hit in response.get("hits", {}).get("hits", []):
                        source = hit["_source"]
                        chunks.append(_extract_chunk_from_source(source))

            # 方案2: 如果没查到且提供了 kb_id，尝试用 kb_id + doc_id 查询（从路径解析 doc_id）
            if len(chunks) == 0 and kb_id:
                # 从 minio_path 解析 doc_id: "source-documents/kb_id/doc_id/filename" -> doc_id
                path_parts = minio_path.split('/')
                if len(path_parts) >= 3:
                    doc_id = path_parts[2]  # 第3段通常是 doc_id

                    fallback_query = {
                        "query": {
                            "bool": {
                                "must": [
                                    {"term": {"metadata.kb_id": kb_id}},
                                    {"term": {"metadata.doc_id": doc_id}}
                                ]
                            }
                        },
                        "sort": [
                            {"chunk_id": {"order": "asc"}}
                        ],
                        "size": 10000
                    }

                    try:
                        response = self.client.search(index=self.index_name, body=fallback_query)
                    except TypeError:
                        response = self.client.search(index=self.index_name, **fallback_query)

                    for hit in response.get("hits", {}).get("hits", []):
                        source = hit["_source"]
                        chunks.append(_extract_chunk_from_source(source))

            return chunks
        except Exception as e:
            raise Exception(f"查询分块失败: {e}")


# 通用知识库（v2 结构） ES 存储实例
es_service_store = ESStore(settings.KB_SERVICE_INDEX, ensure_index=False)

# 保留旧的 es_store 变量用于向后兼容（指向通用知识库 v2）
es_store = es_service_store
