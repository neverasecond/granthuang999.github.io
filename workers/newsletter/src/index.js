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
    'Access-Control-Allow-Headers': 'Content-Type',
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

async function sendEmail(env, { to, subject, html }) {
  if (!env.RESEND_API_KEY) {
    throw new Error('RESEND_API_KEY is not configured');
  }

  const response = await fetch('https://api.resend.com/emails', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${env.RESEND_API_KEY}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      from: env.MAIL_FROM,
      to,
      subject,
      html,
    }),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Resend error ${response.status}: ${text}`);
  }

  return response.json();
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
    if (request.method === 'GET' && url.pathname === '/api/subscribe/unsubscribe') {
      return unsubscribe(request, env, url.searchParams.get('token'));
    }

    return json(request, { message: 'Not found' }, 404);
  },
};
