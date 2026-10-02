import asyncio
import sqlite3
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

BOT_TOKEN = "8945064909:AAEpyCOTdBkXJnbJhA3woPYX3OM9RnSwnkw"
ADMIN_ID = 8854073031

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()

# راه‌اندازی دیتابیس SQLite
def init_db():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id TEXT,
            file_type TEXT,
            caption TEXT,
            del_time INTEGER
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS forced_channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_username TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# وضعیت‌های FSM برای مدیریت مراحل ربات
class AdminStates(StatesGroup):
    waiting_file = State()
    waiting_caption = State()
    waiting_time = State()
    waiting_channel = State()

# بررسی عضویت اجباری
async def check_membership(user_id: int):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT channel_username FROM forced_channels")
    channels = cursor.fetchall()
    conn.close()

    for (channel,) in channels:
        try:
            member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status in ["left", "kicked"]:
                return False
        except Exception:
            continue
    return True

# منوی مدیریت
def get_admin_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 آپلود فایل جدید", callback_data="upload_file")],
        [InlineKeyboardButton(text="🗑 حذف فایل‌ها", callback_data="delete_files")],
        [InlineKeyboardButton(text="➕ افزودن عضویت اجباری", callback_data="add_force"),
         InlineKeyboardButton(text="➖ حذف عضویت اجباری", callback_data="remove_force")]
    ])

@router.message(Command("start"))
async def start_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id
    text_args = message.text.split(" ")

    if user_id != ADMIN_ID:
        is_member = await check_membership(user_id)
        if not is_member:
            conn = sqlite3.connect("bot_database.db")
            cursor = conn.cursor()
            cursor.execute("SELECT channel_username FROM forced_channels")
            channels = cursor.fetchall()
            conn.close()
            
            keyboard = []
            for (ch,) in channels:
                keyboard.append([InlineKeyboardButton(text=f"عضویت در {ch}", url=f"https://t.me/{ch.lstrip('@')}")])
            keyboard.append([InlineKeyboardButton(text="🔄 بررسی عضویت", callback_data="check_join")])
            
            await message.answer(
                "❌ برای استفاده از ربات باید ابتدا در کانال‌های زیر عضو شوید:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
            )
            return

        if len(text_args) > 1 and text_args[1].startswith("file_"):
            file_db_id = text_args[1].replace("file_", "")
            conn = sqlite3.connect("bot_database.db")
            cursor = conn.cursor()
            cursor.execute("SELECT file_id, file_type, caption, del_time FROM files WHERE id = ?", (file_db_id,))
            file_data = cursor.fetchone()
            conn.close()

            if file_data:
                f_id, f_type, f_caption, f_time = file_data
                sent_msg = None
                try:
                    if f_type == "photo":
                        sent_msg = await bot.send_photo(user_id, f_id, caption=f_caption)
                    elif f_type == "video":
                        sent_msg = await bot.send_video(user_id, f_id, caption=f_caption)
                    elif f_type == "audio":
                        sent_msg = await bot.send_audio(user_id, f_id, caption=f_caption)
                    elif f_type == "document":
                        sent_msg = await bot.send_document(user_id, f_id, caption=f_caption)
                    elif f_type == "text":
                        sent_msg = await bot.send_message(user_id, f_caption)

                    if sent_msg and f_time:
                        await asyncio.sleep(f_time)
                        await sent_msg.delete()
                except Exception:
                    pass
            else:
                await message.answer("این فایل یافت نشد یا حذف شده است.")
        else:
            await message.answer("سلام! خوش آمدید.")
        return

    await state.clear()
    await message.answer("به بخش مدیریت خوش آمدید:", reply_markup=get_admin_keyboard())

@router.callback_query(F.data == "check_join")
async def check_join_callback(callback: CallbackQuery):
    is_member = await check_membership(callback.from_user.id)
    if is_member:
        await callback.message.edit_text("✅ عضویت شما تایید شد! حالا لطفاً دوباره روی لینک فایل خود بزنید یا /start را بفرستید.")
    else:
        await callback.answer("هنوز در تمام کانال‌ها عضو نیستید!", show_alert=True)

@router.callback_query(F.data == "upload_file")
async def upload_file_callback(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminStates.waiting_file)
    await callback.message.edit_text("لطفاً فایل خود (عکس، فیلم، آهنگ، سند یا متن) را بفرستید:")

@router.callback_query(F.data == "delete_files")
async def delete_files_callback(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, file_type FROM files")
    files = cursor.fetchall()
    conn.close()

    if not files:
        await callback.answer("هیچ فایلی برای حذف وجود ندارد.", show_alert=True)
        return

    keyboard = []
    for f_id, f_type in files:
        keyboard.append([
            InlineKeyboardButton(text=f"فایل شماره {f_id} ({f_type})", callback_data="none"),
            InlineKeyboardButton(text="🗑 حذف", callback_data=f"delfile_{f_id}")
        ])
    keyboard.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_home")])
    await callback.message.edit_text("لیست فایل‌های آپلود شده:", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))

