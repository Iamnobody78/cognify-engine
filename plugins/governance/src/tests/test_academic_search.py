"""academic_search.py 单元测试 (mock http_get, 不触网)."""

import sys
import pathlib

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT))
import academic_search as acs

ATOM_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2601.06007v1</id>
    <title>Don&apos;t Break the Cache</title>
    <summary>We evaluate prompt caching in agent tasks and reduce cost by 45-80%.</summary>
    <published>2026-01-01T00:00:00Z</published>
    <author><name>Alice Zhang</name></author>
    <author><name>Bob Li</name></author>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2602.12345v1</id>
    <title>Learned Prefix Caching</title>
    <summary>First learned prefix cache eviction algorithm.</summary>
    <published>2026-02-15T00:00:00Z</published>
    <author><name>Carol Wang</name></author>
  </entry>
</feed>
"""

EMPTY_XML = '<?xml version="1.0" encoding="UTF-8"?>\n<feed xmlns="http://www.w3.org/2005/Atom"></feed>\n'


def _fake_fetch(content: str):
    def fetcher(url: str, timeout: float = 20) -> str:
        return content
    return fetcher


def test_parse_fields():
    papers = acs.search_papers("cache", http_get=_fake_fetch(ATOM_XML))
    assert len(papers) == 2
    p = papers[0]
    assert p["title"] == "Don't Break the Cache"          # XML 实体解码
    assert p["authors"] == ["Alice Zhang", "Bob Li"]
    assert p["published"] == "2026-01-01"
    assert p["url"] == "http://arxiv.org/abs/2601.06007v1"
    assert "45-80%" in p["abstract"]


def test_empty_result():
    assert acs.search_papers("nothing", http_get=_fake_fetch(EMPTY_XML)) == []


def test_url_built_correctly():
    captured = {}

    def fetcher(url: str, timeout: float = 20) -> str:
        captured["url"] = url
        return EMPTY_XML

    acs.search_papers("agent governance", max_results=5, http_get=fetcher)
    assert "search_query=all:agent%20governance" in captured["url"]
    assert "max_results=5" in captured["url"]
    assert "sortBy=relevance" in captured["url"]


def test_main_json_output(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(acs, "_http_get", lambda url, timeout=20: ATOM_XML)
    assert acs.main(["cache", "--json"]) == 0
    out = capsys.readouterr().out
    import json
    data = json.loads(out)
    assert len(data) == 2
    assert data[0]["title"] == "Don't Break the Cache"


def test_main_table_output(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(acs, "_http_get", lambda url, timeout=20: ATOM_XML)
    assert acs.main(["cache"]) == 0
    out = capsys.readouterr().out
    assert "📚 arXiv: 2 篇论文" in out
    assert "Don't Break the Cache" in out
    assert "http://arxiv.org/abs/2601.06007v1" in out


def test_main_network_error_exit2(tmp_path, capsys, monkeypatch):
    def boom(url, timeout=20):
        raise OSError("connection refused")
    monkeypatch.setattr(acs, "_http_get", boom)
    assert acs.main(["cache"]) == 2
    assert "ERROR: 学术搜索失败" in capsys.readouterr().err
