import datetime
import logging
import aiomysql  # Removed as it is not accessed
import asyncio
import locale
import html

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

from database import get_player_by_nickname
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config import DEDICATED_CHAT_ID, ADMIN_USERNAMES
from database import connect_db
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from constants import States

def is_admin(username):
    return username in ADMIN_USERNAMES

def is_registered_player(nickname):
    player = get_player_by_nickname(nickname)
    return player is not None
    
def format_timedelta(td):
    total_seconds = int(td.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}"

async def fallback_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("I'm sorry, I didn't understand that command.")

def update_finished_games():
    conn = connect_db()
    cursor = conn.cursor()
    try:
        # Update games where end time has passed and finished is NULL
        cursor.execute("""
            UPDATE schedule
            SET finished = TRUE
            WHERE finished IS NULL
              AND (event_date < CURDATE()
                   OR (event_date = CURDATE() AND end_time <= CURTIME()))
        """)
        conn.commit()
        logging.info("Finished updating games.")
    except Exception as e:
        logging.exception("Error updating finished games")
    finally:
        cursor.close()
        conn.close()
        
async def get_game_data(game_id):
    conn = connect_db()
    cursor = conn.cursor(dictionary=True)
    try:
        # Using explicit table prefixes to avoid ambiguity and get venue information
        cursor.execute("""
            SELECT schedule.*, venue.name AS venue_name
            FROM schedule
            LEFT JOIN venue AS venue ON schedule.venue_id = venue.id
            WHERE schedule.id = %s
        """, (game_id,))
        game = cursor.fetchone()
        return game
    except Exception as e:
        logger.exception("Error fetching game data")
        return None
    finally:
        cursor.close()
        conn.close()
        
async def announce_upcoming_games(application):
    logger.info("Running announce_upcoming_games")
    conn = connect_db()
    cursor = conn.cursor(dictionary=True)
    try:
        # Calculate the datetime 48 hours from now
        now = datetime.datetime.now()
        target_time = now + datetime.timedelta(hours=48)
        
        # Calculate the time window
        time_window_start = target_time - datetime.timedelta(minutes=30)
        time_window_end = target_time + datetime.timedelta(minutes=30)

        # Format the target date and time
#        target_date = target_time.date()
#        target_time_str = target_time.strftime('%H:%M:%S')

        # Fetch games starting in 48 hours that haven't been announced
        cursor.execute("""
            SELECT id, 
                   s.event_date AS event_date_str, 
                   s.start_time AS start_time_str, 
                   v.name as venue_name,
                   v.url as venue_url,
                   s.capacity
            FROM schedule s
            JOIN venue v ON s.venue_id = v.id 
            WHERE s.announced = 0
               AND TIMESTAMP(s.event_date, s.start_time) BETWEEN %s AND %s
        """, (time_window_start, time_window_end))
        games = cursor.fetchall()

        if not games:
            logger.info("No games to announce at this time.")
            return 

        for game in games:
            game_id = game['id']
            event_date = game['event_date_str']
            start_time = game['start_time_str']
            venue = game['venue_name']
            capacity = game['capacity']

            # Build the announcement message
            message = (
                f"📢 **Upcoming Game Alert!** 📢\n\n"
                f"🏀 Game on *{event_date}* at *{start_time}* in *{venue}* for {capacity} players.\n"
                f"Don't forget to register and confirm your registration not later then 24 hours before game start!"
            )

            # Send the announcement to the chat
            # Replace CHAT_ID with your actual chat ID
#            CHAT_ID = DEDICATED_CHAT_ID
            await application.bot.send_message(chat_id=DEDICATED_CHAT_ID, text=message, parse_mode='Markdown')
#            await send_update_to_public_chat(context, public_chat_id=DEDICATED_CHAT_ID, message_text=message)    
            # Update the 'announced' attribute in the database
            cursor.execute("""
                UPDATE schedule SET announced = 1 WHERE id = %s
            """, (game_id,))
            conn.commit()

            logger.info(f"Announced game {game_id}")
    except Exception as e:
        logger.exception("Error in announce_upcoming_games")
    finally:
        cursor.close()
        conn.close()
    
async def unhandled_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.warning(f"Unhandled callback data: {update.callback_query.data}")
    await update.callback_query.answer("This action is not available.")
    
async def handle_unhandled_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("Sorry, I didn't understand that action.")
    return States.GAME_ACTIONS
    
async def send_update_to_public_chat(context, public_chat_id, message_text):
    logger.info(f"Sending update to public chat {public_chat_id}")
    logger.info(f"Message: {message_text}")
    await context.bot.send_message(chat_id=public_chat_id, text=message_text,parse_mode='HTML')

