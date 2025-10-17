import logging

import aiosqlite
from aiogram import Bot

from keyboards.reply import cancel_kb, main_kb, to_main_kb, back_cancel_kb

from aiogram.filters import StateFilter
from aiogram import Router, F, types
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from data.connection import get_connection



# Состояние для настройки канала
class ChannelSetup(StatesGroup):
    waiting_for_channel_id = State()

# Состояние для редактирования сообщения /start
class StartMessageSetup(StatesGroup):
    waiting_for_text = State()

# Состояние для редактирования приветствия в канале
class ChannelWelcomeSetup(StatesGroup):
    waiting_for_photo_and_text = State()

# Состояние для для добавления админа в БД
class AddAdmin(StatesGroup):
    waiting_for_id = State()

# Состояние для прощального сообщения
class GoodbyeMessageSetup(StatesGroup):
    waiting_for_photo_and_text = State()

# Состояние для создание поста в канал
class PostCreation(StatesGroup):
    waiting_for_content = State()      # Ожидание фото и текста
    waiting_for_button_text = State()  # Ожидание текста для кнопки
    waiting_for_button_url = State()   # Ожидание ссылки для кнопки

admin_router = Router()


@admin_router.message(F.text == "Главное меню")
async def menu(message: types.Message):
    user_id = message.from_user.id
    conn = await get_connection()

    try:
        conn.row_factory = aiosqlite.Row

        # 1. Ищем пользователя в базе данных
        async with conn.execute("SELECT is_admin FROM users WHERE user_id = ?", (user_id,)) as cursor:
            user_data = await cursor.fetchone()

        if user_data and user_data["is_admin"]:
            await message.answer("Главное меню:",
                                 reply_markup=main_kb())
        else:
            await message.answer("⛔️ У вас нет доступа.")

    finally:
        if conn:
            await conn.close()

# --- НАСТРОЙКА КАНАЛА ---

@admin_router.message(F.text == "Настроить канал")
async def setup_channel(message: types.Message, state: FSMContext):
    # ... (весь код для настройки канала остается здесь, как и в прошлом ответе)
    conn = await get_connection()
    async with conn.execute("SELECT channel_id FROM settings LIMIT 1") as cursor:
        result = await cursor.fetchone()
    await conn.close()

    if result and result[0]:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Да", callback_data="change_channel_yes")],
            [InlineKeyboardButton(text="Нет", callback_data="change_channel_no")]
        ])
        await message.answer(f"Бот уже привязан к каналу с ID: `{result[0]}`.\nХотите изменить канал?", reply_markup=kb,
                             parse_mode="Markdown")
    else:
        await state.set_state(ChannelSetup.waiting_for_channel_id)
        await message.answer(
            "Канал еще не привязан. Пожалуйста, отправьте ID вашего канала.\n\nИнструкция: Добавьте @бота в администраторы канала со всеми правами.")


@admin_router.callback_query(F.data == "change_channel_no")
async def cancel_change_channel(callback: types.CallbackQuery):
    await callback.answer("Отлично, оставляем как есть.", show_alert=True)
    await callback.message.delete()


