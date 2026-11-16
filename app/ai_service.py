import asyncio
import logging

import httpx

from app.cards_service import TarotCard

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

FALLBACK_FREE_MODELS = [
	"google/gemma-4-31b-it:free",				# Основная: глубокие и связные трактовки
	"google/gemma-4-26b-a4b-it:free",			# Быстрая и качественная замена
	"baidu/ernie-5.5-flash-preview:free",		# Очень быстрая, большой контекст
	"dots-studio/dots-3-note-preview:free",		# Хорошо связывает карты в раскладе
	"thinkingmachines/inkling-2-small:free",	# Модель с логическим рассуждением
	"nvidia/nemotron-3.5-lightning:free",		# Высокая скорость для коротких ответов\
]

SYSTEM_PROMPT = """Ты — бережный проводник в пространстве саморефлексии «Между звёзд». Ты помогаешь человеку осмыслить его запрос через образы карт Таро.

Строгие правила:
1. Никаких предсказаний будущего, фатализма, мистики и утверждений «карты говорят, что случится X».
2. Используй карты только как психологические метафоры и зеркало для размышлений.
3. Не давай медицинских, юридических, финансовых диагнозов или директивных советов («ты должен»). Если вопрос касается отмены лекарств, лечения, диагнозов, юридических рисков или кризисных состояний — мягко откажись делать расклад по этой теме и предложи обратиться к профильному специалисту или близким.
4. Если запрос пользователя выглядит как случайный набор букв, технический копипаст или нераспознанный текст — не отказывай резко: в самом начале мягко отметь, что вопрос не удалось однозначно распознать, дай спокойный разбор выпавших карт как общий фокус на текущее состояние, а в конце предложи переформулировать запрос.
5. Опирайся строго на выпавшие карты и их образы, связывая их с вопросом пользователя.
6. Пиши спокойным, тёплым, ясным русским языком без эзотерического пафоса. Объём ответа — 180–260 слов, с абзацами для удобного чтения в Telegram. Используй только обычный текст и лёгкие HTML-теги <b> и <i> (без Markdown-символов ** и #)."""




class OpenRouterService:
	def __init__(self, api_key: str, model: str) -> None:
		self.api_key = api_key
		self.model = model

	def _get_models_chain(self) -> list[str]:
		chain: list[str] = []
		for item in [self.model, *FALLBACK_FREE_MODELS]:
			cleaned = item.strip()
			if cleaned and cleaned not in chain:
				chain.append(cleaned)
		return chain

	async def _send_chat(self, messages: list[dict[str, str]]) -> str | None:
		if not self.api_key:
			logger.warning("OPENROUTER_API_KEY не задан, используется локальный шаблон.")
			return None

		headers = {
			"Authorization": f"Bearer {self.api_key}",
			"Content-Type": "application/json",
			"HTTP-Referer": "https://t.me",
			"X-Title": "Mezhdu Zvezd Tarot Reflection",
		}

		models_chain = self._get_models_chain()

		async with httpx.AsyncClient(timeout=35.0) as client:
			for idx, model_name in enumerate(models_chain):
				payload = {
					"model": model_name,
					"messages": messages,
					"temperature": 0.7,
					"max_tokens": 2500,
					"reasoning": {"effort": "none"},
				}
				try:
					response = await client.post(OPENROUTER_URL, headers=headers, json=payload)

					if response.status_code in (404, 429, 502, 503, 504):
						logger.warning(
							"Модель %s вернула %s (%s) — переключаюсь на следующую...",
							model_name,
							response.status_code,
							response.text[:160],
						)
						if idx < len(models_chain) - 1:
							await asyncio.sleep(1.5)
						continue

					response.raise_for_status()
					data = response.json()
					choices = data.get("choices")
					if choices:
						text = choices[0]["message"]["content"].strip()
						# Достаём реальное имя модели, которая сгенерировала ответ
						used_model = data.get("model") or model_name
						clean_model = used_model.replace(":free", "")

						# Добавляем аккуратную подпись в конец ответа
						signed_text = f"{text}\n\n—\n✨ <i>Модель: {clean_model}</i>"
						return signed_text

				except Exception as exc:
					logger.error("Ошибка при обращении к модели %s: %s", model_name, exc)

		logger.error("Все модели из цепочки OpenRouter оказались недоступны.")
		return None

	async def synthesize_spread(self, question: str, cards: list[TarotCard]) -> str | None:
		c1, c2, c3 = cards
		user_prompt = f"""Запрос человека: «{question}»

			Выпавшие карты:
			1. Позиция «Ситуация сейчас»: {c1.name} (Образ: {c1.image_cue}; Опора: {c1.situation_hint})
			2. Позиция «На что обратить внимание»: {c2.name} (Образ: {c2.image_cue}; Опора: {c2.notice_hint})
			3. Позиция «Возможный следующий шаг»: {c3.name} (Образ: {c3.image_cue}; Опора: {c3.next_step_hint})

			Собери целостный, спокойный отклик по этим трём позициям в контексте запроса. В конце задай один мягкий открытый вопрос для саморефлексии."""
		messages = [
			{"role": "system", "content": SYSTEM_PROMPT},
			{"role": "user", "content": user_prompt},
		]
		return await self._send_chat(messages)

	async def answer_followup(
		self,
		original_question: str,
		cards_summary: str,
		previous_reply: str,
		followup_question: str,
	) -> str | None:
		messages = [
			{"role": "system", "content": SYSTEM_PROMPT},
			{
				"role": "user",
				"content": f"Мой исходный запрос: «{original_question}».\nВыпавшие карты:\n{cards_summary}",
			},
			{"role": "assistant", "content": previous_reply},
			{
				"role": "user",
				"content": (
					f"У меня есть один уточняющий вопрос по этим же картам: «{followup_question}». "
					"Ответь бережно, опираясь на те же три карты, без новых карт и без предсказаний (120–180 слов)."
				),
			},
		]
		return await self._send_chat(messages)

