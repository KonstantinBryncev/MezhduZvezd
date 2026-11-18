import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class LLMProviderConfig:
	"""Конфигурация одного внешнего API-провайдера LLM."""

	name: str
	base_url: str
	api_key: str = field(repr=False)
	model: str


@dataclass(frozen=True)
class Settings:
	bot_token: str = field(repr=False)
	openrouter_api_key: str = field(repr=False)
	openrouter_model: str
	llm_providers: list[LLMProviderConfig]
	database_url: str
	daily_free_limit: int


def load_settings() -> Settings:
	load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=False)

	bot_token = os.getenv("BOT_TOKEN", "").strip()
	if not bot_token:
		raise ValueError("Не задан BOT_TOKEN в .env")

	openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
	openrouter_model = os.getenv("OPENROUTER_MODEL", "").strip()

	# Собираем цепочку всех доступных API-провайдеров из .env
	raw_providers = [
		(
			"OpenRouter",
			os.getenv("OPENROUTER_BASE_URL", "").strip(),
			openrouter_api_key,
			openrouter_model,
		),
		(
			"AionLabs",
			os.getenv("AIONLABS_BASE_URL", "").strip(),
			os.getenv("AIONLABS_API_KEY", "").strip(),
			os.getenv("AIONLABS_MODEL", "").strip(),
		),
		(
			"Groq",
			os.getenv("GROQ_BASE_URL", "").strip(),
			os.getenv("GROQ_API_KEY", "").strip(),
			os.getenv("GROQ_MODEL", "").strip(),
		),
		(
			"Cloudflare",
			os.getenv("CLOUDFLARE_BASE_URL", "").strip(),
			os.getenv("CLOUDFLARE_API_KEY", "").strip(),
			os.getenv("CLOUDFLARE_MODEL", "").strip(),
		),
	]

	llm_providers = [
		LLMProviderConfig(name=name, base_url=url, api_key=key, model=model)
		for name, url, key, model in raw_providers
		if url and key and model
	]

	database_url = os.getenv("DATABASE_URL", "").strip()

	raw_limit = os.getenv("DAILY_FREE_LIMIT", "3").strip()
	daily_free_limit = int(raw_limit) if raw_limit.isdigit() else 3

	return Settings(
		bot_token=bot_token,
		openrouter_api_key=openrouter_api_key,
		openrouter_model=openrouter_model,
		llm_providers=llm_providers,
		database_url=database_url,
		daily_free_limit=daily_free_limit,
	)
