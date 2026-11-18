import os
from PIL import Image, ImageOps

UI_DIR = os.path.join("assets", "ui")

def prepare_ui_assets():
	# 1. Аватар — оставляем как есть, просто сохраняем в высоком качестве
	avatar_path = os.path.join(UI_DIR, "avatar.png")
	if os.path.exists(avatar_path):
		avatar = Image.open(avatar_path).convert("RGB")
		avatar.save(os.path.join(UI_DIR, "avatar_ready.png"), "PNG")
		print("Готов аватар: avatar_ready.png")

	# 2. Баннер — срезаем верхнюю золотую полоску (первые 14 пикселей)
	banner_path = os.path.join(UI_DIR, "banner.png")
	if os.path.exists(banner_path):
		banner = Image.open(banner_path).convert("RGB")
		w, h = banner.size
		banner_clean = banner.crop((0, 14, w, h))
		banner_clean.save(os.path.join(UI_DIR, "banner.webp"), "WEBP", quality=92)
		print("Готов баннер: banner.webp")

	# 3. Приветственная карточка — срезаем верхнюю золотую полоску (первые 12 пикселей)
	welcome_path = os.path.join(UI_DIR, "welcome.png")
	if os.path.exists(welcome_path):
		welcome = Image.open(welcome_path).convert("RGB")
		w, h = welcome.size
		welcome_clean = welcome.crop((0, 12, w, h))
		welcome_clean.save(os.path.join(UI_DIR, "welcome.webp"), "WEBP", quality=92)
		print("Готов экран /start: welcome.webp")

	# 4. Рубашка карты — убираем светлую полосу слева и выравниваем карту
	back_path = os.path.join(UI_DIR, "card_back.png")
	if os.path.exists(back_path):
		back = Image.open(back_path).convert("RGB")
		w, h = back.size
		# Отрезаем светлый край слева (16 px) и приводим к пропорции 2:3
		back_cropped = back.crop((16, 0, w, h))
		back_final = ImageOps.fit(back_cropped, (800, 1200), method=Image.Resampling.LANCZOS)
		back_final.save(os.path.join(UI_DIR, "card_back.webp"), "WEBP", quality=92)
		print("Готова рубашка: card_back.webp")

if __name__ == "__main__":
	prepare_ui_assets()
