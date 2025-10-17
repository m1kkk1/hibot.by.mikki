import asyncio
import logging
import aiosqlite
from aiogram.filters import Command
from aiogram import Bot, Dispatcher, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from data.connection import close_connection
from data import config
from data.connection import get_connection

from data.creat_db import init_db
from handlers import admin
from keyboards.reply import to_main_kb

from aiogram.enums.chat_member_status import ChatMemberStatus
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from aiogram.filters import ChatMemberUpdatedFilter, KICKED, LEFT, MEMBER

logging.basicConfig(level=logging.INFO)

bot = Bot(token=config.TOKEN, default_bot_properties=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
dp.include_routers(admin.admin_router)



@dp.message(Command("start"))
async def start_command(message: types.Message):
    user_id = message.from_user.id
    conn = await get_connection()
    conn.row_factory = aiosqlite.Row

    try:
        # --- ПРОВЕРКА АДМИНА БЕЗ ДОБАВЛЕНИЯ В БД ---
        # Просто ищем пользователя в таблице users
        async with conn.execute("SELECT is_admin FROM users WHERE user_id = ?", (user_id,)) as cursor:
            user_data = await cursor.fetchone()

        # Если запись найдена и is_admin = 1, это админ
        if user_data and user_data["is_admin"]:
            await message.answer(
                "Добро пожаловать в админ-панель!",
                reply_markup=to_main_kb()
            )
        else:
            # Во всех остальных случаях — это обычный пользователь
            async with conn.execute("SELECT start_message FROM settings LIMIT 1") as cursor:
                settings = await cursor.fetchone()

            start_message = settings["start_message"] if settings else "Добро пожаловать в бота!"
            await message.answer(start_message)

    except Exception as e:
        logging.error(f"Error in start_command: {e}")
        await message.answer("Произошла ошибка, попробуйте позже.")
    finally:
        await conn.close()

@dp.chat_member(ChatMemberUpdatedFilter(member_status_changed=(KICKED | LEFT) >> MEMBER))
async def on_user_join_after_approval(event: types.ChatMemberUpdated, bot: Bot):
    # Убедимся, что пользователь именно ВСТУПИЛ, а не был, например, повышен в правах
    if event.old_chat_member.status not in (ChatMemberStatus.LEFT, ChatMemberStatus.KICKED):
        return

    # 1. Получаем настройки из БД
    conn = await get_connection()
    conn.row_factory = aiosqlite.Row
    async with conn.execute(
            "SELECT channel_id, welcome_message_text, welcome_message_photo_id FROM settings LIMIT 1") as cursor:
        settings = await cursor.fetchone()
    await conn.close()

    # 2. Проверяем, что событие из нашего канала
    if not settings or event.chat.id != settings["channel_id"]:
        return

    user_id = event.new_chat_member.user.id
    user_name = event.new_chat_member.user.full_name

    try:
        # 3. Готовим приветствие
        welcome_text = (settings["welcome_message_text"] or "").replace("{user}", user_name)

        # Пытаемся отправить приветствие в ЛС
        if settings["welcome_message_photo_id"]:
            await bot.send_photo(chat_id=user_id, photo=settings["welcome_message_photo_id"], caption=welcome_text)
        elif welcome_text:
            await bot.send_message(chat_id=user_id, text=welcome_text)

    except Exception as e:
        logging.error(f"Не удалось отправить ЛС пользователю {user_id}. Ошибка: {e}")


@dp.chat_join_request()
async def auto_approve_join_request(request: types.ChatJoinRequest, bot: Bot):
    conn = await get_connection()
    conn.row_factory = aiosqlite.Row
    async with conn.execute("SELECT auto_approve_enabled, channel_id FROM settings LIMIT 1") as cursor:
        settings = await cursor.fetchone()
    await conn.close()

    # 1. Check if the feature is enabled in the database
    if not (settings and settings['auto_approve_enabled']):
        return # Exit if auto-approval is turned off

    # 2. Verify the request is for the correct channel
    if request.chat.id != settings["channel_id"]:
        return # Exit if it's a different channel

    try:
        # 3. Approve the user's request to join
        await bot.approve_chat_join_request(request.chat.id, request.from_user.id)
        logging.info(f"Successfully auto-approved user {request.from_user.id} for channel {request.chat.id}")
    except Exception as e:
        logging.error(f"Failed to auto-approve user {request.from_user.id}: {e}")

# Ханда для ручного приема юзеров
@dp.chat_member(ChatMemberUpdatedFilter(...))
async def on_user_join_after_approval(event: types.ChatMemberUpdated, bot: Bot, settings=None):
    conn = await get_connection()

    # --- КЛЮЧЕВАЯ ПРОВЕРКА ---
    if settings and settings['auto_approve_enabled']:
        return  # Если автоприем включен, выходим, чтобы не дублировать сообщения


@dp.chat_member(ChatMemberUpdatedFilter(member_status_changed=MEMBER >> (KICKED | LEFT)))
async def on_user_leave(event: types.ChatMemberUpdated, bot: Bot):
    conn = await get_connection()
    conn.row_factory = aiosqlite.Row
    async with conn.execute("SELECT * FROM settings LIMIT 1") as cursor:
        settings = await cursor.fetchone()
    await conn.close()

    # 1. Проверяем, что событие из нашего канала и сообщение настроено
    if not settings or event.chat.id != settings["channel_id"]:
        return

    # Если прощального сообщения нет, ничего не делаем
    if not settings["goodbye_message_text"] and not settings["goodbye_message_photo_id"]:
        return

    user_id = event.old_chat_member.user.id
    user_name = event.old_chat_member.user.full_name

    goodbye_text = (settings["goodbye_message_text"] or "").replace("{user}", user_name)
    photo_id = settings["goodbye_message_photo_id"]

    try:
        # 2. Пытаемся отправить сообщение в ЛС
        if photo_id:
            await bot.send_photo(chat_id=user_id, photo=photo_id, caption=goodbye_text)
        elif goodbye_text:
            await bot.send_message(chat_id=user_id, text=goodbye_text)

        logging.info(f"Успешно отправлено прощальное сообщение пользователю {user_id}")

    except Exception as e:
        # Ошибка возникнет, если пользователь никогда не запускал бота
        logging.error(f"Не удалось отправить прощальное сообщение пользователю {user_id}. Ошибка: {e}")


async def main():
    await init_db()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())