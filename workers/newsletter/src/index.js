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

async function ensureOperationsSchema(env) {
  if (!env.OPS_DB) throw new Error('OPS_DB is not configured');

  await env.OPS_DB.batch([
    env.OPS_DB.prepare(`
      CREATE TABLE IF NOT EXISTS daily_metrics (
        metric_date TEXT NOT NULL,
        source TEXT NOT NULL,
        metric TEXT NOT NULL,
        dimension TEXT NOT NULL DEFAULT '',
        value REAL NOT NULL,
        metadata TEXT,
        collected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (metric_date, source, metric, dimension)
      )
    `),
    env.OPS_DB.prepare(`
      CREATE TABLE IF NOT EXISTS collection_runs (
        run_id TEXT PRIMARY KEY,
        metric_date TEXT NOT NULL,
        report_mode TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('started', 'success', 'partial', 'failed')),
        error_summary TEXT,
        started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        finished_at TEXT
      )
    `),
    env.OPS_DB.prepare(`
      CREATE TABLE IF NOT EXISTS manual_x_metrics (
        metric_date TEXT PRIMARY KEY,
        followers INTEGER,
        verified_followers INTEGER,
        impressions INTEGER,
        profile_visits INTEGER,
        link_clicks INTEGER,
        bookmarks INTEGER,
        replies INTEGER,
        reposts INTEGER,
        posts_published INTEGER,
        notes TEXT,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
      )
    `),
    env.OPS_DB.prepare(`
      CREATE TABLE IF NOT EXISTS weekly_operations (
        week_ending TEXT PRIMARY KEY,
        followers INTEGER,
        verified_followers INTEGER,
        posts_published INTEGER,
        impressions INTEGER,
        verified_home_timeline_impressions INTEGER,
        profile_visits INTEGER,
        link_clicks INTEGER,
        bookmarks INTEGER,
        replies INTEGER,
        effective_replies INTEGER,
        reposts INTEGER,
        subscriptions INTEGER,
        creation_hours REAL,
        interaction_hours REAL,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
      )
    `),
    env.OPS_DB.prepare(`
      CREATE TABLE IF NOT EXISTS clarity_reviews (
        week_ending TEXT NOT NULL,
        page_path TEXT NOT NULL,
        recordings_reviewed INTEGER NOT NULL DEFAULT 0,
        heatmap_finding TEXT NOT NULL,
        recording_finding TEXT NOT NULL,
        action_decision TEXT NOT NULL,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (week_ending, page_path)
      )
    `),
    env.OPS_DB.prepare(`
      CREATE INDEX IF NOT EXISTS idx_daily_metrics_source_date
      ON daily_metrics(source, metric_date)
    `),
    env.OPS_DB.prepare(`
      CREATE INDEX IF NOT EXISTS idx_daily_metrics_metric_date
      ON daily_metrics(metric, metric_date)
    `),
    env.OPS_DB.prepare(`
      CREATE INDEX IF NOT EXISTS idx_collection_runs_metric_date
      ON collection_runs(metric_date)
    `),
    env.OPS_DB.prepare(`
      CREATE INDEX IF NOT EXISTS idx_clarity_reviews_week
      ON clarity_reviews(week_ending)
    `),
  ]);

  await ensureTableColumns(env, 'weekly_operations', [
    ['verified_followers', 'INTEGER'],
    ['verified_home_timeline_impressions', 'INTEGER'],
    ['effective_replies', 'INTEGER'],
    ['subscriptions', 'INTEGER'],
  ]);
}

async function ensureTableColumns(env, tableName, columns) {
  const existingRows = await env.OPS_DB.prepare(`PRAGMA table_info(${tableName})`).all();
  const existing = new Set((existingRows.results || []).map((row) => row.name));
  for (const [column, type] of columns) {
    if (!existing.has(column)) {
      await env.OPS_DB.prepare(`ALTER TABLE ${tableName} ADD COLUMN ${column} ${type}`).run();
    }
  }
}

async function authorizeInternalRequest(request, env) {
  if (!env.NEWSLETTER_SEND_TOKEN) {
    throw new Error('NEWSLETTER_SEND_TOKEN is not configured');
  }

  const auth = request.headers.get('Authorization') || '';
  const token = auth.startsWith('Bearer ') ? auth.slice('Bearer '.length).trim() : '';
  return constantTimeEqual(token, env.NEWSLETTER_SEND_TOKEN);
}

