import os
import random
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# =====================================================================
# КОНСТАНТЫ ОФОРМЛЕНИЯ И ПУТИ
# =====================================================================

# Определяем корень проекта (на уровень выше папки app)
BASE_DIR = Path(__file__).resolve().parent.parent

DECK_DIR = BASE_DIR / "assets" / "deck"
FONT_CANDIDATES = [
	BASE_DIR / "assets" / "fonts" / "CormorantGaramond-Bold.ttf",
	BASE_DIR / "CormorantGaramond-Bold.ttf",
]


# Фирменная палитра проекта «Между звёзд»
COLOR_BG_INDIGO = (18, 21, 36)		# Глубокий ночной фон стола
COLOR_CARD_SHADOW = (8, 10, 18)		# Цвет тени под картами
COLOR_GOLD = (200, 171, 115)		# Приглушённое золото (#C8AB73)
COLOR_IVORY = (240, 232, 220)		# Слоновая кость (#F0E8DC)
COLOR_MUTED_GOLD = (165, 145, 105)	# Приглушённый текст для доп. подписей

# Целевой размер одной карты внутри коллажа (пропорция 2:3)
SPREAD_CARD_W = 440
SPREAD_CARD_H = 660


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
	"""Загружает Cormorant Garamond с поддержкой кириллицы."""
	for path in FONT_CANDIDATES:
		if path.exists():
			return ImageFont.truetype(str(path), size)

	for fallback in ("georgia.ttf", "times.ttf", "arial.ttf"):
		try:
			return ImageFont.truetype(fallback, size)
		except OSError:
			continue
	return ImageFont.load_default()


def create_starry_background(width: int, height: int, seed: int = 42) -> Image.Image:
	"""Создаёт тёмно-синий звёздный фон и тонкую золотую рамку по периметру полотна."""
	bg = Image.new("RGB", (width, height), COLOR_BG_INDIGO)
	draw = ImageDraw.Draw(bg)

	# Рисуем россыпь мелких звёзд на фоне с фиксированным seed для аккуратности
	rng = random.Random(seed)
	star_count = (width * height) // 14000
	for _ in range(star_count):
		sx = rng.randint(30, width - 30)
		sy = rng.randint(30, height - 30)
		radius = rng.choice([1, 2])
		brightness = rng.randint(120, 220)
		star_color = (brightness, int(brightness * 0.9), int(brightness * 0.7))
		draw.ellipse([sx - radius, sy - radius, sx + radius, sy + radius], fill=star_color)

	# Внешняя и внутренняя золотые линии по краям всего расклада
	pad_outer = 18
	pad_inner = 26
	draw.rectangle(
		[pad_outer, pad_outer, width - pad_outer, height - pad_outer],
		outline=COLOR_GOLD,
		width=2
	)
	draw.rectangle(
		[pad_inner, pad_inner, width - pad_inner, height - pad_inner],
		outline=COLOR_MUTED_GOLD,
		width=1
	)
	return bg