def is_private_chat(update: Update) -> bool:
    return update.effective_chat.type == 'private'

# Function to get the day of the week in Russian
async def get_day_of_week_in_russian(date):
    try:
        locale.setlocale(locale.LC_TIME, 'ru_RU.UTF-8')  # Common locale format for Russian
        return date.strftime('%A') 
    except locale.Error:
        logger.info("Russian locale not available on this system. Defaulting to English.")
        return date.strftime('%A') 
    
def day_of_week_in_russian(date):

    days_of_week = {
        0: 'Понедельник',
        1: 'Вторник',
        2: 'Среду',
        3: 'Четверг',
        4: 'Пятницу',
        5: 'Субботу',
        6: 'Воскресенье'
    }
    return days_of_week[date.weekday()]

async def shutdown(application):
    await application.stop()
    await application.shutdown()

def is_private_chat_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if update.callback_query and update.callback_query.message:
        return update.callback_query.message.chat.type == 'private'
    return False

def escape_html(text):
    return html.escape(text)

async def announce_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Announcing game")
    from admin_handlers import manage_games_menu
    """Announce the selected game and mark it as announced."""
    query = update.callback_query
    await query.answer()
    game_id = context.user_data.get('selected_game_id')

    if not game_id:
        await query.edit_message_text("Игра не выбрана.")
        return 

    try:
        conn = connect_db()
        cursor = conn.cursor(dictionary=True)

        # Fetch game details
        cursor.execute("""
            SELECT s.event_date, s.start_time, s.end_time, v.name as venue_name, s.capacity, s.announced, v.url as venue_url
            FROM schedule s
            JOIN venue v ON s.venue_id = v.id
            WHERE s.id = %s
        """, (game_id,))
        game = cursor.fetchone()
        
        if not game:
            await query.edit_message_text("Игра не найдена.")
            cursor.close()
            conn.close()
            return 

        # Fetch registration summary
        cursor.execute("""
            SELECT COUNT(CASE WHEN waiting = FALSE THEN 1 END) AS main_count,
                   COUNT(CASE WHEN waiting = TRUE THEN 1 END) AS waiting_count
            FROM registrations
            WHERE game_id = %s
        """, (game_id,))
        registration = cursor.fetchone()
        main_count = registration['main_count']
        waiting_count = registration['waiting_count']
        
        # Mark the game as announced
        cursor.execute("UPDATE schedule SET announced = TRUE WHERE id = %s", (game_id,))
        conn.commit()
        
        cursor.close()
        conn.close()

        week_day = day_of_week_in_russian(game['event_date'])
        logger.info(f"Announcing game at {week_day}")

        # Escape HTML special characters in game details
        venue = escape_html(game['venue_name'])
        event_date = escape_html(str(game['event_date']))
        start_time = escape_html(str(game['start_time'])[:-3])
        end_time = escape_html(str(game['end_time'])[:-3])
        capacity = escape_html(str(game['capacity']))
        main_count_str = escape_html(str(main_count))
        waiting_count_str = escape_html(str(waiting_count))
        game_url = game['venue_url'] if game['venue_url'] and game['venue_url'].lower() != "нет" else None

        # Format announcement message
        announcement_message = (
            f"📢<b>Анонс игры в {week_day}!!!</b>📢\n\n"
            f"Записывайтесь на игру в {week_day} {event_date}\n\n"
            f"📍 Место проведения: {venue}\n"
            f"📅 Дата: {event_date}\n"
            f"🕒 Время: {start_time} - {end_time}\n"
            f"👥 Количество мест: {capacity}\n"
            f"👤 Зарегистрировано: {main_count_str}\n"
            f"\U000023F3 Лист ожидания: {waiting_count_str}\n"
        )

        # Add URL if it exists
        if game_url:
            announcement_message += f"🌐 <a href='{escape_html(game_url)}'>Локация</a>\n"

        # Send the announcement to the specified chat
        await send_update_to_public_chat(context, public_chat_id=DEDICATED_CHAT_ID, message_text=announcement_message)

        if main_count > 0:
            await send_game_status_update(game_id, context)

        await query.edit_message_text("Игра была анонсирована.")
        await manage_games_menu(update, context)

        logger.info(f"Returning to state: SELECT_GAME") 
        
    except Exception as e:
        logger.exception("Failed to send announcement")
        await query.edit_message_text("Не удалось анонсировать игру. Пожалуйста, попробуйте снова.")

def escape_html(text):
    if text is None:
        return ""
    return html.escape(text)

