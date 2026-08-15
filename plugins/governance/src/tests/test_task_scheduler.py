"""Tests for src.task_scheduler (TASK-SCHED-002).

Contract under test (exact):
- ``TaskScheduler.push(task_id: str, priority: int, payload=None) -> None``
- ``pop() -> tuple[str, object] | None``
- ``peek() -> tuple[str, object] | None``
- ``size() -> int``
- ``is_empty() -> bool``
- ``clear() -> None``
- SMALLER priority = HIGHER. Same priority = FIFO.
- pop/peek on empty return None (never raise).
- push with empty/whitespace task_id or non-int priority raises ValueError.
"""

import pytest

from src.task_scheduler import TaskScheduler


def test_highest_priority_first():
    sched = TaskScheduler()
    sched.push("low", 10)
    sched.push("high", 1)
    sched.push("mid", 5)
    assert sched.pop() == ("high", None)
    assert sched.pop() == ("mid", None)
    assert sched.pop() == ("low", None)
    assert sched.pop() is None


def test_same_priority_fifo():
    sched = TaskScheduler()
    sched.push("first", 3)
    sched.push("second", 3)
    sched.push("third", 3)
    assert sched.pop() == ("first", None)
    assert sched.pop() == ("second", None)
    assert sched.pop() == ("third", None)


def test_interleaved_priority_and_fifo():
    sched = TaskScheduler()
    sched.push("a", 5)
    sched.push("b", 1)
    sched.push("c", 5)
    sched.push("d", 1)
    sched.push("e", 3)
    # Priority 1 group (FIFO: b then d), then priority 3, then priority 5 group (a then c)
    assert sched.pop() == ("b", None)
    assert sched.pop() == ("d", None)
    assert sched.pop() == ("e", None)
    assert sched.pop() == ("a", None)
    assert sched.pop() == ("c", None)
    assert sched.pop() is None


def test_peek_is_non_destructive():
    sched = TaskScheduler()
    sched.push("task", 2, payload={"x": 1})
    assert sched.size() == 1
    assert sched.peek() == ("task", {"x": 1})
    assert sched.peek() == ("task", {"x": 1})
    assert sched.size() == 1
    assert sched.is_empty() is False
    assert sched.pop() == ("task", {"x": 1})
    assert sched.size() == 0


def test_peek_empty_returns_none():
    sched = TaskScheduler()
    assert sched.peek() is None
    sched.push("t", 1)
    sched.pop()
    assert sched.peek() is None


def test_pop_empty_returns_none():
    sched = TaskScheduler()
    assert sched.pop() is None
    sched.push("t", 1)
    sched.pop()
    assert sched.pop() is None


def test_size_and_is_empty_transitions():
    sched = TaskScheduler()
    assert sched.size() == 0
    assert sched.is_empty() is True
    sched.push("a", 1)
    sched.push("b", 2)
    assert sched.size() == 2
    assert sched.is_empty() is False
    sched.pop()
    assert sched.size() == 1
    assert sched.is_empty() is False
    sched.pop()
    assert sched.size() == 0
    assert sched.is_empty() is True


def test_clear_removes_all_tasks():
    sched = TaskScheduler()
    sched.push("a", 1)
    sched.push("b", 2)
    sched.push("c", 3)
    sched.clear()
    assert sched.size() == 0
    assert sched.is_empty() is True
    assert sched.pop() is None
    assert sched.peek() is None
    # Scheduler must remain fully usable after clear.
    sched.push("d", 0)
    assert sched.peek() == ("d", None)
    assert sched.pop() == ("d", None)


@pytest.mark.parametrize("bad_id", ["", "   ", "\t", "\n", " \n "])
def test_empty_or_whitespace_task_id_raises_value_error(bad_id):
    sched = TaskScheduler()
    with pytest.raises(ValueError):
        sched.push(bad_id, 1)
    assert sched.size() == 0


@pytest.mark.parametrize("bad_priority", [1.5, "3", None, [], (1,)])
def test_non_int_priority_raises_value_error(bad_priority):
    sched = TaskScheduler()
    with pytest.raises(ValueError):
        sched.push("task", bad_priority)
    assert sched.size() == 0


def test_payload_roundtrip():
    sched = TaskScheduler()
    obj = {"key": [1, 2, 3]}
    lst = ["x"]
    sched.push("t1", 2, payload=obj)
    sched.push("t2", 1, payload=lst)
    sched.push("t3", 3, payload=None)
    t2 = sched.pop()
    t1 = sched.pop()
    t3 = sched.pop()
    assert t2 == ("t2", lst)
    assert t2[1] is lst
    assert t1 == ("t1", obj)
    assert t1[1] is obj
    assert t3 == ("t3", None)


def test_100_item_global_order():
    """100 interleaved pushes; priority-ascending, FIFO within equal priority."""
    sched = TaskScheduler()
    n = 100
    for i in range(n):
        sched.push(f"task-{i}", i % 5, payload=i)
    assert sched.size() == n

    expected = []
    for p in range(5):
        for i in range(n):
            if i % 5 == p:
                expected.append((f"task-{i}", i))

    popped = [sched.pop() for _ in range(n)]
    assert popped == expected
    assert sched.pop() is None
    assert sched.is_empty() is True


def test_pop_returns_exactly_two_element_tuple():
    sched = TaskScheduler()
    sched.push("t", 1, payload="data")
    result = sched.pop()
    assert isinstance(result, tuple)
    assert len(result) == 2
    assert result[0] == "t"
    assert result[1] == "data"
