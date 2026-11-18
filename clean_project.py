import os
import shutil
from pathlib import Path

# ==========================================
# НАСТРОЙКИ ОЧИСТКИ И СОРТИРОВКИ
# ==========================================

# True — только показать список действий без изменений.
# Поменяй на False, когда проверишь отчёт в консоли.
DRY_RUN = False

# Конкретные лишние файлы в корне, которые можно смело удалять
EXACT_TRASH_FILES = {
	"generate_and_build_deck (1).py",
	"generate_and_build_deck-1.py",
	"generate_and_build_deck.py",
	"Cormorant_Garamond.zip",
	"tarot_generation.log",
}

# Папки с кэшем, которые удаляются полностью
TRASH_DIRS = {
	"__pycache__",
	".pytest_cache",
	".mypy_cache",
}

# Папки, в которые скрипт не заходит при поиске мусора
PROTECTED_DIRS = {
	".git",
	"venv",
	".venv",
	"assets",
	"raw_cards",
}


def organize_and_clean(root_dir: Path) -> None:
	"""Переносит шрифт в assets/fonts и удаляет старые дубликаты скриптов."""
	mode_text = "ПРЕДПРОСМОТР (ничего не меняем)" if DRY_RUN else "БОЕВОЙ РЕЖИМ (чистим и сортируем)"
	print(f"=== Наводим порядок в проекте: {root_dir} ===")
	print(f"Режим: {mode_text}\n")

	# ------------------------------------------
	# 1. ПЕРЕНОС ШРИФТА В assets\fonts\
	# ------------------------------------------
	font_src = root_dir / "CormorantGaramond-Bold.ttf"
	fonts_dir = root_dir / "assets" / "fonts"
	font_dst = fonts_dir / "CormorantGaramond-Bold.ttf"

	if font_src.exists():
		print("--- Сортировка файлов ---")
		print(f"  [ПЕРЕМЕСТИТЬ] {font_src.name} -> assets\\fonts\\{font_dst.name}\n")
		if not DRY_RUN:
			fonts_dir.mkdir(parents=True, exist_ok=True)
			shutil.move(str(font_src), str(font_dst))

	# ------------------------------------------
	# 2. УДАЛЕНИЕ СТАРЫХ ДУБЛИКАТОВ И ЛОГОВ
	# ------------------------------------------
	print("--- Файлы к удалению ---")
	found_files = False
	for file_name in sorted(EXACT_TRASH_FILES):
		target = root_dir / file_name
		if target.exists():
			found_files = True
			print(f"  [УДАЛИТЬ ФАЙЛ]  {file_name}")
			if not DRY_RUN:
				target.unlink(missing_ok=True)

	if not found_files:
		print("  Лишних дубликатов не найдено.")

	# ------------------------------------------
	# 3. ОЧИСТКА __pycache__ ВНУТРИ app И КОРНЯ
	# ------------------------------------------
	print("\n--- Кэш-папки к удалению ---")
	found_dirs = False
	for current_root, dirs, _ in os.walk(root_dir):
		current_path = Path(current_root)
		dirs[:] = [d for d in dirs if d not in PROTECTED_DIRS]

		for d in list(dirs):
			if d in TRASH_DIRS:
				found_dirs = True
				rel_path = (current_path / d).relative_to(root_dir)
				print(f"  [УДАЛИТЬ ПАПКУ] {rel_path}")
				if not DRY_RUN:
					shutil.rmtree(current_path / d, ignore_errors=True)
				dirs.remove(d)

	if not found_dirs:
		print("  Кэш-папок не найдено.")

	if DRY_RUN:
		print("\n[!] Это был предпросмотр. Поменяй DRY_RUN = False и запусти снова, чтобы применить.")


if __name__ == "__main__":
	project_root = Path(__file__).resolve().parent
	organize_and_clean(project_root)
