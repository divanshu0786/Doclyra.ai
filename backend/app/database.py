import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    gemini_api_key: str
    notion_access_token: str
    notion_review_queue_id: str
    notion_onboarding_id: str
    notion_run_log_id: str
    notion_documents_id: str
    database_url: str | None = None

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()