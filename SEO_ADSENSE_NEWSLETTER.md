# SEO, AdSense, and Newsletter Checklist

## 已在代码中完成

- 全站保留 AdSense 账号 meta，不加载自动广告脚本。
- 全站增加搜索引擎 robots meta。
- 首页/列表页增加 `CollectionPage` 结构化数据。
- 文章页使用 `BlogPosting` 结构化数据，并补充栏目、关键词、作者、发布和更新时间。
- 订阅页改为可接入真实后端的表单，提交到 `config.json` 的 `subscribeApiUrl`。
- 新增 Cloudflare Worker 订阅后端样板，支持确认订阅和退订。

## AdSense 审核前不要做

- 不要启用 `adsbygoogle.js` 自动广告脚本。
- 不要放空广告位或占位广告卡片。
- 不要批量生成低质量短文来填页面。

## AdSense 审核前建议继续做

- 继续清理旧品牌、旧栏目、重复标题和薄内容。
- 保持关于本站、隐私政策、服务条款、免责声明、订阅页可访问。
- 确保首页、栏目页、文章页在移动端可读。
- 每个主要栏目至少保留一批稳定、原创、主题一致的文章。

## 邮件订阅上线步骤

1. 到 Cloudflare Turnstile 创建站点，域名填 `www.790427.xyz`。
2. 把 Turnstile site key 写入根目录 `config.json` 的 `turnstileSiteKey`。
3. 在 `workers/newsletter` 创建 D1，并把 `database_id` 写入 `wrangler.jsonc`。
4. 用 `schema.sql` 初始化 D1。
5. 在 Resend 或 SES 验证发信域名，配置 SPF/DKIM/DMARC。
6. 用 Wrangler 设置 `RESEND_API_KEY` 和 `TURNSTILE_SECRET`。
7. 部署 Worker，确认 `/api/subscribe` 路由生效。
8. 把根目录 `config.json` 的 `subscribeApiUrl` 改为 `https://www.790427.xyz/api/subscribe`。
9. 发送一次测试订阅，确认收到邮件、确认链接、退订链接都可用。
