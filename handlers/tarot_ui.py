import os
import random
from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import (
	Message,
	CallbackQuery,
	FSInputFile,
	InputMediaPhoto,
	InlineKeyboardMarkup,
	InlineKeyboardButton
)

# Создаём роутер для подключения к главному диспетчеру (dp.include_router(router))
router = Router()

# =====================================================================
# 1. НАСТРОЙКИ ПУТЕЙ И КЭШ FILE_ID
# =====================================================================

UI_DIR = os.path.join("assets", "ui")
DECK_DIR = os.path.join("assets", "deck")

PATH_WELCOME = os.path.join(UI_DIR, "welcome.webp")
PATH_BANNER = os.path.join(UI_DIR, "banner.webp")
PATH_CARD_BACK = os.path.join(UI_DIR, "card_back.webp")

# Словарь-кэш в оперативной памяти для мгновенной повторной отправки картинок
# (в продакшене его можно дублировать в таблицу PostgreSQL)
FILE_ID_CACHE: dict[str, str] = {}

# Пример словаря колоды (сюда подключишь свой полный словарь на 78 карт)
TAROT_DECK = {
	"major_00": {
		"name": "0 · Шут",
		"meaning": "Начало нового пути, лёгкость, доверие миру и готовность сделать шаг в неизвестность."
	},
	"major_01": {
		"name": "I · Маг",
		"meaning": "У вас уже есть все инструменты и внутренний ресурс, чтобы воплотить задуманное."
	},
	"major_17": {
		"name": "XVII · Звезда",
		"meaning": "Тихая надежда, исцеление и верный ориентир даже в самую тёмную ночь."
	},
	"major_18": {
		"name": "XVIII · Луна",
		"meaning": "Время прислушаться к интуиции и снам, не торопя события в тумане неопределённости."
	}
}


def get_photo_source(file_path: str) -> str | FSInputFile:
	"""
	Возвращает закэшированный file_id Telegram, если картинка уже отправлялась.
	Если отправляется впервые — возвращает FSInputFile для загрузки с диска.
	"""
	if file_path in FILE_ID_CACHE:
		return FILE_ID_CACHE[file_path]
	return FSInputFile(file_path)


def save_photo_cache(file_path: str, sent_message: Message) -> None:
	"""
	Сохраняет file_id самой качественной версии фото после первой отправки.
	"""
	if sent_message.photo and file_path not in FILE_ID_CACHE:
		FILE_ID_CACHE[file_path] = sent_message.photo[-1].file_id


# =====================================================================
# 2. КЛАВИАТУРЫ ИНТЕРФЕЙСА
# =====================================================================

def kb_main_menu() -> InlineKeyboardMarkup:
	"""Главное меню бота."""
	return InlineKeyboardMarkup(inline_keyboard=[
		[InlineKeyboardButton(text="✦ Карта дня", callback_data="draw_daily")],
		[InlineKeyboardButton(text="🕯 О пространстве", callback_data="about_space")]
	])


def kb_flip_card(card_id: str) -> InlineKeyboardMarkup:
	"""Кнопка переворота закрытой карты (передаём ID выпавшей карты в callback)."""
	return InlineKeyboardMarkup(inline_keyboard=[
		[InlineKeyboardButton(text="✨ Перевернуть карту", callback_data=f"flip:{card_id}")],
		[InlineKeyboardButton(text="← В меню", callback_data="back_to_main")]
	])


def kb_after_reading() -> InlineKeyboardMarkup:
	"""Кнопки после открытия карты."""
	return InlineKeyboardMarkup(inline_keyboard=[
		[InlineKeyboardButton(text="🔄 Вытянуть другую карту", callback_data="draw_daily")],
		[InlineKeyboardButton(text="← В главное меню", callback_data="back_to_main")]
	])


def kb_back_only() -> InlineKeyboardMarkup:
	"""Кнопка возврата из раздела «О пространстве»."""
	return InlineKeyboardMarkup(inline_keyboard=[
		[InlineKeyboardButton(text="← Вернуться к свече", callback_data="back_to_main")]
	])


# =====================================================================
# 3. ХЕНДЛЕРЫ СЦЕНАРИЯ
# =====================================================================

@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
	"""
	Вход в бот по команде /start.
	Отправляет приветственную картинку со свечой (welcome.webp).
	"""
	welcome_text = (
		"<b>Между звёзд</b>\n\n"
		"Свеча зажжена, колода на столе. Сделайте спокойный вдох, "
		"отпустите суету и выберите, с чего мы начнём."
	)
	
	sent = await message.answer_photo(
		photo=get_photo_source(PATH_WELCOME),
		caption=welcome_text,
		parse_mode="HTML",
		reply_markup=kb_main_menu()
	)
	save_photo_cache(PATH_WELCOME, sent)


