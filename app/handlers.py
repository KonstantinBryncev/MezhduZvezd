import asyncio
from contextlib import suppress
from datetime import timedelta, timezone
import html
from pathlib import Path
import re
import secrets

from aiogram import F, Router
from aiogram.enums import ChatType, ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, InputMediaPhoto, Message

from app.ai_service import OpenRouterService
from app.cards_service import CardsRepository, TarotCard
from app.config import load_settings
from app.database import DatabaseRepository
from app.keyboards import (
	BTN_ABOUT,
	BTN_CANCEL,
	BTN_CARD_OF_DAY,
	BTN_HISTORY,
	BTN_THREE_CARDS,
	get_about_keyboard,
	get_after_day_card_keyboard,
	get_after_spread_keyboard,
	get_cancel_keyboard,
	get_confirm_delete_keyboard,
	get_dislike_reason_keyboard,
	get_history_keyboard,
	get_main_menu_keyboard,
)
from app.spread_builder import build_spread_image
from app.states import SpreadStates

BASE_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = BASE_DIR / "assets"
DECK_DIR = ASSETS_DIR / "deck"
UI_DIR = ASSETS_DIR / "ui"
TEMP_SPREADS_DIR = BASE_DIR / "data" / "temp_spreads"
TEMP_SPREADS_DIR.mkdir(parents=True, exist_ok=True)

PATH_WELCOME = UI_DIR / "welcome.webp"
PATH_CARD_BACK = UI_DIR / "card_back.webp"

MSK_TZ = timezone(timedelta(hours=3))
UI_FILE_ID_CACHE: dict[str, str] = {}

FOLLOWUP_RITUAL_STEPS = [
	"🕯 <i>Осмысляю твоё уточнение...</i>",
	"✨ <i>Всматриваюсь глубже в выпавшие арканы...</i>",
	"📜 <i>Формулирую ответ...</i>",
]


def _sanitize_telegram_html(text: str) -> str:
	"""Заменяет неподдерживаемые Telegram теги (вроде <br>) на обычные переносы."""
	return re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)


def _short_hint(text: str, max_len: int = 135) -> str:
	"""Обрезает подсказку до 1–2 аккуратных строк."""
	clean = " ".join(text.split())
	if len(clean) <= max_len:
		return clean
	return clean[: max_len - 1].rsplit(" ", 1)[0] + "…"


async def _animate_wait_message(
	message: Message,
	steps: list[str],
	is_photo: bool = False,
	interval: float = 2.0,
) -> None:
	"""Плавно меняет текст или подпись под рубашкой во время уточняющего вопроса."""
	idx = 1
	while True:
		await asyncio.sleep(interval)
		next_text = steps[min(idx, len(steps) - 1)]
		with suppress(TelegramBadRequest):
			if is_photo:
				await message.edit_caption(caption=next_text, parse_mode=ParseMode.HTML)
			else:
				await message.edit_text(text=next_text, parse_mode=ParseMode.HTML)
		idx += 1


