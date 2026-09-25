import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or "change-me-in-production"
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or "postgresql://sa:Pa55w0rd@localhost:5332/myfinanceplace"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = None  # no limit on uploaded statements

    # AI reading of scanned/photographed/non-standard statements (app/services/ai_extraction.py)
    # LLM_PROVIDER: "ollama" (local, private) | "anthropic" (Claude API) | empty = disabled
    LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "")
    LLM_MODEL = os.environ.get("LLM_MODEL", "")          # empty = provider default
    OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
    LLM_TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "600"))  # seconds
    DEBUG = False


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


class TestingConfig(Config):
    TESTING = True
    LLM_PROVIDER = ""  # tests enable it explicitly
    SQLALCHEMY_DATABASE_URI = os.environ.get("TEST_DATABASE_URL") or "postgresql://sa:Pa55w0rd@localhost:5332/myfinanceplace_test"
    WTF_CSRF_ENABLED = False


config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}
