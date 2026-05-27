"""Chat 模块 Serializers"""
from rest_framework import serializers
from .models import ConversationFolder, Conversation, Message, MessageAttachment, PromptLibrary, UserMemory


class MessageAttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = MessageAttachment
        fields = ["id", "file_name", "file_path_minio", "file_size", "content_type", "created_at"]


class ConversationFolderSerializer(serializers.ModelSerializer):
    conversation_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = ConversationFolder
        fields = ["id", "name", "sort_order", "conversation_count", "created_at", "updated_at"]


class MessageSerializer(serializers.ModelSerializer):
    attachments = MessageAttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = Message
        fields = ["id", "role", "content", "workflow_id", "metadata_json", "tokens_used", "feedback", "feedback_detail", "attachments", "created_at"]


class ConversationListSerializer(serializers.ModelSerializer):
    message_count = serializers.IntegerField(read_only=True, default=0)
    folder = ConversationFolderSerializer(read_only=True)

    class Meta:
        model = Conversation
        fields = ["id", "title", "folder", "is_pinned", "message_count", "created_at", "updated_at"]


class ConversationDetailSerializer(serializers.ModelSerializer):
    messages = MessageSerializer(many=True, read_only=True)
    folder = ConversationFolderSerializer(read_only=True)

    class Meta:
        model = Conversation
        fields = ["id", "title", "folder", "is_pinned", "messages", "created_at", "updated_at"]


class ChatSendSerializer(serializers.Serializer):
    query = serializers.CharField()
    conversation_id = serializers.IntegerField(required=False, allow_null=True)
    file_paths = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    file_names = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    allowed_tools = serializers.ListField(child=serializers.CharField(), required=False, allow_null=True, default=None)


class PromptLibrarySerializer(serializers.ModelSerializer):
    class Meta:
        model = PromptLibrary
        fields = ["id", "title", "content", "is_system", "created_at", "updated_at"]


# ── 用户记忆 ──

class UserMemorySerializer(serializers.ModelSerializer):
    class Meta:
        model = UserMemory
        fields = ["id", "fact", "category", "confidence", "source_conv_id", "created_at", "updated_at", "access_count"]


class MemoryBatchWriteSerializer(serializers.Serializer):
    """批量写入记忆的请求格式"""
    facts = serializers.ListField(child=serializers.DictField())
    agent_name = serializers.CharField(default="default")
    conversation_id = serializers.IntegerField(required=False, allow_null=True)
