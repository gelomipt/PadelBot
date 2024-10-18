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

# Other database functions...