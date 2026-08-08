"""Environment-based configuration for the AI Chatbot Engine backend."""
import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    def __init__(self):
        self.environment = os.getenv("ENVIRONMENT", "development")
        self.database_url = os.getenv("DATABASE_URL")
        self.openai_api_key = os.getenv("OPENAI_API_KEY")

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


config = Config()
