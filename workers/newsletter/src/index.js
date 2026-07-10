const JSON_HEADERS = {
  'Content-Type': 'application/json; charset=utf-8',
  'Cache-Control': 'no-store',
};

function corsHeaders(request) {
  const origin = request.headers.get('Origin') || '';
  const allowed = new Set([
    'https://www.790427.xyz',
    'https://790427.xyz',
  ]);
  return {
    'Access-Control-Allow-Origin': allowed.has(origin) ? origin : 'https://www.790427.xyz',
    'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
    'Access-Control-Allow-Headers': 'Authorization,Content-Type',
    'Vary': 'Origin',
  };
}

function json(request, data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { ...JSON_HEADERS, ...corsHeaders(request) },
  });
}

function html(body, status = 200) {
  return new Response(body, {
    status,
    headers: {
      'Content-Type': 'text/html; charset=utf-8',
      'Cache-Control': 'no-store',
    },
  });
}

function normalizeEmail(email) {
  return String(email || '').trim().toLowerCase();
}

function isValidEmail(email) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) && email.length <= 254;
}

function newToken() {
  const bytes = new Uint8Array(24);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('');
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  }[char]));
}

function stripHtml(value) {
  return String(value || '').replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
}

function truncate(value, maxLength) {
  const text = String(value || '').trim();
  return text.length > maxLength ? `${text.slice(0, maxLength - 1)}...` : text;
}

function constantTimeEqual(a, b) {
  const encoder = new TextEncoder();
  const left = encoder.encode(String(a || ''));
  const right = encoder.encode(String(b || ''));
  if (left.length !== right.length) return false;

  let diff = 0;
  for (let index = 0; index < left.length; index += 1) {
    diff |= left[index] ^ right[index];
  }
  return diff === 0;
}

async function verifyTurnstile(request, env, token) {
  if (env.REQUIRE_TURNSTILE !== 'true') return true;
  if (!env.TURNSTILE_SECRET) {
    throw new Error('TURNSTILE_SECRET is not configured');
  }
  if (!token) return false;

  const response = await fetch('https://challenges.cloudflare.com/turnstile/v0/siteverify', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      secret: env.TURNSTILE_SECRET,
      response: token,
      remoteip: request.headers.get('CF-Connecting-IP') || undefined,
      idempotency_key: crypto.randomUUID(),
    }),
  });
  const result = await response.json();
  return result.success === true;
}

