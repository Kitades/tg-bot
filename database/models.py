from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Text, Numeric, Index, BigInteger
from sqlalchemy.orm import relationship
from datetime import datetime

from database.session import Base


class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String(100), nullable=True, index=True)
    full_name = Column(String(200), nullable=False)
    language_code = Column(String(10), default='ru')
    is_premium = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    subscriptions = relationship("Subscription", back_populates="user", cascade="all, delete-orphan")
    user_settings = relationship("UserSettings", back_populates="user", cascade="all, delete-orphan")

    __table_args__ = (
        Index('ix_user_telegram_id', 'telegram_id'),
        Index('ix_user_username', 'username'),
    )

    def __repr__(self):
        return f"<User(id={self.id}, username={self.username})>"


class UserSettings(Base):
    __tablename__ = 'user_settings'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    wants_free_posts = Column(Boolean, default=True)
    timezone = Column(String, default="UTC")

    user = relationship("User", back_populates="user_settings")


class FreeDailyPost(Base):
    __tablename__ = 'free_daily_posts'

    id = Column(Integer, primary_key=True)
    content = Column(Text, nullable=False)
    photo_path = Column(String, nullable=True)
    photo_file_id = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    scheduled_time = Column(String, default="10:00")  # Время для бесплатной рассылки
    created_at = Column(DateTime, default=datetime.utcnow)


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    plan_type = Column(String(50), nullable=False)  # 'regular', 'student'
    plan_name = Column(String(100), nullable=False)  # 'Обычный', 'Студенческий'
    price = Column(Numeric(10, 2), nullable=False)  # 8000.00, 5000.00
    currency = Column(String(3), default='RUB')

    status = Column(String(20), default='pending', nullable=False)  # pending, active, canceled, expired
    payment_status = Column(String(20), default='pending')  # pending, completed, failed
    subscription_id = Column(String, index=True)  # ID подписки в ЮКассе
    auto_renew = Column(Boolean, default=True)  # Флаг автосписания
    metadata_json = Column(Text)  # Дополнительные данные от ЮКассы

    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    next_payment_date = Column(DateTime, )

    payment_id = Column(String(100), unique=True, nullable=True)
    payment_method = Column(String(50), nullable=True)

    user = relationship("User", back_populates="subscriptions")

    __table_args__ = (
        Index('ix_subscription_user_id', 'user_id'),
        Index('ix_subscription_status', 'status'),
        Index('ix_subscription_payment_id', 'payment_id'),
    )

    def __repr__(self):
        return f"<Subscription(id={self.id}, user_id={self.user_id}, status={self.status})>"

