"""结构化日志（JSON/plain 双格式，GOV_LOG_FORMAT 控制，零额外依赖）。

用法:
    from logging_setup import setup_logging, get_logger
    setup_logging()                    # 应用启动时调用一次
    log = get_logger("governance.api")
    log.info("deploy", protocol="demo", status="ok")
"""
import json
import logging
import os
import sys
import time

_EXTRA_KEYS = ("endpoint", "outcome", "duration_ms", "protocol", "status", "engine")


class JsonFormatter(logging.Formatter):
    """JSON 结构化输出（审计友好，可直接进 ELK/Loki）。"""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key in _EXTRA_KEYS:
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """初始化 governance 根 logger（幂等：重复调用不叠加 handler）。"""
    fmt = os.getenv("GOV_LOG_FORMAT", "plain")
    logger = logging.getLogger("governance")
    if logger.handlers:
        return logger
    handler = logging.StreamHandler(sys.stdout)
    if fmt == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
    logger.setLevel(level)
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"governance.{name}")