async def _send_and_reveal_three_cards(
	message: Message,
	cards: list[TarotCard],
	image_ids: list[str | None],
	step_delay: float = 2.0,
) -> tuple[Message, asyncio.Task[None]]:
	"""Отправляет 1-ю карту сразу и поочерёдно сменяет её на 2-ю и 3-ю (по 2 сек на каждую)."""
	c1, c2, c3 = cards
	positions = [
		("1/3 • Ситуация сейчас", c1.situation_hint),
		("2/3 • На что обратить внимание", c2.notice_hint),
		("3/3 • Возможный следующий шаг", c3.next_step_hint),
	]

	def _build_caption(idx: int) -> str:
		pos_title, hint = positions[idx]
		text = (
			f"🃏 <b>{pos_title}: {html.escape(cards[idx].name)}</b>\n"
			f"<i>{html.escape(_short_hint(hint))}</i>"
		)
		if idx == 2:
			text += "\n\n✨ <i>Собираю целостный отклик по всем трём картам...</i>"
		return text

	first_caption = _build_caption(0)
	first_id = next(iter(image_ids), None)
	first_path = (DECK_DIR / f"{first_id}.webp") if first_id else None

	if first_path and first_path.exists():
		key = str(first_path)
		photo_source = UI_FILE_ID_CACHE.get(key) or FSInputFile(first_path)
		wait_msg = await message.answer_photo(
			photo=photo_source,
			caption=first_caption,
			parse_mode=ParseMode.HTML,
		)
		if wait_msg.photo and key not in UI_FILE_ID_CACHE:
			UI_FILE_ID_CACHE[key] = wait_msg.photo[-1].file_id
	else:
		wait_msg = await message.answer(first_caption, parse_mode=ParseMode.HTML)

	async def _sequence() -> None:
		for idx in (1, 2):
			await asyncio.sleep(step_delay)
			caption = _build_caption(idx)
			curr_id = image_ids[idx]
			curr_path = (DECK_DIR / f"{curr_id}.webp") if curr_id else None
			with suppress(TelegramBadRequest):
				if curr_path and curr_path.exists():
					key = str(curr_path)
					media_source = UI_FILE_ID_CACHE.get(key) or FSInputFile(curr_path)
					edited = await wait_msg.edit_media(
						media=InputMediaPhoto(
							media=media_source,
							caption=caption,
							parse_mode=ParseMode.HTML,
						)
					)
					if isinstance(edited, Message) and edited.photo and key not in UI_FILE_ID_CACHE:
						UI_FILE_ID_CACHE[key] = edited.photo[-1].file_id
				elif wait_msg.photo:
					await wait_msg.edit_caption(caption=caption, parse_mode=ParseMode.HTML)
				else:
					await wait_msg.edit_text(text=caption, parse_mode=ParseMode.HTML)

		await asyncio.sleep(step_delay)

	return wait_msg, asyncio.create_task(_sequence())




_DECK_FILE_MAP: dict[str, str] | None = None


def resolve_card_image_id(card_id: str) -> str | None:
	"""Находит имя файла картинки в assets/deck по ID карты (учитывая префиксы вроде major_02)."""
	global _DECK_FILE_MAP
	if _DECK_FILE_MAP is None:
		_DECK_FILE_MAP = {}
		if DECK_DIR.exists():
			for p in DECK_DIR.glob("*.webp"):
				stem = p.stem
				_DECK_FILE_MAP[stem] = stem
				# Если файл называется например "02_high_priestess", сохраняем и "high_priestess"
				parts = stem.split("_", 1)
				if len(parts) == 2 and parts[0].isdigit():
					_DECK_FILE_MAP[parts[1]] = stem

	if card_id in _DECK_FILE_MAP:
		return _DECK_FILE_MAP[card_id]

	# Поиск по частичному совпадению (например "major_02" <-> "02_major")
	clean_id = card_id.lower()
	for stem in _DECK_FILE_MAP.values():
		if clean_id in stem.lower() or stem.lower() in clean_id:
			return stem

	return None



def draw_available_cards(count: int) -> list[TarotCard]:
	"""Выбирает случайные карты только из тех, для которых уже готов .webp в assets/deck."""
	picked: list[TarotCard] = []
	seen_ids: set[str] = set()
	for _ in range(500):
		card = cards_repo.get_random_card()
		if card.id in seen_ids:
			continue
		if resolve_card_image_id(card.id) is not None:
			picked.append(card)
			seen_ids.add(card.id)
			if len(picked) == count:
				return picked
	return cards_repo.draw_three_cards()[:count]


def find_card_by_id(card_id: str) -> TarotCard:
	"""Безопасно ищем карту по её ID в загруженной колоде."""
	if hasattr(cards_repo, "get_card_by_id"):
		found = cards_repo.get_card_by_id(card_id)
		if found is not None:
			return found
	all_cards = getattr(cards_repo, "cards", None) or getattr(cards_repo, "_cards", [])
	for item in all_cards:
		if getattr(item, "id", None) == card_id:
			return item
	return cards_repo.get_random_card()


