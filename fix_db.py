import sqlite3

# Bazangiz fayli nomi (masalan, database.db yoki moliya.db)
conn = sqlite3.connect("finance_bot.db")  # <-- bu yerga o'zingizning .db faylingiz nomini yozing
cursor = conn.cursor()

try:
    cursor.execute("ALTER TABLE debts ADD COLUMN type TEXT")
    conn.commit()
    print("Muvaffaqiyatli: 'type' ustuni 'debts' jadvaliga qo'shildi!")
except sqlite3.OperationalError as e:
    print(f"Eslatma yoki xato: {e}")

conn.close()