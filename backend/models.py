from sqlalchemy import Column, Integer, String, Float, Date, DateTime, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import datetime

Base = declarative_base()

class Asset(Base):
    __tablename__ = "assets"
    id = Column(Integer, primary_key=True, index=True)
    category = Column(String)  # A股权益, A股ETF, 港股ETF, 债基, REITs, 现金
    name = Column(String)
    code = Column(String, unique=True, index=True)
    target_weight = Column(Float, default=0.0)
    remark = Column(Text)

class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, index=True)
    code = Column(String, index=True)
    name = Column(String)
    category = Column(String)
    direction = Column(String)  # 买入, 卖出, 分红, 存入, 取出
    quantity = Column(Float, default=0.0)
    price = Column(Float, default=0.0)
    amount = Column(Float)
    fee = Column(Float, default=0.0)
    remark = Column(Text)

class DailySnapshot(Base):
    __tablename__ = "daily_snapshots"
    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, unique=True, index=True)
    total_assets = Column(Float)
    invested_assets = Column(Float)
    cash = Column(Float)
    net_value = Column(Float, default=1.0)  # 净值，用于分析收益

class Holding(Base):
    """Derived or cached holdings for performance"""
    __tablename__ = "holdings"
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True)
    name = Column(String)
    quantity = Column(Float)
    avg_cost = Column(Float)
    diluted_cost = Column(Float) # 摊薄成本
    total_dividend = Column(Float, default=0.0)
    last_price = Column(Float)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow)
