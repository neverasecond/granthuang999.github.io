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
