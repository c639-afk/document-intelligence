from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    gemini_api_key: str

    gemini_model: str = "gemini-3.6-flash"
    gemini_fallback_model: str = "gemini-3.5-flash"

    model_config = SettingsConfigDict(
        env_file="backend/.env",
        extra="ignore",
        )


settings = Settings()
