"""知识库管理 API"""
from django.urls import path
from . import views

urlpatterns = [
    # ── 知识库 (本地 CRUD) ──
    path("bases/", views.KnowledgeBaseListView.as_view(), name="kb-list"),
    path("bases/<str:kb_id>/", views.KnowledgeBaseDetailView.as_view(), name="kb-detail"),

    # ── 文档 (代理 ai-service) ──
    path("documents/", views.DocumentListView.as_view(), name="doc-list"),
    path("documents/upload/", views.DocumentUploadView.as_view(), name="doc-upload"),
    path("documents/<str:doc_id>/", views.DocumentDetailView.as_view(), name="doc-detail"),
    path("documents/<str:doc_id>/enable/", views.DocumentEnableView.as_view(), name="doc-enable"),
    path("documents/<str:doc_id>/disable/", views.DocumentDisableView.as_view(), name="doc-disable"),
    path("documents/<str:doc_id>/metadata/", views.DocumentMetadataView.as_view(), name="doc-metadata"),

    # ── 分块 (代理 ai-service) ──
    path("chunks/", views.ChunkListView.as_view(), name="chunk-list"),
    path("chunks/<str:chunk_id>/", views.ChunkDetailView.as_view(), name="chunk-detail"),
    path("chunks/<str:chunk_id>/enable/", views.ChunkEnableView.as_view(), name="chunk-enable"),
    path("chunks/<str:chunk_id>/disable/", views.ChunkDisableView.as_view(), name="chunk-disable"),

    # ── 任务 & 标签 ──
    path("tasks/<str:task_id>/", views.TaskStatusView.as_view(), name="task-status"),
    path("tags/", views.TagListView.as_view(), name="tag-list"),

    # ── 运维 ──
    path("documents/reprocess/", views.DocumentReprocessView.as_view(), name="doc-reprocess"),
    path("documents/<str:doc_id>/status-callback/", views.DocumentStatusCallbackView.as_view(), name="doc-status-callback"),

    # ── 图片代理 ──
    path("images/<path:path>", views.KnowledgeBaseImageView.as_view(), name="kb-image"),
]