@admin_router.callback_query(F.data == "change_channel_yes")
async def start_change_channel(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите новый ID канала.")
    await state.set_state(ChannelSetup.waiting_for_channel_id)
    await callback.answer()


@admin_router.message(ChannelSetup.waiting_for_channel_id)
async def process_channel_id(message: types.Message, state: FSMContext):
    if not message.text.startswith("-100") or not message.text[1:].isdigit():
        await message.answer("Неверный формат ID. ID канала должен быть числом и начинаться с -100. Попробуйте снова.")
        return
    channel_id = int(message.text)
    conn = await get_connection()
    await conn.execute("UPDATE settings SET channel_id = ? WHERE rowid = 1", (channel_id,))
    await conn.commit()
    await conn.close()
    await message.answer(f"Отлично! Канал с ID `{channel_id}` успешно сохранен.", parse_mode="Markdown")
    await state.clear()


# --- РЕДАКТИРОВАНИЕ СООБЩЕНИЯ ПРИ /START ---

@admin_router.message(F.text == "Сообщение при /start")
async def setup_start_message(message: types.Message, state: FSMContext):
    await message.answer(
        "Отправьте текст, который пользователь увидит при команде /start.",
        reply_markup=cancel_kb()  # <--- ИЗМЕНЕНИЕ: Показываем клавиатуру отмены
    )
    await state.set_state(StartMessageSetup.waiting_for_text)


# НОВЫЙ ХЕНДЛЕР для отмены действия
@admin_router.message(F.text == "Вернуться в главное меню", StartMessageSetup.waiting_for_text)
async def cancel_start_message_setup(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Действие отменено. Вы возвращены в главное меню.",
        reply_markup=main_kb()  # <--- Возвращаем главную клавиатуру
    )


# Хендлер, который получает новый текст
@admin_router.message(StartMessageSetup.waiting_for_text)
async def process_start_message_text(message: types.Message, state: FSMContext):
    start_text = message.text

    # Сохраняем в колонку start_message
    conn = await get_connection()
    await conn.execute("UPDATE settings SET start_message = ? WHERE rowid = 1", (start_text,))
    await conn.commit()
    await conn.close()

    await message.answer(
        "Сообщение для команды /start успешно обновлено!",
        reply_markup=to_main_kb()  # <--- Возвращаем главную клавиатуру после успеха
    )
    await state.clear()

# --- РЕДАКТИРОВАНИЕ ПРИВЕТСТВИЯ В КАНАЛЕ ---

@admin_router.message(F.text == "Редактировать приветствие")
async def setup_channel_welcome(message: types.Message, state: FSMContext, bot: Bot):  # <--- Добавили bot: Bot
    conn = await get_connection()
    conn.row_factory = aiosqlite.Row  # Для доступа к данным по именам колонок

    # 1. Получаем ВСЕ данные о приветствии из БД
    async with conn.execute(
            "SELECT channel_id, welcome_message_text, welcome_message_photo_id FROM settings LIMIT 1") as cursor:
        settings = await cursor.fetchone()
    await conn.close()

    # Проверяем, привязан ли канал (эта логика остается)
    if not (settings and settings["channel_id"]):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Добавить канал", callback_data="redirect_to_add_channel")]
        ])
        await message.answer("Эта функция редактирует приветствие для канала. Сначала нужно привязать канал.",
                             reply_markup=kb)
        return

    # 2. НОВЫЙ БЛОК: Показываем текущее приветствие (если оно есть)
    await message.answer("🔎 Текущее приветствие выглядит так:")

    photo_id = settings["welcome_message_photo_id"]
    welcome_text = settings["welcome_message_text"]

    if photo_id:
        # Если есть фото, отправляем его с подписью
        await bot.send_photo(
            chat_id=message.chat.id,
            photo=photo_id,
            caption=welcome_text or ""  # Если текста нет, подпись будет пустой
        )
    elif welcome_text:
        # Если есть только текст
        await message.answer(welcome_text)
    else:
        # Если ничего не установлено
        await message.answer("Приветствие ещё не создано.")

    # 3. Запрашиваем новое приветствие (эта логика остается)
    await message.answer(
        "Теперь пришлите новое фото и текст для приветствия (одним сообщением).\n"
        "Если хотите оставить только текст, просто пришлите текст.",
        reply_markup=cancel_kb()
    )
    await state.set_state(ChannelWelcomeSetup.waiting_for_photo_and_text)


# НОВЫЙ ХЕНДЛЕР для отмены действия
@admin_router.message(F.text == "Вернуться в главное меню", ChannelWelcomeSetup.waiting_for_photo_and_text)
async def cancel_start_message_setup(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Действие отменено. Вы возвращены в главное меню.",
        reply_markup=main_kb()  # <--- Возвращаем главную клавиатуру
    )


# Хендлер, который ловит контент для приветствия в канале
@admin_router.message(ChannelWelcomeSetup.waiting_for_photo_and_text)
async def process_channel_welcome_content(message: types.Message, state: FSMContext):
    photo_id = message.photo[-1].file_id if message.photo else None
    text = message.caption if message.photo else message.text

    # Сохраняем в колонки welcome_message_...
    conn = await get_connection()
    await conn.execute(
        "UPDATE settings SET welcome_message_text = ?, welcome_message_photo_id = ? WHERE rowid = 1",
        (text, photo_id)
    )
    await conn.commit()
    await conn.close()

    # Вот измененная строка
    await message.answer(
        "Приветствие успешно создано! ✅",
        reply_markup=to_main_kb()
    )
    await state.clear()

