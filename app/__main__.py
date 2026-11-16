import asyncio
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from app.config import load_settings
from app.handlers import db_repo, router

logger = logging.getLogger(__name__)


def setup_logging() -> None:
	# Настраиваем вывод логов и в консоль, и в ротируемый файл logs/bot.log для VPS
	logs_dir = Path(__file__).resolve().parent.parent / "logs"
	logs_dir.mkdir(parents=True, exist_ok=True)
	log_file = logs_dir / "bot.log"

	formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")

	file_handler = RotatingFileHandler(
		filename=log_file,
		maxBytes=5 * 1024 * 1024,
		backupCount=3,
		encoding="utf-8",
	)
	file_handler.setFormatter(formatter)

	console_handler = logging.StreamHandler()
	console_handler.setFormatter(formatter)

	root_logger = logging.getLogger()
	root_logger.setLevel(logging.INFO)
	root_logger.handlers.clear()
	root_logger.addHandler(file_handler)
	root_logger.addHandler(console_handler)


async def main() -> None:
	setup_logging()
	settings = load_settings()

	await db_repo.init_tables()
	db_dialect = settings.database_url.split("://")[0]
	logger.info("База данных инициализирована (%s).", db_dialect)

	dispatcher = Dispatcher(storage=MemoryStorage())
	dispatcher.include_router(router)

	try:
		async with Bot(
			token=settings.bot_token,
			default=DefaultBotProperties(parse_mode=ParseMode.HTML),
		) as bot:
			await bot.delete_webhook(drop_pending_updates=False)

			await bot.set_my_commands(
				[
					BotCommand(command="start", description="Главное меню"),
					BotCommand(command="day", description="Карта дня"),
					BotCommand(command="spread", description="Расклад на 3 карты"),
					BotCommand(command="history", description="Мои расклады"),
					BotCommand(command="help", description="О пространстве"),
				]
			)

			logger.info("Бот «Между звёзд» (v1 релиз-кандидат) запущен.")

			await dispatcher.start_polling(
				bot,
				allowed_updates=dispatcher.resolve_used_update_types(),
				close_bot_session=False,
			)
	finally:
		await db_repo.close()
		logger.info("Бот «Между звёзд» остановлен, соединение с БД закрыто.")


if __name__ == "__main__":
	asyncio.run(main())
