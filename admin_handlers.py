from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    filters,
)
from menu_handlers import show_admin_menu

import datetime
import logging

from database import connect_db, get_player_by_nickname
from config import ADMIN_USERNAMES

# Conversation states
ADD_GAME_DATE, ADD_GAME_START_TIME, ADD_GAME_END_TIME, ADD_GAME_VENUE, ADD_GAME_CAPACITY = range(5)
SELECT_GAME_TO_EDIT, SELECT_ATTRIBUTE_TO_EDIT, EDIT_GAME_ATTRIBUTE_VALUE = range(3)


async def add_new_game_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.username
    if user not in ADMIN_USERNAMES:
        await update.message.reply_text("You do not have permission to add games.")
        return ConversationHandler.END

    await update.message.reply_text("Please enter the date of the game (YYYY-MM-DD):")
    return ADD_GAME_DATE

async def add_game_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    date_text = update.message.text
    try:
        datetime.datetime.strptime(date_text, '%Y-%m-%d')
    except ValueError:
        await update.message.reply_text("Invalid date format. Please enter the date in YYYY-MM-DD format:")
        return ADD_GAME_DATE

    context.user_data['event_date'] = date_text
    await update.message.reply_text("Please enter the start time of the game (HH:MM in 24-hour format):")
    return ADD_GAME_START_TIME

async def add_game_start_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    start_time_text = update.message.text
    try:
        datetime.datetime.strptime(start_time_text, '%H:%M')
    except ValueError:
        await update.message.reply_text("Invalid time format. Please enter the start time in HH:MM format:")
        return ADD_GAME_START_TIME

    context.user_data['start_time'] = start_time_text
    await update.message.reply_text("Please enter the end time of the game (HH:MM in 24-hour format):")
    return ADD_GAME_END_TIME

async def add_game_end_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    end_time_text = update.message.text
    try:
        datetime.datetime.strptime(end_time_text, '%H:%M')
    except ValueError:
        await update.message.reply_text("Invalid time format. Please enter the end time in HH:MM format:")
        return ADD_GAME_END_TIME

    context.user_data['end_time'] = end_time_text
    await update.message.reply_text("Please enter the venue of the game:")
    return ADD_GAME_VENUE

async def add_game_venue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    venue_text = update.message.text
    context.user_data['venue'] = venue_text

    await update.message.reply_text("Please enter the capacity of the game (number of players):")
    return ADD_GAME_CAPACITY

async def add_game_capacity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    capacity_text = update.message.text
    if not capacity_text.isdigit():
        await update.message.reply_text("Capacity must be a number. Please enter the capacity:")
        return ADD_GAME_CAPACITY

    capacity = int(capacity_text)
    context.user_data['capacity'] = capacity

    # Retrieve all collected data
    event_date = context.user_data['event_date']
    start_time = context.user_data['start_time']
    end_time = context.user_data['end_time']
    venue = context.user_data['venue']

    # Save the new game to the database
    conn = connect_db()
    cursor = conn.cursor()

    try:
        cursor.execute('''
            INSERT INTO schedule (event_date, start_time, end_time, venue, capacity)
            VALUES (%s, %s, %s, %s, %s)
        ''', (event_date, start_time, end_time, venue, capacity))
        conn.commit()
        await update.message.reply_text("The new game has been added successfully.")
        
        await show_admin_menu(update, context)

    except Exception as e:
        await update.message.reply_text(f"An error occurred while adding the game: {e}")
    finally:
        cursor.close()
        conn.close()

    # Clear user data and end the conversation
    context.user_data.clear()
    return ConversationHandler.END

async def add_game_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Game addition has been canceled.")
    context.user_data.clear()
    return ConversationHandler.END

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
    try:
        conn = connect_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT id, 
                   DATE_FORMAT(event_date, '%Y-%m-%d') AS event_date_str, 
                   TIME_FORMAT(start_time, '%H:%i') AS start_time_str, 
                   TIME_FORMAT(end_time, '%H:%i') AS end_time_str, 
                   venue 
            FROM schedule 
            ORDER BY event_date DESC
        """)
        games = cursor.fetchall()
        if not games:
            await update.message.reply_text("No games available to edit.")
            return ConversationHandler.END

        keyboard = []
        for game in games:
            event_date = game['event_date_str']
            start_time = game['start_time_str']
            end_time = game['end_time_str']
            venue = game['venue']

            button_text = f"{event_date} {start_time} - {end_time} - {venue}"
            callback_data = f"edit_game_{game['id']}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Select a game to edit:", reply_markup=reply_markup)
        return SELECT_GAME_TO_EDIT  # Proceed to the next state

    except Exception as e:
        logger.exception("Error fetching games")
        await update.message.reply_text("An error occurred while fetching games.")
        return ConversationHandler.END

    finally:
        cursor.close()
        conn.close()
    

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

#Handle Attribute Selection            
async def handle_edit_attribute_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    attribute = query.data.split('_')[-1]
    context.user_data['edit_attribute'] = attribute

    if attribute == 'cancel':
        await query.edit_message_text("Editing canceled.")
        context.user_data.pop('edit_game_id', None)
        context.user_data.pop('edit_attribute', None)
        return

    attribute_prompts = {
        'event_date': "Enter the new event date (YYYY-MM-DD):",
        'start_time': "Enter the new start time (HH:MM):",
        'end_time': "Enter the new end time (HH:MM):",
        'venue': "Enter the new venue:",
        'capacity': "Enter the new capacity:"
    }

    prompt = attribute_prompts.get(attribute, "Invalid attribute.")
    if prompt == "Invalid attribute.":
        await query.edit_message_text("Invalid attribute selected.")
        return

    await query.edit_message_text(prompt)
    context.user_data['edit_step'] = 'update_attribute'

async def edit_game_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("edit_game_cancel function called")
    await update.message.reply_text("Editing game canceled.")
    return ConversationHandler.END

async def handle_new_attribute_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_value = update.message.text
    game_id = context.user_data['edit_game_id']
    attribute = context.user_data['edit_attribute']

    conn = connect_db()
    cursor = conn.cursor(dictionary=True)
    try:
        # Build the SQL query dynamically
        sql = f"UPDATE schedule SET {attribute} = %s WHERE id = %s"
        cursor.execute(sql, (new_value, game_id))
        conn.commit()
        await update.message.reply_text("Game updated successfully.")
    except Exception as e:
        logger.exception("Error updating game")
        await update.message.reply_text("An error occurred while updating the game.")
    finally:
        cursor.close()
        conn.close()

    # Clear user data and end the conversation
    context.user_data.clear()
    return ConversationHandler.END
#