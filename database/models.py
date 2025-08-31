from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Text, Numeric, Index, BigInteger
from sqlalchemy.orm import relationship, validates
from datetime import datetime
import re

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

    __table_args__ = (
        Index('ix_user_telegram_id', 'telegram_id'),
        Index('ix_user_username', 'username'),
    )

    # @validates('username')
    # def validate_username(self, key, username):
    #     """Валидация username"""
    #     if username and not username.startswith('@'):
    #         username = f'@{username}'
    #     return username

    def __repr__(self):
        return f"<User(id={self.id}, username={self.username})>"


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

    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    payment_id = Column(String(100), unique=True, nullable=True)
    payment_method = Column(String(50), nullable=True)

    user = relationship("User", back_populates="subscriptions")

    __table_args__ = (
        Index('ix_subscription_user_id', 'user_id'),
        Index('ix_subscription_status', 'status'),
        Index('ix_subscription_payment_id', 'payment_id'),
    )

    # @validates('plan_type')
    # def validate_plan_type(self, key, plan_type):
    #     valid_types = ['regular', 'student', 'trial']
    #     if plan_type not in valid_types:
    #         raise ValueError(f"Invalid plan type. Must be one of: {valid_types}")
    #     return plan_type
    #
    # @validates('status')
    # def validate_status(self, key, status):
    #     valid_statuses = ['pending', 'active', 'canceled', 'expired']
    #     if status not in valid_statuses:
    #         raise ValueError(f"Invalid status. Must be one of: {valid_statuses}")
    #     return status

    def is_active(self):
        return self.status == 'active' and self.end_date and self.end_date > datetime.utcnow()

    def days_remaining(self):
        if self.is_active() and self.end_date:
            return (self.end_date - datetime.utcnow()).days
        return 0

    def __repr__(self):
        return f"<Subscription(id={self.id}, user_id={self.user_id}, status={self.status})>"
