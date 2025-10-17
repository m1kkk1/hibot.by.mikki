from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton

def to_main_kb():
    return ReplyKeyboardMarkup(
            keyboard = [
                [KeyboardButton(text="Главное меню")]
            ],
        resize_keyboard = True
    )

def main_kb():
    return ReplyKeyboardMarkup(
            keyboard = [
                [KeyboardButton(text="Редактировать приветствие"), KeyboardButton(text="Авто прием Вкл.\Выкл.")],
                [KeyboardButton(text="Сообщение при выходе"), KeyboardButton(text="Настроить канал")],
                [KeyboardButton(text="Добавить админа"), KeyboardButton(text="Сообщение при /start")],
                [KeyboardButton(text="Создать пост")]
            ],
        resize_keyboard = True,
    )

def cancel_kb():
    return ReplyKeyboardMarkup(
            keyboard = [
                [KeyboardButton(text="Вернуться в главное меню")]
            ],
    resize_keyboard=True
    )

def back_cancel_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
                [KeyboardButton(text="⬅️ Назад")]
    ],
    resize_keyboard=True
)

