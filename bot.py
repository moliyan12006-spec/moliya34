import logging
import math
import sqlite3
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, 
    CallbackQueryHandler, ContextTypes, ConversationHandler, filters
)

# Logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# DB Boshqarish
def init_db():
    conn = sqlite3.connect('finance_bot.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, balance REAL DEFAULT 0)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS transactions (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, type TEXT, amount REAL, date TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS debts (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, type TEXT, name TEXT, amount REAL, 
        due_date TEXT, phone TEXT, status TEXT DEFAULT 'active'
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS savings (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, title TEXT, target_amount REAL, current_amount REAL DEFAULT 0
    )''')
    conn.commit()
    conn.close()

init_db()

# Holatlar
KIRIM, CHIQIM = 1, 2
DEBT_NAME, DEBT_AMOUNT, DEBT_PERIOD, DEBT_PHONE = 3, 4, 5, 6
EXTEND_PERIOD = 7
SAVING_TITLE, SAVING_TARGET, SAVING_AMOUNT = 8, 9, 10

def main_keyboard():
    return ReplyKeyboardMarkup([
        ["📥 Kirim","💳 Balans", "📤 Chiqim"],
        ["🤝 Qarz olish", "💸 Qarz berish"],
        ["📋 Qarzlar ro'yxati"],
        ["🎯 Jamg'armalar"]
    ], resize_keyboard=True)

# Xabarlarni avtomatik o'chirish yordamchi funksiyalari
def track_message(context: ContextTypes.DEFAULT_TYPE, message_id: int):
    if 'messages_to_delete' not in context.user_data:
        context.user_data['messages_to_delete'] = []
    context.user_data['messages_to_delete'].append(message_id)

async def clear_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if 'messages_to_delete' in context.user_data:
        for msg_id in context.user_data['messages_to_delete']:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except Exception:
                pass
        context.user_data['messages_to_delete'] = []

# Start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect('finance_bot.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id, balance) VALUES (?, 0)", (user_id,))
    conn.commit()
    conn.close()
    await update.message.reply_text("Xush kelibsiz Shaxboz Shavkatjonivich! Shaxsiy moliya monitoringi boti ishga tayyor.", reply_markup=main_keyboard())

# --- KIRIM / CHIQIM / BALANS ---
async def start_kirim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track_message(context, update.message.message_id)
    msg = await update.message.reply_text("Kirim summasini kiriting:")
    track_message(context, msg.message_id)
    return KIRIM

async def process_kirim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track_message(context, update.message.message_id)
    try:
        amount = float(update.message.text)
        if amount <= 0:
            msg = await update.message.reply_text("Iltimos, 0 dan katta summa kiriting.")
            track_message(context, msg.message_id)
            return KIRIM
        
        user_id = update.effective_user.id
        conn = sqlite3.connect('finance_bot.db')
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        cursor.execute("INSERT INTO transactions (user_id, type, amount, date) VALUES (?, 'kirim', ?, ?)", 
                       (user_id, amount, datetime.now().strftime("%Y-%m-%d %H:%M")))
        conn.commit()
        conn.close()

        await clear_messages(update, context)
        await update.message.reply_text(f"✅ Budjetga {amount:,.0f} so'm qo'shildi.", reply_markup=main_keyboard())
    except ValueError:
        msg = await update.message.reply_text("Iltimos, faqat raqam kiriting.")
        track_message(context, msg.message_id)
        return KIRIM
    return ConversationHandler.END

async def start_chiqim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track_message(context, update.message.message_id)
    msg = await update.message.reply_text("Chiqim summasini kiriting:")
    track_message(context, msg.message_id)
    return CHIQIM

async def process_chiqim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track_message(context, update.message.message_id)
    try:
        amount = float(update.message.text)
        if amount <= 0:
            msg = await update.message.reply_text("Iltimos, 0 dan katta summa kiriting.")
            track_message(context, msg.message_id)
            return CHIQIM

        user_id = update.effective_user.id
        conn = sqlite3.connect('finance_bot.db')
        cursor = conn.cursor()
        cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        res = cursor.fetchone()
        current_balance = res[0] if res else 0

        if current_balance < amount:
            conn.close()
            await clear_messages(update, context)
            await update.message.reply_text(
                f"⚠️ **Mablag' yetarli emas!**\n\nJoriy balans: {current_balance:,.0f} so'm\nKiritilgan chiqim: {amount:,.0f} so'm",
                reply_markup=main_keyboard(),
                parse_mode="Markdown"
            )
            return ConversationHandler.END

        cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
        cursor.execute("INSERT INTO transactions (user_id, type, amount, date) VALUES (?, 'chiqim', ?, ?)", 
                       (user_id, amount, datetime.now().strftime("%Y-%m-%d %H:%M")))
        conn.commit()
        conn.close()

        await clear_messages(update, context)
        await update.message.reply_text(f"💸 {amount:,.0f} so'm sarflandi.", reply_markup=main_keyboard())
    except ValueError:
        msg = await update.message.reply_text("Iltimos, faqat raqam kiriting.")
        track_message(context, msg.message_id)
        return CHIQIM
    return ConversationHandler.END

async def show_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect('finance_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    res = cursor.fetchone()
    balance = res[0] if res else 0
    conn.close()
    await update.message.reply_text(f"💳 Sizning joriy balansikiz: {balance:,.0f} so'm", reply_markup=main_keyboard())

# --- QARZLAR ---
async def start_debt_get(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track_message(context, update.message.message_id)
    context.user_data['debt_type'] = 'olish'
    msg = await update.message.reply_text("Kimdan qarz oldingiz?")
    track_message(context, msg.message_id)
    return DEBT_NAME

async def start_debt_give(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track_message(context, update.message.message_id)
    context.user_data['debt_type'] = 'berish'
    msg = await update.message.reply_text("Kimga qarz berdingiz?")
    track_message(context, msg.message_id)
    return DEBT_NAME

async def process_debt_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track_message(context, update.message.message_id)
    context.user_data['debt_name'] = update.message.text
    msg = await update.message.reply_text("Qancha summa?")
    track_message(context, msg.message_id)
    return DEBT_AMOUNT

async def process_debt_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track_message(context, update.message.message_id)
    try:
        context.user_data['debt_amount'] = float(update.message.text)
        msg = await update.message.reply_text("Qancha muddatga:")
        track_message(context, msg.message_id)
        return DEBT_PERIOD
    except ValueError:
        msg = await update.message.reply_text("Iltimos, summani raqamlarda kiriting.")
        track_message(context, msg.message_id)
        return DEBT_AMOUNT

async def process_debt_period(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track_message(context, update.message.message_id)
    try:
        days = float(update.message.text)
        if days < 0:
            msg = await update.message.reply_text("Kunlar soni musbat bo'lishi kerak.")
            track_message(context, msg.message_id)
            return DEBT_PERIOD
        
        due_date = datetime.now() + timedelta(days=days)
        context.user_data['debt_due_date'] = due_date.strftime("%Y-%m-%d %H:%M:%S")
        context.user_data['debt_days_input'] = days
        
        if context.user_data['debt_type'] == 'berish':
            msg = await update.message.reply_text("Telefon raqamini kiriting:")
            track_message(context, msg.message_id)
            return DEBT_PHONE
        else:
            return await save_debt(update, context, phone="-")
    except ValueError:
        msg = await update.message.reply_text("Kunlar sonini raqamda kiriting.")
        track_message(context, msg.message_id)
        return DEBT_PERIOD

async def process_debt_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track_message(context, update.message.message_id)
    return await save_debt(update, context, phone=update.message.text)

async def save_debt(update: Update, context: ContextTypes.DEFAULT_TYPE, phone: str):
    user_id = update.effective_user.id
    d_type = context.user_data['debt_type']
    name = context.user_data['debt_name']
    amount = context.user_data['debt_amount']
    due_date_str = context.user_data['debt_due_date']
    days_input = context.user_data['debt_days_input']

    conn = sqlite3.connect('finance_bot.db')
    cursor = conn.cursor()
    cursor.execute("""INSERT INTO debts (user_id, type, name, amount, due_date, phone) 
                      VALUES (?, ?, ?, ?, ?, ?)""", (user_id, d_type, name, amount, due_date_str, phone))
    debt_id = cursor.lastrowid
    conn.commit()
    conn.close()

    seconds = days_input * 86400
    if seconds <= 0:
        seconds = 1
        
    if context.job_queue:
        context.job_queue.run_once(send_debt_reminder, when=seconds, data={'debt_id': debt_id, 'user_id': user_id})

    await clear_messages(update, context)
    await update.message.reply_text("✅ Ma'lumotlari saqlandi!", reply_markup=main_keyboard())
    return ConversationHandler.END

async def send_debt_reminder(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    debt_id = job.data['debt_id']
    user_id = job.data['user_id']

    conn = sqlite3.connect('finance_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT type, name, amount, phone FROM debts WHERE id = ? AND status = 'active'", (debt_id,))
    debt = cursor.fetchone()
    conn.close()

    if debt:
        d_type, name, amount, phone = debt
        msg = f"⏰ **ESLATMA!**\n\n{'Siz olgan' if d_type == 'olish' else 'Siz bergan'} qarz muddati tugadi!\n" \
              f"👤 Shaxs: {name}\n💰 Summa: {amount:,.0f} so'm\n📱 Tel: {phone}"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Qarzdorlik yopildi", callback_data=f"close_{debt_id}")],
            [InlineKeyboardButton("📅 Muddatni uzaytirish", callback_data=f"extend_{debt_id}")]
        ])
        await context.bot.send_message(chat_id=user_id, text=msg, reply_markup=keyboard, parse_mode="Markdown")

async def handle_debt_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split("_")
    action, debt_id = data[0], int(data[1])

    if action == "close":
        conn = sqlite3.connect('finance_bot.db')
        cursor = conn.cursor()
        cursor.execute("UPDATE debts SET status = 'closed' WHERE id = ?", (debt_id,))
        conn.commit()
        conn.close()
        await query.edit_message_text("✅ Qarzdorlik yopildi va ro'yxatdan o'chirildi.")
        return ConversationHandler.END
    elif action == "extend":
        context.user_data['extend_debt_id'] = debt_id
        await query.edit_message_text("Necha kunga muddatni uzaytirmoqchisiz?")
        track_message(context, query.message.message_id)
        return EXTEND_PERIOD

async def process_extend_period(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track_message(context, update.message.message_id)
    try:
        days = float(update.message.text)
        debt_id = context.user_data['extend_debt_id']
        new_due_date = datetime.now() + timedelta(days=days)

        conn = sqlite3.connect('finance_bot.db')
        cursor = conn.cursor()
        cursor.execute("UPDATE debts SET due_date = ? WHERE id = ?", (new_due_date.strftime("%Y-%m-%d %H:%M:%S"), debt_id))
        conn.commit()
        conn.close()

        seconds = days * 86400
        if seconds <= 0:
            seconds = 1

        if context.job_queue:
            context.job_queue.run_once(send_debt_reminder, when=seconds, data={'debt_id': debt_id, 'user_id': update.effective_user.id})
        
        await clear_messages(update, context)
        await update.message.reply_text(f"✅ Muddat uzaytirildi.", reply_markup=main_keyboard())
    except ValueError:
        msg = await update.message.reply_text("Iltimos, faqat raqam kiriting.")
        track_message(context, msg.message_id)
        return EXTEND_PERIOD
    return ConversationHandler.END

async def list_debts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect('finance_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT type, name, amount, due_date FROM debts WHERE user_id = ? AND status = 'active'", (user_id,))
    debts = cursor.fetchall()
    conn.close()

    if not debts:
        await update.message.reply_text("Sizda faol qarzlar mavjud emas.")
        return

    msg = "📋 **QARZLAR RO'YXATI:**\n\n"
    now = datetime.now()
    for d_type, name, amount, due_date_str in debts:
        try:
            due_date = datetime.strptime(due_date_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            due_date = datetime.strptime(due_date_str, "%Y-%m-%d %H:%M")
            
        remaining_seconds = (due_date - now).total_seconds()
        days_left = math.ceil(remaining_seconds / 86400) if remaining_seconds > 0 else 0
        
        tag = "🔴 Sizning qarzlaringiz" if d_type == 'olish' else "🟢 Sizdan qarzdorlar"
        msg += f"{tag}:\n👤 {name} - {amount:,.0f} so'm\n⏳ Qolgan muddat: {days_left} kun\n\n"

    await update.message.reply_text(msg, parse_mode="Markdown")

# --- JAMG'ARMALAR ---
async def show_savings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect('finance_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, target_amount, current_amount FROM savings WHERE user_id = ?", (user_id,))
    savings = cursor.fetchall()
    conn.close()

    if not savings:
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("➕ Yangi jamg'arma qo'shish", callback_data="add_saving")]])
        await update.message.reply_text("Sizda hali jamg'armalar yo'q.", reply_markup=keyboard)
        return

    msg = "🎯 **SIZNIG JAMG'ARMALARINGIZ:**\n\n"
    buttons = []
    for s_id, title, target, current in savings:
        percent = (current / target) * 100 if target > 0 else 0
        msg += f"📌 **{title}**\n💰 Yig'ilgan: {current:,.0f} / {target:,.0f} so'm ({percent:.1f}%)\n\n"
        buttons.append([InlineKeyboardButton(f"⚙️ {title}", callback_data=f"manage_saving_{s_id}")])

    buttons.append([InlineKeyboardButton("➕ Yangi jamg'arma qo'shish", callback_data="add_saving")])
    await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")

async def start_add_saving(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Jamg'arma maqsadi nima?:")
    track_message(context, query.message.message_id)
    return SAVING_TITLE

async def process_saving_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track_message(context, update.message.message_id)
    context.user_data['saving_title'] = update.message.text
    msg = await update.message.reply_text("Qancha pul yig'ish kerak:")
    track_message(context, msg.message_id)
    return SAVING_TARGET

async def process_saving_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track_message(context, update.message.message_id)
    try:
        target = float(update.message.text)
        if target <= 0:
            msg = await update.message.reply_text("Iltimos, 0 dan katta summa kiriting.")
            track_message(context, msg.message_id)
            return SAVING_TARGET

        user_id = update.effective_user.id
        title = context.user_data['saving_title']

        conn = sqlite3.connect('finance_bot.db')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO savings (user_id, title, target_amount) VALUES (?, ?, ?)", (user_id, title, target))
        conn.commit()
        conn.close()

        await clear_messages(update, context)
        await update.message.reply_text(f"✅ '{title}' jamg'armasi yaratildi!", reply_markup=main_keyboard())
    except ValueError:
        msg = await update.message.reply_text("Iltimos, summani raqamlarda kiriting.")
        track_message(context, msg.message_id)
        return SAVING_TARGET
    return ConversationHandler.END

async def start_manage_saving(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    s_id = int(query.data.split("_")[2])
    context.user_data['active_saving_id'] = s_id

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Balansni to'ldirish", callback_data="deposit_saving")],
        [InlineKeyboardButton("➖ Balansdan olish", callback_data="withdraw_saving")],
        [InlineKeyboardButton("❌ O'chirish", callback_data="delete_saving")]
    ])
    await query.edit_message_text("Amalni tanlang:", reply_markup=keyboard)

async def handle_saving_manage_actions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data
    s_id = context.user_data.get('active_saving_id')

    if action == "delete_saving":
        conn = sqlite3.connect('finance_bot.db')
        cursor = conn.cursor()
        cursor.execute("DELETE FROM savings WHERE id = ?", (s_id,))
        conn.commit()
        conn.close()
        await query.edit_message_text("🗑 Jamg'arma o'chirildi.")
        return ConversationHandler.END
    elif action in ["deposit_saving", "withdraw_saving"]:
        context.user_data['saving_action_type'] = action
        await query.edit_message_text("Summani kiriting:")
        track_message(context, query.message.message_id)
        return SAVING_AMOUNT

async def process_saving_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track_message(context, update.message.message_id)
    try:
        amount = float(update.message.text)
        if amount <= 0:
            msg = await update.message.reply_text("Iltimos, 0 dan katta summa kiriting.")
            track_message(context, msg.message_id)
            return SAVING_AMOUNT

        s_id = context.user_data.get('active_saving_id')
        action = context.user_data.get('saving_action_type')

        conn = sqlite3.connect('finance_bot.db')
        cursor = conn.cursor()
        cursor.execute("SELECT title, target_amount, current_amount FROM savings WHERE id = ?", (s_id,))
        row = cursor.fetchone()

        if not row:
            conn.close()
            await clear_messages(update, context)
            await update.message.reply_text("Jamg'arma topilmadi.", reply_markup=main_keyboard())
            return ConversationHandler.END

        title, target, old_current = row

        if action == "deposit_saving":
            new_current = old_current + amount
        else:
            new_current = old_current - amount

        cursor.execute("UPDATE savings SET current_amount = ? WHERE id = ?", (new_current, s_id))
        conn.commit()
        conn.close()

        await clear_messages(update, context)

        percent = (new_current / target) * 100 if target > 0 else 0
        msg = f"✅ '{title}' jamg'armasi yangilandi!\n💰 Hozirgi balans: {new_current:,.0f} / {target:,.0f} so'm ({percent:.1f}%)"
        await update.message.reply_text(msg, reply_markup=main_keyboard())

        # MAQSADGA ERISHILGANDA BILDIRISHNOMA
        if action == "deposit_saving" and old_current < target and new_current >= target:
            congratulation_msg = (
                f"🎉 **TABRIKLAYMIZ! FAXRLANSA BO'LADI!** 🥳\n\n"
                f"🎯 Siz **'{title}'** maqsadingiz uchun belgilangan **{target:,.0f} so'm** summani to'liq yig'ib bo'ldingiz!\n\n"
                f"Moliyaviy intizomingiz tahsinga loyiq. "
                f"Maqsadingiz sari qo'yilgan yana bir katta qadam muborak bo'lsin! 🚀"
            )
            await update.message.reply_text(congratulation_msg, parse_mode="Markdown")

    except ValueError:
        msg = await update.message.reply_text("Iltimos, faqat raqam kiriting.")
        track_message(context, msg.message_id)
        return SAVING_AMOUNT
        
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await clear_messages(update, context)
    await update.message.reply_text("Amal bekor qilindi.", reply_markup=main_keyboard())
    return ConversationHandler.END

def main():
    # TOKENINGIZNI SHU YERGA QO'YING:
    app = ApplicationBuilder().token("8496042584:AAFpQAwQ9KCxxob7SujeYmjURJXDDUyoVTk").build()

    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex('^📥 Kirim$'), start_kirim),
            MessageHandler(filters.Regex('^📤 Chiqim$'), start_chiqim),
            MessageHandler(filters.Regex('^🤝 Qarz olish$'), start_debt_get),
            MessageHandler(filters.Regex('^💸 Qarz berish$'), start_debt_give),
            CallbackQueryHandler(start_add_saving, pattern="^add_saving$"),
            CallbackQueryHandler(handle_saving_manage_actions, pattern="^(deposit_saving|withdraw_saving|delete_saving)$"),
            CallbackQueryHandler(handle_debt_callback, pattern="^(close_|extend_)")
        ],
        states={
            KIRIM: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_kirim)],
            CHIQIM: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_chiqim)],
            DEBT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_debt_name)],
            DEBT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_debt_amount)],
            DEBT_PERIOD: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_debt_period)],
            DEBT_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_debt_phone)],
            EXTEND_PERIOD: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_extend_period)],
            SAVING_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_saving_title)],
            SAVING_TARGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_saving_target)],
            SAVING_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_saving_amount)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Regex('^💳 Balans$'), show_balance))
    app.add_handler(MessageHandler(filters.Regex('^📋 Qarzlar ro\'yxati$'), list_debts))
    app.add_handler(MessageHandler(filters.Regex('^🎯 Jamg\'armalar$'), show_savings))
    app.add_handler(CallbackQueryHandler(start_manage_saving, pattern="^manage_saving_"))
    app.add_handler(conv_handler)

    print("Bot ishga tushdi...")
    app.run_polling()

if __name__ == '__main__':
    main()