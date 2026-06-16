from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """
    The main settings class. Pydantic will search the local system 
    environment and the target .env file to match these exact variable types.
    """
    REDIS_URL: str
    OPENAI_API_KEY: str
    ANTHROPIC_API_KEY: str
    MOCK_MODE: bool = False
    print(MOCK_MODE)
    
    # Configuration hook specialized for Pydantic v2
    model_config = SettingsConfigDict(
        env_file=".env",            # Look specifically for this local hidden file
        env_file_encoding="utf-8",  # Read standard text characters safely
        extra="ignore"              # If there are extra tokens in the .env file, ignore them silently
    )

# Instantiate the settings object immediately. 
# This runs the parsing logic *once* at initial startup boot.
settings = Settings()