# def markAttendance(name):
#     conn = sqlite3.connect('database.db')
#     c = conn.cursor()

#     # Optional: Check if already marked today (avoid duplicates)
#     now = datetime.now()
#     date_today = now.strftime("%Y-%m-%d")
#     timestamp_now = now.strftime("%Y-%m-%d %H:%M:%S")

#     c.execute("SELECT * FROM attendance WHERE name=? AND timestamp LIKE ?", (name, f'{date_today}%'))
#     record = c.fetchone()

#     if not record:
#         c.execute("INSERT INTO attendance (name, timestamp) VALUES (?, ?)", (name, timestamp_now))
#         conn.commit()

#     conn.close()

#     # replace this code with the actual attendance marking logic
#     print(f"Attendance marked for {name} at {timestamp_now}")

#     #and update import code statements
# import sqlite3
#     #update new route
#     @app.route('/view')
# def view_attendance():
#     conn = sqlite3.connect('database.db')
#     c = conn.cursor()
#     c.execute("SELECT * FROM attendance ORDER BY timestamp DESC")
#     data = c.fetchall()
#     conn.close()
#     return render_template('view.html', data=data)

# Replace your current markAttendance in app.py with this:
# import sqlite3  # make sure this is at the top of app.py

# def markAttendance(name):
#     conn = sqlite3.connect('database.db')
#     c = conn.cursor()

#     now = datetime.now()
#     date_today = now.strftime("%Y-%m-%d")
#     timestamp_now = now.strftime("%Y-%m-%d %H:%M:%S")

#     # Prevent duplicate entry for same day
#     c.execute("SELECT * FROM attendance WHERE name=? AND timestamp LIKE ?", (name, f'{date_today}%'))
#     record = c.fetchone()

#     if not record:
#         c.execute("INSERT INTO attendance (name, timestamp) VALUES (?, ?)", (name, timestamp_now))
#         conn.commit()

#     conn.close()

# Check the Call Location
# In your /upload route (in app.py), you're already calling:
# markAttendance(name)

# Add this at the bottom of your app.py (but above the if __name__ == '__main__': line):

# @app.route('/view')
# def view_attendance():
#     conn = sqlite3.connect('database.db')
#     c = conn.cursor()
#     c.execute("SELECT name, timestamp FROM attendance ORDER BY timestamp DESC")
#     records = c.fetchall()
#     conn.close()
#     return render_template('view.html', records=records)

# Data Insertion

# def markAttendance(name):
#     conn = sqlite3.connect('database.db')
#     c = conn.cursor()

#     now = datetime.now()
#     date_today = now.strftime("%Y-%m-%d")
#     timestamp_now = now.strftime("%Y-%m-%d %H:%M:%S")

#     # Avoid duplicate for same person per day
#     c.execute("SELECT * FROM attendance WHERE name=? AND timestamp LIKE ?", (name, f'{date_today}%'))
#     if not c.fetchone():
#         c.execute("INSERT INTO attendance (name, timestamp) VALUES (?, ?)", (name, timestamp_now))
#         conn.commit()

#     conn.close()
