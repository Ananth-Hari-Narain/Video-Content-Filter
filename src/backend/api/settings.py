from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
import os

BASE_DIR = Path(__file__).resolve().parent


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if value is None:
        raise RuntimeError(f"{name} not loaded from dotenv file")
    return value


@dataclass(frozen=True)
class Settings:
    cloudflare_account_id: str
    r2_access_key_id: str
    r2_secret_access_key: str
    upstash_redis_job_store_url: str
    rabbitmq_url: str
    database_url: str
    bucket_name: str = "vcf-bucket"
    job_queue_name: str = "jobs_queue"

    @property
    def r2_endpoint_url(self) -> str:
        return f"https://{self.cloudflare_account_id}.r2.cloudflarestorage.com"


def load_settings() -> Settings:
    """Load settings from the environment (populated from `file.env` in dev)."""
    load_dotenv(BASE_DIR / "file.env")

    return Settings(
        cloudflare_account_id=_require_env("CLOUDFLARE_ACCOUNT_ID"),
        r2_access_key_id=_require_env("R2_ACCESS_KEY_ID"),
        r2_secret_access_key=_require_env("R2_SECRET_ACCESS_KEY"),
        upstash_redis_job_store_url=_require_env("UPSTASH_REDIS_JOB_STORE_URL"),
        rabbitmq_url=_require_env("RABBITMQ_URL"),
        database_url=_require_env("DATABASE_URL"),
    )
