# test_db_connection.py

from database import connect_db

def test_connection():
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT 1")
    result = cursor.fetchone()
    print(f"Database test result: {result}")
    cursor.close()
    conn.close()

def test_player_registration(user_id):
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM players WHERE telegram_id = %s", (user_id,))
    player = cursor.fetchone()
    if player:
        print(f"User {user_id} is registered.")
    else:
        print(f"User {user_id} is not registered.")
    cursor.close()
    conn.close()
    
if __name__ == "__main__":
    test_connection()
    test_player_registration('gelomipt')
