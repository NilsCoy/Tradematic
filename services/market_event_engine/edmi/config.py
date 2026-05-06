from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "EventDrivenMarket Intelligence"
    redis_url: str = "redis://localhost:6379/0"
    database_url: str | None = None
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"
    tbank_token: str | None = None
    tradematic_datasets_dir: Path | None = Path("../Tradematic/main/scripts/datasets")
    news_aggregator_dir: Path = Path("../news_aggregator")
    news_aggregator_csv_path: Path = Path("../news_aggregator/data/news_dataset.csv")
    news_aggregator_collect_timeout_seconds: float = Field(default=180.0, gt=0)
    embedding_model: str = "intfloat/multilingual-e5-base"
    embedding_local_files_only: bool = True
    batch_size: int = Field(default=100, ge=1, le=1000)
    semantic_dup_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    cluster_eps: float = Field(default=0.3, ge=0.0, le=2.0)
    llm_timeout_seconds: float = Field(default=20.0, gt=0)
    queue_max_jobs: int = Field(default=20, ge=1)

    model_config = SettingsConfigDict(env_prefix="EDMI_", env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
