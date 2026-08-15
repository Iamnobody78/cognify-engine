# -*- coding: utf-8 -*-
"""批量执行 META-KB 迁移：处理 PM 提供的全部 8 个 Notion 链接，写入统一 manifest。"""
import io, json, os, sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))

import meta_kb

URLS = [
    "https://app.notion.com/p/33a22db60a618014ad56f4a2f30569e3",
    "https://app.notion.com/p/8e7eb305131f43c9a34a534e7a68e4b7",
    "https://app.notion.com/p/33b22db60a618050b770db2d47b7c222",
    "https://app.notion.com/p/33a22db60a6180f09652c3ecab6b346c",
    "https://app.notion.com/p/33b22db60a6180f9977ffbf6d2ecd2f9",
    "https://app.notion.com/p/BottleSumo-10-11-1-P-3a122db60a61807ab4a5eaea03c3b5fc",
    "https://app.notion.com/p/3a122db60a618049bb19ce1cd0296e68",
    "https://app.notion.com/p/3a722db60a6180ceb2d2c1411248e6f4",
    "https://app.notion.com/p/2d922db60a6183fabba481b26b7ffc2a",
    "https://app.notion.com/p/33a22db60a618009865ced863e2bc7e3",
]

entries = []
for url in URLS:
    r = meta_kb.phase_r(url, "KB_MIGRATE_ALL")
    entries.append(r)
    print("%-12s %-40s %s" % (r.get("content_source", "?"), r.get("title", "?"), url))

# 统一写入 manifest
os.makedirs(meta_kb.KB_DIR, exist_ok=True)
manifest = {
    "manifest_version": "1.0",
    "last_sync": meta_kb.now_iso(),
    "total_links": len(entries),
    "entries": entries,
    "affine_import_ready": True,
}
with io.open(meta_kb.MANIFEST, "w", encoding="utf-8") as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2)

with io.open(meta_kb.MIGRATION_REPORT, "w", encoding="utf-8") as f:
    f.write("# META-KB 批量迁移报告 [KB_MIGRATE_ALL]\n\n")
    for e in entries:
        f.write("- **%s** | %s | %s\n" % (e.get("title") or e.get("url"), e.get("content_source"), e["fetch_ok"]))
    f.write("\n- manifest: %s\n" % meta_kb.MANIFEST)

print("\nmanifest written:", meta_kb.MANIFEST)
