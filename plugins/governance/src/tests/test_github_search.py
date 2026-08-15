"""github_search.py 单元测试 (mock http_get/subprocess, 不触网)."""

import io
import json
import os
import subprocess
import sys
import pathlib
import urllib.error

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT))
import github_search as ghs

REPO_JSON = json.dumps({"items": [
    {"full_name": "agent/governance", "stargazers_count": 1234,
     "language": "Python", "description": "A governance framework",
     "html_url": "https://github.com/agent/governance", "updated_at": "2026-07-01T00:00:00Z"},
    {"full_name": "user/tool", "stargazers_count": 42,
     "language": "Go", "description": None,
     "html_url": "https://github.com/user/tool", "updated_at": "2026-06-15T00:00:00Z"},
]})
EMPTY_JSON = json.dumps({"items": []})


def _fake_fetch(raw: str):
    def fetcher(url: str, timeout: float = 20, headers: dict | None = None) -> str:
        return raw
    return fetcher


def test_parse_fields():
    repos = ghs.search_repos("governance", http_get=_fake_fetch(REPO_JSON))
    assert len(repos) == 2
    r = repos[0]
    assert r["full_name"] == "agent/governance"
    assert r["stars"] == 1234
    assert r["language"] == "Python"
    assert r["description"] == "A governance framework"
    assert r["html_url"].startswith("https://github.com/")
    assert repos[1]["description"] == ""  # null → 空串


def test_empty_result():
    assert ghs.search_repos("zzz", http_get=_fake_fetch(EMPTY_JSON)) == []


def test_url_and_auth_header():
    captured = {}

    def fetcher(url: str, timeout: float = 20, headers: dict | None = None) -> str:
        captured["url"] = url
        captured["headers"] = headers
        return EMPTY_JSON

    ghs.search_repos("tree-sitter AST", max_results=7, token="tok-1", http_get=fetcher)
    assert "q=tree-sitter%20AST" in captured["url"]
    assert "sort=stars" in captured["url"]
    assert "per_page=7" in captured["url"]
    assert captured["headers"]["Authorization"] == "Bearer tok-1"


def test_no_auth_header_without_token():
    captured = {}

    def fetcher(url: str, timeout: float = 20, headers: dict | None = None) -> str:
        captured["headers"] = headers
        return EMPTY_JSON

    ghs.search_repos("x", token=None, http_get=fetcher)
    assert "Authorization" not in captured["headers"]


def test_get_token_env(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.setenv("GITHUB_TOKEN", "env-tok")

    def fake_run(*a, **k):
        raise AssertionError("不应调用 gh CLI")
    monkeypatch.setattr(subprocess, "run", fake_run)
    assert ghs.get_token() == "env-tok"
    assert ghs.get_token("explicit") == "explicit"  # --token 优先


def test_get_token_gh_fallback(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)

    class FakeOut:
        stdout = "gh-token-abc\n"
        returncode = 0
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: FakeOut())
    assert ghs.get_token() == "gh-token-abc"


def test_get_token_none(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(OSError()))
    assert ghs.get_token() is None


def test_main_json_output(capsys, monkeypatch):
    monkeypatch.setattr(ghs, "get_token", lambda explicit=None: None)
    monkeypatch.setattr(ghs, "_http_get", lambda url, timeout=20, headers=None: REPO_JSON)
    assert ghs.main(["governance", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert len(data) == 2 and data[0]["full_name"] == "agent/governance"


def test_main_table_output(capsys, monkeypatch):
    monkeypatch.setattr(ghs, "get_token", lambda explicit=None: None)
    monkeypatch.setattr(ghs, "_http_get", lambda url, timeout=20, headers=None: REPO_JSON)
    assert ghs.main(["governance"]) == 0
    out = capsys.readouterr().out
    assert "🐙 GitHub: 2 个仓库" in out
    assert "agent/governance ⭐1234" in out


def test_main_http_error_exit2(capsys, monkeypatch):
    monkeypatch.setattr(ghs, "get_token", lambda explicit=None: "bad-tok")

    def boom(url, timeout=20, headers=None):
        raise urllib.error.HTTPError(url, 401, "Unauthorized", {}, io.BytesIO(b""))
    monkeypatch.setattr(ghs, "_http_get", boom)
    assert ghs.main(["governance"]) == 2
    err = capsys.readouterr().err
    assert "401" in err and "token" in err