async function operationsHealth(request, env) {
  let newsletterDatabase = 'error';
  let operationsDatabase = 'error';
  try {
    await env.DB.prepare('SELECT 1 AS ok').first();
    newsletterDatabase = 'ok';
    await ensureOperationsSchema(env);
    await env.OPS_DB.prepare('SELECT 1 AS ok').first();
    operationsDatabase = 'ok';
  } catch (error) {
    console.error('Operations health check failed', error);
  }
  const ok = newsletterDatabase === 'ok' && operationsDatabase === 'ok';
  return json(request, {
    ok,
    database: ok ? 'ok' : 'error',
    newsletterDatabase,
    operationsDatabase,
  }, ok ? 200 : 503);
}

function validMetricDate(value) {
  return /^\d{4}-\d{2}-\d{2}$/.test(String(value || ''));
}

async function newsletterMetrics(request, env, metricDate) {
  if (!validMetricDate(metricDate)) {
    return json(request, { message: 'metricDate must use YYYY-MM-DD.' }, 400);
  }
  const statements = [
    env.DB.prepare("SELECT COUNT(*) AS value FROM subscribers WHERE status = 'active'"),
    env.DB.prepare("SELECT COUNT(*) AS value FROM subscribers WHERE status = 'pending'"),
    env.DB.prepare("SELECT COUNT(*) AS value FROM subscribers WHERE status = 'unsubscribed'"),
    env.DB.prepare("SELECT COUNT(*) AS value FROM subscribers WHERE DATE(created_at, '+8 hours') = ?").bind(metricDate),
    env.DB.prepare("SELECT COUNT(*) AS value FROM subscribers WHERE DATE(confirmed_at, '+8 hours') = ?").bind(metricDate),
    env.DB.prepare("SELECT COUNT(*) AS value FROM subscribers WHERE DATE(unsubscribed_at, '+8 hours') = ?").bind(metricDate),
    env.DB.prepare("SELECT COUNT(*) AS value FROM newsletter_sends WHERE status = 'sent' AND DATE(sent_at, '+8 hours') = ?").bind(metricDate),
    env.DB.prepare("SELECT COUNT(*) AS value FROM newsletter_sends WHERE status = 'failed' AND DATE(created_at, '+8 hours') = ?").bind(metricDate),
    env.DB.prepare("SELECT COUNT(*) AS value FROM subscribers WHERE DATE(created_at, '+8 hours') BETWEEN DATE(?, '-6 days') AND ?").bind(metricDate, metricDate),
    env.DB.prepare("SELECT COUNT(*) AS value FROM subscribers WHERE DATE(confirmed_at, '+8 hours') BETWEEN DATE(?, '-6 days') AND ?").bind(metricDate, metricDate),
    env.DB.prepare("SELECT COUNT(*) AS value FROM subscribers WHERE DATE(created_at, '+8 hours') BETWEEN DATE(?, '-27 days') AND ?").bind(metricDate, metricDate),
    env.DB.prepare("SELECT COUNT(*) AS value FROM subscribers WHERE DATE(confirmed_at, '+8 hours') BETWEEN DATE(?, '-27 days') AND ?").bind(metricDate, metricDate),
  ];
  const results = await env.DB.batch(statements);
  const names = [
    'activeSubscribers',
    'pendingSubscribers',
    'unsubscribedSubscribers',
    'createdYesterday',
    'confirmedYesterday',
    'unsubscribedYesterday',
    'messagesSentYesterday',
    'messagesFailedYesterday',
    'created7d',
    'confirmed7d',
    'created28d',
    'confirmed28d',
  ];
  const response = {};
  names.forEach((name, index) => {
    response[name] = Number(results[index]?.results?.[0]?.value || 0);
  });
  return json(request, response);
}

async function storeOperationsMetrics(request, env) {
  let payload;
  try {
    payload = await request.json();
  } catch {
    return json(request, { message: '请求格式不正确。' }, 400);
  }

  const runId = String(payload.runId || '').slice(0, 120);
  const metricDate = String(payload.metricDate || '');
  const reportMode = String(payload.reportMode || 'none').slice(0, 30);
  const status = ['success', 'partial', 'failed'].includes(payload.status)
    ? payload.status
    : 'failed';
  const metrics = Array.isArray(payload.metrics) ? payload.metrics : [];
  if (!runId || !validMetricDate(metricDate) || metrics.length > 500) {
    return json(request, { message: '指标批次不合法。' }, 400);
  }

  await ensureOperationsSchema(env);
  const statements = [];
  for (const item of metrics) {
    const source = String(item.source || '').slice(0, 80);
    const metric = String(item.metric || '').slice(0, 120);
    const dimension = String(item.dimension || '').slice(0, 500);
    const value = Number(item.value);
    if (!source || !metric || !Number.isFinite(value)) continue;
    const metadata = JSON.stringify(item.metadata || {}).slice(0, 5000);
    statements.push(env.OPS_DB.prepare(`
      INSERT INTO daily_metrics (
        metric_date, source, metric, dimension, value, metadata, collected_at
      ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
      ON CONFLICT(metric_date, source, metric, dimension) DO UPDATE SET
        value = excluded.value,
        metadata = excluded.metadata,
        collected_at = CURRENT_TIMESTAMP
    `).bind(metricDate, source, metric, dimension, value, metadata));
  }
  if (statements.length) await env.OPS_DB.batch(statements);

  const errors = Array.isArray(payload.errors)
    ? payload.errors.map((item) => String(item).slice(0, 300)).slice(0, 20)
    : [];
  await env.OPS_DB.prepare(`
    INSERT INTO collection_runs (
      run_id, metric_date, report_mode, status, error_summary, finished_at
    ) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    ON CONFLICT(run_id) DO UPDATE SET
      status = excluded.status,
      error_summary = excluded.error_summary,
      finished_at = CURRENT_TIMESTAMP
  `).bind(runId, metricDate, reportMode, status, errors.join('\n')).run();

  return json(request, { stored: statements.length, runId });
}

