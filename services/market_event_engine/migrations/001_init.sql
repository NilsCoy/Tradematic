CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS news (
  id UUID PRIMARY KEY,
  source TEXT NOT NULL,
  title TEXT NOT NULL,
  text TEXT NOT NULL,
  url TEXT NOT NULL,
  text_hash TEXT NOT NULL UNIQUE,
  embedding vector(768),
  published_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS events (
  id UUID PRIMARY KEY,
  event_type TEXT NOT NULL,
  confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
  centroid_embedding vector(768),
  entities JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS event_news (
  event_id UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  news_id UUID NOT NULL REFERENCES news(id) ON DELETE CASCADE,
  PRIMARY KEY (event_id, news_id)
);

CREATE TABLE IF NOT EXISTS event_asset_relation (
  event_id UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  asset TEXT NOT NULL,
  level TEXT NOT NULL,
  confidence DOUBLE PRECISION NOT NULL,
  explanation TEXT NOT NULL,
  PRIMARY KEY (event_id, asset)
);

CREATE TABLE IF NOT EXISTS event_market_effect (
  event_id UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  asset TEXT NOT NULL,
  delta_1h DOUBLE PRECISION,
  delta_1d DOUBLE PRECISION,
  impact_1h DOUBLE PRECISION,
  impact_1d DOUBLE PRECISION,
  explanation TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (event_id, asset)
);

CREATE INDEX IF NOT EXISTS news_hash_idx ON news(text_hash);
CREATE INDEX IF NOT EXISTS event_asset_relation_asset_idx ON event_asset_relation(asset);
