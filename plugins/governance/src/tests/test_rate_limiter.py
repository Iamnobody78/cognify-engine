'''TASK-SCHED-003 tester: RateLimiter contract tests (written via MCP write_file).'''

import pytest

from src.rate_limiter import RateLimiter


def test_full_capacity_allows_until_exhausted():
    rl = RateLimiter(capacity=3)
    assert rl.allow('alpha') is True
    assert rl.allow('alpha') is True
    assert rl.allow('alpha') is True
    assert rl.allow('alpha') is False


def test_allow_false_does_not_consume():
    rl = RateLimiter(capacity=2)
    rl.allow('beta')
    rl.allow('beta')
    before = rl.remaining('beta')
    assert rl.allow('beta') is False
    assert rl.remaining('beta') == before == 0


def test_unknown_key_autocreates_full_bucket():
    rl = RateLimiter(capacity=5)
    assert rl.remaining('ghost') == 5
    assert rl.allow('ghost') is True
    assert rl.remaining('ghost') == 4


def test_refill_adds_tokens():
    rl = RateLimiter(capacity=4)
    rl.allow('gamma', tokens=3)
    assert rl.remaining('gamma') == 1
    rl.refill('gamma', 2)
    assert rl.remaining('gamma') == 3


def test_refill_caps_at_capacity():
    rl = RateLimiter(capacity=3)
    rl.allow('delta', tokens=2)
    rl.refill('delta', 10)
    assert rl.remaining('delta') == 3


def test_multi_key_isolation():
    rl = RateLimiter(capacity=2)
    assert rl.allow('key_a') is True
    assert rl.allow('key_b') is True
    assert rl.allow('key_b') is True
    assert rl.allow('key_b') is False
    assert rl.allow('key_a') is True
    assert rl.remaining('key_a') == 0
    assert rl.remaining('key_b') == 0


def test_remaining_unknown_key_is_capacity():
    rl = RateLimiter(capacity=7)
    assert rl.remaining('nope') == 7
    assert RateLimiter().remaining('default_cap') == 10


def test_init_invalid_capacity_raises():
    for bad in (0, -1, -100):
        with pytest.raises(ValueError):
            RateLimiter(capacity=bad)


def test_empty_or_whitespace_key_raises():
    rl = RateLimiter()
    for key in ('', '   ', '\t'):
        with pytest.raises(ValueError):
            rl.allow(key)
        with pytest.raises(ValueError):
            rl.refill(key, 1)
        with pytest.raises(ValueError):
            rl.remaining(key)


def test_invalid_tokens_raise():
    rl = RateLimiter()
    for bad in (0, -1, -5):
        with pytest.raises(ValueError):
            rl.allow('epsilon', tokens=bad)
        with pytest.raises(ValueError):
            rl.refill('epsilon', bad)
    for bad in ('x', 1.5, None):
        with pytest.raises(ValueError):
            rl.allow('epsilon', tokens=bad)


def test_multi_token_consume_works_when_enough():
    rl = RateLimiter(capacity=10)
    assert rl.allow('zeta', tokens=8) is True
    assert rl.remaining('zeta') == 2
    assert rl.allow('zeta', tokens=2) is True
    assert rl.remaining('zeta') == 0
    assert rl.allow('zeta', tokens=8) is False
    assert rl.remaining('zeta') == 0


def test_multi_token_partial_consume_is_atomic():
    rl = RateLimiter(capacity=4)
    rl.allow('eta', tokens=3)
    before = rl.remaining('eta')
    assert rl.allow('eta', tokens=2) is False
    assert rl.remaining('eta') == before == 1