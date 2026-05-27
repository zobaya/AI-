"""
工具管理器 - 统一管理和调用各种工具
"""
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional


class ToolManager:
    """工具管理器，用于统一管理和调用各种工具"""
    def __init__(self):
        self.tools: Dict[str, Any] = {}

    def register_tool(self, tool) -> None:
        """注册工具"""
        self.tools[tool.name] = tool

    def get_tool(self, name: str):
        """获取工具实例"""
        return self.tools.get(name)

    def list_tools(self) -> List[Dict[str, str]]:
        """列出所有已注册的工具"""
        return [{"name": tool.name, "description": tool.description} for tool in self.tools.values()]

    def execute_tool(self, name: str, **kwargs) -> Dict[str, Any]:
        """执行指定工具"""
        tool = self.get_tool(name)
        if not tool:
            return {"success": False, "error": f"工具 {name} 未找到"}
        try:
            return tool.run(**kwargs)
        except Exception as e:
            return {"success": False, "error": f"执行工具 {name} 时出错: {str(e)}"}


# 工具结果模型
class ExtractionResult(BaseModel):
    """文本提取结果模型"""
    original_text: str = Field("", description="原始文本")
    cleaned_text: str = Field("", description="清理后的文本")
    encoding: str = Field("", description="编码格式")
    chunks: List[str] = Field(default_factory=list, description="文本块列表")
    chunk_count: int = Field(0, description="文本块数量")
    keywords: List[str] = Field(default_factory=list, description="关键词列表")
    word_count: int = Field(0, description="词数")
    character_count: int = Field(0, description="字符数")
    success: bool = Field(False, description="是否成功")
    error: Optional[str] = Field(None, description="错误信息")


class SearchResult(BaseModel):
    """搜索结果模型"""
    text: str = Field(..., description="文档内容")
    owner: str = Field("", description="所有者")
    title: str = Field("", description="标题")
    date: str = Field("", description="日期")
    score: float = Field(..., description="匹配分数")
    type: str = Field("text", description="文档类型")
    chunk_index: int = Field(0, description="块索引")
    doc_id: str = Field("", description="文档ID")
    context_chunks: List[Dict[str, Any]] = Field(default_factory=list, description="上下文块")
    kb_id: str = Field("", description="知识库ID")


class SearchResponse(BaseModel):
    """搜索响应模型"""
    total: int = Field(0, description="总匹配数")
    hits: List[Dict[str, Any]] = Field(default_factory=list, description="结果列表")
    success: bool = Field(False, description="是否成功")
    error: Optional[str] = Field(None, description="错误信息")
