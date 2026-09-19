import asyncio
import logging
import sqlite3
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

# توکن دریافت شده از BotFather را اینجا وارد کنید
BOT_TOKEN = "8914219897:AAHr7ZbHp1sEgpDsfycdPKqBAoIJIAZDrfY"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
logging.basicConfig(level=logging.INFO)

# --- مدیریت دیتابیس SQLite ---
def init_db():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            name TEXT,
            age INTEGER,
            gender TEXT,
            target_gender TEXT,
            state TEXT DEFAULT 'idle',
            partner_id INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def db_query(query, params=(), fetchone=False, fetchall=False, commit=False):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute(query, params)
    res = None
    if fetchone:
        res = cursor.fetchone()
    elif fetchall:
        res = cursor.fetchall()
    if commit:
        conn.commit()
    conn.close()
    return res

# --- تعریف مراحل ثبت‌نام (FSM) ---
class Registration(StatesGroup):
    name = State()
    age = State()
    gender = State()
    target_gender = State()

# --- کیبوردهای اصلی ---
def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔍 شروع جستجو / هم‌صحبت")],
            [KeyboardButton(text="👤 پروفایل من")]
        ],
        resize_keyboard=True
    )

def chat_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="❌ پایان مکالمه")]
        ],
        resize_keyboard=True
    )

# --- هندلرهای شروع و ثبت‌نام ---
@dp.message(CommandStart())
async def start_cmd(message: types.Message, state: FSMContext):
    user = db_query("SELECT * FROM users WHERE user_id = ?", (message.from_user.id,), fetchone=True)
    if user:
        await message.answer("به ربات دوست‌یابی خوش آمدید!", reply_markup=main_menu())
    else:
        await message.answer("سلام! برای استفاده از ربات لطفا نام خود را وارد کنید:")
        await state.set_state(Registration.name)

@dp.message(Registration.name)
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("سن خود را به عدد وارد کنید:")
    await state.set_state(Registration.age)

@dp.message(Registration.age)
async def process_age(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("لطفاً سن را به عدد وارد کنید:")
        return
    await state.update_data(age=int(message.text))
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="پسر"), KeyboardButton(text="دختر")]], resize_keyboard=True)
    await message.answer("جنسیت خود را مشخص کنید:", reply_markup=kb)
    await state.set_state(Registration.gender)

@dp.message(Registration.gender)
async def process_gender(message: types.Message, state: FSMContext):
    if message.text not in ["پسر", "دختر"]:
        await message.answer("لطفاً از گزینه‌های کیبورد انتخاب کنید.")
        return
    await state.update_data(gender=message.text)
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="پسر"), KeyboardButton(text="دختر"), KeyboardButton(text="فرقی نمیکنه")]], resize_keyboard=True)
    await message.answer("مایلید با چه کسی گفتگو کنید؟", reply_markup=kb)
    await state.set_state(Registration.target_gender)

@dp.message(Registration.target_gender)
async def process_target(message: types.Message, state: FSMContext):
    data = await state.get_data()
    db_query(
        "INSERT INTO users (user_id, name, age, gender, target_gender) VALUES (?, ?, ?, ?, ?)",
        (message.from_user.id, data['name'], data['age'], data['gender'], message.text),
        commit=True
    )
    await state.clear()
    await message.answer("ثبت‌نام شما با موفقیت انجام شد!", reply_markup=main_menu())

# --- سیستم اتصال دو کاربر ---
@dp.message(F.text == "🔍 شروع جستجو / هم‌صحبت")
async def start_search(message: types.Message):
    user_id = message.from_user.id
    user = db_query("SELECT gender, target_gender, state FROM users WHERE user_id = ?", (user_id,), fetchone=True)
    
    if not user:
        await message.answer("لطفاً ابتدا با دستور /start ثبت‌نام کنید.")
        return
        
    if user[2] == 'chatting':
        await message.answer("شما در حال حاضر در یک مکالمه هستید!")
        return

    db_query("UPDATE users SET state = 'waiting' WHERE user_id = ?", (user_id,), commit=True)
    await message.answer("در حال جستجو برای یافتن هم‌صحبت... لطفاً شکیبا باشید.", reply_markup=ReplyKeyboardRemove())

    my_gender, my_target = user[0], user[1]
    
    query = "SELECT user_id, gender, target_gender FROM users WHERE state = 'waiting' AND user_id != ?"
    waiting_users = db_query(query, (user_id,), fetchall=True)

    partner_id = None
    for u_id, u_gender, u_target in waiting_users:
        cond1 = (my_target == "فرقی نمیکنه" or my_target == u_gender)
        cond2 = (u_target == "فرقی نمیکنه" or u_target == my_gender)
        if cond1 and cond2:
            partner_id = u_id
            break

    if partner_id:
        db_query("UPDATE users SET state = 'chatting', partner_id = ? WHERE user_id = ?", (partner_id, user_id), commit=True)
        db_query("UPDATE users SET state = 'chatting', partner_id = ? WHERE user_id = ?", (user_id, partner_id), commit=True)

        await bot.send_message(user_id, "هم‌صحبت پیدا شد! می‌توانید گفتگو را شروع کنید.", reply_markup=chat_menu())
        await bot.send_message(partner_id, "هم‌صحبت پیدا شد! می‌توانید گفتگو را شروع کنید.", reply_markup=chat_menu())

@dp.message(F.text == "❌ پایان مکالمه")
async def end_chat(message: types.Message):
    user_id = message.from_user.id
    user = db_query("SELECT partner_id, state FROM users WHERE user_id = ?", (user_id,), fetchone=True)

    if user and user[1] == 'chatting':
        partner_id = user[0]
        db_query("UPDATE users SET state = 'idle', partner_id = 0 WHERE user_id = ?", (user_id,), commit=True)
        db_query("UPDATE users SET state = 'idle', partner_id = 0 WHERE user_id = ?", (partner_id,), commit=True)

        await message.answer("مکالمه پایان یافت.", reply_markup=main_menu())
        await bot.send_message(partner_id, "هم‌صحبت شما مکالمه را پایان داد.", reply_markup=main_menu())
    else:
        await message.answer("شما در مکالمه‌ای حضور ندارید.", reply_markup=main_menu())

# --- چت متنی بین طرفین ---
@dp.message(F.text & ~F.text.startswith("/"))
async def relay_message(message: types.Message):
    user_id = message.from_user.id
    user = db_query("SELECT partner_id, state FROM users WHERE user_id = ?", (user_id,), fetchone=True)

    if user and user[1] == 'chatting':
        try:
            await bot.send_message(user[0], message.text)
        except Exception:
            await message.answer("خطا در ارسال پیام.")
    elif user and user[1] == 'waiting':
        await message.answer("هنوز هم‌صحبتی پیدا نشده است. صبور باشید...")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
