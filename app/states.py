from aiogram.fsm.state import State, StatesGroup


class SpreadStates(StatesGroup):
	# Ожидание первичного вопроса для расклада на 3 карты
	waiting_for_question = State()
	# Ожидание одного уточняющего вопроса после получения расклада
	waiting_for_followup = State()
