-- Create the attendance database (SQLite handles this as a file)
-- This part is implicit when using SQLite

-- Drop the table if you want to reset it (optional)
DROP TABLE IF EXISTS attendance;

-- Create a new table for attendance records
CREATE TABLE attendance (
    id INTEGER PRIMARY KEY auto_increment,
    name TEXT NOT NULL,
    timestamp TEXT NOT NULL
);

-- Optional: Index for faster query on date
CREATE INDEX idx_timestamp ON attendance(timestamp);

-- Sample insert (you can delete this after testing)
INSERT INTO attendance (name, timestamp)
VALUES ('JOHN DOE', '2025-07-29 08:15:00');

-- Sample query to view all records
SELECT * FROM attendance;

-- Optional: Get today’s attendance
-- (replace YYYY-MM-DD with today’s date)
SELECT * FROM attendance
WHERE timestamp LIKE '2025-07-29%';
