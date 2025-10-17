import os
import aiosqlite
import logging

DB_PATH = os.path.join('data', 'database.db')

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

async def get_connection():
    logging.info("Creating new database connection")
    conn = await aiosqlite.connect(DB_PATH, timeout=10, isolation_level=None)
    conn.row_factory = aiosqlite.Row
    return conn

async def close_connection(conn):
    logging.info("Closing database connection")
    try:
        await conn.close()
    except Exception as e:
        logging.error(f"Error closing connection: {e}")