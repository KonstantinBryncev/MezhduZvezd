from datetime import datetime, time, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.models import Base, DailyCardLog, Reading, User

MSK_TZ = timezone(timedelta(hours=3))


class DatabaseRepository:
	def __init__(self, database_url: str, default_daily_limit: int) -> None:
		self.engine = create_async_engine(database_url, echo=False)
		self.session_factory = async_sessionmaker(
			bind=self.engine,
			class_=AsyncSession,
			expire_on_commit=False,
		)
		self.default_daily_limit = default_daily_limit

	async def init_tables(self) -> None:
		async with self.engine.begin() as conn:
			await conn.run_sync(Base.metadata.create_all)

	async def close(self) -> None:
		await self.engine.dispose()

	async def get_or_create_user(
		self,
		telegram_id: int,
		username: str | None = None,
		first_name: str | None = None,
	) -> User:
		async with self.session_factory() as session:
			stmt = select(User).where(User.telegram_id == telegram_id)
			result = await session.execute(stmt)
			user = result.scalar_one_or_none()

			if user is None:
				user = User(
					telegram_id=telegram_id,
					username=username,
					first_name=first_name,
				)
				session.add(user)
				await session.commit()
				await session.refresh(user)
				return user

			changed = False
			if username != user.username:
				user.username = username
				changed = True
			if first_name != user.first_name:
				user.first_name = first_name
				changed = True

			if changed:
				await session.commit()
				await session.refresh(user)

			return user

	async def get_or_set_daily_card_id(
		self,
		telegram_id: int,
		username: str | None,
		first_name: str | None,
		candidate_card_id: str,
	) -> tuple[str, bool]:
		# Возвращает (card_id, was_already_drawn_today) для текущей даты по МСК
		user = await self.get_or_create_user(
			telegram_id=telegram_id,
			username=username,
			first_name=first_name,
		)
		today_msk = datetime.now(MSK_TZ).date().isoformat()

		async with self.session_factory() as session:
			stmt = (
				select(DailyCardLog)
				.where(DailyCardLog.user_id == user.id)
				.where(DailyCardLog.msk_date == today_msk)
			)
			result = await session.execute(stmt)
			existing = result.scalar_one_or_none()

			if existing is not None:
				return existing.card_id, True

			entry = DailyCardLog(
				user_id=user.id,
				msk_date=today_msk,
				card_id=candidate_card_id,
			)
			session.add(entry)
			await session.commit()
			return candidate_card_id, False

	async def get_daily_usage(self, telegram_id: int) -> tuple[int, int, bool]:
		user = await self.get_or_create_user(telegram_id=telegram_id)
		effective_limit = (
			user.custom_daily_limit
			if user.custom_daily_limit is not None
			else self.default_daily_limit
		)

		now_msk = datetime.now(MSK_TZ)
		start_of_day_msk = datetime.combine(now_msk.date(), time.min, tzinfo=MSK_TZ)
		start_of_day_utc = start_of_day_msk.astimezone(timezone.utc)

		async with self.session_factory() as session:
			stmt = (
				select(func.count(Reading.id))
				.where(Reading.user_id == user.id)
				.where(Reading.created_at >= start_of_day_utc)
			)
			result = await session.execute(stmt)
			used_today = int(result.scalar() or 0)

		return used_today, effective_limit, user.is_premium

	async def create_reading(
		self,
		telegram_id: int,
		username: str | None,
		first_name: str | None,
		question: str,
		card_names: list[str],
		ai_interpretation: str,
	) -> Reading:
		user = await self.get_or_create_user(
			telegram_id=telegram_id,
			username=username,
			first_name=first_name,
		)
		async with self.session_factory() as session:
			reading = Reading(
				user_id=user.id,
				question=question,
				card_1_name=card_names[0],
				card_2_name=card_names[1],
				card_3_name=card_names[2],
				ai_interpretation=ai_interpretation,
			)
			session.add(reading)
			await session.commit()
			await session.refresh(reading)
			return reading

	async def save_followup(
		self,
		reading_id: int,
		followup_question: str,
		followup_answer: str,
	) -> None:
		async with self.session_factory() as session:
			stmt = select(Reading).where(Reading.id == reading_id)
			result = await session.execute(stmt)
			reading = result.scalar_one_or_none()
			if reading is not None:
				reading.followup_question = followup_question
				reading.followup_answer = followup_answer
				await session.commit()

	async def save_reading_feedback(
		self,
		reading_id: int,
		telegram_id: int,
		score: int,
		reason: str | None = None,
	) -> bool:
		# Сохраняем оценку расклада (1 или -1) и опциональную причину
		user = await self.get_or_create_user(telegram_id=telegram_id)
		async with self.session_factory() as session:
			stmt = (
				select(Reading)
				.where(Reading.id == reading_id)
				.where(Reading.user_id == user.id)
			)
			result = await session.execute(stmt)
			reading = result.scalar_one_or_none()
			if reading is None:
				return False
			reading.feedback_score = score
			if reason is not None:
				reading.feedback_reason = reason
			await session.commit()
			return True

	async def get_recent_readings(self, telegram_id: int, limit: int = 5) -> list[Reading]:
		user = await self.get_or_create_user(telegram_id=telegram_id)
		async with self.session_factory() as session:
			stmt = (
				select(Reading)
				.where(Reading.user_id == user.id)
				.order_by(Reading.created_at.desc())
				.limit(limit)
			)
			result = await session.execute(stmt)
			return list(result.scalars().all())

	async def get_reading_by_id(self, reading_id: int, telegram_id: int) -> Reading | None:
		user = await self.get_or_create_user(telegram_id=telegram_id)
		async with self.session_factory() as session:
			stmt = (
				select(Reading)
				.where(Reading.id == reading_id)
				.where(Reading.user_id == user.id)
			)
			result = await session.execute(stmt)
			return result.scalar_one_or_none()

	async def delete_user_data(self, telegram_id: int) -> bool:
		# Полное удаление пользователя и всех его записей из базы
		async with self.session_factory() as session:
			stmt = select(User).where(User.telegram_id == telegram_id)
			result = await session.execute(stmt)
			user = result.scalar_one_or_none()
			if user is None:
				return False
			await session.execute(delete(DailyCardLog).where(DailyCardLog.user_id == user.id))
			await session.execute(delete(Reading).where(Reading.user_id == user.id))
			await session.delete(user)
			await session.commit()
			return True
