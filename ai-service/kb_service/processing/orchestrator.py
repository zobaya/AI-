"""
文档处理编排器 - 统一处理流水线

职责：
1. 协调各层处理流程（Parse → Chunk → Enhance → Vectorize → Store）
2. 管理处理进度
3. 错误处理和重试

tasks.py 只需调用 orchestrator.process_document()
"""
import os
from typing import Dict, Optional
from core.object_store import object_store
from core.config import settings


class DocumentOrchestrator:
    """
    文档处理编排器

    完整流水线：
    1. Parser Layer   → Markdown
    2. Chunker Layer  → Chunks
    3. Enhancer Layer → 添加宏观字段
    4. Vectorizer Layer → 向量化
    5. Storage Layer  → 写入 ES
    """

    def __init__(self):
        # 导入各层模块（延迟导入避免循环依赖）
        from kb_service.processing.parsers.registry import get_parser
        from kb_service.processing.chunkers.registry import get_chunker as get_chunker_registry
        from kb_service.processing.enhancers.macro_enhancer import MacroEnhancer
        from kb_service.processing.vectorizers.ollama_vectorizer import OllamaVectorizer
        from kb_service.processing.storage.es_writer import ESWriter

        self.get_parser = get_parser
        self.get_chunker = get_chunker_registry
        # MacroEnhancer 使用静态方法，不需要实例化
        self.macro_enhance = MacroEnhancer.enhance
        self.OllamaVectorizer = OllamaVectorizer
        self.ESWriter = ESWriter

    def process_document(
        self,
        minio_path: str,
        file_name: str,
        department: str = None,
        category_l1: int = None,
        category_l2: int = None,
        reporter = None
    ) -> Dict:
        """
        完整文档处理流水线

        Args:
            minio_path: MinIO 中的文件路径
            file_name: 文件名
            department: 部门（宏观管理字段）
            category_l1: 一级分类（宏观管理字段）
            category_l2: 二级分类（宏观管理字段）
            reporter: 进度报告器

        Returns:
            Dict: 处理结果
        """
        try:
            # 解析 minio_path
            path_parts = minio_path.split('/')
            kb_id = path_parts[1]
            doc_id = path_parts[2]

            print(f"\n[Orchestrator] Starting document processing")
            print(f"  KB: {kb_id}, Doc: {doc_id}")
            print(f"  File: {file_name}")

            # ========== Step 1: Parser Layer ==========
            file_ext = os.path.splitext(file_name)[1].lower()

            if file_ext in (".md", ".txt"):
                # Markdown / 纯文本文件：直接读取，跳过 Parser
                if reporter:
                    reporter.info(f"{file_ext} 文件，跳过解析...", 5)

                file_data = object_store.get_object(minio_path)
                markdown_text = file_data.decode('utf-8')

                if reporter:
                    reporter.info(f"读取成功: {len(markdown_text)} 字符", 15)
            else:
                # 其他文件（PDF/DOCX 等）：需要 Parser 解析
                if reporter:
                    reporter.info("解析文档...", 5)

                file_data = object_store.get_object(minio_path)
                parser = self.get_parser(file_ext)

                if reporter:
                    reporter.info(f"使用 {parser.__class__.__name__} 解析...", 8)

                parse_result = parser.parse(file_data, file_name, kb_id, doc_id)

                if not parse_result.success:
                    raise Exception(f"解析失败: {parse_result.error}")

                markdown_text = parse_result.markdown

                if reporter:
                    reporter.info(f"解析成功: {len(markdown_text)} 字符", 15)
                    reporter.info(f"提取图片: {len(parse_result.images)} 张", 16)

                # ========== Step 1.6: PDF 标题层级还原 ==========
                if file_ext == ".pdf":
                    try:
                        from kb_service.processing.common.hierarchy_restorer import HierarchyRestorer
                        restorer = HierarchyRestorer()
                        markdown_text = restorer.restore(markdown_text)
                        if reporter:
                            reporter.info("PDF 标题层级还原完成", 17)
                    except Exception as herr:
                        print(f"[Orchestrator] [WARN] 层级还原失败，使用原始 Markdown: {herr}")

                # ========== Step 1.7: 保存 Markdown 到 MinIO ==========
                try:
                    md_filename = os.path.splitext(os.path.basename(minio_path))[0] + ".md"
                    md_object_name = f"{kb_id}/{doc_id}/{md_filename}"
                    md_bytes = markdown_text.encode('utf-8')
                    md_url = object_store.put_object(
                        object_name=md_object_name,
                        data=md_bytes,
                        content_type="text/markdown; charset=utf-8"
                    )
                    print(f"[Orchestrator] Markdown saved to MinIO: {md_object_name}")
                except Exception as md_err:
                    print(f"[Orchestrator] [WARN] Failed to save markdown to MinIO: {md_err}")

            # ========== Step 1.6b: 表格平铺降维（所有格式通用） ==========
            try:
                from kb_service.processing.common.table_flattener import TableFlattener
                flattener = TableFlattener()
                markdown_text = flattener.flatten(markdown_text)
                if reporter:
                    reporter.info("表格平铺降维完成", 18)
            except Exception as tferr:
                print(f"[Orchestrator] [WARN] 表格降维失败，使用原始 Markdown: {tferr}")

            # ========== Step 2: Chunker Layer ==========
            if reporter:
                reporter.report_step("分块处理", "正在分块...", 20)

            chunker = self.get_chunker()
            chunks = chunker.chunk(markdown_text, doc_id, file_name)

            if reporter:
                reporter.info(f"分块完成: {len(chunks)} 个分块", 25)

            # ========== Step 3: Enhancer Layer ==========
            if reporter:
                reporter.report_step("添加宏观字段", "正在添加宏观管理字段...", 26)

            chunks = self.macro_enhance(
                chunks, department, category_l1, category_l2
            )

            # ========== Step 4: Vectorizer Layer ==========
            if reporter:
                reporter.report_step("生成向量嵌入", f"准备生成 {len(chunks)} 个分块的向量...", 30)

            vectorizer = self.OllamaVectorizer()
            chunks = vectorizer.vectorize(chunks)

            if reporter:
                reporter.info("向量嵌入生成完成", 80)

            # ========== Step 5: Storage Layer ==========
            if reporter:
                reporter.report_step("写入ES", f"正在写入 {len(chunks)} 个分块...", 85)

            self.ESWriter.write(kb_id, doc_id, chunks)

            if reporter:
                reporter.info(f"成功写入 {len(chunks)} 个分块到 ES", 95)
                reporter.info("处理完成！", 100)

            return {
                "status": "completed",
                "kb_id": kb_id,
                "doc_id": doc_id,
                "file_name": file_name,
                "chunks_count": len(chunks),
                "metadata": {
                    "department": department,
                    "category_l1": category_l1,
                    "category_l2": category_l2,
                }
            }

        except Exception as e:
            error_msg = f"处理失败: {str(e)}"
            print(f"[Orchestrator] ERROR: {error_msg}")
            import traceback
            traceback.print_exc()

            if reporter:
                reporter.error(error_msg)

            raise

