# Newsletter Worker

这个 Worker 为 `www.790427.xyz` 提供自建邮件订阅接口：

- `POST /api/subscribe`：写入 D1，并发送确认邮件
- `GET /api/subscribe/confirm?token=...`：确认订阅
- `GET /api/subscribe/unsubscribe?token=...`：退订
- `POST /api/newsletter/send`：内部接口，用于 GitHub Actions 发送新文章提醒

## 首次配置

1. 创建 D1：

   ```bash
   cd workers/newsletter
   npx wrangler d1 create bailai_newsletter
   ```

2. 把命令返回的 `database_id` 填到 `wrangler.jsonc`。

3. 初始化表：

   ```bash
   npx wrangler d1 execute bailai_newsletter --remote --file=./schema.sql
   ```

4. 设置密钥：

   ```bash
   npx wrangler secret put RESEND_API_KEY
   npx wrangler secret put TURNSTILE_SECRET
   npx wrangler secret put NEWSLETTER_SEND_TOKEN
   ```

5. 在 Cloudflare Turnstile 新建站点，把 site key 填到根目录 `config.json` 的 `turnstileSiteKey`。当前站点已配置 Turnstile site key，secret key 只应通过 Wrangler secret 保存，不要写入仓库。

6. 部署：

   ```bash
   npx wrangler deploy
   ```

## 发信域名

Resend/SES 等服务需要单独验证 `790427.xyz` 或子域名，并配置 SPF/DKIM/DMARC。验证完成前，确认邮件可能发不出去或进入垃圾箱。

## 新文章通知

`/api/newsletter/send` 只接受带 `Authorization: Bearer <NEWSLETTER_SEND_TOKEN>` 的内部请求。GitHub Actions 也需要保存同一个 token 到仓库 secret `NEWSLETTER_SEND_TOKEN`。

请求体示例：

```json
{
  "post": {
    "title": "文章标题",
    "url": "https://www.790427.xyz/post/example.html",
    "description": "文章摘要",
    "date": "2026-07-10"
  },
  "dryRun": false
}
```

Worker 会读取 D1 中 `status = active` 的订阅者，并把每个 `post_url + email` 的发送结果写入 `newsletter_sends`，避免重复发送。

## 私有运营数据

运营数据接口统一使用 `NEWSLETTER_SEND_TOKEN` 鉴权，不向公网暴露报表或原始数据。GA4、Search Console 和 Clarity 由 `Daily Operations Metrics` 自动采集；X 不使用付费 API，改为每周导入 X Analytics CSV：

- `POST /api/ops/weekly-input`：保存 X CSV 解析后的每周合计与时间投入。
- `GET /api/ops/weekly-input`：返回最近一周的 X CSV 合计。
- `GET /api/ops/newsletter-metrics`：返回订阅者的单日、7 日和 28 日汇总。

`Daily Operations Metrics` 会直接调用 GA4 Data API、Search Console API 和 Clarity Data Export API。`Record Weekly Operations` 负责导入 X Analytics CSV，可通过 `csv_data` 粘贴内容，也可用 GitHub CLI 传文件内容，例如 `gh workflow run record-weekly-operations.yml -f week_ending=2026-07-26 -F csv_data=@x-analytics.csv -f time_split=20,20`。Clarity 不再保留手工复盘 workflow；不录入访客标识、IP、录像链接、邮箱、完整对话或截图。
