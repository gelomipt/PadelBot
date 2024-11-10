from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
import asyncio
import logging
import os
from dotenv import load_dotenv

# Load environment variables from .env file if present
load_dotenv()

TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not TOKEN:
    raise EnvironmentError("TELEGRAM_BOT_TOKEN not set in environment variables")

DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_NAME = os.getenv('DB_NAME', 'Padel')

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)


ADMIN_USERNAMES = ["@gelomipt", "@gelomipt2"]  # Replace with actual admin usernames

# MySQL Database connection configuration
if not all([DB_USER, DB_PASSWORD, DB_NAME]):
    raise EnvironmentError("Database configuration incomplete in environment variables")

DB_CONFIG = {
    'user': DB_USER,
    'password': DB_PASSWORD,
    'host': DB_HOST,
    'database': DB_NAME,
}

def connect_db():
    """Create a connection to the MySQL database."""
    return mysql.connector.connect(**DB_CONFIG)

#Start Command Handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user.username

    # Check if user is admin
    if user in ADMIN_USERNAMES:
        keyboard = [
            [InlineKeyboardButton("Enter as Admin", callback_data='enter_admin')],
            [InlineKeyboardButton("Continue as Player", callback_data='enter_player')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Are you an admin?", reply_markup=reply_markup)
    else:
        await show_player_menu(update, context)

#buttons
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == 'enter_admin':
        await show_admin_menu(query, context)
    elif query.data == 'enter_player':
        await show_player_menu(query, context)
    # Handle other callback data

#Handle Confirmation Response
async def handle_remove_confirmation_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user.username
    if user not in ADMIN_USERNAMES:
        await query.edit_message_text("You do not have permission to remove games.")
        return

    confirmation = query.data.split('_')[-1]
    game_id = context.user_data.get('remove_game_id')

    if confirmation == 'yes':
        # Proceed to remove the game
        conn = connect_db()
        cursor = conn.cursor()

        # Delete registrations associated with the game
        cursor.execute("DELETE FROM registrations WHERE game_id = %s", (game_id,))

        # Delete the game
        cursor.execute("DELETE FROM schedule WHERE id = %s", (game_id,))

        conn.commit()
        cursor.close()
        conn.close()

        await query.edit_message_text("The game has been successfully removed.")

        # Clear the remove game ID from context
        context.user_data.pop('remove_game_id', None)
    else:
        await query.edit_message_text("Game removal canceled.")
        # Clear the remove game ID from context
        context.user_data.pop('remove_game_id', None)

#Remove game function
async def remove_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user.username
    if user not in ADMIN_USERNAMES:
        await update.message.reply_text("You do not have permission to remove games.")
        return

    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, event_date, start_time, venue FROM schedule WHERE finished IS NULL")
    games = cursor.fetchall()
    cursor.close()
    conn.close()

    if not games:
        await update.message.reply_text("There are no unfinished games to remove.")
        return

    buttons = []
    for game in games:
        game_id = game[0]
        event_date = game[1]
        start_time = game[2]
        venue = game[3]
        button_text = f"{game_id}: {venue} on {event_date} at {start_time}"
        buttons.append([InlineKeyboardButton(button_text, callback_data=f"remove_game_{game_id}")])

    reply_markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text("Select a game to remove:", reply_markup=reply_markup)

#handle remove game
async def handle_remove_game_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user.username
    if user not in ADMIN_USERNAMES:
        await query.edit_message_text("You do not have permission to remove games.")
        return

    game_id = int(query.data.split('_')[-1])
    context.user_data['remove_game_id'] = game_id

    # Fetch game details and number of registered players
    conn = connect_db()
    cursor = conn.cursor()

    # Get game details
    cursor.execute("SELECT event_date, start_time, end_time, venue FROM schedule WHERE id = %s", (game_id,))
    game = cursor.fetchone()

    if not game:
        await query.edit_message_text("Game not found.")
        cursor.close()
        conn.close()
        return

    event_date = game[0]
    start_time = game[1]
    end_time = game[2]
    venue = game[3]

    # Get number of registered players
    cursor.execute("SELECT COUNT(*) FROM registrations WHERE game_id = %s", (game_id,))
    num_players = cursor.fetchone()[0]

    cursor.close()
    conn.close()

    # Prepare confirmation message
    message = (f"Are you sure you want to remove the game at {venue} on {event_date} from {start_time} to {end_time}?\n"
               f"There are currently {num_players} player(s) registered for this game.\n"
               "This action cannot be undone. Proceed?")

    # Provide Yes/No buttons
    buttons = [
        [InlineKeyboardButton("Yes", callback_data='confirm_remove_yes'),
         InlineKeyboardButton("No", callback_data='confirm_remove_no')]
    ]
    reply_markup = InlineKeyboardMarkup(buttons)

    await query.edit_message_text(message, reply_markup=reply_markup)

# show_admin_menu function
async def show_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ['Add New Game', 'Edit Existing Game'],
        ['Remove Game', 'Manage Players'],
        ['Back to Main Menu']
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    if update.callback_query:
        await update.callback_query.edit_message_text("Admin Menu:", reply_markup=reply_markup)
    else:
        await update.message.reply_text("Admin Menu:", reply_markup=reply_markup)

#manage_players_menu function
async def manage_players_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user.username
    if user not in ADMIN_USERNAMES:
        await update.message.reply_text("You do not have permission to manage players.")
        return

    keyboard = [
        ['Add Player', 'Edit Player'],
        ['Remove Player', 'Back to Admin Menu']
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("Manage Players Menu:", reply_markup=reply_markup)

#Add Player Handler
async def add_player_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user.username
    if user not in ADMIN_USERNAMES:
        await update.message.reply_text("You do not have permission to add players.")
        return

    await update.message.reply_text("Enter the player's name:")
    context.user_data['add_player_step'] = 'name'

#Handle Player Addition Steps
async def handle_add_player(update: Update, context: ContextTypes.DEFAULT_TYPE):
    step = context.user_data.get('add_player_step')
    if not step:
        return  # Not in the process of adding a player

    if step == 'name':
        context.user_data['player_name'] = update.message.text
        context.user_data['add_player_step'] = 'nickname'
        await update.message.reply_text("Enter the player's Telegram nickname:")
    elif step == 'nickname':
        context.user_data['player_nickname'] = update.message.text
        context.user_data['add_player_step'] = 'level'
        await update.message.reply_text("Enter the player's level (Novice, D-, D, D+, C-, C, C+):")
    elif step == 'level':
        level = update.message.text
        valid_levels = ['Novice', 'D-', 'D', 'D+', 'C-', 'C', 'C+']
        if level not in valid_levels:
            await update.message.reply_text("Invalid level. Please enter one of the following: Novice, D-, D, D+, C-, C, C+.")
            return

        player_name = context.user_data.get('player_name')
        player_nickname = context.user_data.get('player_nickname')

        # Save the new player to the database
        conn = connect_db()
        cursor = conn.cursor()

        try:
            cursor.execute('''INSERT INTO players (name, nickname, level)
                              VALUES (%s, %s, %s)''', (player_name, player_nickname, level))
            conn.commit()
            await update.message.reply_text(f"Player {player_name} ({player_nickname}) has been added successfully.")
        except mysql.connector.IntegrityError:
            await update.message.reply_text(f"A player with the nickname {player_nickname} already exists.")
        finally:
            cursor.close()
            conn.close()

        # Clear user data
        context.user_data.pop('add_player_step', None)
        context.user_data.pop('player_name', None)
        context.user_data.pop('player_nickname', None)
    else:
        await update.message.reply_text("An error occurred. Please try again.")
        context.user_data.clear()

#Edit Player Handler
async def edit_player_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user.username
    if user not in ADMIN_USERNAMES:
        await update.message.reply_text("You do not have permission to edit players.")
        return

    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, nickname FROM players WHERE active = TRUE")
    players = cursor.fetchall()
    cursor.close()
    conn.close()

    if not players:
        await update.message.reply_text("There are no players to edit.")
        return

    buttons = []
    for player in players:
        player_id = player[0]
        name = player[1]
        nickname = player[2]
        button_text = f"{player_id}: {name} ({nickname})"
        buttons.append([InlineKeyboardButton(button_text, callback_data=f"edit_player_{player_id}")])

    reply_markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text("Select a player to edit:", reply_markup=reply_markup)

#Handle Player Selection for Editing
async def handle_edit_player_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user.username
    if user not in ADMIN_USERNAMES:
        await query.edit_message_text("You do not have permission to edit players.")
        return

    player_id = int(query.data.split('_')[-1])
    context.user_data['edit_player_id'] = player_id

    keyboard = [
        [InlineKeyboardButton("Name", callback_data='edit_player_attr_name')],
        [InlineKeyboardButton("Nickname", callback_data='edit_player_attr_nickname')],
        [InlineKeyboardButton("Level", callback_data='edit_player_attr_level')],
        [InlineKeyboardButton("Cancel", callback_data='edit_player_attr_cancel')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("Select an attribute to edit:", reply_markup=reply_markup)

#Handle Attribute Selection and Update
async def handle_edit_player_attribute_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    attribute = query.data.split('_')[-1]
    context.user_data['edit_player_attribute'] = attribute

    if attribute == 'cancel':
        await query.edit_message_text("Editing canceled.")
        context.user_data.pop('edit_player_id', None)
        context.user_data.pop('edit_player_attribute', None)
        return

    attribute_prompts = {
        'name': "Enter the new name:",
        'nickname': "Enter the new Telegram nickname:",
        'level': "Enter the new level (Novice, D-, D, D+, C-, C, C+):"
    }

    prompt = attribute_prompts.get(attribute, "Invalid attribute.")
    if prompt == "Invalid attribute.":
        await query.edit_message_text("Invalid attribute selected.")
        return

    await query.edit_message_text(prompt)
    context.user_data['edit_player_step'] = 'update_attribute'

#Handle New Attribute Value
async def handle_new_player_attribute_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('edit_player_step') != 'update_attribute':
        return  # Not in the middle of editing a player attribute

    user = update.message.from_user.username
    if user not in ADMIN_USERNAMES:
        await update.message.reply_text("You do not have permission to edit players.")
        return

    player_id = context.user_data.get('edit_player_id')
    attribute = context.user_data.get('edit_player_attribute')
    new_value = update.message.text

    # Validate the new value based on attribute
    valid = True
    if attribute == 'level':
        valid_levels = ['Novice', 'D-', 'D', 'D+', 'C-', 'C', 'C+']
        if new_value not in valid_levels:
            valid = False
            await update.message.reply_text("Invalid level. Please enter one of the following: Novice, D-, D, D+, C-, C, C+.")
    elif attribute == 'nickname':
        if not new_value:
            valid = False
            await update.message.reply_text("Nickname cannot be empty.")
    elif attribute == 'name':
        if not new_value:
            valid = False
            await update.message.reply_text("Name cannot be empty.")

    if not valid:
        return  # Do not proceed if validation failed

    # Update the database
    conn = connect_db()
    cursor = conn.cursor()

    try:
        update_query = f"UPDATE players SET {attribute} = %s WHERE id = %s"
        cursor.execute(update_query, (new_value, player_id))
        conn.commit()
        await update.message.reply_text(f"The player's {attribute} has been updated successfully.")
    except mysql.connector.IntegrityError:
        if attribute == 'nickname':
            await update.message.reply_text(f"A player with the nickname {new_value} already exists.")
    finally:
        cursor.close()
        conn.close()

    # Clear the editing state
    context.user_data.pop('edit_player_id', None)
    context.user_data.pop('edit_player_attribute', None)
    context.user_data.pop('edit_player_step', None)

#Remove Player Handler
async def remove_player_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user.username
    if user not in ADMIN_USERNAMES:
        await update.message.reply_text("You do not have permission to remove players.")
        return

    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, nickname FROM players WHERE active = TRUE")
    players = cursor.fetchall()
    cursor.close()
    conn.close()

    if not players:
        await update.message.reply_text("There are no players to remove.")
        return

    buttons = []
    for player in players:
        player_id = player[0]
        name = player[1]
        nickname = player[2]
        button_text = f"{player_id}: {name} ({nickname})"
        buttons.append([InlineKeyboardButton(button_text, callback_data=f"remove_player_{player_id}")])

    reply_markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text("Select a player to remove:", reply_markup=reply_markup)

#Handle Player Selection for Removal
async def handle_remove_player_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user.username
    if user not in ADMIN_USERNAMES:
        await query.edit_message_text("You do not have permission to remove players.")
        return

    player_id = int(query.data.split('_')[-1])
    context.user_data['remove_player_id'] = player_id

    # Fetch player details
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT name, nickname FROM players WHERE id = %s", (player_id,))
    player = cursor.fetchone()
    cursor.close()
    conn.close()

    if not player:
        await query.edit_message_text("Player not found.")
        context.user_data.pop('remove_player_id', None)
        return

    name = player[0]
    nickname = player[1]

    # Prepare confirmation message
    message = (f"Are you sure you want to permanently delete {name} ({nickname})?\n"
               "This action cannot be undone. Proceed?")

    # Provide Yes/No buttons
    buttons = [
        [InlineKeyboardButton("Yes", callback_data='confirm_remove_player_yes'),
         InlineKeyboardButton("No", callback_data='confirm_remove_player_no')]
    ]
    reply_markup = InlineKeyboardMarkup(buttons)

    await query.edit_message_text(message, reply_markup=reply_markup)

#Handle Removal Confirmation
async def handle_remove_player_confirmation_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user.username
    if user not in ADMIN_USERNAMES:
        await query.edit_message_text("You do not have permission to remove players.")
        return

    confirmation = query.data.split('_')[-1]
    player_id = context.user_data.get('remove_player_id')

    if confirmation == 'yes':
        # Proceed to remove the player
        conn = connect_db()
        cursor = conn.cursor()

        # Delete registrations associated with the player
        cursor.execute("DELETE FROM registrations WHERE player_id = %s", (player_id,))

        # Delete the player
        cursor.execute("DELETE FROM players WHERE id = %s", (player_id,))

        conn.commit()
        cursor.close()
        conn.close()

        await query.edit_message_text("The player has been successfully removed.")

        # Clear the remove player ID from context
        context.user_data.pop('remove_player_id', None)
    else:
        await query.edit_message_text("Player removal canceled.")
        # Clear the remove player ID from context
        context.user_data.pop('remove_player_id', None)

#show_player_menu function
async def show_player_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ['Register', 'Register for the Game'],
        ['Confirm Registration for the Game'],
        ['View Your Registrations', 'Cancel Your Registrations'],
        ['Swap Your Confirmed Registration'],
        ['Back to Main Menu']
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    if update.callback_query:
        await update.callback_query.edit_message_text("Player Menu:", reply_markup=reply_markup)
    else:
        await update.message.reply_text("Player Menu:", reply_markup=reply_markup)

#List Available Games and Register
async def list_available_games(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM players WHERE nickname = %s", (nickname,))
    player = cursor.fetchone()
    if not player:
        await query.edit_message_text("You are not registered. Please register first.")
        cursor.close()
        conn.close()
        return
    player_id = player[0]

    game_id = int(data.split('_')[-1])

    # Check if the player is already registered for the game
    cursor.execute("SELECT * FROM registrations WHERE player_id = %s AND game_id = %s", (player_id, game_id))
    registration = cursor.fetchone()
    if registration:
        await query.edit_message_text("You are already registered for this game.")
        cursor.close()
        conn.close()
        return

    # Register the player for the game
    cursor.execute("INSERT INTO registrations (player_id, game_id) VALUES (%s, %s)", (player_id, game_id))
    conn.commit()
    cursor.close()
    conn.close()

    await query.edit_message_text("You have been registered for the game. Please confirm your registration in 'Confirm Registration for the Game' option.")

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
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM players WHERE nickname = %s", (nickname,))
    player = cursor.fetchone()
    if not player:
        await update.message.reply_text("You are not registered. Please register first.")
        cursor.close()
        conn.close()
        return
    player_id = player[0]

    # Get all registrations
    cursor.execute("""
        SELECT s.event_date, s.start_time, s.venue, r.confirmed
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
        event_date = reg[0]
        start_time = reg[1]
        venue = reg[2]
        confirmed = "Confirmed" if reg[3] else "Unconfirmed"
        message += f"{event_date} at {start_time} - {venue} [{confirmed}]\n"

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

    # Delete the unconfirmed registration
    cursor.execute("DELETE FROM registrations WHERE id = %s AND player_id = %s AND confirmed = FALSE", (reg_id, player_id))
    conn.commit()
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

#Registration Function
#list_available_games function
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

#Registration Cancellation Function
#handle_cancel_registration_callback Function
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

#Registration Confirmation Function
#list_unconfirmed_registrations function 
async def list_unconfirmed_registrations(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    # Get unconfirmed registrations not on waiting list
    cursor.execute("""
        SELECT r.id, s.event_date, s.start_time, s.venue
        FROM registrations r
        JOIN schedule s ON r.game_id = s.id
        WHERE r.player_id = %s AND r.confirmed = FALSE AND r.waiting = FALSE
    """, (player_id,))
    registrations = cursor.fetchall()
    cursor.close()
    conn.close()

    if not registrations:
        await update.message.reply_text("You have no unconfirmed registrations ready for confirmation.")
        return

    buttons = []
    for reg in registrations:
        reg_id = reg['id']
        event_date = reg['event_date']
        start_time = reg['start_time']
        venue = reg['venue']
        button_text = f"{event_date} at {start_time} - {venue}"
        buttons.append([InlineKeyboardButton(button_text, callback_data=f"confirm_registration_{reg_id}")])

    reply_markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text("Select a registration to confirm:", reply_markup=reply_markup)

# view_registrations function
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
    
#handle_edit_game_callback function
async def handle_edit_game_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user.username
    if user not in ADMIN_USERNAMES:
        await query.edit_message_text("You do not have permission to edit games.")
        return

    game_id = int(query.data.split('_')[-1])
    context.user_data['edit_game_id'] = game_id

    keyboard = [
        [InlineKeyboardButton("Event Date", callback_data='edit_attr_event_date')],
        [InlineKeyboardButton("Start Time", callback_data='edit_attr_start_time')],
        [InlineKeyboardButton("End Time", callback_data='edit_attr_end_time')],
        [InlineKeyboardButton("Venue", callback_data='edit_attr_venue')],
        [InlineKeyboardButton("Capacity", callback_data='edit_attr_capacity')],
        [InlineKeyboardButton("Cancel", callback_data='edit_attr_cancel')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("Select an attribute to edit:", reply_markup=reply_markup)
    
#edit_existing_game function
async def edit_existing_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user.username
    if user not in ADMIN_USERNAMES:
        await update.message.reply_text("You do not have permission to edit games.")
        return

    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, event_date, start_time, end_time, venue FROM schedule WHERE finished IS NULL")
    games = cursor.fetchall()
    cursor.close()
    conn.close()

    if not games:
        await update.message.reply_text("There are no unfinished games to edit.")
        return

    buttons = []
    for game in games:
        game_id = game[0]
        event_date = game[1]
        start_time = game[2]
        venue = game[4]
        button_text = f"{game_id}: {venue} on {event_date} at {start_time}"
        buttons.append([InlineKeyboardButton(button_text, callback_data=f"edit_game_{game_id}")])

    reply_markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text("Select a game to edit:", reply_markup=reply_markup)

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

#Handle Game Creation Steps
async def handle_game_creation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    step = context.user_data.get('game_creation_step')

    if step == 'event_date':
        context.user_data['event_date'] = update.message.text
        context.user_data['game_creation_step'] = 'start_time'
        await update.message.reply_text("Enter the start time (HH:MM):")
    elif step == 'start_time':
        context.user_data['start_time'] = update.message.text
        context.user_data['game_creation_step'] = 'end_time'
        await update.message.reply_text("Enter the end time (HH:MM):")
    elif step == 'end_time':
        context.user_data['end_time'] = update.message.text
        context.user_data['game_creation_step'] = 'venue'
        await update.message.reply_text("Enter the venue:")
    elif step == 'venue':
        context.user_data['venue'] = update.message.text
        context.user_data['game_creation_step'] = 'capacity'
        await update.message.reply_text("Enter the capacity:")
    elif step == 'capacity':
        capacity = update.message.text
        try:
            capacity = int(capacity)
            event_date = context.user_data['event_date']
            start_time = context.user_data['start_time']
            end_time = context.user_data['end_time']
            venue = context.user_data['venue']

            conn = connect_db()
            cursor = conn.cursor()
            cursor.execute('''INSERT INTO schedule (event_date, start_time, end_time, venue, capacity)
                              VALUES (%s, %s, %s, %s, %s)''',
                           (event_date, start_time, end_time, venue, capacity))
            conn.commit()
            cursor.close()
            conn.close()

            await update.message.reply_text("New game has been added successfully.")
            context.user_data.clear()
        except ValueError:
            await update.message.reply_text("Invalid capacity. Please enter a number.")



#main code
def main():
    TOKEN = '8175985461:AAHBYoM-juaM1X01fgLIDhniQQlcu1rHHNE'  # Replace with your bot's token
    application = ApplicationBuilder().token(TOKEN).build()

    # Command Handlers
    application.add_handler(CommandHandler('start', start))

    # Callback Query Handlers
    application.add_handler(CallbackQueryHandler(button))
    application.add_handler(CallbackQueryHandler(handle_register_game_callback, pattern=r'^register_game_\d+$'))
    application.add_handler(CallbackQueryHandler(handle_confirm_registration_callback, pattern=r'^confirm_registration_\d+$'))
    application.add_handler(CallbackQueryHandler(handle_cancel_registration_callback, pattern=r'^cancel_registration_\d+$'))
    application.add_handler(CallbackQueryHandler(handle_swap_registration_callback, pattern=r'^swap_registration_\d+$'))
    application.add_handler(CallbackQueryHandler(handle_edit_game_callback, pattern=r'^edit_game_\d+$'))
    application.add_handler(CallbackQueryHandler(handle_edit_attribute_callback, pattern=r'^edit_attr_.*'))
    application.add_handler(CallbackQueryHandler(handle_remove_game_callback, pattern=r'^remove_game_\d+$'))
    application.add_handler(CallbackQueryHandler(handle_remove_confirmation_callback, pattern=r'^confirm_remove_.*'))

    application.add_handler(CallbackQueryHandler(handle_edit_player_callback, pattern=r'^edit_player_\d+$'))
    application.add_handler(CallbackQueryHandler(handle_edit_player_attribute_callback, pattern=r'^edit_player_attr_.*'))
    application.add_handler(CallbackQueryHandler(handle_remove_player_callback, pattern=r'^remove_player_\d+$'))
    application.add_handler(CallbackQueryHandler(handle_remove_player_confirmation_callback, pattern=r'^confirm_remove_player_.*'))

    application.add_handler(CallbackQueryHandler(handle_edit_game_callback, pattern=r'^edit_game_\d+$'))
    application.add_handler(CallbackQueryHandler(handle_edit_attribute_callback, pattern=r'^edit_attr_.*'))
    application.add_handler(CallbackQueryHandler(handle_remove_game_callback, pattern=r'^remove_game_\d+$'))
    application.add_handler(CallbackQueryHandler(handle_remove_confirmation_callback, pattern=r'^confirm_remove_.*'))
 
# Message Handlers 
    application.add_handler(MessageHandler(filters.Regex('^Manage Games Schedule$'), show_manage_games_menu))
    application.add_handler(MessageHandler(filters.Regex('^Add New Game$'), add_new_game))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_game_creation))

    application.add_handler(MessageHandler(filters.Regex('^Register$'), register_player))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_registration))

    application.add_handler(MessageHandler(filters.Regex('^Register for the Game$'), list_available_games))
    application.add_handler(MessageHandler(filters.Regex('^Confirm Registration for the Game$'), list_unconfirmed_registrations))
    application.add_handler(MessageHandler(filters.Regex('^View Your Registrations$'), view_registrations))
    application.add_handler(MessageHandler(filters.Regex('^Cancel Your Registrations$'), list_unconfirmed_registrations_for_cancellation))
    application.add_handler(MessageHandler(filters.Regex('^Swap Your Confirmed Registration$'), list_confirmed_registrations_for_swap))
    application.add_handler(MessageHandler(filters.Regex('^Manage Players$'), manage_players_menu))
    application.add_handler(MessageHandler(filters.Regex('^Add Player$'), add_player_start))
    application.add_handler(MessageHandler(filters.Regex('^Edit Player$'), edit_player_start))
    application.add_handler(MessageHandler(filters.Regex('^Remove Player$'), remove_player_start))

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_add_player))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_new_player_attribute_value))
    application.add_handler(MessageHandler(filters.Regex('^Edit Existing Game$'), edit_existing_game))
    application.add_handler(MessageHandler(filters.Regex('^Remove Game$'), remove_game))
#    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_new_attribute_value))

    # ... other handlers ...

    application.run_polling()



if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        logging.error(f"An error occurred: {e}")




