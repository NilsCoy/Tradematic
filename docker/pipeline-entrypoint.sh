#!/usr/bin/env sh
set -eu

mkdir -p main/scripts/datasets services/news_aggregator/data

if [ "${PIPELINE_MODE:-once}" = "schedule" ]; then
  exec make schedule LIMIT="${LIMIT:-20}" INTERVAL_SECONDS="${INTERVAL_SECONDS:-900}"
fi

if [ "${PIPELINE_MODE:-once}" = "existing-csv" ]; then
  exec make pipeline-from-existing-csv LIMIT="${LIMIT:-5}"
fi

exec make pipeline LIMIT="${LIMIT:-5}"