def format_day_card(card: TarotCard, already_drawn: bool = False) -> str:
	note = ""
	if already_drawn:
		note = "\n\n<i>🌙 Ты уже вытянул(а) карту дня сегодня. Новая откроется после полуночи по МСК.</i>"
	return (
		f"✨ <b>Карта дня: {card.name}</b>\n\n"
		f"<i>Образ: {card.image_cue}</i>\n\n"
		f"{card.day_text}\n\n"
		f"<b>Вопрос для тихой паузы:</b>\n"
		f"— {card.reflection_question}"
		f"{note}"
	)


def format_fallback_spread(question: str, cards: list[TarotCard]) -> str:
	c1, c2, c3 = cards
	return (
		f"<i>Запрос: {html.escape(question)}</i>\n\n"
		f"<b>1. Ситуация сейчас — {c1.name}</b>\n"
		f"{c1.situation_hint}\n\n"
		f"<b>2. На что обратить внимание — {c2.name}</b>\n"
		f"{c2.notice_hint}\n\n"
		f"<b>3. Возможный следующий шаг — {c3.name}</b>\n"
		f"{c3.next_step_hint}\n\n"
		f"<b>Вопрос для размышления:</b>\n"
		f"— {c3.reflection_question}"
	)


async def check_spread_access(telegram_id: int) -> tuple[bool, str]:
	used_today, daily_limit, is_premium = await db_repo.get_daily_usage(telegram_id)
	if is_premium or used_today < daily_limit:
		return True, ""

	text = (
		f"🌙 На сегодня бесплатный лимит глубоких раскладов исчерпан "
		f"(<b>{used_today} из {daily_limit}</b>).\n\n"
		f"Счётчик обновится в полночь по МСК. "
		f"А прямо сейчас ты можешь заглянуть в <b>✨ Карту дня</b> "
		f"или перечитать <b>📜 Мои расклады</b>."
	)
	return False, text


settings = load_settings()
router = Router(name="tarot_main")
db_repo = DatabaseRepository(settings.database_url, settings.daily_free_limit)
cards_repo = CardsRepository()
ai_service = OpenRouterService(
	api_key=settings.openrouter_api_key,
	model=settings.openrouter_model,
	providers=settings.llm_providers,
)


@router.message(CommandStart())
async def handle_start(message: Message, state: FSMContext) -> None:
	await state.clear()
	if message.from_user:
		await db_repo.get_or_create_user(
			telegram_id=message.from_user.id,
			username=message.from_user.username,
			first_name=message.from_user.first_name,
		)

	welcome_caption = (
		"Привет! Это <b>«Между звёзд»</b> — пространство для спокойной "
		"саморефлексии через образы карт Таро.\n\n"
		"Здесь нет предсказаний будущего и «правильных» толкований. "
		"Карта — это зеркало, которое помогает прислушаться к себе.\n\n"
		"Выбери практику в меню ниже. Остановиться можно в любой момент."
	)
	if PATH_WELCOME.exists():
		await message.answer_photo(
			photo=FSInputFile(PATH_WELCOME),
			caption=welcome_caption,
			parse_mode=ParseMode.HTML,
			reply_markup=get_main_menu_keyboard(),
		)
	else:
		await message.answer(
			welcome_caption,
			parse_mode=ParseMode.HTML,
			reply_markup=get_main_menu_keyboard(),
		)


