import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
APP_DIR = BASE_DIR / "app"

# Лишние черновики и случайные пустые файлы внутри папки app/
APP_TRASH_FILES = [
	"ai_tarologist.py",
	"deck_engine.py",
	"fill_major_arcana.py",
	"tarot_ui.py",
	"Image.Image",
	"None",
	"Path",
]

# Временные тестовые папки в корне и внутри app/
TEMP_DIRS = [
	BASE_DIR / "test_spreads",
	APP_DIR / "test_spreads",
]


def clean_all() -> None:
	"""Удаляет неиспользуемые черновики, пустые файлы и кэш перед деплоем."""
	print("=== Финальная уборка проекта «Между звёзд» ===\n")

	for fname in APP_TRASH_FILES:
		target = APP_DIR / fname
		if target.exists():
			target.unlink(missing_ok=True)
			print(f"[УДАЛЁН ФАЙЛ]  app\\{fname}")

	for dpath in TEMP_DIRS:
		if dpath.exists() and dpath.is_dir():
			shutil.rmtree(dpath, ignore_errors=True)
			print(f"[УДАЛЕНА ПАПКА] {dpath.relative_to(BASE_DIR)}")

	# Удаляем __pycache__ по всему проекту
	for cache_dir in BASE_DIR.rglob("__pycache__"):
		if ".venv" not in cache_dir.parts and "venv" not in cache_dir.parts:
			shutil.rmtree(cache_dir, ignore_errors=True)
			print(f"[КЭШ ОЧИЩЕН]   {cache_dir.relative_to(BASE_DIR)}")

	# Создаём пустую папку temp_spreads для работы склейки раскладов
	(BASE_DIR / "temp_spreads").mkdir(exist_ok=True)
	print("\n[OK] Структура проекта чистая и готова к переносу на сервер!")


if __name__ == "__main__":
	clean_all()
