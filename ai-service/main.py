"""FastAPI 总入口"""
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

from core.config import settings
from kb_service.api import router as kb_router
# Harness/App 分层：使用新路由替代原 tool_calling_agent.main
from src.app.routers.chat import router as agent_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时：确保 ES 索引已初始化（仅一次）
    import kb_service.es_store as es_store_module

    # 初始化知识库索引
    es_store_module.es_service_store._ensure_index()
    print("[System] 知识库服务启动完成")
    yield
    # 关闭时：清理资源
    print("[System] 服务关闭")


# 创建 FastAPI 应用
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI Service - 知识库管理系统 & 智能问答服务",
    debug=settings.DEBUG,
    lifespan=lifespan,
)

# 挂载静态文件目录（用于访问测试页面）
import os

# KB服务页面（通用知识库查看器）
kb_pages_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kb_service", "pages")
if os.path.exists(kb_pages_dir):
    app.mount("/kb_pages", StaticFiles(directory=kb_pages_dir), name="kb_pages")

# 项目根目录（用于访问其他静态资源）
project_root = os.path.dirname(os.path.abspath(__file__))
if os.path.exists(project_root):
    app.mount("/static", StaticFiles(directory=project_root), name="static")

# Agent 静态资源
agent_static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src", "app", "pages")
if os.path.exists(agent_static_dir):
    app.mount("/agent/static", StaticFiles(directory=agent_static_dir), name="agent_static")

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应配置具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def limit_content_length(request: Request, call_next):
    """限制请求体大小的中间件（100MB）- 只在真正需要时检查"""
    # 跳过上传端点的预检，让请求正常传递
    if request.url.path == "/api/upload-files" and request.method == "POST":
        # 直接放行，让后续的 UploadFile 处理
        return await call_next(request)

    content_length = request.headers.get("content-length")
    if content_length:
        content_length = int(content_length)
        max_size = 100 * 1024 * 1024  # 100MB
        if content_length > max_size:
            raise HTTPException(
                status_code=413,
                detail=f"Request body too large (max {max_size // (1024*1024)}MB)"
            )
    return await call_next(request)

# 注册路由
app.include_router(kb_router, prefix="/api/kb", tags=["知识库"])
app.include_router(agent_router, prefix="/agent", tags=["Tool Calling Agent"])

@app.get("/")
async def root():
    """根路径健康检查"""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
    }

@app.get("/favicon.ico")
async def favicon():
    """处理浏览器图标请求，返回空响应"""
    from fastapi.responses import Response
    return Response(status_code=204)  # No Content

@app.get("/health")
async def health_check():
    """健康检查端点"""
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=7729,
        reload=settings.DEBUG,
        log_level="info",
        http="h11",  # 显式使用 h11
        h11_max_incomplete_event_size=100 * 1024 * 1024,  # 100MB
    )