"""治理中心数据模型 (SQLAlchemy)。

五张表 (S67 dashboard_spec.md §3.2 + ARCH-ROUND 2 RBAC):
  - agents          代理清单
  - audit_events    审计事件 (evaluate_verified 自动入库)
  - vce_scans       VCE 扫描历史 (趋势图数据源)
  - policy_snapshots 策略快照 (编译时入库)
  - users           治理用户 (RBAC: viewer/auditor/admin, GAP-3.1)
"""
from datetime import datetime

from sqlalchemy import (JSON, Boolean, Column, DateTime, Float, ForeignKey,
                        Integer, String, Text)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class User(Base):
    """治理用户（JWT 认证 + 角色访问控制, ARCH-ROUND 2 / GAP-3.1）。

    角色: viewer(只读) < auditor(查看审计+验证) < admin(策略部署+用户管理)
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)   # passlib bcrypt
    role = Column(String, default="viewer", nullable=False)  # viewer/auditor/admin
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)


class Agent(Base):
    __tablename__ = "agents"

    id = Column(String, primary_key=True)       # agent_id
    name = Column(String, nullable=False)
    role = Column(String, default="executor")   # 执行器/审查器/规划器...
    status = Column(String, default="active")   # active/idle/suspended
    last_seen = Column(DateTime, default=datetime.utcnow)
    sessions = Column(Integer, default=0)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(DateTime, default=datetime.utcnow, index=True)
    agent_id = Column(String, ForeignKey("agents.id"), index=True)
    path = Column(String, default="")
    method = Column(String, default="POST")
    matched_rule = Column(String, index=True)
    action = Column(String, index=True)         # 最终动作 (含降级后 ESCALATE)
    channel = Column(String, default="none", index=True)
    verification = Column(JSON, default=dict)   # VerificationResult.to_dict()
    raw_body = Column(JSON, default=dict)       # 请求体 (声明)


class VceScan(Base):
    __tablename__ = "vce_scans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(DateTime, default=datetime.utcnow)
    report = Column(JSON, default=dict)         # vce_scan_report 全量快照
    polarization = Column(Float, default=0.0, index=True)
    conflict_count = Column(Integer, default=0)
    blindspot_count = Column(Integer, default=0)
    channel_enabled = Column(Boolean, default=False)


class PolicySnapshot(Base):
    __tablename__ = "policy_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(DateTime, default=datetime.utcnow)
    protocol = Column(String, index=True)
    rule_type = Column(String)                  # ethics/enforce/ok
    rule_name = Column(String)
    priority = Column(Integer)
    action = Column(String)
    json_path = Column(String, default="")
    json_pattern = Column(Text, default="")
    origin = Column(String, default="")
