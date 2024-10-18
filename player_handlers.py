from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from database import (
    connect_db,
    get_player_by_nickname
    )
from utils import is_registered_player, format_timedelta
import logging
import datetime


#register for game
async def register_for_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id

        # Fetch the list of available games from the database
        conn = connect_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, event_date, start_time, venue FROM schedule WHERE event_date >= CURDATE() ORDER BY event_date ASC")
        games = cursor.fetchall()
        cursor.close()
        conn.close()

        if not games:
            await update.message.reply_text("There are no upcoming games available for registration.")
            return

        # Build inline keyboard with list of games
        keyboard = []
        for game in games:
            game_id = game['id']
            event_date = game['event_date']
            start_time = format_timedelta(game['start_time'])
            venue = game['venue']
            button_text = f"{event_date} at {start_time} at {venue}"
            callback_data = f"select_game_{game_id}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Please select a game to register for:", reply_markup=reply_markup)

    except Exception as e:
        logger.exception("Error in register_for_game")
        await update.message.reply_text("An error occurred while fetching games. Please try again later.")

#handle game selection
async def handle_game_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.exception("starting registeration for game")
    query = update.callback_query
    await query.answer()

    try:
        user_id = update.effective_user.id
        data = query.data  # e.g., 'select_game_123'
        game_id = int(data.split('_')[2])

        # Insert registration into the database
        conn = connect_db()
        cursor = conn.cursor()
        
        # Check if the user is already registered for this game
        cursor.execute("SELECT * FROM registrations WHERE game_id = %s AND player_id = %s", (game_id, user_id))
        existing_registration = cursor.fetchone()
        if existing_registration:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="You are already registered for this game."
            )
            cursor.close()
            conn.close()
            return

        # Insert registration into the database
        cursor.execute("INSERT INTO registrations (game_id, player_id) VALUES (%s, %s)", (game_id, user_id))
        conn.commit()
        cursor.close()
        conn.close()

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="You have been registered for the game successfully!"
        )
        logger.info(f"User {user_id} registered for game {game_id}")
    except Exception as e:
        logger.exception("Error in handle_game_selection")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="An error occurred during registration. Please try again later."
        )


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

    cursor.execute("SELECT id, event_date, start_time, venue FROM schedule WHERE finished IS NULL")
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
        cursor.execute("INSERT INTO registrations (player_id, game_id, confirmed, waiting) VALUES (%s, %s, %s, %s)",
                       (player_id, game_id, False, False))
        conn.commit()
        await query.edit_message_text("You have been registered for the game. Please confirm your registration in 'Confirm Registration for the Game' option.")
    else:
        # Add the player to the waiting list
        cursor.execute("INSERT INTO registrations (player_id, game_id, confirmed, waiting) VALUES (%s, %s, %s, %s)",
                       (player_id, game_id, False, True))
        conn.commit()
        await query.edit_message_text("The game is currently full. You have been added to the waiting list.")
    
    cursor.close()
    conn.close()

#List Unconfirmed Registrations
async def list_unconfirmed_registrations(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        WHERE r.player_id = %s AND r.confirmed = FALSE
    """, (player_id,))
    registrations = cursor.fetchall()
    cursor.close()
    conn.close()

    if not registrations:
        await update.message.reply_text("You have no unconfirmed registrations.")
        return

    buttons = []
    for reg in registrations:
        reg_id = reg[0]
        event_date = reg[1]
        start_time = reg[2]
        venue = reg[3]
        button_text = f"{event_date} at {start_time} - {venue}"
        buttons.append([InlineKeyboardButton(button_text, callback_data=f"confirm_registration_{reg_id}")])

    reply_markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text("Select a registration to confirm:", reply_markup=reply_markup)

#Handle Confirmation
async def handle_confirm_registration_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    # Confirm the registration
    cursor.execute("UPDATE registrations SET confirmed = TRUE WHERE id = %s AND player_id = %s", (reg_id, player_id))
    conn.commit()
    cursor.close()
    conn.close()

    await query.edit_message_text("Your registration has been confirmed.")

#Display All Registrations
async def view_registrations(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nickname = update.message.from_user.username

    # Check if the player is registered
    conn = connect_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id FROM players WHERE nickname = %s", (nickname,))
    player = cursor.fetchone()
    if not player:
        await update.message.reply_text("You are not registered.")
        cursor.close()
        conn.close()
        return
    player_id = player['id']

    # Get all registrations
    cursor.execute("""
        SELECT s.event_date, s.start_time, s.venue, r.confirmed, r.waiting
        FROM registrations r
        JOIN schedule s ON r.game_id = s.id
        WHERE r.player_id = %s
    """, (player_id,))
    registrations = cursor.fetchall()
    cursor.close()
    conn.close()

    if not registrations:
        await update.message.reply_text("You have no registrations.")
        return

    message = "Your Registrations:\n"
    for reg in registrations:
        event_date = reg['event_date']
        start_time = reg['start_time']
        venue = reg['venue']
        confirmed = "Confirmed" if reg['confirmed'] else "Unconfirmed"
        waiting = " (Waiting List)" if reg['waiting'] else ""
        message += f"{event_date} at {start_time} - {venue} [{confirmed}{waiting}]\n"

    await update.message.reply_text(message)

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
        WHERE r.player_id = %s AND r.confirmed = FALSE
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

    cursor.close()
    conn.close()

    await query.edit_message_text("Your registration has been canceled.")

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
        WHERE r.player_id = %s AND r.confirmed = TRUE
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
    cursor.execute("UPDATE registrations SET swap_requested = TRUE WHERE id = %s AND player_id = %s AND confirmed = TRUE", (reg_id, player_id))
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
# Other player handlers...