import os
from pathlib import Path

# =====================================================================
# БАЗОВЫЕ ПУТИ ПРОЕКТА
# =====================================================================

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"

ASSETS_DIR = BASE_DIR / "assets"
DECK_DIR = ASSETS_DIR / "deck"
FONTS_DIR = ASSETS_DIR / "fonts"
UI_DIR = ASSETS_DIR / "ui"

RAW_CARDS_DIR = BASE_DIR / "raw_cards"
TEMP_SPREADS_DIR = BASE_DIR / "temp_spreads"
LOGS_DIR = BASE_DIR / "logs"

PROMPTS_FILE = BASE_DIR / "tarot_78_prompts_full.json"
PROGRESS_FILE = BASE_DIR / "generation_progress.json"
FONT_PATH = FONTS_DIR / "CormorantGaramond-Bold.ttf"


# =====================================================================
# ЗАГРУЗКА СЕКРЕТОВ ИЗ .ENV (РАБОТАЕТ ДАЖЕ БЕЗ PYTHON-DOTENV)
# =====================================================================

def _load_env_file(env_path: Path) -> None:
	"""Читает пары КЛЮЧ=ЗНАЧЕНИЕ из файла .env в переменные окружения процесса."""
	if not env_path.exists():
		return

	with open(env_path, "r", encoding="utf-8") as f:
		for raw_line in f:
			line = raw_line.strip()
			if not line or line.startswith("#") or "=" not in line:
				continue
			key, value = line.split("=", 1)
			key = key.strip()
			value = value.strip().strip('"').strip("'")
			os.environ.setdefault(key, value)


_load_env_file(ENV_FILE)
# =====================================================================
# СЕКРЕТНЫЕ КЛЮЧИ И ПАРАМЕТРЫ ИЗ ТВОЕГО .ENV
# =====================================================================

TELEGRAM_BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
TAROLOGIST_MODEL = [
	"google/gemma-4-31b-it:free",				# Основная: глубокие и связные трактовки
	"google/gemma-4-26b-a4b-it:free",		# Очень быстрая, большой контекст
	"dots-studio/dots-3-note-preview:free",		# Хорошо связывает карты в раскладе
	"thinkingmachines/inkling-2-small:free",	# Модель с логическим рассуждением
	"nvidia/nemotron-3.5-lightning:free",		# Высокая скорость для коротких ответов\
]

DAILY_FREE_LIMIT = 5
MOCK_AI_RESPONSES = os.getenv("MOCK_AI_RESPONSES", "True").lower() in ("true", "1", "yes")

# Список ID администраторов (например: ADMIN_IDS=123456789,987654321)
_raw_admins = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(x.strip()) for x in _raw_admins.split(",") if x.strip().isdigit()]


# =====================================================================
# НАСТРОЙКИ OPENROUTER И НЕЙРОСЕТИ
# =====================================================================

OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_IMAGE_URL = "https://openrouter.ai/api/v1/images"



IMAGE_GEN_MODEL = "recraft/recraft-v4.1-flash-v2:free"

AI_REQUEST_TIMEOUT_SEC = 60
AI_TEMPERATURE = 0.75
AI_MAX_TOKENS = 1400

# True — использовать локальную заглушку вместо реальных запросов в OpenRouter
MOCK_AI_RESPONSES = True


# =====================================================================
# НАСТРОЙКИ КОЛОДЫ, РАСКЛАДОВ И ОФОРМЛЕНИЯ
# =====================================================================

CARD_WIDTH = 800
CARD_HEIGHT = 1200

SPREAD_CARD_W = 440
SPREAD_CARD_H = 660

# Вероятность выпадения перевёрнутой карты (0.30 = 30%)
REVERSED_CHANCE = 0.30

# Фирменная палитра проекта «Между звёзд»
COLOR_BG_INDIGO = (18, 21, 36)
COLOR_CARD_INDIGO = (23, 26, 43)
COLOR_CARD_SHADOW = (8, 10, 18)
COLOR_GOLD = (200, 171, 115)
COLOR_MUTED_GOLD = (165, 145, 105)
COLOR_IVORY = (240, 232, 220)
