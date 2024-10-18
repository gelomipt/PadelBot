import os
from dotenv import load_dotenv

load_dotenv(override=True)

TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not TOKEN:
    raise EnvironmentError("TELEGRAM_BOT_TOKEN not set in environment variables")

DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_NAME = os.getenv('DB_NAME', 'Padel')
ADMIN_USERNAMES = ["gelomipt", "tg_anton"]

if not all([DB_USER, DB_PASSWORD, DB_NAME]):
    raise ValueError("Database credentials are not fully set in environment variables")
