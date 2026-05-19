from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env_bool(name: str, default: bool) -> bool:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    return raw_value.lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    try:
        return float(raw_value)
    except ValueError:
        return default


@dataclass(frozen=True)
class RagpipeSettings:
    ollama_url: str = "http://localhost:11434"
    datasets_dir: Path = Path("main/scripts/datasets")
    embedding_model: str = "nomic-embed-text"
    chat_model: str = "tradematic-analyst"
    rerank_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    local_files_only: bool = True
    enable_chroma: bool = True
    enable_rerank: bool = False
    multi_query_timeout: float = 8.0
    embedding_timeout: float = 30.0
    chat_timeout: float = 600.0
    chat_context_chars: int = 900
    chat_num_predict: int = 384


def get_settings() -> RagpipeSettings:
    datasets_dir = os.environ.get("EDMI_TRADEMATIC_DATASETS_DIR", "main/scripts/datasets")
    return RagpipeSettings(
        ollama_url=os.environ.get("EDMI_OLLAMA_URL", "http://localhost:11434").rstrip("/"),
        datasets_dir=Path(datasets_dir),
        embedding_model=os.environ.get("RAGPIPE_EMBEDDING_MODEL", "nomic-embed-text"),
        chat_model=os.environ.get("RAGPIPE_CHAT_MODEL", "tradematic-analyst"),
        rerank_model=os.environ.get("RAGPIPE_RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2"),
        local_files_only=_env_bool("EDMI_EMBEDDING_LOCAL_FILES_ONLY", True),
        enable_chroma=_env_bool("RAGPIPE_ENABLE_CHROMA", True),
        enable_rerank=_env_bool("RAGPIPE_ENABLE_RERANK", False),
        multi_query_timeout=_env_float("RAGPIPE_MULTI_QUERY_TIMEOUT", 8.0),
        embedding_timeout=_env_float("RAGPIPE_EMBEDDING_TIMEOUT", 30.0),
        chat_timeout=_env_float("RAGPIPE_CHAT_TIMEOUT", 600.0),
        chat_context_chars=int(_env_float("RAGPIPE_CHAT_CONTEXT_CHARS", 900)),
        chat_num_predict=int(_env_float("RAGPIPE_CHAT_NUM_PREDICT", 384)),
    )


def default_index_dir() -> Path:
    return get_settings().datasets_dir / "ragpipe"
