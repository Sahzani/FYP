# reset_db.py
import sqlite3

def reset_attendance_table():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("DELETE FROM attendance")  # Remove all rows
    conn.commit()
    conn.close()
    print("All attendance records have been cleared.")

if __name__ == '__main__':
    reset_attendance_table()