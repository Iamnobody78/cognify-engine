"""p2_env.py 单元测试 (tmp_path 假 .env, 不触网)."""

import pathlib
import sys

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT))
import p2_env as pe

# 测试用假 key — 故意含连字符, 避免命中 GitHub secret-scan 模式 (sk- + 20+ 字母数字)
FAKE_KEY = "sk-test-fake-key-not-a-real-secret"
GOOD_ENV = f"""FAST_LLM="deepseek:deepseek-chat"
SMART_LLM="deepseek:deepseek-chat"
STRATEGIC_LLM="deepseek:deepseek-reasoner"
DEEPSEEK_API_KEY="{FAKE_KEY}"
RETRIEVER="duckduckgo"
"""


# ---------- write-template ----------

def test_write_template_creates(tmp_path, capsys):
    env = tmp_path / ".env"
    assert pe.write_template(env) == 0
    text = env.read_text(encoding="utf-8")
    assert "DEEPSEEK_API_KEY" in text and "sk-REPLACE_ME" in text
    assert "RETRIEVER=" in text and "duckduckgo" in text
    assert "✅" in capsys.readouterr().out


def test_write_template_no_overwrite(tmp_path, capsys):
    env = tmp_path / ".env"
    env.write_text("CUSTOM=1\n", encoding="utf-8")
    assert pe.write_template(env) == 1  # 已存在 → 跳过
    assert env.read_text(encoding="utf-8") == "CUSTOM=1\n"
    assert "未覆盖" in capsys.readouterr().out


def test_write_template_force(tmp_path):
    env = tmp_path / ".env"
    env.write_text("CUSTOM=1\n", encoding="utf-8")
    assert pe.write_template(env, force=True) == 0
    assert "sk-REPLACE_ME" in env.read_text(encoding="utf-8")


# ---------- validate ----------

def test_validate_good(tmp_path, capsys):
    env = tmp_path / ".env"
    env.write_text(GOOD_ENV, encoding="utf-8")
    assert pe.validate(env) == 0
    assert "校验通过" in capsys.readouterr().out


def test_validate_placeholder_key(tmp_path, capsys):
    env = tmp_path / ".env"
    env.write_text(
        GOOD_ENV.replace(f'DEEPSEEK_API_KEY="{FAKE_KEY}"',
                         'DEEPSEEK_API_KEY="sk-REPLACE_ME"'),
        encoding="utf-8")
    assert pe.validate(env) == 1
    assert "未填写" in capsys.readouterr().out


def test_validate_suspicious_key_format(tmp_path, capsys):
    env = tmp_path / ".env"
    env.write_text(GOOD_ENV.replace(FAKE_KEY, "short"), encoding="utf-8")
    assert pe.validate(env) == 1
    assert "格式可疑" in capsys.readouterr().out


def test_validate_bad_model_and_retriever(tmp_path, capsys):
    env = tmp_path / ".env"
    bad = (GOOD_ENV
           .replace("deepseek:deepseek-chat", "openai:gpt-4")
           .replace('RETRIEVER="duckduckgo"', 'RETRIEVER="bogus"'))
    env.write_text(bad, encoding="utf-8")
    assert pe.validate(env) == 1
    out = capsys.readouterr().out
    assert "FAST_LLM" in out and "RETRIEVER" in out


def test_validate_tavily_warns(tmp_path, capsys):
    env = tmp_path / ".env"
    env.write_text(GOOD_ENV.replace('RETRIEVER="duckduckgo"', 'RETRIEVER="tavily"'),
                   encoding="utf-8")
    assert pe.validate(env) == 1
    assert "tavily" in capsys.readouterr().out


def test_validate_missing_file(tmp_path, capsys):
    assert pe.validate(tmp_path / "nope.env") == 2
    assert "不存在" in capsys.readouterr().err


def test_validate_quoted_values(tmp_path):
    """单引号/无引号值也应正确解析。"""
    env = tmp_path / ".env"
    env.write_text(GOOD_ENV.replace('"', "'"), encoding="utf-8")
    assert pe.validate(env) == 0


# ---------- ollama 本地模式 (零 API Key) ----------

OLLAMA_ENV = """FAST_LLM="ollama:qwen2.5:7b"
SMART_LLM="ollama:qwen2.5:7b"
STRATEGIC_LLM="ollama:qwen2.5:7b"
OLLAMA_BASE_URL="http://localhost:11434"
EMBEDDING="ollama:bge-m3"
RETRIEVER="duckduckgo"
"""

def test_validate_ollama_zero_key(tmp_path, capsys):
    """ollama 模式无需 DEEPSEEK_API_KEY, 应通过。"""
    env = tmp_path / ".env"
    env.write_text(OLLAMA_ENV, encoding="utf-8")
    assert pe.validate(env) == 0
    assert "ollama(零key)" in capsys.readouterr().out

def test_validate_ollama_bad_embedding(tmp_path, capsys):
    """EMBEDDING provider 不受支持 → 失败。"""
    env = tmp_path / ".env"
    env.write_text(OLLAMA_ENV.replace("ollama:bge-m3", "azure:text-embedding-3"),
                   encoding="utf-8")
    assert pe.validate(env) == 1
    assert "EMBEDDING" in capsys.readouterr().out

def test_validate_ollama_missing_base_url(tmp_path, capsys):
    """ollama 模式缺 OLLAMA_BASE_URL → 失败。"""
    env = tmp_path / ".env"
    env.write_text(OLLAMA_ENV.replace('OLLAMA_BASE_URL="http://localhost:11434"\n', ""),
                   encoding="utf-8")
    assert pe.validate(env) == 1
    assert "OLLAMA_BASE_URL" in capsys.readouterr().out

def test_validate_ollama_bad_base_url(tmp_path, capsys):
    """OLLAMA_BASE_URL 非 http(s):// → 失败。"""
    env = tmp_path / ".env"
    env.write_text(OLLAMA_ENV.replace("http://localhost:11434", "localhost:11434"),
                   encoding="utf-8")
    assert pe.validate(env) == 1
    assert "OLLAMA_BASE_URL" in capsys.readouterr().out

def test_validate_ollama_unknown_model(tmp_path, capsys):
    """ollama 模型不在已知列表 → 告警。"""
    env = tmp_path / ".env"
    env.write_text(OLLAMA_ENV.replace("qwen2.5:7b", "my-custom-model"), encoding="utf-8")
    assert pe.validate(env) == 1
    out = capsys.readouterr().out
    assert "my-custom-model" in out and "KNOWN_OLLAMA_MODELS" in out

def test_validate_mixed_deepseek_still_needs_key(tmp_path, capsys):
    """任一 LLM 为 deepseek: → key 仍必需。"""
    env = tmp_path / ".env"
    mixed = OLLAMA_ENV.replace('SMART_LLM="ollama:qwen2.5:7b"',
                               'SMART_LLM="deepseek:deepseek-chat"')
    env.write_text(mixed, encoding="utf-8")
    assert pe.validate(env) == 1
    assert "DEEPSEEK_API_KEY" in capsys.readouterr().out

def test_write_template_has_ollama_section(tmp_path):
    """模板应同时含 ollama 零-key 与 deepseek 两种模式。"""
    env = tmp_path / ".env"
    assert pe.write_template(env) == 0
    text = env.read_text(encoding="utf-8")
    assert "ollama:qwen2.5:7b" in text
    assert "OLLAMA_BASE_URL" in text
    assert "DEEPSEEK_API_KEY" in text  # 注释保留的 deepseek 模式
