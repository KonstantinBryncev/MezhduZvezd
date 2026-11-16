import json
import random
from dataclasses import dataclass
from pathlib import Path

# Путь к справочнику карт внутри пакета app
CARDS_FILE_PATH = Path(__file__).resolve().parent / "data" / "cards.json"


@dataclass(frozen=True)
class TarotCard:
	# Модель одной карты Таро для саморефлексии
	id: str
	name: str
	arcana: str
	image_cue: str
	day_text: str
	situation_hint: str
	notice_hint: str
	next_step_hint: str
	reflection_question: str


class CardsRepository:
	# Хранилище карт с методами случайного выбора без повторов
	def __init__(self, file_path: Path = CARDS_FILE_PATH) -> None:
		if not file_path.exists():
			raise FileNotFoundError(f"Не найден файл с картами: {file_path}")

		raw_data = json.loads(file_path.read_text(encoding="utf-8"))
		self._cards: list[TarotCard] = [
			TarotCard(**item) for item in raw_data
		]

		if len(self._cards) < 3:
			raise ValueError("В справочнике должно быть минимум 3 карты.")

	def get_random_card(self) -> TarotCard:
		# Возвращает одну случайную карту для практики дня
		return random.choice(self._cards)

	def draw_three_cards(self) -> list[TarotCard]:
		# Возвращает 3 уникальные карты для расклада
		return random.sample(self._cards, k=3)
