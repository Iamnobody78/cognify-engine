#!/usr/bin/env python3
# S34 P1 v2: D5 蒸馏三强规则写入 engineering_rules.md（字节级，保持 CRLF 行尾）
# v2 修复：PR 表与 HC 标题间补空行；复用原 --- 分隔线（不产生重复）；footer 独立一行
import sys

path = r"/mnt/c/Users/ivy/AppData/Roaming/AionUi/aionui/conversations/2026/07/27/aionrs-temp-48324704/bottlesumo_pi/governance/dashboard/engineering_rules.md"

with open(path, "rb") as f:
    raw = f.read()

eol = b"\r\n" if b"\r\n" in raw else b"\n"
text = raw.decode("utf-8")
eol_s = eol.decode("utf-8")

# 新章节：以空行开头（与 PR 表分隔），结尾不含 ---（复用原分隔线）
new_section = (
    eol_s +
    "## 高置信度规则 (HC) —— D5 蒸馏入库 (Sprint 34)" + eol_s + eol_s +
    "> 来源：D5 置信度校准 (experience/distill_rules_20260808_192416.json，conf≥0.3 三强规则)。" + eol_s +
    "> 用途：抑制已知 REGRESSION 方向、锁定已解决特征，指导后续候选生成，防止重复探索已证伪拓扑。" + eol_s + eol_s +
    "| ID | 规则 | 来源 |" + eol_s +
    "| :--- | :--- | :--- |" + eol_s +
    "| RULE-HC-001 | **FLANK 阈值收窄 ±10→±15 为 REGRESSION 方向**（topo_B, conf=0.48）：avg_steps +3.4、熵 Δ+0.024（S29 最强信号）；候选生成禁止沿 FLANK 收窄方向，需在效率约束下放宽 | D5 校准 (S33) |" + eol_s +
    "| RULE-HC-002 | **flank dist 0.15 截止为 REGRESSION 方向**（mapping_001, conf=0.30）：avg_steps +7.9，4 次复现（S27v3/S29/S31/S33）；特征已解决，保持锁定，禁止重试该映射变体 | D5 校准 (S33) |" + eol_s +
    "| RULE-HC-003 | **CLOSE-PUSH edge 0.65→0.80 对齐为 SUSPICIOUS 边界**（topo_A, conf=0.26）：Q=+0.02、熵 Δ+0.013，CAUTIOUS-EDGE 触发域被吸收（13→0）；M2 捕获微信号，可作保守探索参考，不承诺胜率收益 | D5 校准 (S33) |" + eol_s
)

marker = eol_s + "---" + eol_s

if "RULE-HC-001" in text:
    print("ALREADY PRESENT - no change")
    sys.exit(0)

idx = text.find(marker)
if idx < 0:
    print("ERROR: separator marker not found")
    sys.exit(1)

text = text[:idx] + new_section + text[idx:]

# 更新底部维护行（保持独立一行，前面已有空行）
old_footer = "*维护：治理智能体 | 更新：2026-08-05 (SEED-ROUND-1)*"
new_footer = "*维护：治理智能体 | 更新：2026-08-08 (Sprint 34 D5 蒸馏入库)*"
if old_footer in text:
    text = text.replace(old_footer, new_footer)

with open(path, "wb") as f:
    f.write(text.encode("utf-8"))

print("OK: HC section inserted before separator, footer updated")