@router.callback_query(F.data == "back_to_main")
async def on_back_to_main(callback: CallbackQuery) -> None:
	"""
	Плавный возврат в главное меню без спама новыми сообщениями (через edit_media).
	"""
	welcome_text = (
		"<b>Между звёзд</b>\n\n"
		"Вы снова у тихого стола. Выберите действие или задайте новый вопрос."
	)
	
	media = InputMediaPhoto(
		media=get_photo_source(PATH_WELCOME),
		caption=welcome_text,
		parse_mode="HTML"
	)
	
	edited = await callback.message.edit_media(
		media=media,
		reply_markup=kb_main_menu()
	)
	if isinstance(edited, Message):
		save_photo_cache(PATH_WELCOME, edited)
	await callback.answer()


@router.callback_query(F.data == "about_space")
async def on_about_space(callback: CallbackQuery) -> None:
	"""
	Переход в раздел «О пространстве».
	Подменяет картинку на широкий баннер с человеком у озера (banner.webp).
	"""
	about_text = (
		"<b>О пространстве «Между звёзд»</b>\n\n"
		"Здесь карты не пугают фатальными прогнозами. Это зеркало вашего "
		"текущего состояния и бережный навигатор для принятия решений.\n\n"
		"✦ <i>Авторская ночная колода</i>\n"
		"✦ <i>Глубокий разбор символов в контексте вашего вопроса</i>"
	)
	
	media = InputMediaPhoto(
		media=get_photo_source(PATH_BANNER),
		caption=about_text,
		parse_mode="HTML"
	)
	
	edited = await callback.message.edit_media(
		media=media,
		reply_markup=kb_back_only()
	)
	if isinstance(edited, Message):
		save_photo_cache(PATH_BANNER, edited)
	await callback.answer()


@router.callback_query(F.data == "draw_daily")
async def on_draw_daily(callback: CallbackQuery) -> None:
	"""
	Шаг 1 гадания: бот выбирает случайную карту из колоды, но показывает пользователю
	рубашку (card_back.webp) с предложением перевернуть её.
	"""
	# Выбираем случайный ID карты
	chosen_card_id = random.choice(list(TAROT_DECK.keys()))
	
	shuffle_text = (
		"🕯 <i>Колода перемешана...</i>\n\n"
		"Перед вами лежит закрытая карта. Мысленно сформулируйте свой запрос "
		"и нажмите кнопку ниже, когда будете готовы увидеть ответ."
	)
	
	media = InputMediaPhoto(
		media=get_photo_source(PATH_CARD_BACK),
		caption=shuffle_text,
		parse_mode="HTML"
	)
	
	edited = await callback.message.edit_media(
		media=media,
		reply_markup=kb_flip_card(chosen_card_id)
	)
	if isinstance(edited, Message):
		save_photo_cache(PATH_CARD_BACK, edited)
	await callback.answer()


@router.callback_query(F.data.startswith("flip:"))
async def on_flip_card(callback: CallbackQuery) -> None:
	"""
	Шаг 2 гадания: пользователь нажал «Перевернуть карту».
	Рубашка плавно заменяется на лицевой аркан и выводится его толкование.
	"""
	# Извлекаем ID карты из callback_data (формат "flip:major_17")
	card_id = callback.data.split(":", 1)[1]
	card_info = TAROT_DECK.get(card_id)
	
	if not card_info:
		await callback.answer("Карта потерялась в колоде, попробуйте снова.", show_alert=True)
		return
	
	# Путь к лицевой картинке аркана (если файла ещё нет на диске, подстрахуемся рубашкой)
	card_image_path = os.path.join(DECK_DIR, f"{card_id}.webp")
	if not os.path.exists(card_image_path):
		card_image_path = PATH_CARD_BACK
		
	result_text = (
		f"<b>{card_info['name']}</b>\n\n"
		f"{card_info['meaning']}"
	)
	
	media = InputMediaPhoto(
		media=get_photo_source(card_image_path),
		caption=result_text,
		parse_mode="HTML"
	)
	
	edited = await callback.message.edit_media(
		media=media,
		reply_markup=kb_after_reading()
	)
	if isinstance(edited, Message):
		save_photo_cache(card_image_path, edited)
	await callback.answer()