@router.message(Command("help"))
@router.message(F.text == BTN_ABOUT)
async def handle_help(message: Message, state: FSMContext) -> None:
	await state.clear()
	limit_line = f"Доступно до <b>{settings.daily_free_limit}</b> раскладов на 3 карты в день."
	if message.from_user:
		used, limit, is_premium = await db_repo.get_daily_usage(message.from_user.id)
		if is_premium:
			limit_line = "У тебя активен безлимитный доступ к раскладам."
		else:
			left = max(0, limit - used)
			limit_line = f"Сегодня осталось раскладов на 3 карты: <b>{left} из {limit}</b>."

	await message.answer(
		"<b>О пространстве «Между звёзд»</b>\n\n"
		"• <b>Карта дня</b> — один образ из 78 карт и вопрос для фокуса на текущие сутки по МСК.\n"
		"• <b>Расклад на 3 карты</b> — глубокий разбор под твой запрос с возможностью "
		"задать один уточняющий вопрос.\n"
		f"• <b>Лимит:</b> {limit_line}\n\n"
		"<i>Важно:</i> бот не предсказывает будущее и не заменяет "
		"психологическую, медицинскую или юридическую помощь.",
		parse_mode=ParseMode.HTML,
		reply_markup=get_about_keyboard(),
	)


@router.callback_query(F.data == "confirm_delete_data")
async def callback_confirm_delete_data(callback: CallbackQuery) -> None:
	await callback.answer()
	if callback.message:
		await callback.message.answer(
			"Ты уверен(а), что хочешь <b>безвозвратно удалить</b> все свои сохранённые "
			"расклады, карты дня и запись профиля из базы данных?",
			parse_mode=ParseMode.HTML,
			reply_markup=get_confirm_delete_keyboard(),
		)


@router.callback_query(F.data == "cancel_delete_data")
async def callback_cancel_delete_data(callback: CallbackQuery) -> None:
	await callback.answer("Удаление отменено.")
	if callback.message:
		await callback.message.edit_text("Хорошо, все твои записи оставлены на месте.")


@router.callback_query(F.data == "execute_delete_data")
async def callback_execute_delete_data(callback: CallbackQuery, state: FSMContext) -> None:
	await callback.answer()
	await state.clear()
	if callback.from_user:
		await db_repo.delete_user_data(telegram_id=callback.from_user.id)
	if callback.message:
		await callback.message.edit_text(
			"🗑 Готово. Все твои расклады и данные полностью удалены из базы."
		)


@router.message(Command("history"))
@router.message(F.text == BTN_HISTORY)
async def handle_history(message: Message, state: FSMContext) -> None:
	await state.clear()
	if not message.from_user:
		return

	readings = await db_repo.get_recent_readings(telegram_id=message.from_user.id, limit=5)
	if not readings:
		await message.answer(
			"У тебя пока нет сохранённых раскладов на 3 карты.\n\n"
			"Нажми <b>«🌌 Расклад на 3 карты»</b>, чтобы сделать первую практику.",
			parse_mode=ParseMode.HTML,
			reply_markup=get_main_menu_keyboard(),
		)
		return

	lines = ["📜 <b>Твои последние расклады:</b>\n"]
	kb_items: list[tuple[int, str]] = []

	for idx, item in enumerate(readings, start=1):
		created_utc = (
			item.created_at.replace(tzinfo=timezone.utc)
			if item.created_at.tzinfo is None
			else item.created_at
		)
		dt_msk = created_utc.astimezone(MSK_TZ).strftime("%d.%m.%Y %H:%M")
		short_q = html.escape(item.question[:70]) + ("..." if len(item.question) > 70 else "")
		cards_str = f"{item.card_1_name} • {item.card_2_name} • {item.card_3_name}"

		lines.append(
			f"<b>{idx}. {dt_msk} (МСК)</b>\n"
			f"<i>Запрос:</i> {short_q}\n"
			f"<i>Карты:</i> {cards_str}"
		)
		if item.followup_question:
			lines.append("<i>💬 Есть уточняющий вопрос и ответ</i>")
		lines.append("")

		btn_label = f"📖 Открыть №{idx} ({dt_msk[:5]} • {item.card_1_name[:18]})"
		kb_items.append((item.id, btn_label))

	lines.append("<i>Нажми на кнопку ниже, чтобы прочитать полный разбор:</i>")

	await message.answer(
		"\n".join(lines).strip(),
		parse_mode=ParseMode.HTML,
		reply_markup=get_history_keyboard(kb_items),
	)


