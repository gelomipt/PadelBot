import logging
import datetime
import mysql.connector

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from database import (
    connect_db,
    get_player_by_nickname
    )
from utils import (
    is_registered_player, 
    format_timedelta,
    send_game_status_update
    )

PLAYER_REGISTER_FOR_GAME, PLAYER_GAME_SELECTION = range(2)
GAME_FOR_REGISTRATION_CONFIRMATION_SELECTION = range(1)
GAME_FOR_CANCELLATION_CONFIRMATION_SELECTION = range(1)

logger = logging.getLogger(__name__)

#register for game
async def register_for_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        await query.answer()  # Acknowledge the callback
        # Fetch the list of available games from the database
        conn = connect_db()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT id, event_date, start_time, venue, capacity 
            FROM schedule 
            WHERE announced = TRUE 
                AND finished = FALSE           
            ORDER BY event_date ASC, start_time ASC
        """)
        games = cursor.fetchall()       

        if not games:
            await query.edit_message_text("There are no upcoming games available for registration.")
            return

        # Build inline keyboard with list of games
        keyboard = []
        for game in games:
            game_id = game['id']
            event_date = game['event_date']
            start_time = format_timedelta(game['start_time'])
            venue = game['venue']
            capacity = game['capacity']

            cursor.execute("""
                SELECT COUNT(CASE WHEN waiting = FALSE THEN 1 END) AS main_count,
                    COUNT(CASE WHEN waiting = TRUE THEN 1 END) AS waiting_count
                FROM registrations
                WHERE game_id = %s
            """, (game_id,))
            registration = cursor.fetchone()
            main_count = registration['main_count']  

            # Format event_date and start_time if necessary
            event_date_str = event_date.strftime('%Y-%m-%d') if isinstance(event_date, datetime.date) else str(event_date)
            start_time_str = start_time.strftime('%H:%M') if isinstance(start_time, datetime.time) else str(start_time)
            
            button_text = f"{event_date_str} в {start_time_str} в {venue}. {main_count} из {capacity}"
            callback_data = f"select_game_{game_id}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        logger.info("register_game_function called")
        
        await query.edit_message_text("Выбери игру для предварительной регистрации:", reply_markup=reply_markup)

    except Exception as e:
        logger.exception("Error in register_for_game")
        await update.callback_query.edit_message_text("An error occurred while fetching games. Please try again later.")
        
    finally:
        cursor.close()
        conn.close()
    return PLAYER_GAME_SELECTION

#handle game selection
async def handle_game_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    logger.info("handle_game_selection called")

    telegram_user_id = update.effective_user.id
    game_id = int(query.data.split('_')[-1])

    conn = connect_db()
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("SELECT id FROM players WHERE telegram_id = %s", (telegram_user_id,))
        result = cursor.fetchone()
        
        if result is None:
            await update.effective_chat.send_message("You are not registered as a player. Please register first.")
            return ConversationHandler.END

        player_id = result['id']
        
        # Check if the user is already registered for this game
        cursor.execute("SELECT * FROM registrations WHERE game_id = %s AND player_id = %s", (game_id, player_id))
        existing_registration = cursor.fetchone()
        if existing_registration:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Ты уже зеригистрирован на эту игру."
            )
            return ConversationHandler.END
        logger.info("register_player_logic called")
        # Check the current number of non-waiting registrations
        cursor.execute("SELECT COUNT(*) AS count FROM registrations WHERE game_id = %s AND waiting = FALSE", (game_id,))
        current_count = cursor.fetchone()['count']

        # Get the game's capacity
        cursor.execute("SELECT capacity FROM schedule WHERE id = %s", (game_id,))
        game = cursor.fetchone()
        if not game:
            await query.edit_message_text("Game not found.")
            return ConversationHandler.END
            
        capacity = game['capacity']
        alias = context.user_data.get('alias') if context.user_data.get('alias') else None

        if current_count < capacity:
            # Register the player normally
            cursor.execute("INSERT INTO registrations (player_id, game_id, is_confirmed, waiting, alias) VALUES (%s, %s, %s, %s, %s)",
                    (player_id, game_id, False, False, alias))
            conn.commit()
            await query.edit_message_text("Ты в основном списке. Не забудь подтвердить регистрацию.")
            logger.info(f"User {telegram_user_id} registered for game {game_id} in main list.")
        else:
            # Add the player to the waiting list
            cursor.execute("INSERT INTO registrations (player_id, game_id, is_confirmed, waiting, alias) VALUES (%s, %s, %s, %s, %s)",
                    (player_id, game_id, False, True, alias))
            conn.commit()
            await query.edit_message_text("Игра заполнена. Ты в листе ожидания.")
            logger.info(f"User {telegram_user_id} registered for game {game_id} in waiting list.")
    
        # Send the game status update
        await send_game_status_update(game_id, context)
        
    except Exception as e:
        logger.exception("Error in register_for_game")
        await query.edit_message_text("An error occurred while fetching games. Please try again later.")
        
    finally:
        cursor.close()
        conn.close()
    # Clear the registration progress flag and context data
    context.user_data.clear()   
    return ConversationHandler.END

#List Available Games and Register
async def list_available_games(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nickname = update.message.from_user.username
    logger.info("starting list of available games.")

    # Check if the player is registered
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM players WHERE nickname = %s", (nickname,))
    player = cursor.fetchone()
    if not player:
        await update.message.reply_text("You are not registered. Please register first.")
        cursor.close()
        conn.close()
        return
    player_id = player[0]

    cursor.execute("""
        SELECT id, event_date, start_time, venue 
        FROM schedule 
        WHERE finished IS NULL
        AND announced IS NOT NULL 
        AND (event_date > CURDATE() OR (event_date = CURDATE() AND start_time >= CURTIME()))
        ORDER BY event_date, start_time
    """)
    games = cursor.fetchall()
    cursor.close()
    conn.close()

    if not games:
        await update.message.reply_text("There are no available games to register for.")
        return

    buttons = []
    for game in games:
        game_id = game[0]
        event_date = game[1]
        start_time = game[2]
        venue = game[3]
        button_text = f"{event_date} at {start_time} - {venue}"
        buttons.append([InlineKeyboardButton(button_text, callback_data=f"register_game_{game_id}")])

    reply_markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text("Select a game to register for:", reply_markup=reply_markup)

#Handle Game Selection and Registration
async def handle_register_game_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    nickname = query.from_user.username

    # Check if the player is registered
    conn = connect_db()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT id FROM players WHERE nickname = %s", (nickname,))
        player = cursor.fetchone()
        if not player:
            await query.edit_message_text("You are not registered. Please register first.")
            cursor.close()
            conn.close()
            return
        player_id = player['id']

        game_id = int(data.split('_')[-1])

        # Check if the player is already registered for the game
        cursor.execute("SELECT * FROM registrations WHERE player_id = %s AND game_id = %s", (player_id, game_id))
        registration = cursor.fetchone()
        if registration:
            await query.edit_message_text("You are already registered for this game.")
            cursor.close()
            conn.close()
            return

        # Check the current number of non-waiting registrations
        cursor.execute("SELECT COUNT(*) AS count FROM registrations WHERE game_id = %s AND waiting = FALSE", (game_id,))
        current_count = cursor.fetchone()['count']

        # Get the game's capacity
        cursor.execute("SELECT capacity FROM schedule WHERE id = %s", (game_id,))
        game = cursor.fetchone()
        capacity = game['capacity']

        if current_count < capacity:
            # Register the player normally
            cursor.execute("INSERT INTO registrations (player_id, game_id, is_confirmed, waiting) VALUES (%s, %s, %s, %s)",
                       (player_id, game_id, False, False))
            conn.commit()
            await query.edit_message_text("You have been registered for the game. Please confirm your registration in 'Confirm Registration for the Game' option.")
        else:
            # Add the player to the waiting list
            cursor.execute("INSERT INTO registrations (player_id, game_id, is_confirmed, waiting) VALUES (%s, %s, %s, %s)",
                       (player_id, game_id, False, True))
            conn.commit()
            await query.edit_message_text("The game is currently full. You have been added to the waiting list.")
    
        # Send the game status update
        await send_game_status_update(game_id, context)
    
    except mysql.connector.Error as err:
        logger.exception("Error in handle_game_selection")
        await update.effective_chat.send_message(f"An error occurred: {err}")
    finally:
        cursor.close()
        conn.close()

#List Unconfirmed Registrations
async def list_unconfirmed_registrations(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    logger.info("list_unconfirmed_registrations called")

    nickname = query.from_user.username  # Corrected to use the callback query

    # Check if the player is registered
    conn = connect_db()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT id FROM players WHERE nickname = %s", (nickname,))
        player = cursor.fetchone()
        if not player:
            await query.edit_message_text("Нет регистраций для подтверждения.")
            return ConversationHandler.END
        player_id = player['id']
        logger.info(f"player id {player['id']}")
        # Get unconfirmed registrations
        cursor.execute("""
            SELECT r.id, s.event_date, s.start_time, v.short_name as venue_name, r.waiting, r.alias
            FROM registrations r
            JOIN schedule s ON r.game_id = s.id
            JOIN venues v ON s.venue_id = v.id
            WHERE r.player_id = %s AND r.is_confirmed = FALSE AND s.finished IS NULL
        """, (player_id,))
        registrations = cursor.fetchall()
        logger.info(f"registrations {registrations}")

        if not registrations:
            await query.edit_message_text("Все регистрации подтвержены.")
            return ConversationHandler.END

        buttons = []
        for reg in registrations:
            reg_id = reg['id']
            event_date = reg['event_date']
            start_time = f"{reg['start_time']}"[:-3]
            venue = reg['venue_name']
            waiting_list = reg['waiting']
            alias = reg['alias'] if reg['alias'] else ""
            context.user_data['alias'] = alias
            if waiting_list:
                continue
#                button_text = f"{event_date} at {start_time} - {venue} (Waiting list)"
#                await update.message.reply_text("Подтвердить можно только регистрацию из основного списка.") 
            else:
                button_text = f"{event_date} at {start_time} - {venue}. {alias}"
                buttons.append([InlineKeyboardButton(button_text, callback_data=f"confirm_registration_{reg_id}")])
        if buttons:
            reply_markup = InlineKeyboardMarkup(buttons)
            await query.edit_message_text("Выбери регистрацию для подтверждения:", reply_markup=reply_markup)
        else:
            await query.edit_message_text("Нет доступных регистраций для подтверждения.")

    except Exception as e:
        logger.exception("Error in register_for_game")
        await query.edit_message_text("An error occurred while registering for the game. Please try again later.")
        
    finally:
        cursor.close()
        conn.close()
    return GAME_FOR_REGISTRATION_CONFIRMATION_SELECTION

#Handle Confirmation 
async def handle_confirm_registration_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("handle_confirm_registration_callback called")

    query = update.callback_query
    await query.answer()
    data = query.data
    alias = context.user_data.get('alias') if context.user_data.get('alias') else None

    nickname = query.from_user.username

    # Check if the player is registered
    conn = connect_db()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT id FROM players WHERE nickname = %s", (nickname,))
        player = cursor.fetchone()
        if not player:
            await query.edit_message_text("You are not registered. Please register first.")
            return ConversationHandler.END
        player_id = player['id']

        reg_id = int(data.split('_')[-1])
        logger.info(f"reg_id {reg_id}, player_id {player_id}, alias {alias}")

        # Confirm the registration
        cursor.execute("""
        UPDATE registrations 
        SET is_confirmed = TRUE 
        WHERE id = %s AND player_id = %s
        """, (reg_id, player_id))
        conn.commit()
        
        await update.effective_chat.send_message("Регистрация подтверждена. Ждем на корте!")
    
        # Send the game status update
        cursor.execute("SELECT game_id FROM registrations WHERE id = %s", (reg_id,))
        game = cursor.fetchone()
        if game:
            await send_game_status_update(game['game_id'], context)
    
    except mysql.connector.Error as err:
        logger.exception("Error in handle_game_selection")
        await update.effective_chat.send_message(f"An error occurred: {err}")
    finally:
        cursor.close()
        conn.close()
    return ConversationHandler.END

#Display All Registrations
async def view_registrations(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Connect to the database
    conn = connect_db()
    cursor = conn.cursor(dictionary=True)
        # Get all registrations
    cursor.execute("""
        SELECT p.id
        FROM players p
        WHERE p.telegram_id = %s
    """, (user_id,))
    player = cursor.fetchall()
    player_id = player[0]['id']

    # Get all registrations
    cursor.execute("""
        SELECT s.event_date, s.start_time, s.venue, r.is_confirmed, r.waiting, r.alias
        FROM registrations r
        JOIN schedule s ON r.game_id = s.id
        WHERE r.player_id = %s
    """, (player_id,))
    registrations = cursor.fetchall()
    cursor.close()
    conn.close()

    if not registrations:
        message = "You have no registrations."
    else:
        message = "Your Registrations:\n"
        for reg in registrations:
            event_date = reg['event_date']
            start_time = reg['start_time']
            venue = reg['venue']
            alias = reg['alias'] if reg['alias'] else ""
            confirmed = '✅' if reg['is_confirmed'] else '❌'
#            confirmed = "Подтверждена" if reg['is_confirmed'] else "Не подтверждена"
            waiting = " (Лист ожидания)" if reg['waiting'] else ""
            message += f"{event_date} в {start_time} в {venue} ({alias}) [{confirmed}{waiting}]\n"

    # Check if the update has a message or a callback_query and reply accordingly
    if update.message:
        await update.message.reply_text(message)
    elif update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(message)
    else:
        # If none of these types, use context.bot to send a direct message
        await context.bot.send_message(chat_id=update.effective_user.id, text=message)
    from menu_handlers import show_player_menu 
    await show_player_menu(update, context)

#List Unconfirmed Registrations
async def list_unconfirmed_registrations_for_cancellation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nickname = update.message.from_user.username

    # Check if the player is registered
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM players WHERE nickname = %s", (nickname,))
    player = cursor.fetchone()
    if not player:
        await update.message.reply_text("You are not registered. Please register first.")
        cursor.close()
        conn.close()
        return
    player_id = player[0]

    # Get unconfirmed registrations
    cursor.execute("""
        SELECT r.id, s.event_date, s.start_time, s.venue
        FROM registrations r
        JOIN schedule s ON r.game_id = s.id
        WHERE r.player_id = %s AND r.is_confirmed = FALSE
        AND finished IS NULL
        AND (event_date > CURDATE() OR (event_date = CURDATE() AND start_time >= CURTIME()))
        ORDER BY event_date, start_time
    """, (player_id,))
    registrations = cursor.fetchall()
    cursor.close()
    conn.close()

    if not registrations:
        await update.message.reply_text("You have no unconfirmed registrations to cancel.")
        return

    buttons = []
    for reg in registrations:
        reg_id = reg[0]
        event_date = reg[1]
        start_time = reg[2]
        venue = reg[3]
        button_text = f"{event_date} at {start_time} - {venue}"
        buttons.append([InlineKeyboardButton(button_text, callback_data=f"cancel_registration_{reg_id}")])

    reply_markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text("Select a registration to cancel:", reply_markup=reply_markup)

#Handle Cancellation
async def handle_cancel_registration_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    nickname = query.from_user.username

    # Check if the player is registered
    conn = connect_db()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT id FROM players WHERE nickname = %s", (nickname,))
        player = cursor.fetchone()
        if not player:
            await query.edit_message_text("You are not registered.")
            cursor.close()
            conn.close()
            return
        player_id = player['id']

        reg_id = int(data.split('_')[-1])

        # Get the game ID from the registration
        cursor.execute("SELECT game_id, waiting FROM registrations WHERE id = %s AND player_id = %s", (reg_id, player_id))
        registration = cursor.fetchone()
        if not registration:
            await query.edit_message_text("Registration not found.")
            cursor.close()
            conn.close()
            return

        game_id = registration['game_id']
        was_waiting = registration['waiting']

        # Delete the registration
        cursor.execute("DELETE FROM registrations WHERE id = %s AND player_id = %s", (reg_id, player_id))
        conn.commit()

        if not was_waiting:
            # Check if there are players on the waiting list
            cursor.execute("""
                SELECT id, player_id FROM registrations
                WHERE game_id = %s AND waiting = TRUE
                ORDER BY id ASC LIMIT 1
            """, (game_id,))
            waiting_player = cursor.fetchone()

            if waiting_player:
                # Promote the first player from the waiting list
                cursor.execute("""
                    UPDATE registrations SET waiting = FALSE
                    WHERE id = %s
                """, (waiting_player['id'],))
                conn.commit()

                # Notify the promoted player (optional)
                cursor.execute("SELECT nickname FROM players WHERE id = %s", (waiting_player['player_id'],))
                promoted_nickname = cursor.fetchone()['nickname']

                # Send a message to the promoted player
                try:
                    await context.bot.send_message(chat_id='@' + promoted_nickname, text="A spot has opened up in the game you were waitlisted for. You have been moved to the main registration list. Please confirm your registration.")
                except Exception as e:
                    print(f"Failed to send message to {promoted_nickname}: {e}")

        await query.edit_message_text("Your registration has been canceled.")
        # Send the game status update
        await send_game_status_update(game_id, context)
    
    except mysql.connector.Error as err:
        logger.exception("Error in handle_game_selection")
        await update.effective_chat.send_message(f"An error occurred: {err}")
    finally:
        cursor.close()
        conn.close()

#Request Swap for Confirmed Registration
async def list_confirmed_registrations_for_swap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nickname = update.message.from_user.username

    # Check if the player is registered
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM players WHERE nickname = %s", (nickname,))
    player = cursor.fetchone()
    if not player:
        await update.message.reply_text("You are not registered. Please register first.")
        cursor.close()
        conn.close()
        return
    player_id = player[0]

    # Get confirmed registrations
    cursor.execute("""
        SELECT r.id, s.event_date, s.start_time, s.venue
        FROM registrations r
        JOIN schedule s ON r.game_id = s.id
        WHERE r.player_id = %s AND r.is_confirmed = TRUE
    """, (player_id,))
    registrations = cursor.fetchall()
    cursor.close()
    conn.close()

    if not registrations:
        await update.message.reply_text("You have no confirmed registrations to swap.")
        return

    buttons = []
    for reg in registrations:
        reg_id = reg[0]
        event_date = reg[1]
        start_time = reg[2]
        venue = reg[3]
        button_text = f"{event_date} at {start_time} - {venue}"
        buttons.append([InlineKeyboardButton(button_text, callback_data=f"swap_registration_{reg_id}")])

    reply_markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text("Select a registration to request a swap for:", reply_markup=reply_markup)

#Handle Swap Request
async def handle_swap_registration_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    nickname = query.from_user.username

    # Check if the player is registered
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM players WHERE nickname = %s", (nickname,))
    player = cursor.fetchone()
    if not player:
        await query.edit_message_text("You are not registered. Please register first.")
        cursor.close()
        conn.close()
        return
    player_id = player[0]

    reg_id = int(data.split('_')[-1])

    # Mark the registration as swap requested
    cursor.execute("UPDATE registrations SET swap_requested = TRUE WHERE id = %s AND player_id = %s AND is_confirmed = TRUE", (reg_id, player_id))
    conn.commit()
    cursor.close()
    conn.close()

    await query.edit_message_text("Your swap request has been noted. An admin will contact you if a swap is possible.")

#Handle Registration Steps
async def handle_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    step = context.user_data.get('registration_step')

    if step == 'name':
        context.user_data['name'] = update.message.text
        context.user_data['registration_step'] = 'level'
        await update.message.reply_text("Enter your level (Novice, D-, D, D+, C-, C, C+):")
    elif step == 'level':
        level = update.message.text
        valid_levels = ['Novice', 'D-', 'D', 'D+', 'C-', 'C', 'C+']
        if level in valid_levels:
            name = context.user_data['name']
            nickname = update.message.from_user.username

            conn = connect_db()
            cursor = conn.cursor()
            cursor.execute('''INSERT INTO players (name, nickname, level)
                              VALUES (%s, %s, %s)''',
                           (name, nickname, level))
            conn.commit()
            cursor.close()
            conn.close()

            await update.message.reply_text("You have been registered successfully.")
            context.user_data.clear()
        else:
            await update.message.reply_text("Invalid level. Please enter one of the following: Novice, D-, D, D+, C-, C, C+.")

#Register
async def register_player(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nickname = update.message.from_user.username

    # Check if the player is already registered
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM players WHERE nickname = %s", (nickname,))
    player = cursor.fetchone()
    cursor.close()
    conn.close()

    if player:
        await update.message.reply_text("You are already registered.")
    else:
        context.user_data['registration_step'] = 'name'
        await update.message.reply_text("Please enter your name:")

async def cancel_player_for_game_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Регистрация игрока отменена.")
    context.user_data.clear()
    return ConversationHandler.END
# Other player handlers...
async def cancel_game_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Подтверждение регистрации отменено.")
    context.user_data.clear()
    return ConversationHandler.END