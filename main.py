import os
import sqlite3
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery

# اطلاعات ربات و مالک
API_ID = 2521323  # مقدار پیش‌فرض پایتون-تلگرام، یا می‌توانید تغییر دهید
API_HASH = "6b6103d2fac35677054f0a0c644ef56e"
BOT_TOKEN = "8945064909:AAEpyCOTdBkXJnbJhA3woPYX3OM9RnSwnkw"
ADMIN_ID = 8854073031

app = Client("file_uploader_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# راه‌اندازی دیتابیس SQLite
def init_db():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    # جدول فایل‌ها
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id TEXT,
            file_type TEXT,
            caption TEXT,
            del_time INTEGER
        )
    """)
    # جدول کانال‌های عضویت اجباری
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS forced_channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_username TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ذخیره موقت وضعیت ادمین برای مراحل آپلود
admin_states = {}

# بررسی عضویت اجباری کاربر
async def check_membership(client, user_id):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT channel_username FROM forced_channels")
    channels = cursor.fetchall()
    conn.close()

    for (channel,) in channels:
        try:
            member = await client.get_chat_member(channel, user_id)
            if member.status in ["left", "kicked"]:
                return False
        except Exception:
            # اگر ربات نتواند بررسی کند یا خطا رخ دهد
            continue
    return True

# منوی مدیریت
def get_admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 آپلود فایل جدید", callback_data="upload_file")],
        [InlineKeyboardButton("🗑 حذف فایل‌ها", callback_data="delete_files")],
        [InlineKeyboardButton("➕ افزودن عضویت اجباری", callback_data="add_force"),
         InlineKeyboardButton("➖ حذف عضویت اجباری", callback_data="remove_force")]
    ])

@app.on_message(filters.command("start"))
async def start_handler(client, message: Message):
    user_id = message.from_user.id
    text_args = message.text.split(" ")

    # اگر ربات توسط کسی غیر از مالک استارت شد
    if user_id != ADMIN_ID:
        # بررسی عضویت اجباری
        is_member = await check_membership(client, user_id)
        if not is_member:
            conn = sqlite3.connect("bot_database.db")
            cursor = conn.cursor()
            cursor.execute("SELECT channel_username FROM forced_channels")
            channels = cursor.fetchall()
            conn.close()
            
            keyboard = []
            for (ch,) in channels:
                keyboard.append([InlineKeyboardButton(f"عضویت در {ch}", url=f"https://t.me/{ch.lstrip('@')}")])
            keyboard.append([InlineKeyboardButton("🔄 بررسی عضویت", callback_data="check_join")])
            
            await message.reply(
                "❌ برای استفاده از ربات باید ابتدا در کانال‌های زیر عضو شوید:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return

        # اگر فایل خاصی درخواست شده بود (از طریق لینک)
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
                if f_type == "photo":
                    sent_msg = await client.send_photo(user_id, f_id, caption=f_caption)
                elif f_type == "video":
                    sent_msg = await client.send_video(user_id, f_id, caption=f_caption)
                elif f_type == "audio":
                    sent_msg = await client.send_audio(user_id, f_id, caption=f_caption)
                elif f_type == "document":
                    sent_msg = await client.send_document(user_id, f_id, caption=f_caption)
                elif f_type == "text":
                    sent_msg = await client.send_message(user_id, f_caption)

                if sent_msg and f_time:
                    import asyncio
                    await asyncio.sleep(f_time)
                    try:
                        await sent_msg.delete()
                    except:
                        pass
            else:
                await message.reply("این فایل یافت نشد یا حذف شده است.")
        else:
                            await message.reply("سلام! خوش آمدید.")
        return

    # پنل ادمین برای مالک
    admin_states.pop(user_id, None)
    await message.reply("به بخش مدیریت خوش آمدید:", reply_markup=get_admin_keyboard())

@app.on_callback_query()
async def callback_handler(client, callback: CallbackQuery):
    user_id = callback.from_user.id
    data = callback.data

    if user_id != ADMIN_ID:
        if data == "check_join":
            is_member = await check_membership(client, user_id)
            if is_member:
                await callback.message.edit_text("✅ عضویت شما تایید شد! حالا لطفاً دوباره روی لینک فایل خود بزنید یا /start را بفرستید.")
            else:
                await callback.answer("هنوز در تمام کانال‌ها عضو نیستید!", show_alert=True)
        return

    if data == "upload_file":
        admin_states[user_id] = {"step": "waiting_file"}
        await callback.message.edit_text("لطفاً فایل خود (عکس، فیلم، آهنگ، سند یا متن) را بفرستید:")

    elif data == "delete_files":
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
                InlineKeyboardButton(f"فایل شماره {f_id} ({f_type})", callback_data=f"none"),
                InlineKeyboardButton("🗑 حذف", callback_data=f"delfile_{f_id}")
            ])
        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_home")])
        await callback.message.edit_text("لیست فایل‌های آپلود شده:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("delfile_"):
        file_db_id = data.split("_")[1]
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        cursor.execute("DELETE FROM files WHERE id = ?", (file_db_id,))
        conn.commit()
        conn.close()
        await callback.answer("فایل با موفقیت حذف شد.", show_alert=True)
        await callback.message.delete()

    elif data == "add_force":
        admin_states[user_id] = {"step": "waiting_channel"}
        await callback.message.edit_text("لطفاً یوزرنیم کانال را همراه با @ بفرستید (مثال: @ChannelUsername):\nنکته: ربات حتماً باید مدیر کانال باشد.")

    elif data == "remove_force":
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
                InlineKeyboardButton(c_username, callback_data="none"),
                InlineKeyboardButton("🗑 حذف", callback_data=f"delchan_{c_id}")
            ])
        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_home")])
        await callback.message.edit_text("لیست کانال‌های عضویت اجباری:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("delchan_"):
        c_id = data.split("_")[1]
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        cursor.execute("DELETE FROM forced_channels WHERE id = ?", (c_id,))
        conn.commit()
        conn.close()
        await callback.answer("کانال از لیست عضویت اجباری حذف شد.", show_alert=True)
        await callback.message.delete()

    elif data == "back_home":
        admin_states.pop(user_id, None)
        await callback.message.edit_text("به بخش مدیریت خوش آمدید:", reply_markup=get_admin_keyboard())

@app.on_message(filters.user(ADMIN_ID) & ~filters.command("start"))
async def admin_steps_handler(client, message: Message):
    user_id = message.from_user.id
    state = admin_states.get(user_id)

    if not state:
        return

    step = state.get("step")

    if step == "waiting_file":
        file_type = "text"
        file_id = None

        if message.photo:
            file_type = "photo"
            file_id = message.photo.file_id
        elif message.video:
            file_type = "video"
            file_id = message.video.file_id
        elif message.audio:
            file_type = "audio"
            file_id = message.audio.file_id
        elif message.document:
            file_type = "document"
            file_id = message.document.file_id
        else:
            file_type = "text"
            file_id = None

        state["file_type"] = file_type
        state["file_id"] = file_id
        state["step"] = "waiting_caption"
        
        await message.reply("پیام زیر متن (کپشن یا متن مورد نظر) را ارسال کنید:")

    elif step == "waiting_caption":
        state["caption"] = message.text or message.caption or ""
        state["step"] = "waiting_time"
        await message.reply("زمان پاک شدن فایل را اعلام کنید (زمان مجاز: 20 تا 50 ثانیه):")

    elif step == "waiting_time":
        try:
            del_time = int(message.text)
            if not (20 <= del_time <= 50):
                await message.reply("❌ زمان مجاز بین 20 تا 50 ثانیه است. لطفاً عدد درستی وارد کنید:")
                return
        except ValueError:
            await message.reply("❌ لطفاً فقط یک عدد صحیح وارد کنید:")
            return

        # ذخیره در دیتابیس
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO files (file_id, file_type, caption, del_time) VALUES (?, ?, ?, ?)",
            (state.get("file_id"), state.get("file_type"), state.get("caption"), del_time)
        )
        conn.commit()
        cursor.execute("SELECT last_insert_rowid()")
        new_file_id = cursor.fetchone()[0]
        conn.close()

        bot_username = (await client.get_me()).username
        link = f"https://t.me/{bot_username}?start=file_{new_file_id}"

        admin_states.pop(user_id, None)
        await message.reply(
            f"✅ فایل با موفقیت ثبت شد!\n\nلینک اختصاصی فایل:\n{link}",
            reply_markup=get_admin_keyboard()
        )

    elif step == "waiting_channel":
        channel_username = message.text.strip()
        if not channel_username.startswith("@"):
            await message.reply("❌ یوزرنیم باید با @ شروع شود. دوباره بفرستید:")
            return

        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        cursor.execute("INSERT INTO forced_channels (channel_username) VALUES (?)", (channel_username,))
        conn.commit()
        conn.close()

        admin_states.pop(user_id, None)
        await message.reply(
            f"✅ کانال {channel_username} با موفقیت به لیست عضویت اجباری اضافه شد.",
            reply_markup=get_admin_keyboard()
        )

print("Bot is running...")
app.run()
