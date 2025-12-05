"""
Application Configuration

Uses Pydantic Settings for type-safe configuration management.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # API Metadata
    app_name: str = "Translation API"
    app_version: str = "1.0.0"
    app_description: str = "API for Chinese translation, phonetic transcription, and expression generation"

    # Deepseek API Settings
    deepseek_api_key: str
    deepseek_base_url: str = "https://api.deepseek.com"

    # MongoDB Settings
    mongodb_uri: str
    mongodb_database_name: str = "dev_lingohow"

    # R2 (Cloudflare) Storage Settings
    r2_bucket_name: str = ""
    r2_transcript_bucket_name: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_account_id: str = ""
    r2_endpoint_url: str = ""
    r2_token_value: str = ""

    # COS (Tencent Cloud Object Storage) Settings
    cos_secret_id: str = ""
    cos_secret_key: str = ""
    cos_bucket: str = ""
    cos_region: str = ""

    # CORS Settings
    cors_origins: List[str] = ["*"]
    cors_allow_credentials: bool = False

    # Rate Limiting
    rate_limit_transcript: str = "1/5seconds"

    # Performance Settings
    max_workers: int = 4
    max_concurrent_audio: int = 5
    audio_timeout_seconds: int = 30

    # Storage Paths
    audio_output_dir: str = "audio/sentences"

    # Logging
    log_level: str = "INFO"

    class Config:
        env_file = ".env.local"
        case_sensitive = False
        env_prefix = ""

    def get_r2_url(self, object_key: str) -> str:
        """
        Construct R2 public URL for an object.

        Args:
            object_key: The object key (path) in R2 bucket

        Returns:
            Full URL to access the file in R2
        """
        if not self.r2_account_id or not self.r2_bucket_name:
            return ""
        # R2 public URL pattern: https://{bucket}.{account_id}.r2.cloudflarestorage.com/{object_key}
        return f"https://{self.r2_bucket_name}.{self.r2_account_id}.r2.cloudflarestorage.com/{object_key}"

    def get_cos_url(self, object_key: str) -> str:
        """
        Construct COS public URL for an object.

        Args:
            object_key: The object key (path) in COS bucket

        Returns:
            Full URL to access the file in COS
        """
        if not self.cos_bucket or not self.cos_region:
            return ""
        # COS public URL pattern: https://{bucket}.cos.{region}.myqcloud.com/{object_key}
        return f"https://{self.cos_bucket}.cos.{self.cos_region}.myqcloud.com/{object_key}"


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached settings instance.

    Using lru_cache ensures we only create one Settings instance,
    improving performance and consistency.
    """
    return Settings()
