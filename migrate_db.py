from sqlmodel import create_engine, text
from app.database import sqlite_url

engine = create_engine(sqlite_url)

with engine.connect() as connection:
    result = connection.execute(text("PRAGMA table_info(schedule)"))
    columns = [row.name for row in result]
    print(f"Current columns: {columns}")
    
    if "command_id" not in columns:
        print("Adding command_id column...")
        try:
            connection.execute(text("ALTER TABLE schedule ADD COLUMN command_id INTEGER"))
            connection.commit()
            print("Column added successfully.")
        except Exception as e:
            print(f"Error adding column: {e}")
    else:
        print("command_id column already exists.")