async function sendEmail(env, { to, subject, html, text, headers }) {
  if (!env.RESEND_API_KEY) {
    throw new Error('RESEND_API_KEY is not configured');
  }

  const message = {
    from: env.MAIL_FROM,
    to,
    subject,
    html,
  };
  if (text) message.text = text;
  if (headers) message.headers = headers;

  const response = await fetch('https://api.resend.com/emails', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${env.RESEND_API_KEY}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(message),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Resend error ${response.status}: ${text}`);
  }

  return response.json();
}

async function ensureNewsletterSchema(env) {
  await env.DB.prepare(`
    CREATE TABLE IF NOT EXISTS newsletter_sends (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      post_url TEXT NOT NULL,
      post_title TEXT NOT NULL,
      email TEXT NOT NULL,
      status TEXT NOT NULL CHECK (status IN ('sent', 'failed')),
      provider_id TEXT,
      error TEXT,
      sent_at TEXT,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(post_url, email)
    )
  `).run();

  await env.DB.prepare(`
    CREATE INDEX IF NOT EXISTS idx_newsletter_sends_post_url
    ON newsletter_sends(post_url)
  `).run();
}

async function authorizeInternalRequest(request, env) {
  if (!env.NEWSLETTER_SEND_TOKEN) {
    throw new Error('NEWSLETTER_SEND_TOKEN is not configured');
  }

  const auth = request.headers.get('Authorization') || '';
  const token = auth.startsWith('Bearer ') ? auth.slice('Bearer '.length).trim() : '';
  return constantTimeEqual(token, env.NEWSLETTER_SEND_TOKEN);
}

function postNotificationHtml(env, post, subscriber) {
  const siteUrl = env.SITE_URL || 'https://www.790427.xyz';
  const siteName = escapeHtml(env.SITE_NAME || '人到中年');
  const title = escapeHtml(post.title);
  const url = escapeHtml(post.url);
  const description = escapeHtml(truncate(stripHtml(post.description), 280));
  const date = escapeHtml(post.date || '');
  const unsubscribeUrl = subscriber.unsubscribe_token
    ? `${siteUrl}/api/subscribe/unsubscribe?token=${encodeURIComponent(subscriber.unsubscribe_token)}`
    : '';

  return `
    <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;line-height:1.7;color:#24292f;max-width:680px;margin:0 auto">
      <p style="font-size:13px;color:#57606a">来自《${siteName}》的新文章提醒${date ? ` · ${date}` : ''}</p>
      <h2 style="line-height:1.35;margin:0 0 12px">${title}</h2>
      ${description ? `<p>${description}</p>` : ''}
      <p><a href="${url}" style="display:inline-block;background:#0969da;color:#fff;padding:10px 14px;border-radius:6px;text-decoration:none">阅读全文</a></p>
      <p style="font-size:13px;color:#57606a">你收到这封邮件，是因为订阅了《${siteName}》。${unsubscribeUrl ? `不想继续收到提醒，可以点击 <a href="${escapeHtml(unsubscribeUrl)}">退订</a>。` : ''}</p>
    </div>
  `;
}

function postNotificationText(env, post, subscriber) {
  const siteUrl = env.SITE_URL || 'https://www.790427.xyz';
  const siteName = env.SITE_NAME || '人到中年';
  const unsubscribeUrl = subscriber.unsubscribe_token
    ? `${siteUrl}/api/subscribe/unsubscribe?token=${encodeURIComponent(subscriber.unsubscribe_token)}`
    : '';
  return [
    `《${siteName}》新文章：${post.title}`,
    post.date ? `日期：${post.date}` : '',
    stripHtml(post.description),
    `阅读全文：${post.url}`,
    unsubscribeUrl ? `退订：${unsubscribeUrl}` : '',
  ].filter(Boolean).join('\n\n');
}

async function sendNewsletter(request, env) {
  let payload;
  try {
    payload = await request.json();
  } catch {
    return json(request, { message: '请求格式不正确。' }, 400);
  }

  let authorized;
  try {
    authorized = await authorizeInternalRequest(request, env);
  } catch (error) {
    console.error(error);
    return json(request, { message: '邮件通知服务尚未完成内部鉴权配置。' }, 503);
  }
  if (!authorized) return json(request, { message: 'Unauthorized' }, 401);

  const post = payload.post || {};
  post.title = String(post.title || '').trim();
  post.url = String(post.url || '').trim();
  post.description = String(post.description || '').trim();
  post.date = String(post.date || '').trim();

  if (!post.title || !post.url.startsWith((env.SITE_URL || 'https://www.790427.xyz') + '/')) {
    return json(request, { message: '文章信息不完整或 URL 不属于本站。' }, 400);
  }

  const dryRun = payload.dryRun === true;
  const testEmail = normalizeEmail(payload.testEmail || '');
  const batchLimit = Math.max(1, Math.min(Number(env.NEWSLETTER_BATCH_LIMIT || 50), 100));

  await ensureNewsletterSchema(env);

  let subscribers;
  if (testEmail) {
    if (!isValidEmail(testEmail)) return json(request, { message: '测试邮箱格式不正确。' }, 400);
    subscribers = [{ email: testEmail, unsubscribe_token: '' }];
  } else {
    const result = await env.DB.prepare(`
      SELECT email, unsubscribe_token
      FROM subscribers
      WHERE status = 'active'
        AND email NOT IN (
          SELECT email FROM newsletter_sends
          WHERE post_url = ? AND status = 'sent'
        )
      ORDER BY confirmed_at ASC
      LIMIT ?
    `).bind(post.url, batchLimit).all();
    subscribers = result.results || [];
  }

  const summary = {
    postUrl: post.url,
    dryRun,
    testEmail: testEmail || null,
    attempted: subscribers.length,
    sent: 0,
    failed: 0,
    skipped: dryRun ? subscribers.length : 0,
  };

  if (dryRun) return json(request, summary);

  for (const subscriber of subscribers) {
    const unsubscribeUrl = subscriber.unsubscribe_token
      ? `${env.SITE_URL || 'https://www.790427.xyz'}/api/subscribe/unsubscribe?token=${encodeURIComponent(subscriber.unsubscribe_token)}`
      : '';

    try {
      const result = await sendEmail(env, {
        to: subscriber.email,
        subject: `新文章：${post.title}`,
        html: postNotificationHtml(env, post, subscriber),
        text: postNotificationText(env, post, subscriber),
        headers: unsubscribeUrl ? {
          'List-Unsubscribe': `<${unsubscribeUrl}>`,
          'List-Unsubscribe-Post': 'List-Unsubscribe=One-Click',
        } : undefined,
      });

      summary.sent += 1;
      if (!testEmail) {
        await env.DB.prepare(`
          INSERT INTO newsletter_sends (post_url, post_title, email, status, provider_id, sent_at)
          VALUES (?, ?, ?, 'sent', ?, CURRENT_TIMESTAMP)
          ON CONFLICT(post_url, email) DO UPDATE SET
            post_title = excluded.post_title,
            status = 'sent',
            provider_id = excluded.provider_id,
            error = NULL,
            sent_at = CURRENT_TIMESTAMP
        `).bind(post.url, post.title, subscriber.email, result?.id || null).run();
      }
    } catch (error) {
      console.error(error);
      summary.failed += 1;
      if (!testEmail) {
        await env.DB.prepare(`
          INSERT INTO newsletter_sends (post_url, post_title, email, status, error)
          VALUES (?, ?, ?, 'failed', ?)
          ON CONFLICT(post_url, email) DO UPDATE SET
            post_title = excluded.post_title,
            status = 'failed',
            error = excluded.error
        `).bind(post.url, post.title, subscriber.email, String(error).slice(0, 1000)).run();
      }
    }
  }

  return json(request, summary, summary.failed ? 207 : 200);
}

function confirmEmailHtml(env, email, confirmToken, unsubscribeToken) {
  const siteUrl = env.SITE_URL || 'https://www.790427.xyz';
  const confirmUrl = `${siteUrl}/api/subscribe/confirm?token=${encodeURIComponent(confirmToken)}`;
  const unsubscribeUrl = `${siteUrl}/api/subscribe/unsubscribe?token=${encodeURIComponent(unsubscribeToken)}`;
  const siteName = escapeHtml(env.SITE_NAME || '人到中年');
  const safeEmail = escapeHtml(email);
  return `
    <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;line-height:1.7;color:#24292f">
      <h2>确认订阅《${siteName}》</h2>
      <p>你好，${safeEmail}：</p>
      <p>请点击下面的链接确认订阅。确认后，你会收到白来关于职场、投资、读书与修行的新文章提醒。</p>
      <p><a href="${escapeHtml(confirmUrl)}" style="display:inline-block;background:#0969da;color:#fff;padding:10px 14px;border-radius:6px;text-decoration:none">确认订阅</a></p>
      <p style="font-size:13px;color:#57606a">如果不是你本人操作，可以忽略这封邮件，或点击 <a href="${escapeHtml(unsubscribeUrl)}">退订</a>。</p>
    </div>
  `;
}

async function subscribe(request, env) {
  let payload;
  try {
    payload = await request.json();
  } catch {
    return json(request, { message: '请求格式不正确。' }, 400);
  }

  const email = normalizeEmail(payload.email);
  const name = String(payload.name || '').trim().slice(0, 80) || null;
  const source = String(payload.source || '').trim().slice(0, 500) || null;

  if (!isValidEmail(email)) {
    return json(request, { message: '邮箱格式不正确。' }, 400);
  }

  let passedTurnstile;
  try {
    passedTurnstile = await verifyTurnstile(request, env, payload.turnstileToken);
  } catch (error) {
    console.error(error);
    return json(request, { message: '订阅服务尚未完成安全配置。' }, 503);
  }
  if (!passedTurnstile) return json(request, { message: '验证失败，请刷新页面后重试。' }, 403);

  const existing = await env.DB.prepare(
    'SELECT email, status, confirm_token, unsubscribe_token FROM subscribers WHERE email = ?'
  ).bind(email).first();

  if (existing && existing.status === 'active') {
    return json(request, { message: '这个邮箱已经订阅。' });
  }

  const confirmToken = existing?.confirm_token || newToken();
  const unsubscribeToken = existing?.unsubscribe_token || newToken();

  await env.DB.prepare(`
    INSERT INTO subscribers (email, name, status, source, confirm_token, unsubscribe_token, updated_at)
    VALUES (?, ?, 'pending', ?, ?, ?, CURRENT_TIMESTAMP)
    ON CONFLICT(email) DO UPDATE SET
      name = excluded.name,
      status = 'pending',
      source = excluded.source,
      confirm_token = excluded.confirm_token,
      unsubscribe_token = excluded.unsubscribe_token,
      updated_at = CURRENT_TIMESTAMP
  `).bind(email, name, source, confirmToken, unsubscribeToken).run();

  try {
    await sendEmail(env, {
      to: email,
      subject: `确认订阅《${env.SITE_NAME || '人到中年'}》`,
      html: confirmEmailHtml(env, email, confirmToken, unsubscribeToken),
    });
  } catch (error) {
    console.error(error);
    return json(request, { message: '订阅记录已保存，但确认邮件暂时无法发送。' }, 503);
  }

  return json(request, { message: '确认邮件已发送，请去邮箱里完成确认。' }, 202);
}

async function confirm(request, env, token) {
  if (!token) return html(renderMessage(env, '确认链接无效', '缺少确认 token。'), 400);

  const result = await env.DB.prepare(`
    UPDATE subscribers
    SET status = 'active', confirmed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
    WHERE confirm_token = ?
  `).bind(token).run();

  if (result.meta.changes === 0) {
    return html(renderMessage(env, '确认链接无效', '没有找到对应的订阅记录。'), 404);
  }

  return html(renderMessage(env, '订阅已确认', '以后你会收到《人到中年》的新文章提醒。'));
}

async function unsubscribe(request, env, token) {
  if (!token) return html(renderMessage(env, '退订链接无效', '缺少退订 token。'), 400);

  const result = await env.DB.prepare(`
    UPDATE subscribers
    SET status = 'unsubscribed', unsubscribed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
    WHERE unsubscribe_token = ?
  `).bind(token).run();

  if (result.meta.changes === 0) {
    return html(renderMessage(env, '退订链接无效', '没有找到对应的订阅记录。'), 404);
  }

  return html(renderMessage(env, '已退订', '这个邮箱不会再收到新文章提醒。'));
}

function renderMessage(env, title, message) {
  const siteUrl = env.SITE_URL || 'https://www.790427.xyz';
  const safeTitle = escapeHtml(title);
  const safeMessage = escapeHtml(message);
  const safeSiteName = escapeHtml(env.SITE_NAME || '人到中年');
  const safeSiteUrl = escapeHtml(siteUrl);
  return `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>${safeTitle} - ${safeSiteName}</title>
  <style>
    body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:680px;margin:48px auto;padding:0 20px;line-height:1.7;color:#24292f}
    a{color:#0969da}
  </style>
</head>
<body>
  <h1>${safeTitle}</h1>
  <p>${safeMessage}</p>
  <p><a href="${safeSiteUrl}">返回首页</a></p>
</body>
</html>`;
}

export default {
  async fetch(request, env) {
    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: corsHeaders(request) });
    }

    const url = new URL(request.url);
    if (request.method === 'POST' && url.pathname === '/api/subscribe') {
      return subscribe(request, env);
    }
    if (request.method === 'GET' && url.pathname === '/api/subscribe/confirm') {
      return confirm(request, env, url.searchParams.get('token'));
    }
    if ((request.method === 'GET' || request.method === 'POST') && url.pathname === '/api/subscribe/unsubscribe') {
      return unsubscribe(request, env, url.searchParams.get('token'));
    }
    if (request.method === 'POST' && url.pathname === '/api/newsletter/send') {
      return sendNewsletter(request, env);
    }

    return json(request, { message: 'Not found' }, 404);
  },
};