async function sendOperationsReport(request, env) {
  if (!env.OPS_REPORT_EMAIL) {
    return json(request, { message: 'OPS_REPORT_EMAIL is not configured.' }, 503);
  }
  let payload;
  try {
    payload = await request.json();
  } catch {
    return json(request, { message: '请求格式不正确。' }, 400);
  }
  const subject = String(payload.subject || '').trim().slice(0, 200);
  const reportHtml = String(payload.html || '').trim().slice(0, 100000);
  const text = String(payload.text || '').trim().slice(0, 50000);
  if (!subject || !reportHtml || !text) {
    return json(request, { message: '运营报告内容不完整。' }, 400);
  }

  await sendEmail(env, {
    to: env.OPS_REPORT_EMAIL,
    subject,
    html: reportHtml,
    text,
  });
  return json(request, { sent: true });
}

const WEEKLY_NUMBER_FIELDS = [
  'followers', 'verifiedFollowers', 'postsPublished', 'impressions',
  'verifiedHomeTimelineImpressions', 'profileVisits', 'linkClicks',
  'bookmarks', 'replies', 'effectiveReplies', 'reposts', 'subscriptions',
  'creationHours', 'interactionHours',
];

async function weeklyOperations(request, env) {
  if (request.method === 'GET') {
    await ensureOperationsSchema(env);
    const row = await env.OPS_DB.prepare(`
      SELECT week_ending AS weekEnding, followers,
             verified_followers AS verifiedFollowers,
             posts_published AS postsPublished, impressions,
             verified_home_timeline_impressions AS verifiedHomeTimelineImpressions,
             profile_visits AS profileVisits, link_clicks AS linkClicks,
             bookmarks, replies, effective_replies AS effectiveReplies,
             reposts, subscriptions,
             creation_hours AS creationHours,
             interaction_hours AS interactionHours
      FROM weekly_operations
      ORDER BY week_ending DESC
      LIMIT 1
    `).first();
    return json(request, row || {});
  }

  let payload;
  try {
    payload = await request.json();
  } catch {
    return json(request, { message: '请求格式不正确。' }, 400);
  }
  const weekEnding = String(payload.weekEnding || '');
  if (!validMetricDate(weekEnding)) {
    return json(request, { message: 'weekEnding must use YYYY-MM-DD.' }, 400);
  }
  const values = {};
  for (const field of WEEKLY_NUMBER_FIELDS) {
    const value = Number(payload[field] ?? 0);
    if (!Number.isFinite(value) || value < 0) {
      return json(request, { message: `Invalid weekly metric: ${field}` }, 400);
    }
    values[field] = value;
  }

  await ensureOperationsSchema(env);
  await env.OPS_DB.prepare(`
    INSERT INTO weekly_operations (
      week_ending, followers, verified_followers, posts_published,
      impressions, verified_home_timeline_impressions, profile_visits,
      link_clicks, bookmarks, replies, effective_replies, reposts,
      subscriptions, creation_hours, interaction_hours, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    ON CONFLICT(week_ending) DO UPDATE SET
      followers = excluded.followers,
      verified_followers = excluded.verified_followers,
      posts_published = excluded.posts_published,
      impressions = excluded.impressions,
      verified_home_timeline_impressions = excluded.verified_home_timeline_impressions,
      profile_visits = excluded.profile_visits,
      link_clicks = excluded.link_clicks,
      bookmarks = excluded.bookmarks,
      replies = excluded.replies,
      effective_replies = excluded.effective_replies,
      reposts = excluded.reposts,
      subscriptions = excluded.subscriptions,
      creation_hours = excluded.creation_hours,
      interaction_hours = excluded.interaction_hours,
      updated_at = CURRENT_TIMESTAMP
  `).bind(
    weekEnding, values.followers, values.verifiedFollowers,
    values.postsPublished, values.impressions,
    values.verifiedHomeTimelineImpressions, values.profileVisits,
    values.linkClicks, values.bookmarks, values.replies,
    values.effectiveReplies, values.reposts, values.subscriptions,
    values.creationHours, values.interactionHours,
  ).run();
  return json(request, { stored: true, weekEnding });
}