@router.callback_query(F.data.startswith("view_reading:"))
async def callback_view_reading(callback: CallbackQuery) -> None:
	await callback.answer()
	if not callback.from_user or not callback.message or not callback.data:
		return

	raw_id = callback.data.split(":", maxsplit=1)[1]
	if not raw_id.isdigit():
		return

	reading = await db_repo.get_reading_by_id(
		reading_id=int(raw_id),
		telegram_id=callback.from_user.id,
	)
	if reading is None:
		await callback.message.answer("Не удалось найти этот расклад в базе.")
		return

	created_utc = (
		reading.created_at.replace(tzinfo=timezone.utc)
		if reading.created_at.tzinfo is None
		else reading.created_at
	)
	dt_msk = created_utc.astimezone(MSK_TZ).strftime("%d.%m.%Y %H:%M")

	header = (
		f"📜 <b>Расклад от {dt_msk} (МСК)</b>\n"
		f"<i>Запрос:</i> {html.escape(reading.question)}\n"
		f"<i>Карты:</i> {reading.card_1_name} • {reading.card_2_name} • {reading.card_3_name}\n\n"
	)

	full_body = _sanitize_telegram_html(header + reading.ai_interpretation)
	for start in range(0, len(full_body), 4000):
		await callback.message.answer(
			full_body[start : start + 4000],
			parse_mode=ParseMode.HTML,
		)

	if reading.followup_question and reading.followup_answer:
		followup_block = _sanitize_telegram_html(
			f"💬 <b>Твой уточняющий вопрос:</b>\n"
			f"<i>{html.escape(reading.followup_question)}</i>\n\n"
			f"<b>Отклик на уточнение:</b>\n"
			f"{reading.followup_answer}"
		)
		for start in range(0, len(followup_block), 4000):
			await callback.message.answer(
				followup_block[start : start + 4000],
				parse_mode=ParseMode.HTML,
			)


@router.message(Command("day"))
@router.message(F.text == BTN_CARD_OF_DAY)
async def handle_day_card(message: Message, state: FSMContext) -> None:
	await state.clear()
	(candidate,) = draw_available_cards(1)

	if message.from_user:
		saved_id, already_drawn = await db_repo.get_or_set_daily_card_id(
			telegram_id=message.from_user.id,
			username=message.from_user.username,
			first_name=message.from_user.first_name,
			candidate_card_id=candidate.id,
		)
		card = find_card_by_id(saved_id)
	else:
		card = candidate
		already_drawn = False

	day_text = format_day_card(card, already_drawn=already_drawn)
	img_id = resolve_card_image_id(card.id)
	photo_to_send = (DECK_DIR / f"{img_id}.webp") if img_id else PATH_CARD_BACK

	if photo_to_send.exists():
		await message.answer_photo(
			photo=FSInputFile(photo_to_send),
			caption=day_text,
			parse_mode=ParseMode.HTML,
			reply_markup=get_after_day_card_keyboard(),
		)
	else:
		await message.answer(
			day_text,
			parse_mode=ParseMode.HTML,
			reply_markup=get_after_day_card_keyboard(),
		)


@router.message(Command("spread"))
@router.message(F.text == BTN_THREE_CARDS)
async def handle_start_spread(message: Message, state: FSMContext) -> None:
	await state.clear()
	if message.from_user:
		allowed, deny_text = await check_spread_access(message.from_user.id)
		if not allowed:
			await message.answer(
				deny_text,
				parse_mode=ParseMode.HTML,
				reply_markup=get_main_menu_keyboard(),
			)
			return

	await state.set_state(SpreadStates.waiting_for_question)
	await message.answer(
		"О чём бы ты хотел(а) спокойно подумать сейчас?\n\n"
		"Напиши свой вопрос или кратко опиши ситуацию одним сообщением. "
		"Например: <i>«Чувствую усталость от работы и не понимаю, на что опереться»</i>.",
		parse_mode=ParseMode.HTML,
		reply_markup=get_cancel_keyboard(),
	)


