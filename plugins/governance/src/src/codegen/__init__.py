# -*- coding: utf-8 -*-
"""src.codegen -- P11 编译式自生成（YAML 策略 -> Python 匹配函数）。

模块布局:
    generator.py          -- YAML->Python 匹配函数编译器（确定性 + 幂等）
    _generated_matches.py -- 生成产物（DO NOT EDIT；由 generator 重新生成）

诚实边界见 docs/META_CAPABILITIES.md（自生成 = 编译式生成，非 LLM 合成）。
"""