# Callback для кнопки "Добавить канал" (перенаправление), если его нет
@admin_router.callback_query(F.data == "redirect_to_add_channel")
async def redirect_to_add_channel_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите ID канала.")
    await state.set_state(ChannelSetup.waiting_for_channel_id)
    await callback.answer()


# --- БЛОК ДОБАВЛЕНИЯ АДМИНИСТРАТОРА ---

# 1. Хендлер, который реагирует на кнопку "Добавить админа"
@admin_router.message(F.text == "Добавить админа")
async def start_add_admin(message: types.Message, state: FSMContext):
    await message.answer(
        "Введите ID пользователя, которого хотите назначить администратором.",
        reply_markup=cancel_kb() # Показываем клавиатуру с кнопкой "Отмена"
    )
    # Устанавливаем состояние ожидания ID
    await state.set_state(AddAdmin.waiting_for_id)


# 2. Хендлер для отмены действия (если админ передумал)
@admin_router.message(F.text == "Вернуться в главное меню", AddAdmin.waiting_for_id)
async def cancel_add_admin(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Действие отменено. Вы возвращены в главное меню.",
        reply_markup=main_kb()
    )


# ПРАВИЛЬНЫЙ КОД ДЛЯ ДОБАВЛЕНИЯ АДМИНА
@admin_router.message(AddAdmin.waiting_for_id)
async def process_admin_id(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("ID должен состоять только из цифр. Попробуйте еще раз.",
                             reply_markup=cancel_kb())
        return

    new_admin_id = int(message.text)
    conn = await get_connection()

    try:
        # Сначала добавляем пользователя в базу, если его там еще нет.
        # Это предотвратит ошибки, если пользователь никогда не запускал бота.
        await conn.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (new_admin_id,))

        # Теперь устанавливаем ему флаг администратора
        await conn.execute(
            "UPDATE users SET is_admin = 1 WHERE user_id = ?",
            (new_admin_id,)
        )
        await conn.commit()

        await message.answer(
            f"✅ Пользователь с ID `{new_admin_id}` успешно назначен администратором.",
            parse_mode="Markdown",
            reply_markup=to_main_kb()
        )

    except Exception as e:
        logging.error(f"Error while adding admin: {e}")
        await message.answer("Произошла ошибка при добавлении администратора.")
    finally:
        await conn.close()
        await state.clear()


# Хендлер для кнопки "Автоприем заявок"
@admin_router.message(F.text.startswith("Авто прием Вкл.\Выкл."))  # Ловит оба состояния кнопки
async def toggle_auto_approve(message: types.Message):
    user_id = message.from_user.id
    conn = await get_connection()
    conn.row_factory = aiosqlite.Row

    try:
        # 1. Проверяем, что пишет администратор
        async with conn.execute("SELECT is_admin FROM users WHERE user_id = ?", (user_id,)) as cursor:
            user_data = await cursor.fetchone()

        if not (user_data and user_data["is_admin"]):
            return  # Если не админ, молча выходим

        # 2. Узнаем текущий статус автоприема
        async with conn.execute("SELECT auto_approve_enabled FROM settings LIMIT 1") as cursor:
            settings = await cursor.fetchone()

        current_status = settings['auto_approve_enabled'] if settings else 0

        # 3. Меняем статус на противоположный (если был 0, станет 1; если был 1, станет 0)
        new_status = 1 - current_status

        # 4. Обновляем статус в базе данных
        await conn.execute("UPDATE settings SET auto_approve_enabled = ? WHERE rowid = 1", (new_status,))
        await conn.commit()

        # 5. Отправляем подтверждение и обновляем клавиатуру
        status_text = "✅ Включен" if new_status else "❌ Выключен"

        # Замените 'main_kb()' на вашу реальную функцию клавиатуры, если она динамическая
        # Если клавиатура статическая, вам понадобится ее обновить/пересоздать
        await message.answer(
            f"Режим автоприема заявок: {status_text}",
           reply_markup=main_kb()
        )
    finally:
        await conn.close()

# --- БЛОК НАСТРОЙКИ СООБЩЕНИЯ ПРИ ВЫХОДЕ ---

