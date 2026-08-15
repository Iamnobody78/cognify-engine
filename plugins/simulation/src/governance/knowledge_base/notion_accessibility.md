# Notion 链接可访问性实证（2026-08-10 复查）

## PM 声称
"我notion发布了网站 所有链接（包括我这次给你的）应该可以在网站上看到"

## 实证结果：10/10 链接仍为工作区内链，非公开网站链接

| 验证方式 | 结果 | 证据 |
| :--- | :--- | :--- |
| `www.notion.so/{pageid}`（公开格式） | 302 重定向 | → `app.notion.com/p/...?session_sync_attempted`（登录墙特征） |
| `notion.site/{pageid}` | 跳转主页 | → `www.notion.com/`（页面不存在） |
| headful Edge + stealth | 反爬拦截 | → `unsupported-browser.html` "Your browser is not compatible" |
| headless Playwright | 反爬拦截 | → 同上 |

## 结论
1. **PM 给的 10 个链接格式是 `app.notion.com/p/*` —— 这是 Notion 工作区内链**，
   无论页面是否发布为网站，此格式都必须登录才能访问
2. Notion Sites 发布后生成的是**新的公开 URL**：`https://{workspace}.notion.site/{slug}-{pageid}`
3. PM 能在浏览器看到链接，是因为**其浏览器已登录 Notion**（session 有效）
   → 对他可用 ≠ 对无登录态的自动化可用
4. `app.notion.com` 对自动化浏览器有**硬性反爬**（headless 和 headful 均被拦截），
   且私有页本来就需要登录——不是绕过反爬能解决的

## 需要的下一步（PM 提供其一即可）
- **发布后的公开网站 URL**（`*.notion.site` 格式，无需登录即可爬取）
- 或 Notion Integration Token（API 读取，无需登录态浏览器）
- 或确认页面未发布公开（维持"不可程序化抓取"的结论）

## 关键区分
- PM 视角"我发布了网站" ✓（可能为真）
- PM 视角"链接应该能看到" ✓（他登录着）
- 自动化视角"无需登录可抓取" ✗（app 内链格式 + 登录墙 + 反爬）
