from aiogram.types import (
	InlineKeyboardButton,
	InlineKeyboardMarkup,
	KeyboardButton,
	ReplyKeyboardMarkup,
)

BTN_CARD_OF_DAY = "✨ Карта дня"
BTN_THREE_CARDS = "🌌 Расклад на 3 карты"
BTN_HISTORY = "📜 Мои расклады"
BTN_ABOUT = "📖 О пространстве"
BTN_CANCEL = "Отменить"


def get_main_menu_keyboard() -> ReplyKeyboardMarkup:
	return ReplyKeyboardMarkup(
		keyboard=[
			[
				KeyboardButton(text=BTN_CARD_OF_DAY),
				KeyboardButton(text=BTN_THREE_CARDS),
			],
			[
				KeyboardButton(text=BTN_HISTORY),
				KeyboardButton(text=BTN_ABOUT),
			],
		],
		resize_keyboard=True,
		input_field_placeholder="Выберите практику...",
	)


def get_cancel_keyboard() -> ReplyKeyboardMarkup:
	return ReplyKeyboardMarkup(
		keyboard=[[KeyboardButton(text=BTN_CANCEL)]],
		resize_keyboard=True,
		input_field_placeholder="Напишите ваш текст...",
	)


def get_after_day_card_keyboard() -> InlineKeyboardMarkup:
	return InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(
					text="🌌 Сделать расклад на 3 карты",
					callback_data="start_three_cards",
				)
			],
		]
	)


def get_after_spread_keyboard(reading_id: int | None = None, can_followup: bool = True) -> InlineKeyboardMarkup:
	rows: list[list[InlineKeyboardButton]] = []
	if can_followup:
		rows.append(
			[
				InlineKeyboardButton(
					text="💬 Задать 1 уточняющий вопрос",
					callback_data="ask_followup",
				)
			]
		)
	if reading_id is not None:
		rows.append(
			[
				InlineKeyboardButton(
					text="👍 Полезно",
					callback_data=f"rate:{reading_id}:up",
				),
				InlineKeyboardButton(
					text="👎 Не очень",
					callback_data=f"rate:{reading_id}:down",
				),
			]
		)
	rows.append(
		[
			InlineKeyboardButton(
				text="✨ Завершить практику",
				callback_data="finish_spread",
			)
		]
	)
	return InlineKeyboardMarkup(inline_keyboard=rows)


def get_dislike_reason_keyboard(reading_id: int) -> InlineKeyboardMarkup:
	return InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="Слишком общо", callback_data=f"reason:{reading_id}:general"),
				InlineKeyboardButton(text="Не по вопросу", callback_data=f"reason:{reading_id}:offtopic"),
			],
			[
				InlineKeyboardButton(text="Не понравился тон", callback_data=f"reason:{reading_id}:tone"),
			],
		]
	)


def get_history_keyboard(items: list[tuple[int, str]]) -> InlineKeyboardMarkup:
	rows = [
		[
			InlineKeyboardButton(
				text=label,
				callback_data=f"view_reading:{reading_id}",
			)
		]
		for reading_id, label in items
	]
	return InlineKeyboardMarkup(inline_keyboard=rows)


def get_about_keyboard() -> InlineKeyboardMarkup:
	return InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(
					text="🗑 Удалить мои данные",
					callback_data="confirm_delete_data",
				)
			]
		]
	)


def get_confirm_delete_keyboard() -> InlineKeyboardMarkup:
	return InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(
					text="Да, удалить всё навсегда",
					callback_data="execute_delete_data",
				)
			],
			[
				InlineKeyboardButton(
					text="Отмена",
					callback_data="cancel_delete_data",
				)
			],
		]
	)
