import html
from datetime import timedelta, timezone

from aiogram import F, Router
from aiogram.enums import ChatAction, ChatType, ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

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
from app.states import SpreadStates

router = Router(name="private_messages")
router.message.filter(F.chat.type == ChatType.PRIVATE)

MSK_TZ = timezone(timedelta(hours=3))

settings = load_settings()
cards_repo = CardsRepository()
ai_service = OpenRouterService(
	api_key=settings.openrouter_api_key,
	model=settings.openrouter_model,
)
db_repo = DatabaseRepository(
	database_url=settings.database_url,
	default_daily_limit=settings.daily_free_limit,
)


def find_card_by_id(card_id: str) -> TarotCard:
	# Безопасно ищем карту по её ID в загруженной колоде
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


@router.message(CommandStart())
async def handle_start(message: Message, state: FSMContext) -> None:
	await state.clear()
	if message.from_user:
		await db_repo.get_or_create_user(
			telegram_id=message.from_user.id,
			username=message.from_user.username,
			first_name=message.from_user.first_name,
		)

	await message.answer(
		"Привет! Это <b>«Между звёзд»</b> — пространство для спокойной "
		"саморефлексии через образы карт Таро.\n\n"
		"Здесь нет предсказаний будущего и «правильных» толкований. "
		"Карта — это зеркало, которое помогает прислушаться к себе.\n\n"
		"Выбери практику в меню ниже. Остановиться можно в любой момент.",
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

	full_body = header + reading.ai_interpretation
	for start in range(0, len(full_body), 4000):
		await callback.message.answer(
			full_body[start : start + 4000],
			parse_mode=ParseMode.HTML,
		)

	if reading.followup_question and reading.followup_answer:
		followup_block = (
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
	candidate = cards_repo.get_random_card()

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

	await message.answer(
		format_day_card(card, already_drawn=already_drawn),
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


@router.message(SpreadStates.waiting_for_question, F.text)
async def handle_spread_question(message: Message, state: FSMContext) -> None:
	user_question = message.text.strip()
	if len(user_question) < 3:
		await message.answer(
			"Напиши чуть подробнее (хотя бы пару слов), "
			"чтобы картам было на что опереться."
		)
		return

	if message.from_user:
		allowed, deny_text = await check_spread_access(message.from_user.id)
		if not allowed:
			await state.clear()
			await message.answer(
				deny_text,
				parse_mode=ParseMode.HTML,
				reply_markup=get_main_menu_keyboard(),
			)
			return

	safe_question = user_question[:400]
	drawn_cards = cards_repo.draw_three_cards()
	c1, c2, c3 = drawn_cards

	await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
	wait_msg = await message.answer(
		f"🌌 <b>Выпавшие карты:</b>\n"
		f"1. Ситуация сейчас — <b>{c1.name}</b>\n"
		f"2. На что обратить внимание — <b>{c2.name}</b>\n"
		f"3. Возможный следующий шаг — <b>{c3.name}</b>\n\n"
		f"<i>Собираю спокойный отклик под твой запрос...</i>",
		parse_mode=ParseMode.HTML,
	)

	ai_reply = await ai_service.synthesize_spread(safe_question, drawn_cards)
	final_text = ai_reply if ai_reply else format_fallback_spread(safe_question, drawn_cards)

	reading_id: int | None = None
	if message.from_user:
		saved_reading = await db_repo.create_reading(
			telegram_id=message.from_user.id,
			username=message.from_user.username,
			first_name=message.from_user.first_name,
			question=safe_question,
			card_names=[c1.name, c2.name, c3.name],
			ai_interpretation=final_text,
		)
		reading_id = saved_reading.id

	cards_summary = (
		f"1. Ситуация: {c1.name} ({c1.situation_hint})\n"
		f"2. Внимание: {c2.name} ({c2.notice_hint})\n"
		f"3. Шаг: {c3.name} ({c3.next_step_hint})"
	)

	await state.update_data(
		reading_id=reading_id,
		original_question=safe_question,
		cards_summary=cards_summary,
		previous_reply=final_text,
	)
	await state.set_state(None)

	await wait_msg.delete()
	await message.answer(
		f"🌌 <b>Расклад «Между звёзд»</b>\n"
		f"<i>Карты: {c1.name} • {c2.name} • {c3.name}</i>\n\n"
		f"{final_text}",
		parse_mode=ParseMode.HTML,
		reply_markup=get_after_spread_keyboard(reading_id=reading_id, can_followup=True),
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


@router.message(SpreadStates.waiting_for_followup, F.text)
async def handle_followup_question(message: Message, state: FSMContext) -> None:
	followup = message.text.strip()
	if len(followup) < 3:
		await message.answer("Напиши вопрос чуть подробнее.")
		return

	data = await state.get_data()
	reading_id = data.get("reading_id")
	original_question = data.get("original_question", "")
	cards_summary = data.get("cards_summary", "")
	previous_reply = data.get("previous_reply", "")
	safe_followup = followup[:300]

	await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
	wait_msg = await message.answer("<i>Осмысляю уточнение...</i>", parse_mode=ParseMode.HTML)

	ai_followup = await ai_service.answer_followup(
		original_question=original_question,
		cards_summary=cards_summary,
		previous_reply=previous_reply,
		followup_question=safe_followup,
	)

	await wait_msg.delete()
	await state.clear()

	reply_text = ai_followup or (
		"Сейчас связь с языковой моделью временно недоступна, "
		"но ты можешь опереться на три выпавшие карты и вопрос для паузы выше."
	)

	saved_id = reading_id if isinstance(reading_id, int) else None
	if saved_id is not None:
		await db_repo.save_followup(
			reading_id=saved_id,
			followup_question=safe_followup,
			followup_answer=reply_text,
		)

	await message.answer(
		f"💬 <b>Отклик на уточнение:</b>\n\n"
		f"{reply_text}\n\n"
		f"<i>На этом разбор завершён. Буду рад твоей оценке ниже:</i>",
		parse_mode=ParseMode.HTML,
		reply_markup=get_after_spread_keyboard(reading_id=saved_id, can_followup=False),
	)


@router.callback_query(F.data.startswith("rate:"))
async def callback_rate_reading(callback: CallbackQuery) -> None:
	if not callback.from_user or not callback.message or not callback.data:
		await callback.answer()
		return

	parts = callback.data.split(":")
	if len(parts) != 3 or not parts[1].isdigit():
		await callback.answer()
		return

	reading_id = int(parts[1])
	vote = parts[2]

	if vote == "up":
		await db_repo.save_reading_feedback(
			reading_id=reading_id,
			telegram_id=callback.from_user.id,
			score=1,
		)
		await callback.answer("Спасибо за отклик! Рад, что разбор оказался полезным.")
		await callback.message.edit_reply_markup(reply_markup=None)
	else:
		await db_repo.save_reading_feedback(
			reading_id=reading_id,
			telegram_id=callback.from_user.id,
			score=-1,
		)
		await callback.answer("Спасибо за честность!")
		await callback.message.edit_reply_markup(
			reply_markup=get_dislike_reason_keyboard(reading_id)
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
