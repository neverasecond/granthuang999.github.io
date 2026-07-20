CREATE TABLE IF NOT EXISTS daily_metrics (
  metric_date TEXT NOT NULL,
  source TEXT NOT NULL,
  metric TEXT NOT NULL,
  dimension TEXT NOT NULL DEFAULT '',
  value REAL NOT NULL,
  metadata TEXT,
  collected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (metric_date, source, metric, dimension)
);

CREATE INDEX IF NOT EXISTS idx_daily_metrics_source_date
ON daily_metrics(source, metric_date);

CREATE INDEX IF NOT EXISTS idx_daily_metrics_metric_date
ON daily_metrics(metric, metric_date);

CREATE TABLE IF NOT EXISTS collection_runs (
  run_id TEXT PRIMARY KEY,
  metric_date TEXT NOT NULL,
  report_mode TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('started', 'success', 'partial', 'failed')),
  error_summary TEXT,
  started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  finished_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_collection_runs_metric_date
ON collection_runs(metric_date);

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
);
