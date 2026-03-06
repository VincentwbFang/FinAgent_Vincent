from __future__ import annotations

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class ProviderLimits(BaseModel):
    per_minute: int = 30
    per_day: int = 300


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Financial Analyst Agent"
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"

    database_url: str = "sqlite:///./data/agent.db"

    openrouter_api_key: str | None = None
    groq_api_key: str | None = None
    github_token: str | None = None
    hf_token: str | None = None

    openrouter_model: str = "openrouter/auto"
    groq_model: str = "llama-3.3-70b-versatile"
    github_model: str = "openai/gpt-4.1-mini"
    hf_model: str = "meta-llama/Llama-3.1-8B-Instruct"

    alpha_vantage_api_key: str | None = None
    fmp_api_key: str | None = None
    bls_api_key: str | None = None
    bea_api_key: str | None = None
    brave_api_key: str | None = None

    sec_user_agent: str = "FinancialAnalystAgent/1.0 (your_email@example.com)"

    request_timeout_seconds: float = 30.0

    groq_limits_per_minute: int = 30
    groq_limits_per_day: int = 300
    openrouter_limits_per_minute: int = 30
    openrouter_limits_per_day: int = 300
    github_limits_per_minute: int = 20
    github_limits_per_day: int = 200
    hf_limits_per_minute: int = 20
    hf_limits_per_day: int = 200

    @property
    def llm_limits(self) -> dict[str, ProviderLimits]:
        return {
            "groq": ProviderLimits(per_minute=self.groq_limits_per_minute, per_day=self.groq_limits_per_day),
            "openrouter": ProviderLimits(
                per_minute=self.openrouter_limits_per_minute,
                per_day=self.openrouter_limits_per_day,
            ),
            "github": ProviderLimits(per_minute=self.github_limits_per_minute, per_day=self.github_limits_per_day),
            "huggingface": ProviderLimits(per_minute=self.hf_limits_per_minute, per_day=self.hf_limits_per_day),
        }


settings = Settings()
