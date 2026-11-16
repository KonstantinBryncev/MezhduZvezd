import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
	bot_token: str = field(repr=False)
	openrouter_api_key: str = field(repr=False)
	openrouter_model: str
	database_url: str
	daily_free_limit: int


def load_settings() -> Settings:
	load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=False)

	bot_token = os.getenv("BOT_TOKEN", "").strip()
	if not bot_token:
		raise ValueError("Не задан BOT_TOKEN в .env")

	openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
	openrouter_model = os.getenv("OPENROUTER_MODEL", "google/gemma-4-26b-a4b-it:free").strip()
	database_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./mezhdu_zvezd.db").strip()

	raw_limit = os.getenv("DAILY_FREE_LIMIT", "3").strip()
	daily_free_limit = int(raw_limit) if raw_limit.isdigit() else 3

	return Settings(
		bot_token=bot_token,
		openrouter_api_key=openrouter_api_key,
		openrouter_model=openrouter_model,
		database_url=database_url,
		daily_free_limit=daily_free_limit,
	)
