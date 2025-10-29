from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "FastAPI Project"
    VERSION: str = "1.0.0"
    DESCRIPTION: str = "FastAPI Project Template"
    API_V1_STR: str = "/api/v1"
    ALLOWED_ORIGINS: list[str] = ["http://localhost:3000"]  # Add your frontend URLs
    DATABASE_URL: str = "sqlite:///./sql_app.db"

    class Config:
        case_sensitive = True

settings = Settings()