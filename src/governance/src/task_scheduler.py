"""Priority task scheduler backed by a heap.

Implements the TASK-SCHED-002 interface contract:

- SMALLER priority number = HIGHER priority (1 beats 5).
- Equal priorities are served FIFO (insertion order preserved).
- Empty queue: ``pop()`` / ``peek()`` return ``None`` (never raise).
- Invalid inputs: ``push()`` with an empty/whitespace ``task_id`` or a
  non-integer ``priority`` raises ``ValueError``.

The queue is backed by a heap of ``(priority, insertion_counter,
task_id, payload)`` tuples. The monotonically increasing insertion
counter guarantees FIFO ordering among equal priorities without any
extra tie-break comparisons on the task payloads.
"""

import heapq
import itertools
from typing import Any, Optional, Tuple


class TaskScheduler:
    """A priority queue scheduler satisfying the TASK-SCHED-002 contract."""

    def __init__(self) -> None:
        """Create an empty task scheduler."""
        self._heap: list[Tuple[int, int, str, Any]] = []
        self._counter = itertools.count()

    def push(self, task_id: str, priority: int, payload: object = None) -> None:
        """Insert a task into the scheduler.

        Args:
            task_id: Unique identifier for the task. Must be a non-empty
                string; empty or whitespace-only values raise ``ValueError``.
            priority: Scheduling priority. Smaller numbers mean higher
                priority. Must be an integer (bool excluded); anything
                else raises ``ValueError``.
            payload: Optional application data associated with the task.

        Raises:
            ValueError: If ``task_id`` is empty/whitespace (or not a
                string) or ``priority`` is not an integer.
        """
        if not isinstance(task_id, str) or not task_id.strip():
            raise ValueError("task_id must be a non-empty string")
        if not isinstance(priority, int) or isinstance(priority, bool):
            raise ValueError("priority must be an integer")
        heapq.heappush(
            self._heap,
            (priority, next(self._counter), task_id, payload),
        )

    def pop(self) -> Optional[Tuple[str, object]]:
        """Remove and return the highest-priority task.

        Returns:
            A ``(task_id, payload)`` tuple for the highest-priority task
            (lowest priority number; FIFO among equal priorities), or
            ``None`` if the queue is empty.
        """
        if not self._heap:
            return None
        _, _, task_id, payload = heapq.heappop(self._heap)
        return task_id, payload

    def peek(self) -> Optional[Tuple[str, object]]:
        """Return the highest-priority task without removing it.

        Returns:
            A ``(task_id, payload)`` tuple for the highest-priority task,
            or ``None`` if the queue is empty. The queue is not modified.
        """
        if not self._heap:
            return None
        _, _, task_id, payload = self._heap[0]
        return task_id, payload

    def size(self) -> int:
        """Return the number of tasks currently in the scheduler."""
        return len(self._heap)

    def is_empty(self) -> bool:
        """Return ``True`` if the scheduler holds no tasks."""
        return len(self._heap) == 0

    def clear(self) -> None:
        """Remove all tasks from the scheduler."""
        self._heap = []
        self._counter = itertools.count()