async function clarityReview(request, env) {
  if (request.method === 'GET') {
    await ensureOperationsSchema(env);
    const latest = await env.OPS_DB.prepare(`
      SELECT MAX(week_ending) AS weekEnding
      FROM clarity_reviews
    `).first();
    const weekEnding = String(latest?.weekEnding || '');
    if (!weekEnding) return json(request, { weekEnding: '', reviews: [] });

    const result = await env.OPS_DB.prepare(`
      SELECT week_ending AS weekEnding, page_path AS pagePath,
             recordings_reviewed AS recordingsReviewed,
             heatmap_finding AS heatmapFinding,
             recording_finding AS recordingFinding,
             action_decision AS actionDecision
      FROM clarity_reviews
      WHERE week_ending = ?
      ORDER BY page_path ASC
      LIMIT 20
    `).bind(weekEnding).all();
    return json(request, { weekEnding, reviews: result.results || [] });
  }

  let payload;
  try {
    payload = await request.json();
  } catch {
    return json(request, { message: '请求格式不正确。' }, 400);
  }

  const weekEnding = String(payload.weekEnding || '');
  const pagePath = String(payload.pagePath || '').trim().slice(0, 500);
  const recordingsReviewed = Number(payload.recordingsReviewed);
  const heatmapFinding = String(payload.heatmapFinding || '').trim().slice(0, 1500);
  const recordingFinding = String(payload.recordingFinding || '').trim().slice(0, 1500);
  const actionDecision = String(payload.actionDecision || '').trim().slice(0, 1500);
  if (!validMetricDate(weekEnding) || !pagePath ||
      !Number.isInteger(recordingsReviewed) || recordingsReviewed < 0 ||
      !heatmapFinding || !recordingFinding || !actionDecision) {
    return json(request, { message: 'Clarity 周度复盘字段不完整或不合法。' }, 400);
  }

  await ensureOperationsSchema(env);
  await env.OPS_DB.prepare(`
    INSERT INTO clarity_reviews (
      week_ending, page_path, recordings_reviewed, heatmap_finding,
      recording_finding, action_decision, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    ON CONFLICT(week_ending, page_path) DO UPDATE SET
      recordings_reviewed = excluded.recordings_reviewed,
      heatmap_finding = excluded.heatmap_finding,
      recording_finding = excluded.recording_finding,
      action_decision = excluded.action_decision,
      updated_at = CURRENT_TIMESTAMP
  `).bind(
    weekEnding, pagePath, recordingsReviewed, heatmapFinding,
    recordingFinding, actionDecision,
  ).run();
  return json(request, { stored: true, weekEnding, pagePath });
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
      <p>请点击下面的链接确认订阅。确认后，你会收到莫白来关于读书与人生、投资复盘、iPhone/AI 教学的新文章提醒。</p>
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

  return Response.redirect(`${env.SITE_URL || 'https://www.790427.xyz'}/subscribe.html?status=confirmed`, 302);
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
    if (url.pathname.startsWith('/api/ops/')) {
      let authorized;
      try {
        authorized = await authorizeInternalRequest(request, env);
      } catch (error) {
        console.error(error);
        return json(request, { message: '运营接口尚未完成内部鉴权配置。' }, 503);
      }
      if (!authorized) return json(request, { message: 'Unauthorized' }, 401);

      if (request.method === 'GET' && url.pathname === '/api/ops/health') {
        return operationsHealth(request, env);
      }
      if (request.method === 'GET' && url.pathname === '/api/ops/newsletter-metrics') {
        return newsletterMetrics(request, env, url.searchParams.get('metricDate'));
      }
      if (request.method === 'POST' && url.pathname === '/api/ops/metrics') {
        return storeOperationsMetrics(request, env);
      }
      if (request.method === 'POST' && url.pathname === '/api/ops/report') {
        return sendOperationsReport(request, env);
      }
      if ((request.method === 'GET' || request.method === 'POST') && url.pathname === '/api/ops/weekly-input') {
        return weeklyOperations(request, env);
      }
      if ((request.method === 'GET' || request.method === 'POST') && url.pathname === '/api/ops/clarity-review') {
        return clarityReview(request, env);
      }
    }

    return json(request, { message: 'Not found' }, 404);
  },
};
