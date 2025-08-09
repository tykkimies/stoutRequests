from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Database - Only setting needed in .env
    database_url: str = "postgresql://cueplex_user:CuePlexSecure2024!@localhost/cueplex"
    
    # Application Settings - Only core settings in .env
    secret_key: str = "your-secret-key-change-this-in-production"
    algorithm: str = "HS256" 
    access_token_expire_minutes: int = 1440  # 24 hours for better user experience
    
    # Environment
    environment: str = "development"
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()

# Note: API keys and service URLs are now stored in the database
# Use SettingsService to retrieve them at runtime for security