async def send_game_status_update(game_id: int, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Sending game status update for game {game_id}.")
    conn = connect_db()
    cursor = conn.cursor(dictionary=True)

    try:
        # Fetch game details
        cursor.execute("""
            SELECT s.event_date, s.start_time, s.end_time, v.name as venue_name, s.capacity, v.url as venue_url
            FROM schedule s
            JOIN venue v ON s.venue_id = v.id           
            WHERE s.id = %s
        """, (game_id,))
        game = cursor.fetchone()

        if not game:
            logger.error(f"Game with id {game_id} not found.")
            return 

        # Fetch registered players
        cursor.execute("""
            SELECT p.name, p.nickname, p.level, p.chat_id, r.alias, r.is_confirmed
            FROM registrations r
            JOIN players p ON r.player_id = p.id
            WHERE r.game_id = %s
            ORDER BY r.registration_time ASC
        """, (game_id,))
        players = cursor.fetchall()
        capacity_int = int(game['capacity'])
        main_count = players[:capacity_int]
        waiting_count = players[capacity_int:]

        # Escape any HTML special characters
        venue = escape_html(game['venue_name'])
        event_date = escape_html(str(game['event_date']))
        start_time = escape_html(str(game['start_time'])[:-3])
        end_time = escape_html(str(game['end_time'])[:-3])
        capacity = escape_html(str(game['capacity']))
        game_url = game['venue_url'] if game['venue_url'] and game['venue_url'].lower() != "нет" else None

        # Prepare the message
        week_day = day_of_week_in_russian(game['event_date'])
        message = (
            f"📢<b>Игра в {week_day}!!!</b> 📢\n\n"
            f"Записывайтесь на игру в {week_day} {event_date}\n\n"
            f"📍 Место проведения: {venue}\n"
            f"📅 Дата: {event_date}\n"
            f"🕒 Время: {start_time} - {end_time}\n"
            f"👥 Количество мест: {capacity}\n"
            f"👤 Зарегистрировано: {len(main_count)} ({len(waiting_count)} в листе ожидания)\n"
        )

        # Add URL if it exists
        if game_url:
            # Use proper anchor tag if adding hyperlink, otherwise just include the URL as plain text
            message += f"🔗 <a href='{escape_html(game_url)}'>Расположение клуба</a>\n\n"

        # Split players into main list and waiting list
        main_list = players[:capacity_int]
        waiting_list = players[capacity_int:]

        def format_player_list(player_list, start_number=1):
            lines = []
            for idx, player in enumerate(player_list, start=start_number):
                status = '✅' if player['is_confirmed'] else '❌'
                lines.append(f"#{idx}. {escape_html(player['name'])} {escape_html(player['alias']) or ''} "
                             f"{escape_html(player['level'])} @{escape_html(player['nickname'])} {status}")
            return "\n".join(lines)

        # Main list
        if main_list:
            message += "\nОсновной состав:\n"
            message += format_player_list(main_list)

        # Waiting list
        if waiting_list:
            message += "\n\nЛист ожидания:\n"
            message += format_player_list(waiting_list, start_number=capacity_int + 1)

        # Send the message
        await send_update_to_public_chat(context, public_chat_id=DEDICATED_CHAT_ID, message_text=message)

    except Exception as e:
        logger.exception("Error sending game status update.")
    finally:
        cursor.close()
        conn.close()

async def list_venues(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Connect to the database
    conn = connect_db()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Fetch all venues
        cursor.execute("SELECT id, name FROM venue")
        venues = cursor.fetchall()

        if not venues:
            # Check if it's a callback query or a message update
            if update.callback_query:
                await update.callback_query.message.reply_text("There are no venues available. Please add venues before creating or editing a game.")
            else:
                await update.message.reply_text("There are no venues available. Please add venues before creating or editing a game.")
            return

        # Create buttons for each venue
        buttons = [
            [InlineKeyboardButton(venue['name'], callback_data=f"select_venue_{venue['id']}")]
            for venue in venues
        ]
        
        reply_markup = InlineKeyboardMarkup(buttons)
        # Send message depending on the type of update
        if update.callback_query:
            await update.callback_query.message.reply_text("Выбери клуб где будет проходить игра:", reply_markup=reply_markup)
        else:
            await update.message.reply_text("Выбери клуб где будет проходить игра:", reply_markup=reply_markup)
    
    except Exception as e:
        logger.exception("Error fetching venues")
        if update.callback_query:
            await update.callback_query.message.reply_text("An error occurred while fetching venues. Please try again later.")
        else:
            await update.message.reply_text("An error occurred while fetching venues. Please try again later.")
    
    finally:
        cursor.close()
        conn.close()