@router.callback_query(F.data == "start_three_cards")
async def callback_start_spread(callback: CallbackQuery, state: FSMContext) -> None:
	await callback.answer()
	await state.clear()
	if callback.from_user:
		allowed, deny_text = await check_spread_access(callback.from_user.id)
		if not allowed and callback.message:
			await callback.message.answer(
				deny_text,
				parse_mode=ParseMode.HTML,
				reply_markup=get_main_menu_keyboard(),
			)
			return

	await state.set_state(SpreadStates.waiting_for_question)
	if callback.message:
		await callback.message.answer(
			"О чём бы ты хотел(а) спокойно подумать сейчас?\n\n"
			"Напиши свой вопрос или кратко опиши ситуацию одним сообщением.",
			parse_mode=ParseMode.HTML,
			reply_markup=get_cancel_keyboard(),
		)


@router.message(F.text == BTN_CANCEL)
@router.message(Command("cancel"))
async def handle_cancel(message: Message, state: FSMContext) -> None:
	await state.clear()
	await message.answer(
		"Хорошо, сделали паузу. Возвращаю главное меню.",
		reply_markup=get_main_menu_keyboard(),
	)


@router.message(SpreadStates.waiting_for_question)
async def handle_spread_question(message: Message, state: FSMContext) -> None:
	if not message.text:
		await message.answer(
			"Пожалуйста, сформулируй вопрос текстом в одном сообщении.",
			reply_markup=get_cancel_keyboard(),
		)
		return

	question = message.text.strip()
	if question == BTN_CANCEL:
		await handle_cancel(message, state)
		return

	if len(question) < 3:
		await message.answer(
			"Вопрос слишком короткий. Попробуй описать ситуацию чуть подробнее — "
			"хотя бы в нескольких словах.",
			reply_markup=get_cancel_keyboard(),
		)
		return

	if len(question) > 500:
		await message.answer(
			"Сообщение получилось слишком длинным (больше 500 символов). "
			"Сократи его, пожалуйста, до главного вопроса.",
			reply_markup=get_cancel_keyboard(),
		)
		return

	if message.from_user:
		used_today, effective_limit, is_premium = await db_repo.get_daily_usage(
			telegram_id=message.from_user.id
		)
		if not is_premium and used_today >= effective_limit:
			await state.clear()
			await message.answer(
				f"Сегодняшний лимит бесплатных раскладов ({effective_limit} в день) исчерпан.\n"
				"Возвращайся завтра или загляни в раздел «Карта дня».",
				reply_markup=get_main_menu_keyboard(),
			)
			return

	await state.clear()

	# 1. Вытягиваем 3 карты сразу
	drawn_cards = draw_available_cards(3)
	c1, c2, c3 = drawn_cards
	img1 = resolve_card_image_id(c1.id)
	img2 = resolve_card_image_id(c2.id)
	img3 = resolve_card_image_id(c3.id)

	# 2. Сразу показываем 1-ю карту и запускаем показ 2-й и 3-й (по 2 сек на каждую)
	wait_msg, reveal_task = await _send_and_reveal_three_cards(
		message=message,
		cards=drawn_cards,
		image_ids=[img1, img2, img3],
		step_delay=2.0,
	)

	# 3. Параллельно запрашиваем ответ нейросети и клеим финальный коллаж
	ai_task = asyncio.create_task(
		ai_service.synthesize_spread(question=question, cards=drawn_cards)
	)

	collage_path: Path | None = None
	try:
		if img1 and img2 and img3:
			spread_cards_data = [
				{"id": img1, "position": "1. СИТУАЦИЯ", "reversed": False},
				{"id": img2, "position": "2. ВНИМАНИЕ", "reversed": False},
				{"id": img3, "position": "3. СЛЕДУЮЩИЙ ШАГ", "reversed": False},
			]
			token = secrets.token_hex(4)
			collage_path = TEMP_SPREADS_DIR / f"spread_{message.chat.id}_{token}.webp"
			await asyncio.to_thread(
				build_spread_image,
				cards_data=spread_cards_data,
				output_path=collage_path,
				spread_title="РАСКЛАД МЕЖДУ ЗВЁЗД",
				deck_dir=DECK_DIR,
			)
		_, interpretation = await asyncio.gather(reveal_task, ai_task)
	finally:
		for task in (reveal_task, ai_task):
			if not task.done():
				task.cancel()
				with suppress(asyncio.CancelledError):
					await task

	# 4. Убираем одиночную карту и выкладываем общий коллаж из 3 карт
	with suppress(TelegramBadRequest):
		await wait_msg.delete()

	if collage_path and collage_path.exists():
		await message.answer_photo(
			photo=FSInputFile(collage_path),
			caption=(
				f"🌌 <b>Карты расклада:</b> "
				f"{html.escape(c1.name)} • {html.escape(c2.name)} • {html.escape(c3.name)}"
			),
			parse_mode=ParseMode.HTML,
		)
		collage_path.unlink(missing_ok=True)

	if not interpretation:
		interpretation = format_fallback_spread(question=question, cards=drawn_cards)

	# 5. Сохраняем в БД и отправляем полный разбор
	reading_id = None
	if message.from_user:
		reading = await db_repo.create_reading(
			telegram_id=message.from_user.id,
			username=message.from_user.username,
			first_name=message.from_user.first_name,
			question=question,
			card_names=[c1.name, c2.name, c3.name],
			ai_interpretation=interpretation,
		)
		reading_id = reading.id

	cards_header = (
		f"<b>Выпавшие карты:</b>\n"
		f"1. Ситуация — <b>{html.escape(c1.name)}</b>\n"
		f"2. На что обратить внимание — <b>{html.escape(c2.name)}</b>\n"
		f"3. Следующий шаг — <b>{html.escape(c3.name)}</b>\n\n"
	)

	cards_summary = (
		f"1. Ситуация сейчас: {c1.name}\n"
		f"2. На что обратить внимание: {c2.name}\n"
		f"3. Возможный следующий шаг: {c3.name}"
	)
	await state.update_data(
		reading_id=reading_id,
		original_question=question,
		cards_summary=cards_summary,
		previous_reply=interpretation,
	)

	full_text = _sanitize_telegram_html(f"{cards_header}{interpretation}")
	await message.answer(
		full_text,
		parse_mode=ParseMode.HTML,
		reply_markup=get_after_spread_keyboard(reading_id=reading_id),
	)


