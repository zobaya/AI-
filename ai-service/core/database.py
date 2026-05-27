""" (MySQL) SQLAlchemy引擎和Session """
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from core.config import settings

# 数据库引擎
engine = None
# 会话工厂
SessionLocal = None
# 基础模型类
Base = declarative_base()


def init_db():
    """初始化数据库连接"""
    global engine, SessionLocal
    
    engine = create_engine(
        settings.MYSQL_URL,
        pool_pre_ping=True,  # 连接前检查连接是否有效
        pool_recycle=3600,   # 连接回收时间（秒）
        echo=settings.DEBUG,  # 是否打印 SQL 语句
    )
    
    SessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )


def get_db():
    """获取数据库会话（用于依赖注入）"""
    if SessionLocal is None:
        raise RuntimeError("数据库未初始化，请先调用 init_db()")
    
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def close_db():
    """关闭数据库连接"""
    global engine
    if engine:
        engine.dispose()
