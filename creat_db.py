import logging
import aiosqlite
from data.connection import get_connection, close_connection


async def init_db():
    logging.info("Initializing database")
    conn = await get_connection()
    conn.row_factory = aiosqlite.Row
    try:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                chat_id INTEGER PRIMARY KEY,
                welcome_message TEXT,
                auto_accept_enabled BOOLEAN DEFAULT 0,
                leave_message TEXT,
                channel_id INTEGER,
                admins TEXT,
                start_message TEXT,
                welcome_message_photo_id TEXT,
                is_admin BOOLEAN DEFAULT 0,
                username TEXT
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY
            )
        """)
        await conn.commit()
        logging.info("Database initialized successfully ✅")
    except Exception as e:
        logging.error(f"Error initializing database: {e}")
    finally:
        await close_connection(conn)

