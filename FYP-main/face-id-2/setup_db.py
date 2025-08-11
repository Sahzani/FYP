import sqlite3

def setup_database():
    with open('setup_attendance.sql', 'r') as f:
        sql_script = f.read()

    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.executescript(sql_script)
    conn.commit()
    conn.close()
    print("Database setup complete.")

if __name__ == '__main__':
    setup_database()