@router.callback_query(F.data.startswith("delfile_"))
async def delfile_callback(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    file_db_id = callback.data.split("_")[1]
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM files WHERE id = ?", (file_db_id,))
    conn.commit()
    conn.close()
    await callback.answer("فایل با موفقیت حذف شد.", show_alert=True)
    await callback.message.delete()

@router.callback_query(F.data == "add_force")
async def add_force_callback(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminStates.waiting_channel)
    await callback.message.edit_text("لطفاً یوزرنیم کانال را همراه با @ بفرستید (مثال: @ChannelUsername):\nنکته: ربات حتماً باید مدیر کانال باشد.")

@router.callback_query(F.data == "remove_force")
async def remove_force_callback(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, channel_username FROM forced_channels")
    channels = cursor.fetchall()
    conn.close()

    if not channels:
        await callback.answer("هیچ کانالی در لیست عضویت اجباری نیست.", show_alert=True)
        return

    keyboard = []
    for c_id, c_username in channels:
        keyboard.append([
            InlineKeyboardButton(text=c_username, callback_data="none"),
            InlineKeyboardButton(text="🗑 حذف", callback_data=f"delchan_{c_id}")
        ])
    keyboard.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_home")])
    await callback.message.edit_text("لیست کانال‌های عضویت اجباری:", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))

@router.callback_query(F.data.startswith("delchan_"))
async def delchan_callback(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    c_id = callback.data.split("_")[1]
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM forced_channels WHERE id = ?", (c_id,))
    conn.commit()
    conn.close()
    await callback.answer("کانال از لیست عضویت اجباری حذف شد.", show_alert=True)
    await callback.message.delete()

@router.callback_query(F.data == "back_home")
async def back_home_callback(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await state.clear()
    await callback.message.edit_text("به بخش مدیریت خوش آمدید:", reply_markup=get_admin_keyboard())

@router.message(AdminStates.waiting_file, F.from_user.id == ADMIN_ID)
async def process_file(message: Message, state: FSMContext):
    file_type = "text"
    file_id = None

    if message.photo:
        file_type = "photo"
        file_id = message.photo[-1].file_id
    elif message.video:
        file_type = "video"
        file_id = message.video.file_id
    elif message.audio:
        file_type = "audio"
        file_id = message.audio.file_id
    elif message.document:
        file_type = "document"
        file_id = message.document.file_id

    await state.update_data(file_type=file_type, file_id=file_id)
    await state.set_state(AdminStates.waiting_caption)
    await message.answer("پیام زیر متن (کپشن یا متن مورد نظر) را ارسال کنید:")

@router.message(AdminStates.waiting_caption, F.from_user.id == ADMIN_ID)
async def process_caption(message: Message, state: FSMContext):
    caption = message.text or message.caption or ""
    await state.update_data(caption=caption)
    await state.set_state(AdminStates.waiting_time)
    await message.answer("زمان پاک شدن فایل را اعلام کنید (زمان مجاز: 20 تا 50 ثانیه):")

@router.message(AdminStates.waiting_time, F.from_user.id == ADMIN_ID)
async def process_time(message: Message, state: FSMContext):
    try:
        del_time = int(message.text)
        if not (20 <= del_time <= 50):
            await message.answer("❌ زمان مجاز بین 20 تا 50 ثانیه است. لطفاً عدد درستی وارد کنید:")
            return
    except ValueError:
        await message.answer("❌ لطفاً فقط یک عدد صحیح وارد کنید:")
        return

    data = await state.get_data()
    
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO files (file_id, file_type, caption, del_time) VALUES (?, ?, ?, ?)",
        (data.get("file_id"), data.get("file_type"), data.get("caption"), del_time)
    )
    conn.commit()
    cursor.execute("SELECT last_insert_rowid()")
    new_file_id = cursor.fetchone()[0]
    conn.close()

    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start=file_{new_file_id}"

    await state.clear()
    await message.answer(
        f"✅ فایل با موفقیت ثبت شد!\n\nلینک اختصاصی فایل:\n{link}",
        reply_markup=get_admin_keyboard()
    )

@router.message(AdminStates.waiting_channel, F.from_user.id == ADMIN_ID)
async def process_channel(message: Message, state: FSMContext):
    channel_username = message.text.strip()
    if not channel_username.startswith("@"):
        await message.answer("❌ یوزرنیم باید با @ شروع شود. دوباره بفرستید:")
        return

    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO forced_channels (channel_username) VALUES (?)", (channel_username,))
    conn.commit()
    conn.close()

    await state.clear()
    await message.answer(
        f"✅ کانال {channel_username} با موفقیت به لیست عضویت اجباری اضافه شد.",
        reply_markup=get_admin_keyboard()
    )

async def main():
    dp.include_router(router)
    print("Bot is running...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