@admin_router.message(F.text == "Сообщение при выходе")
async def setup_goodbye_message(message: types.Message, state: FSMContext, bot: Bot):
    conn = await get_connection()
    conn.row_factory = aiosqlite.Row
    async with conn.execute("SELECT * FROM settings LIMIT 1") as cursor:
        settings = await cursor.fetchone()
    await conn.close()

    # Check if a channel is linked (this logic remains the same)
    if not settings["channel_id"]:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Добавить канал", callback_data="redirect_to_add_channel")]
        ])
        await message.answer("Сначала нужно настроить канал.", reply_markup=kb)
        return

    # Display the current goodbye message
    await message.answer("🔎 Текущее прощальное сообщение выглядит так:",
                         reply_markup=cancel_kb())

    photo_id = settings["goodbye_message_photo_id"]
    goodbye_text = settings["goodbye_message_text"]

    if photo_id:
        await bot.send_photo(chat_id=message.chat.id, photo=photo_id, caption=goodbye_text or "")
    elif goodbye_text:
        await message.answer(goodbye_text)
    else:
        await message.answer("Прощальное сообщение ещё не создано.")

    # Request the new message
    await message.answer(
        "Теперь пришлите новое фото и текст для прощального сообщения (одним сообщением)."
    )
    await state.set_state(GoodbyeMessageSetup.waiting_for_photo_and_text)

@admin_router.message(F.text == "Вернуться в главное меню", GoodbyeMessageSetup.waiting_for_photo_and_text)
async def cancel_add_admin(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Действие отменено. Вы возвращены в главное меню.",
        reply_markup=main_kb())


# 2. Хендлер, который ловит фото и текст
@admin_router.message(GoodbyeMessageSetup.waiting_for_photo_and_text)
async def process_goodbye_content(message: types.Message, state: FSMContext):
    photo_id = message.photo[-1].file_id if message.photo else None
    text = message.caption if message.photo else message.text

    # Сохраняем в новые колонки в БД
    conn = await get_connection()
    await conn.execute(
        "UPDATE settings SET goodbye_message_text = ?, goodbye_message_photo_id = ? WHERE rowid = 1",
        (text, photo_id)
    )
    await conn.commit()
    await conn.close()

    await message.answer(
        "✅ Прощальное сообщение успешно сохранено!",
        reply_markup=main_kb() # Используем вашу динамическую клавиатуру
    )
    await state.clear()

#Хендлер для отправки сообщения в канал

@admin_router.message(F.text == "Создать пост")
async def start_post_creation(message: types.Message, state: FSMContext):
    # На первом шаге кнопка "Назад" не нужна, поэтому используем старую клавиатуру
    await message.answer(
        "Шаг 1: Пришлите фото с текстом (или просто текст) для вашего будущего поста.",
        reply_markup=cancel_kb()
    )
    await state.set_state(PostCreation.waiting_for_content)

@admin_router.message(F.text == "Вернуться в главное меню", PostCreation.waiting_for_content)
async def start_post_cancel(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Действие отменено. Вы возвращены в главное меню.",
        reply_markup=main_kb())

# НОВЫЙ ХЕНДЛЕР ДЛЯ КНОПКИ "НАЗАД"
@admin_router.message(F.text == "⬅️ Назад", StateFilter(PostCreation.waiting_for_button_text, PostCreation.waiting_for_button_url))
async def back_step_handler(message: types.Message, state: FSMContext):
    current_state = await state.get_state()

    # Если мы на шаге ввода URL, возвращаемся к шагу ввода текста кнопки
    if current_state == PostCreation.waiting_for_button_url:
        await message.answer("Возвращаемся назад. Введите новый текст для кнопки.")
        await state.set_state(PostCreation.waiting_for_button_text)

    # Если мы на шаге ввода текста кнопки, возвращаемся к шагу ввода контента
    elif current_state == PostCreation.waiting_for_button_text:
        await message.answer("Возвращаемся назад. Пришлите новый контент (фото/текст) для поста.")
        await state.set_state(PostCreation.waiting_for_content)


@admin_router.message(F.text == "Создать пост")
async def start_post_creation(message: types.Message, state: FSMContext):
    await message.answer(
        "Шаг 1: Пришлите фото с текстом (или просто текст) для вашего будущего поста.",
        reply_markup=back_cancel_kb()  # Используем вашу клавиатуру отмены
    )
    await state.set_state(PostCreation.waiting_for_content)


