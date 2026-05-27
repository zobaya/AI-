"""Chat API URL 配置"""
from django.urls import path
from . import views

urlpatterns = [
    # 文件夹
    path("folders/", views.FolderListView.as_view(), name="folder-list"),
    path("folders/<int:pk>/", views.FolderDetailView.as_view(), name="folder-detail"),
    # 会话
    path("conversations/", views.ConversationListView.as_view(), name="conversation-list"),
    path("conversations/<int:pk>/", views.ConversationDetailView.as_view(), name="conversation-detail"),
    path("conversations/<int:pk>/export/", views.ConversationExportView.as_view(), name="conversation-export"),
    path("conversations/<int:conv_id>/messages/", views.MessageTruncateView.as_view(), name="message-truncate"),
    # 消息反馈
    path("messages/<int:pk>/feedback/", views.MessageFeedbackView.as_view(), name="message-feedback"),
    # 聊天
    path("send/", views.ChatSendView.as_view(), name="chat-send"),
    path("upload/", views.FileUploadView.as_view(), name="chat-upload"),
    # 快捷提示词
    path("prompts/", views.PromptLibraryView.as_view(), name="prompt-list"),
    path("prompts/<int:pk>/", views.PromptLibraryDetailView.as_view(), name="prompt-detail"),
    # 用户记忆
    path("memory/", views.UserMemoryListView.as_view(), name="memory-list"),
    path("memory/batch/", views.UserMemoryBatchView.as_view(), name="memory-batch"),
    path("memory/<int:pk>/", views.UserMemoryDetailView.as_view(), name="memory-detail"),
    # AI 生成文件
    path("files/", views.GeneratedFileListView.as_view(), name="generated-file-list"),
    path("files/<int:pk>/download/", views.FileDownloadView.as_view(), name="file-download"),
    path("files/create/", views.GeneratedFileCreateView.as_view(), name="generated-file-create"),
]
