"""
Module F: Human-in-the-Loop (HIL) — mandatory confirmation for critical operations.
Stores pending tasks as JSON files; user must approve before execution.
"""

import json
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional


@dataclass
class PendingTask:
    """A task requiring human confirmation before execution."""

    task_id: str
    description: str
    action_type: str  # firmware_flash, config_modify, pcb_change, code_deploy, etc.
    parameters: Dict[str, Any] = field(default_factory=dict)
    status: str = "pending"  # pending, approved, rejected, executed, expired
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    approved_at: Optional[str] = None
    approved_by: Optional[str] = None
    expires_after_hours: int = 24
    risk_level: str = "medium"  # low, medium, high, critical
    rollback_instructions: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "description": self.description,
            "action_type": self.action_type,
            "parameters": self.parameters,
            "status": self.status,
            "created_at": self.created_at,
            "approved_at": self.approved_at,
            "approved_by": self.approved_by,
            "expires_after_hours": self.expires_after_hours,
            "risk_level": self.risk_level,
            "rollback_instructions": self.rollback_instructions,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PendingTask":
        return cls(
            task_id=data["task_id"],
            description=data.get("description", ""),
            action_type=data.get("action_type", ""),
            parameters=data.get("parameters", {}),
            status=data.get("status", "pending"),
            created_at=data.get("created_at", ""),
            approved_at=data.get("approved_at"),
            approved_by=data.get("approved_by"),
            expires_after_hours=data.get("expires_after_hours", 24),
            risk_level=data.get("risk_level", "medium"),
            rollback_instructions=data.get("rollback_instructions"),
        )


# ── Critical action types ──────────────────────────────────────────────────

CRITICAL_ACTIONS = {
    "firmware_flash": {"risk": "high", "rollback": "Re-flash previous firmware version"},
    "config_modify": {"risk": "medium", "rollback": "Restore config from backup (.bak file)"},
    "pcb_change": {"risk": "critical", "rollback": "Use Git to revert KiCad files"},
    "code_deploy": {"risk": "medium", "rollback": "Git revert to previous commit"},
    "dependency_upgrade": {"risk": "medium", "rollback": "pip install previous version"},
    "hardware_test": {"risk": "low", "rollback": "N/A — read-only"},
    "schematic_modify": {"risk": "high", "rollback": "Git revert schematic files"},
}

DEFAULT_PENDING_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", ".aionui", "pending_tasks"
)


class HILManager:
    """Manages the human-in-the-loop task queue."""

    def __init__(self, pending_dir: Optional[str] = None):
        self.pending_dir = pending_dir or DEFAULT_PENDING_DIR
        os.makedirs(self.pending_dir, exist_ok=True)

    def create_task(
        self,
        description: str,
        action_type: str,
        parameters: Optional[Dict[str, Any]] = None,
        risk_level: Optional[str] = None,
    ) -> PendingTask:
        """Create a pending task requiring human approval."""
        task_id = f"HIL-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"

        if risk_level is None and action_type in CRITICAL_ACTIONS:
            risk_level = CRITICAL_ACTIONS[action_type]["risk"]

        rollback = None
        if action_type in CRITICAL_ACTIONS:
            rollback = CRITICAL_ACTIONS[action_type]["rollback"]

        task = PendingTask(
            task_id=task_id,
            description=description,
            action_type=action_type,
            parameters=parameters or {},
            risk_level=risk_level or "medium",
            rollback_instructions=rollback,
        )

        self._save_task(task)
        return task

    def approve_task(self, task_id: str, approved_by: str = "user") -> Optional[PendingTask]:
        """Approve and execute a pending task."""
        task = self._load_task(task_id)
        if task is None:
            return None
        if task.status != "pending":
            print(f"[HIL] Task {task_id} already {task.status}")
            return task

        task.status = "approved"
        task.approved_at = datetime.now().isoformat()
        task.approved_by = approved_by
        self._save_task(task)

        # Execute
        success = self._execute_action(task)
        task.status = "executed" if success else "rejected"
        self._save_task(task)
        return task

    def reject_task(self, task_id: str, reason: str = "") -> Optional[PendingTask]:
        """Reject a pending task."""
        task = self._load_task(task_id)
        if task is None:
            return None
        task.status = "rejected"
        task.parameters["reject_reason"] = reason
        self._save_task(task)
        return task

    def get_pending_tasks(self) -> List[PendingTask]:
        """Get all tasks still awaiting approval."""
        tasks = []
        if not os.path.isdir(self.pending_dir):
            return tasks
        for fname in os.listdir(self.pending_dir):
            if not fname.endswith(".json"):
                continue
            task = self._load_task_by_filename(fname)
            if task and task.status == "pending":
                # Check expiration
                created = datetime.fromisoformat(task.created_at)
                age_hours = (datetime.now() - created).total_seconds() / 3600
                if age_hours > task.expires_after_hours:
                    task.status = "expired"
                    self._save_task(task)
                    continue
                tasks.append(task)
        return tasks

    def get_all_tasks(self) -> List[PendingTask]:
        """Get all tasks (any status)."""
        tasks = []
        if not os.path.isdir(self.pending_dir):
            return tasks
        for fname in sorted(os.listdir(self.pending_dir)):
            if fname.endswith(".json"):
                task = self._load_task_by_filename(fname)
                if task:
                    tasks.append(task)
        return tasks

    def summary(self) -> str:
        """Human-readable summary of pending tasks."""
        pending = self.get_pending_tasks()
        if not pending:
            return "✅ No pending tasks requiring approval."

        lines = [f"⚠️  {len(pending)} pending task(s) requiring approval:"]
        for t in pending:
            lines.append(
                f"  [{t.risk_level.upper():8s}] {t.task_id} — {t.description[:60]} "
                f"({t.action_type})"
            )
        return "\n".join(lines)

    # ── Internals ──

    def _task_path(self, task_id: str) -> str:
        return os.path.join(self.pending_dir, f"{task_id}.json")

    def _save_task(self, task: PendingTask):
        path = self._task_path(task.task_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(task.to_dict(), f, indent=2, ensure_ascii=False)

    def _load_task(self, task_id: str) -> Optional[PendingTask]:
        path = self._task_path(task_id)
        if not os.path.exists(path):
            return None
        return self._load_task_by_path(path)

    def _load_task_by_filename(self, filename: str) -> Optional[PendingTask]:
        path = os.path.join(self.pending_dir, filename)
        return self._load_task_by_path(path)

    @staticmethod
    def _load_task_by_path(path: str) -> Optional[PendingTask]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return PendingTask.from_dict(data)
        except Exception:
            return None

    @staticmethod
    def _execute_action(task: PendingTask) -> bool:
        """Execute the approved action. Extend this with real executors."""
        print(f"[HIL] Executing {task.action_type}: {task.description}")
        print(f"[HIL] Parameters: {json.dumps(task.parameters, indent=2)}")
        # In production, hook into actual operation executors here
        return True


# ── Global singleton ────────────────────────────────────────────────────────

hil_manager = HILManager()
