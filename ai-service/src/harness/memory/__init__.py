"""
异步记忆系统

核心组件：
- MemoryStorage: 存储抽象层
- DjangoMemoryStorage: 通过 Django API 存储记忆到 MySQL
- MemoryUpdater: 使用 LLM 从对话中抽取事实
"""
from .storage import MemoryStorage, DjangoMemoryStorage
from .updater import MemoryUpdater
