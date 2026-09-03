"""
Centralized app settings, read from environment variables / .env.

Import get_settings() wherever you need a config value instead of calling
os.environ directly — this keeps validation and defaults in one place.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Postgres connection (see compose.yaml / .env)
    database_url: str

    # Langfuse tracing — optional; the app runs fine without them, tracing is just a no-op
    # (see app/graph/tracing.py). LANGFUSE_BASE_URL is the current name for what used to
    # be LANGFUSE_HOST — self-host it, or leave the default for Langfuse Cloud.
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_base_url: str = "https://cloud.langfuse.com"

    # LLM provider — set ANTHROPIC_API_KEY when you're ready to wire up app/graph/agent.py.
    # ANTHROPIC_WORKSPACE_ID is only needed if that key is "identity-linked" (tied to your
    # Console account across multiple workspaces) rather than scoped to one workspace —
    # find it at console.anthropic.com under the workspace's settings.
    anthropic_api_key: str | None = None
    anthropic_workspace_id: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
