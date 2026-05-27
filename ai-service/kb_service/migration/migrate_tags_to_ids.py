"""
一次性迁移脚本：将 ES 中 metadata.category_l1 和 metadata.category_l2
从标签名称（keyword 字符串）转换为标签 ID（integer）。

运行方式：
    cd ai-service
    uv run python -m kb_service.migration.migrate_tags_to_ids

前置条件：
    1. 暂停 Celery Worker（防止并发写入）
    2. 确保 Django 后端正在运行（用于拉取标签树）
    3. 确保 ES 服务可用

流程：
    1. 从 Django API 拉取标签树，构建 name → id 映射
    2. 创建新临时索引（integer 映射）
    3. 滚动遍历旧索引，转换 tag name → tag id
    4. 批量写入新索引
    5. 安全检查后切换索引
"""
import os
import sys

import httpx
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk

# 添加项目根目录到 sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from core.config import settings


def fetch_tag_registry() -> dict:
    """从 Django API 拉取标签树，构建 name → id 映射"""
    service_token = getattr(settings, "SERVICE_AUTH_TOKEN", "")
    headers = {"Content-Type": "application/json"}
    if service_token:
        headers["Authorization"] = f"Service {service_token}"

    url = f"{settings.DJANGO_API_BASE_URL}/api/tags/internal/registry/"
    print(f"[迁移] 拉取标签树: {url}")

    with httpx.Client(timeout=10.0) as client:
        resp = client.get(url, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    categories = data.get("categories", [])
    print(f"[迁移] 拉取到 {len(categories)} 个一级标签")

    # 构建 name → id 映射
    name_to_id: dict[str, int] = {}
    for cat in categories:
        l1_name = cat.get("category_l1", "")
        l1_id = cat.get("id")
        if l1_name and l1_id:
            name_to_id[l1_name] = l1_id
        for l2 in cat.get("category_l2", []):
            l2_name = l2.get("name", "")
            l2_id = l2.get("id")
            if l2_name and l2_id:
                name_to_id[l2_name] = l2_id

    print(f"[迁移] 映射表: {len(name_to_id)} 个标签 name → id")
    return name_to_id


def run_migration(dry_run: bool = False):
    """执行迁移"""
    # 1. 拉取标签映射
    name_to_id = fetch_tag_registry()

    # 2. 连接 ES
    es = Elasticsearch(
        [{"host": settings.ES_HOST, "port": settings.ES_PORT}],
        request_timeout=30,
    )
    index_name = settings.KB_SERVICE_INDEX
    temp_index = f"{index_name}_tag_migration"

    # 检查旧索引是否存在
    if not es.indices.exists(index=index_name):
        print(f"[迁移] 索引 {index_name} 不存在，无需迁移")
        return

    old_count = es.count(index=index_name).get("count", 0)
    print(f"[迁移] 旧索引 {index_name} 共 {old_count} 条文档")

    if old_count == 0:
        print("[迁移] 索引为空，无需迁移")
        return

    if dry_run:
        # 仅统计需要转换的文档数
        converted = 0
        unmatched_l1: set[str] = set()
        unmatched_l2: set[str] = set()

        scroll_result = es.search(
            index=index_name,
            body={"query": {"match_all": {}}, "size": 500},
            scroll="2m",
        )
        scroll_id = scroll_result["_scroll_id"]
        hits = scroll_result["hits"]["hits"]

        while hits:
            for hit in hits:
                metadata = hit["_source"].get("metadata", {})
                l1 = metadata.get("category_l1")
                l2 = metadata.get("category_l2")
                if l1 and isinstance(l1, str) and l1 not in name_to_id:
                    unmatched_l1.add(l1)
                if l2 and isinstance(l2, str) and l2 not in name_to_id:
                    unmatched_l2.add(l2)
                if (l1 and isinstance(l1, str)) or (l2 and isinstance(l2, str)):
                    converted += 1
            scroll_result = es.scroll(scroll_id=scroll_id, scroll="2m")
            scroll_id = scroll_result["_scroll_id"]
            hits = scroll_result["hits"]["hits"]

        try:
            es.clear_scroll(scroll_id=scroll_id)
        except Exception:
            pass

        print("\n[DRY RUN] 统计结果:")
        print(f"  需要转换的文档数: {converted}")
        if unmatched_l1:
            print(f"  无法匹配的 L1 标签名: {unmatched_l1}")
        if unmatched_l2:
            print(f"  无法匹配的 L2 标签名: {unmatched_l2}")
        return

    # 3. 创建临时索引（使用 v2 mapping，category 字段为 integer）
    if es.indices.exists(index=temp_index):
        es.indices.delete(index=temp_index)

    # 导入 ESStore 的 mapping 方法
    from kb_service.es_store import ESStore
    store = ESStore(index_name, ensure_index=False)
    index_config = store._get_index_mapping()

    try:
        es.indices.create(index=temp_index, body=index_config, request_timeout=10)
    except TypeError:
        es.indices.create(index=temp_index, **index_config, request_timeout=10)

    print(f"[迁移] 创建临时索引: {temp_index}")

    # 4. 滚动遍历旧索引，转换并写入新索引
    docs = []
    converted_count = 0
    unmatched_l1: set[str] = set()
    unmatched_l2: set[str] = set()

    scroll_result = es.search(
        index=index_name,
        body={"query": {"match_all": {}}, "size": 500},
        scroll="2m",
    )
    scroll_id = scroll_result["_scroll_id"]
    hits = scroll_result["hits"]["hits"]

    while hits:
        for hit in hits:
            source = hit["_source"]
            metadata = source.get("metadata", {})

            # 转换 category_l1: string name → integer id
            l1 = metadata.get("category_l1")
            if l1 is not None and isinstance(l1, str) and l1:
                if l1 in name_to_id:
                    metadata["category_l1"] = name_to_id[l1]
                    converted_count += 1
                else:
                    unmatched_l1.add(l1)
                    metadata["category_l1"] = None
            elif l1 is not None and not isinstance(l1, int):
                try:
                    metadata["category_l1"] = int(l1)
                except (ValueError, TypeError):
                    metadata["category_l1"] = None

            # 转换 category_l2: string name → integer id
            l2 = metadata.get("category_l2")
            if l2 is not None and isinstance(l2, str) and l2:
                if l2 in name_to_id:
                    metadata["category_l2"] = name_to_id[l2]
                else:
                    unmatched_l2.add(l2)
                    metadata["category_l2"] = None
            elif l2 is not None and not isinstance(l2, int):
                try:
                    metadata["category_l2"] = int(l2)
                except (ValueError, TypeError):
                    metadata["category_l2"] = None

            docs.append({
                "_index": temp_index,
                "_id": hit["_id"],
                "_source": source,
            })

        scroll_result = es.scroll(scroll_id=scroll_id, scroll="2m")
        scroll_id = scroll_result["_scroll_id"]
        hits = scroll_result["hits"]["hits"]

    try:
        es.clear_scroll(scroll_id=scroll_id)
    except Exception:
        pass

    # 5. 批量写入临时索引
    print(f"[迁移] 写入 {len(docs)} 条文档到临时索引...")
    success_count, errors = bulk(es, docs, raise_on_error=False, request_timeout=120)
    error_items = [e for e in errors if isinstance(e, dict) and e.get("error")]
    if error_items:
        print(f"[迁移] ⚠️ 批量写入有 {len(error_items)} 个错误")
        for err in error_items[:3]:
            print(f"  示例: {err}")

    temp_count = es.count(index=temp_index).get("count", 0)
    print(f"[迁移] 文档迁移: 旧 {old_count} → 临时 {temp_count}")

    # 6. 安全检查
    if temp_count == 0 and old_count > 0:
        print("[迁移] ❌ 临时索引为空，中止迁移（不删除旧索引）")
        es.indices.delete(index=temp_index)
        return

    if unmatched_l1:
        print(f"[迁移] ⚠️ 无法匹配的 L1 标签名（已置 null）: {unmatched_l1}")
    if unmatched_l2:
        print(f"[迁移] ⚠️ 无法匹配的 L2 标签名（已置 null）: {unmatched_l2}")

    # 7. 切换索引
    print("[迁移] 切换索引...")
    es.indices.delete(index=index_name)

    try:
        es.indices.create(index=index_name, body=index_config, request_timeout=10)
    except TypeError:
        es.indices.create(index=index_name, **index_config, request_timeout=10)

    # 从临时索引 reindex 回正式索引
    es.reindex(
        body={
            "source": {"index": temp_index},
            "dest": {"index": index_name},
        },
        request_timeout=120,
    )
    es.indices.refresh(index=index_name)

    # 删除临时索引
    es.indices.delete(index=temp_index)

    final_count = es.count(index=index_name).get("count", 0)
    print("\n[迁移] ✅ 迁移完成!")
    print(f"  旧索引文档数: {old_count}")
    print(f"  新索引文档数: {final_count}")
    print(f"  标签转换数: {converted_count}")


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    if dry:
        print("=" * 60)
        print("  标签迁移 DRY RUN 模式（仅统计，不写入）")
        print("=" * 60)
    run_migration(dry_run=dry)
