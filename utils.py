import datetime
import logging

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

from database import get_player_by_nickname
from telegram import Update
from telegram.ext import ContextTypes
from config import DEDICATED_CHAT_ID
from database import connect_db
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from constants import States
#from admin_handlers import manage_games_menu


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

async def send_game_status_update(game_id: int, context: ContextTypes.DEFAULT_TYPE):
    
    conn = connect_db()
    cursor = conn.cursor(dictionary=True)  # Use dictionary=True for easier access

    try:
        # Fetch game details
        cursor.execute("""
            SELECT event_date, start_time, end_time, venue, capacity
            FROM schedule
            WHERE id = %s
        """, (game_id,))
        game = cursor.fetchone()

        if not game:
            logger.error(f"Game with id {game_id} not found.")
            return 

        # Fetch registered players
        cursor.execute("""
            SELECT p.name, r.is_confirmed
            FROM registrations r
            JOIN players p ON r.player_id = p.id
            WHERE r.game_id = %s
            ORDER BY r.registration_time ASC
        """, (game_id,))
        players = cursor.fetchall()

        # Prepare the message
        start_time_formatted = format_timedelta(game['start_time'])
        end_time_formatted = format_timedelta(game['end_time'])

        message = (
            f"Game at {game['venue']} on {game['event_date']} starting at {game['start_time']} "
            f"ending at {game['end_time']} for {game['capacity']} players.\n"
        )

        # Split players into main list and waiting list
        capacity = game['capacity']
        main_list = players[:capacity]
        waiting_list = players[capacity:]

        def format_player_list(player_list, start_number=1):
            lines = []
            for idx, player in enumerate(player_list, start=start_number):
                status = 'C' if player['is_confirmed'] else 'R'
                lines.append(f"#{idx} {player['name']} {status}")
            return "\n".join(lines)

        # Main list
        if main_list:
            message += "\nMain List:\n"
            message += format_player_list(main_list)

        # Waiting list
        if waiting_list:
            message += "\n\nWaiting List:\n"
            message += format_player_list(waiting_list, start_number=capacity + 1)

        # Send the message
#        await context.bot.send_message(chat_id=DEDICATED_CHAT_ID, text=message)
        await send_update_to_public_chat(context, public_chat_id=DEDICATED_CHAT_ID, message_text=message)    

#    except Exception as e:
#        logger.exception("Error sending game status update.")
    finally:
        cursor.close()
        conn.close()

async def update_finished_games():
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
        cursor.execute("""
            SELECT id, 
                   event_date AS event_date_str, 
                   start_time AS start_time_str, 
                   end_time AS end_time_str, 
                   venue, 
                   capacity
            FROM schedule 
            WHERE id = %s
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
                   event_date AS event_date_str, 
                   start_time AS start_time_str, 
                   venue
                   capacity
            FROM schedule 
            WHERE announced = 0
               AND TIMESTAMP(event_date, start_time) BETWEEN %s AND %s
        """, (time_window_start, time_window_end))
        games = cursor.fetchall()

        if not games:
            logger.info("No games to announce at this time.")
            return States.GAME_ACTION

        for game in games:
            game_id = game['id']
            event_date = game['event_date_str']
            start_time = game['start_time_str']
            venue = game['venue']
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
#            await application.bot.send_message(chat_id=CHAT_ID, text=message, parse_mode='Markdown')
            await send_update_to_public_chat(context, public_chat_id=DEDICATED_CHAT_ID, message_text=message)    
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

async def announce_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Announce the selected game and mark it as announced."""
#    query = update.callback_query
#    await query.answer()
    game_id = context.user_data['selected_game_id']

#    game_id = context.user_data.get('selected_game_id')
    if not game_id:
        await query.edit_message_text("No game selected for announcement.")
        return States.GAME_ACTION

    try:
        conn = connect_db()
        cursor = conn.cursor(dictionary=True)

        # Fetch game details
        cursor.execute("""
            SELECT event_date, start_time, end_time, venue, capacity, announced
            FROM schedule
            WHERE id = %s
        """, (game_id,))
        game = cursor.fetchone()
        
        if not game:
            await query.edit_message_text("Game not found.")
            cursor.close()
            conn.close()
            return States.GAME_ACTION

        # Ensure game has not already been announced
    #    if game['announced']:
    #        await query.edit_message_text("This game has already been announced.")
    #        cursor.close()
    #        conn.close()
    #        return

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

        # Format announcement message
        announcement_message = (
            f"📢 **Upcoming Game Announcement** 📢\n\n"
            f"📍 **Venue**: {game['venue']}\n"
            f"📅 **Date**: {game['event_date']}\n"
            f"🕒 **Time**: {game['start_time']} - {game['end_time']}\n"
            f"👥 **Capacity**: {game['capacity']} players\n"
            f"👤 **Registered**: {main_count} ({waiting_count} in waiting list)"
        )

        # Send the announcement to the specified chat
    #    try:
#        await context.bot.send_message(chat_id=DEDICATED_CHAT_ID, text=announcement_message, parse_mode='Markdown')
        await send_update_to_public_chat(context, public_chat_id=DEDICATED_CHAT_ID, message_text=announcement_message)    
        
        if main_count > 0:
            await send_game_status_update (game_id, context)
        return States.GAME_ACTION
        
        await query.edit_message_text("Game has been announced.")

        await manage_games_menu(update, context)
        logger.info(f"Returning to state: {SELECT_GAME}")
        return States.SELECT_GAME  # Ensure SELECT_GAME is a defined state
        
    except Exception as e:
        logger.exception("Failed to send announcement")
        await update.message.reply_text("Failed to announce game. Please try again.")
        return States.GAME_ACTION
    
async def unhandled_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.warning(f"Unhandled callback data: {update.callback_query.data}")
    await update.callback_query.answer("This action is not available.")
    
async def handle_unhandled_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("Sorry, I didn't understand that action.")
    return States.GAME_ACTIONS
    
async def send_update_to_public_chat(context, public_chat_id, message_text):
    await context.bot.send_message(chat_id=public_chat_id, text=message_text,parse_mode='Markdown')