@router.callback_query(F.data == "ask_followup")
async def callback_ask_followup(callback: CallbackQuery, state: FSMContext) -> None:
	data = await state.get_data()
	if not data.get("cards_summary"):
		await callback.answer("Этот расклад уже завершён. Можешь начать новый!", show_alert=True)
		return

	await callback.answer()
	await state.set_state(SpreadStates.waiting_for_followup)
	if callback.message:
		await callback.message.answer(
			"Напиши свой <b>один уточняющий вопрос</b> по этим же трём картам.\n"
			"Мы не будем тянуть новые карты, а просто посмотрим глубже на текущий образ.",
			parse_mode=ParseMode.HTML,
			reply_markup=get_cancel_keyboard(),
		)


@router.message(SpreadStates.waiting_for_followup)
async def handle_followup_question(message: Message, state: FSMContext) -> None:
	if not message.text:
		await message.answer(
			"Напиши уточняющий вопрос текстом в одном сообщении.",
			reply_markup=get_cancel_keyboard(),
		)
		return

	followup_question = message.text.strip()
	if followup_question == BTN_CANCEL:
		await handle_cancel(message, state)
		return

	if len(followup_question) < 3:
		await message.answer(
			"Вопрос слишком короткий. Уточни, пожалуйста, чуть подробнее.",
			reply_markup=get_cancel_keyboard(),
		)
		return

	if len(followup_question) > 400:
		await message.answer(
			"Уточняющий вопрос слишком длинный (максимум 400 символов). "
			"Сформулируй его короче.",
			reply_markup=get_cancel_keyboard(),
		)
		return

	data = await state.get_data()
	reading_id = data.get("reading_id")
	original_question = data.get("original_question")
	cards_summary = data.get("cards_summary")
	previous_reply = data.get("previous_reply")

	await state.clear()

	if not original_question or not cards_summary or not previous_reply:
		await message.answer(
			"Не удалось найти контекст прошлого расклада. Сделай новый расклад на 3 карты.",
			reply_markup=get_main_menu_keyboard(),
		)
		return

	first_step_idx = 0
	has_card_back = PATH_CARD_BACK.exists()
	if has_card_back:
		back_key = str(PATH_CARD_BACK)
		photo_source = UI_FILE_ID_CACHE.get(back_key) or FSInputFile(PATH_CARD_BACK)
		wait_msg = await message.answer_photo(
			photo=photo_source,
			caption=FOLLOWUP_RITUAL_STEPS[first_step_idx],
			parse_mode=ParseMode.HTML,
		)
		if wait_msg.photo and back_key not in UI_FILE_ID_CACHE:
			UI_FILE_ID_CACHE[back_key] = wait_msg.photo[-1].file_id
	else:
		wait_msg = await message.answer(
			FOLLOWUP_RITUAL_STEPS[first_step_idx],
			parse_mode=ParseMode.HTML,
		)

	ritual_task = asyncio.create_task(
		_animate_wait_message(wait_msg, FOLLOWUP_RITUAL_STEPS, is_photo=has_card_back)
	)

	try:
		followup_reply = await ai_service.answer_followup(
			original_question=original_question,
			cards_summary=cards_summary,
			previous_reply=previous_reply,
			followup_question=followup_question,
		)
	finally:
		ritual_task.cancel()
		with suppress(asyncio.CancelledError):
			await ritual_task
		with suppress(TelegramBadRequest):
			await wait_msg.delete()

	if not followup_reply:
		followup_reply = (
			"Сейчас сложно уловить тонкий отклик. Попробуй вернуться к уже выпавшим "
			"картам чуть позже и посмотреть, какая из них вызывает самый сильный отклик."
		)

	if reading_id and message.from_user:
		await db_repo.save_followup(
			reading_id=reading_id,
			followup_question=followup_question,
			followup_answer=followup_reply,
		)

	clean_reply = _sanitize_telegram_html(followup_reply)
	await message.answer(
		f"✨ <b>Уточнение по раскладу:</b>\n\n{clean_reply}",
		parse_mode=ParseMode.HTML,
		reply_markup=get_main_menu_keyboard(),
	)