# 2. Хендлер, который получает фото и текст поста
@admin_router.message(PostCreation.waiting_for_content, F.photo | F.text)
async def process_post_content(message: types.Message, state: FSMContext):
    photo_id = message.photo[-1].file_id if message.photo else None
    text = message.caption if message.photo else message.text

    # Сохраняем полученные данные во временное хранилище FSM
    await state.update_data(photo_id=photo_id, text=text)

    await message.answer("Шаг 2: Теперь введите текст для кнопки (например, 'Перейти на сайт').",
                         reply_markup=back_cancel_kb())
    await state.set_state(PostCreation.waiting_for_button_text)


# 3. Хендлер, который получает текст для кнопки
@admin_router.message(PostCreation.waiting_for_button_text)
async def process_button_text(message: types.Message, state: FSMContext):
    await state.update_data(button_text=message.text)
    await message.answer(
        "Шаг 3: Отлично! Теперь пришлите полную ссылку (URL), которая должна быть в кнопке (начиная с https://).",
                         reply_markup=back_cancel_kb())
    await state.set_state(PostCreation.waiting_for_button_url)


# 4. Хендлер, который получает ссылку, сохраняет пост и показывает превью
@admin_router.message(PostCreation.waiting_for_button_url)
async def process_button_url(message: types.Message, state: FSMContext, bot: Bot):
    if not message.text.startswith(('http://', 'https://')):
        await message.answer("Ссылка должна начинаться с http:// или https://. Попробуйте еще раз.")
        return

    await state.update_data(button_url=message.text)

    # Получаем все данные из хранилища
    post_data = await state.get_data()

    # Сохраняем пост в базу данных
    conn = await get_connection()
    await conn.execute(
        """UPDATE settings
           SET post_photo_id    = ?,
               post_text        = ?,
               post_button_text = ?,
               post_button_url  = ?
           WHERE rowid = 1""",
        (post_data['photo_id'], post_data['text'], post_data['button_text'], post_data['button_url'])
    )
    await conn.commit()
    await conn.close()

    # --- Показываем превью поста администратору ---
    await message.answer("Вот так будет выглядеть ваш пост.",
                         reply_markup=cancel_kb())


    # Формируем кнопку для превью
    preview_button = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=post_data['button_text'], url=post_data['button_url'])]
    ])

    # Отправляем превью
    if post_data['photo_id']:
        await bot.send_photo(message.chat.id, photo=post_data['photo_id'], caption=post_data['text'],
                             reply_markup=preview_button)
    else:
        await bot.send_message(message.chat.id, text=post_data['text'], reply_markup=preview_button)

    # Предлагаем отправить пост
    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Отправить в канал", callback_data="send_post_confirm")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="send_post_cancel")]
    ])
    await message.answer("Подтверждаете отправку?", reply_markup=confirm_kb)

    await state.clear()


# 5. Хендлеры для кнопок подтверждения
@admin_router.callback_query(F.data == "send_post_cancel")
async def cancel_post_send(callback: types.CallbackQuery):
    await callback.message.edit_text("Отправка отменена.")
    await callback.answer()


@admin_router.callback_query(F.data == "send_post_confirm")
async def confirm_post_send(callback: types.CallbackQuery, bot: Bot):
    # Берем данные для поста из базы данных
    conn = await get_connection()
    conn.row_factory = aiosqlite.Row
    async with conn.execute(
            "SELECT channel_id, post_photo_id, post_text, post_button_text, post_button_url FROM settings LIMIT 1") as cursor:
        settings = await cursor.fetchone()
    await conn.close()

    if not settings or not settings['channel_id']:
        await callback.message.edit_text("Ошибка: Канал не настроен!")
        await callback.answer()
        return

    # Формируем кнопку
    final_button = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=settings['post_button_text'], url=settings['post_button_url'])]
    ])

    # Отправляем пост в канал
    try:
        if settings['post_photo_id']:
            await bot.send_photo(settings['channel_id'], photo=settings['post_photo_id'], caption=settings['post_text'],
                                 reply_markup=final_button)
        else:
            await bot.send_message(settings['channel_id'], text=settings['post_text'], reply_markup=final_button)

        await callback.message.edit_text("✅ Пост успешно отправлен в канал!")
    except Exception as e:
        await callback.message.edit_text(f"❌ Не удалось отправить пост. Ошибка: {e}")

    await callback.answer()