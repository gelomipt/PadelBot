import mysql.connector
import os
from config import DB_USER, DB_PASSWORD, DB_HOST, DB_NAME


DB_CONFIG = {
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST', 'localhost'),
    'database': os.getenv('DB_NAME', 'Padel'),
}
# MySQL Database connection configuration
if not all([DB_USER, DB_PASSWORD, DB_NAME]):
    raise EnvironmentError("Database configuration incomplete in environment variables")
    
def connect_db():
    """Create a connection to the MySQL database."""
    return mysql.connector.connect(**DB_CONFIG)

# Database functions
def get_player_by_nickname(nickname):
    conn = connect_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM players WHERE nickname = %s", (nickname,))
    player = cursor.fetchone()
    cursor.close()
    conn.close()
    return player

async def update_game_attribute(game_id, attribute, new_value):
    conn = connect_db()
    cursor = conn.cursor()
    try:
        # Build the SQL query dynamically
        sql = f"UPDATE schedule SET {attribute} = %s WHERE id = %s"
        cursor.execute(sql, (new_value, game_id))
        conn.commit()
        return True
    except Exception as e:
        logger.exception("Error updating game attribute")
        return False
    finally:
        cursor.close()
        conn.close()
# Other database functions...