def draw_centered_text(draw: ImageDraw.ImageDraw, text: str, center_x: int, y: int, font: ImageFont.ImageFont, color: tuple) -> int:
	"""Рисует текст строго по центру координаты center_x и возвращает его высоту."""
	bbox = draw.textbbox((0, 0), text, font=font)
	text_w = bbox[2] - bbox[0]
	text_h = bbox[3] - bbox[1]
	draw.text((center_x - text_w // 2, y), text, font=font, fill=color)
	return text_h



def build_spread_image(
	cards_data: list[dict],
	output_path: str | Path,
	spread_title: str = "РАСКЛАД МЕЖДУ ЗВЁЗД",
	deck_dir: Path = DECK_DIR
) -> Path:
	"""
	Собирает единое изображение расклада из 1 или нескольких карт.

	Параметры:
		cards_data: список словарей формата:
			[
				{"id": "major_00", "position": "ПРОШЛОЕ", "reversed": False},
				{"id": "wands_04", "position": "НАСТОЯЩЕЕ", "reversed": True},
				{"id": "major_01", "position": "БУДУЩЕЕ", "reversed": False},
			]
		output_path: путь, куда сохранить итоговый .webp или .jpg файл.
		spread_title: заголовок расклада сверху полотна.
		deck_dir: папка с готовыми картами колоды.
	"""
	if not cards_data:
		raise ValueError("Список карт для расклада пуст!")

	num_cards = len(cards_data)

	# Отступы и расчёт размеров итогового холста
	side_padding = 70
	gap_between_cards = 55
	top_header_height = 115
	bottom_footer_height = 105

	canvas_w = side_padding * 2 + num_cards * SPREAD_CARD_W + (num_cards - 1) * gap_between_cards
	# Для одиночной карты (Карта дня) делаем холст чуть шире, чтобы красиво смотрелся заголовок
	if num_cards == 1:
		canvas_w = max(canvas_w, 680)

	canvas_h = top_header_height + SPREAD_CARD_H + bottom_footer_height

	# Создаём фон и слой для мягких теней
	canvas = create_starry_background(canvas_w, canvas_h).convert("RGBA")
	shadow_layer = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
	shadow_draw = ImageDraw.Draw(shadow_layer)

	# Вычисляем стартовую X-координату, чтобы блок карт стоял ровно по центру холста
	total_cards_block_w = num_cards * SPREAD_CARD_W + (num_cards - 1) * gap_between_cards
	start_x = (canvas_w - total_cards_block_w) // 2
	cards_y = top_header_height

	# Подготавливаем карты и рисуем под них тени
	prepared_items = []
	for idx, item in enumerate(cards_data):
		card_id = item["id"]
		is_reversed = bool(item.get("reversed", False))
		position_label = item.get("position", f"ПОЗИЦИЯ {idx + 1}")

		card_path = deck_dir / f"{card_id}.webp"
		if not card_path.exists():
			raise FileNotFoundError(f"Карта не найдена в колоде: {card_path}")

		card_img = Image.open(card_path).convert("RGBA")
		card_img = card_img.resize((SPREAD_CARD_W, SPREAD_CARD_H), Image.Resampling.LANCZOS)

		# Если выпала перевёрнутая карта — разворачиваем на 180 градусов
		if is_reversed:
			card_img = card_img.rotate(180)

		cx = start_x + idx * (SPREAD_CARD_W + gap_between_cards)

		# Прямоугольник тени со смещением вниз и вправо
		shadow_offset = 10
		shadow_draw.rectangle(
			[cx + shadow_offset, cards_y + shadow_offset, cx + SPREAD_CARD_W + shadow_offset, cards_y + SPREAD_CARD_H + shadow_offset],
			fill=(*COLOR_CARD_SHADOW, 190)
		)

		prepared_items.append((card_img, cx, position_label, is_reversed))

	# Размываем слой теней и накладываем на фон
	shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=12))
	canvas = Image.alpha_composite(canvas, shadow_layer)

	# Вклеиваем сами карты поверх теней
	for card_img, cx, _, _ in prepared_items:
		canvas.alpha_composite(card_img, dest=(cx, cards_y))

	# Переходим к рисованию текста (заголовок и подписи позиций)
	final_img = canvas.convert("RGB")
	draw = ImageDraw.Draw(final_img)

	title_font = load_font(34)
	pos_font = load_font(26)
	sub_font = load_font(20)

	# Верхний заголовок расклада + декоративная золотая линия под ним
	spaced_header = " ".join(list(spread_title.upper()))
	draw_centered_text(draw, spaced_header, canvas_w // 2, 42, title_font, COLOR_GOLD)
	line_half_w = min(220, canvas_w // 3)
	draw.line(
		[(canvas_w // 2 - line_half_w, 90), (canvas_w // 2 + line_half_w, 90)],
		fill=COLOR_MUTED_GOLD,
		width=1
	)

	# Подписи позиций под каждой картой
	for _, cx, position_label, is_reversed in prepared_items:
		card_center_x = cx + SPREAD_CARD_W // 2
		label_y = cards_y + SPREAD_CARD_H + 18

		h = draw_centered_text(draw, position_label.upper(), card_center_x, label_y, pos_font, COLOR_IVORY)
		if is_reversed:
			draw_centered_text(draw, "(перевёрнутая)", card_center_x, label_y + h + 6, sub_font, COLOR_MUTED_GOLD)

	out_path = Path(output_path)
	out_path.parent.mkdir(parents=True, exist_ok=True)
	final_img.save(out_path, "WEBP", quality=92)
	return out_path


# =====================================================================
# ТЕСТОВЫЙ ЗАПУСК (СОБИРАЕТ ПРИМЕРЫ ИЗ ГОТОВЫХ КАРТ В test_spreads/)
# =====================================================================

if __name__ == "__main__":
	test_out_dir = Path("test_spreads")
	print("=== Тестовая сборка раскладов «Между звёзд» ===")

	# 1. Тест расклада на 3 карты (с одной перевёрнутой картой)
	three_cards = [
		{"id": "wands_04", "position": "ПРОШЛОЕ", "reversed": False},
		{"id": "wands_07", "position": "НАСТОЯЩЕЕ", "reversed": True},
		{"id": "wands_09", "position": "БУДУЩЕЕ", "reversed": False},
	]
	p1 = build_spread_image(
		cards_data=three_cards,
		output_path=test_out_dir / "test_3_cards.webp",
		spread_title="ТРИ КАРТЫ СУДЬБЫ"
	)
	print(f"[OK] Расклад на 3 карты готов: {p1}")

	# 2. Тест Карты дня (1 карта)
	one_card = [
		{"id": "wands_08", "position": "КАРТА ДНЯ", "reversed": False},
	]
	p2 = build_spread_image(
		cards_data=one_card,
		output_path=test_out_dir / "test_card_of_day.webp",
		spread_title="ПОСЛАНИЕ ДНЯ"
	)
	print(f"[OK] Карта дня готова: {p2}")
