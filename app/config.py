"""Environment-based configuration for the AI Chatbot Engine backend."""
import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    def __init__(self):
        self.environment = os.getenv("ENVIRONMENT", "development")
        self.database_url = os.getenv("DATABASE_URL")
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.jwt_secret = os.getenv("JWT_SECRET")
        self.frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
        self.stripe_secret_key = os.getenv("STRIPE_SECRET_KEY")
        self.stripe_webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
        self.stripe_price_id = os.getenv("STRIPE_PRICE_ID")

        if self.is_production and not self.jwt_secret:
            raise ValueError("JWT_SECRET is required in production")

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def effective_jwt_secret(self) -> str:
        # Dev-only fallback so local smoke tests don't need a real secret.
        return self.jwt_secret or "dev-only-insecure-secret-change-me"


config = Config()