@router.callback_query(F.data.startswith("reason:"))
async def callback_rate_reason(callback: CallbackQuery) -> None:
	if not callback.from_user or not callback.message or not callback.data:
		await callback.answer()
		return

	parts = callback.data.split(":")
	if len(parts) != 3 or not parts[1].isdigit():
		await callback.answer()
		return

	reading_id = int(parts[1])
	reason_code = parts[2]

	await db_repo.save_reading_feedback(
		reading_id=reading_id,
		telegram_id=callback.from_user.id,
		score=-1,
		reason=reason_code,
	)
	await callback.answer("Записал, это поможет сделать бота лучше!")
	await callback.message.edit_reply_markup(reply_markup=None)


@router.callback_query(F.data == "finish_spread")
async def callback_finish_spread(callback: CallbackQuery, state: FSMContext) -> None:
	await callback.answer()
	await state.clear()
	if callback.message:
		await callback.message.answer(
			"Спасибо за эту тихую паузу. Возвращаю главное меню.",
			reply_markup=get_main_menu_keyboard(),
		)


@router.message()
async def handle_fallback(message: Message) -> None:
	await message.answer(
		"Выбери практику на клавиатуре ниже или отправь /start, чтобы открыть меню.",
		reply_markup=get_main_menu_keyboard(),
	)



