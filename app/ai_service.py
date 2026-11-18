import asyncio
import logging

import httpx

from app.cards_service import TarotCard
from app.config import LLMProviderConfig

logger = logging.getLogger(__name__)

# Дополнительные бесплатные модели OpenRouter на случай, если основная модель OpenRouter недоступна
OPENROUTER_EXTRA_FREE_MODELS = [
	"google/gemma-4-31b-it:free",
	"google/gemma-4-26b-a4b-it:free",
	"dots-studio/dots-3-note-preview:free",
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
	def __init__(
		self,
		api_key: str = "",
		model: str = "",
		providers: list[LLMProviderConfig] | None = None,
	) -> None:
		# Собираем итоговую очередь маршрутов (провайдер + модель)
		self.routes: list[LLMProviderConfig] = list(providers) if providers else []

		# Обратная совместимость, если сервис вызвали по-старому (только api_key и model)
		if not self.routes and api_key and model:
			self.routes.append(
				LLMProviderConfig(
					name="OpenRouter",
					base_url="https://openrouter.ai",
					api_key=api_key,
					model=model,
				)
			)

		# Если среди маршрутов есть OpenRouter — добавим его бесплатные модели в резерв
		or_route = next((r for r in self.routes if "openrouter.ai" in r.base_url), None)
		if or_route is not None:
			existing_models = {r.model for r in self.routes if r.base_url == or_route.base_url}
			for extra_model in OPENROUTER_EXTRA_FREE_MODELS:
				if extra_model not in existing_models:
					self.routes.append(
						LLMProviderConfig(
							name="OpenRouter-Fallback",
							base_url=or_route.base_url,
							api_key=or_route.api_key,
							model=extra_model,
						)
					)

	async def _send_chat(self, messages: list[dict[str, str]]) -> str | None:
		if not self.routes:
			logger.warning("Не задан ни один API-провайдер LLM, используется локальный шаблон.")
			return None

		async with httpx.AsyncClient(timeout=35.0) as client:
			for idx, route in enumerate(self.routes):
				endpoint = f"{route.base_url.rstrip('/')}/chat/completions"
				headers = {
					"Authorization": f"Bearer {route.api_key}",
					"Content-Type": "application/json",
				}
				if "openrouter.ai" in route.base_url:
					headers["HTTP-Referer"] = "https://t.me"
					headers["X-Title"] = "Mezhdu Zvezd Tarot Reflection"

				payload: dict = {
					"model": route.model,
					"messages": messages,
					"temperature": 0.7,
					"max_tokens": 3000,
				}
				# Для reasoning-моделей AionLabs снижаем глубину размышлений, чтобы ответ шёл сразу в content
				if "aionlabs.ai" in route.base_url:
					payload["reasoning_effort"] = "low"


				try:
					response = await client.post(endpoint, headers=headers, json=payload)

					if response.status_code in (400, 401, 402, 403, 404, 429, 500, 502, 503, 504):
						logger.warning(
							"[%s | %s] вернул код %s (%s) — переключаюсь на следующий API...",
							route.name,
							route.model,
							response.status_code,
							response.text[:160],
						)
						if idx < len(self.routes) - 1:
							await asyncio.sleep(0.8)
						continue

					response.raise_for_status()
					data = response.json()
					choices = data.get("choices")
					if choices:
						text = (choices[0]["message"].get("content") or "").strip()

						# Защита от технических заглушек вроде "...response..." и обрезанных ответов
						if not text or text == "...response..." or len(text) < 50:
							logger.warning(
								"[%s | %s] вернул некорректный ответ (%r) — переключаюсь на следующий API...",
								route.name,
								route.model,
								text,
							)
							continue

						used_model = (data.get("model") or route.model).replace(":free", "")
						clean_model = used_model.removeprefix("@cf/")

						signed_text = f"{text}\n\n—\n✨ <i>Модель: {clean_model} ({route.name})</i>"
						return signed_text

				except Exception as exc:
					logger.error(
						"Сбой соединения с [%s | %s]: %s — переключаюсь дальше...",
						route.name,
						route.model,
						exc,
					)

		logger.error("Все подключённые API-провайдеры оказались недоступны.")
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
