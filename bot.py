print("admin_handlers.py is being imported and executed")

import datetime
import logging
import re
import mysql.connector

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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
from database import connect_db, get_player_by_nickname, update_game_attribute
from config import ADMIN_USERNAMES, DEDICATED_CHAT_ID
from enum import IntEnum
from utils import get_game_data, send_game_status_update

from constants import States

logger.info(f"In admin_handlers.py, SELECT_GAME id: {id(States.SELECT_GAME)}")

ADD_GAME_DATE = 1
ADD_GAME_START_TIME = 2
ADD_GAME_END_TIME = 3
ADD_GAME_VENUE = 4
ADD_GAME_CAPACITY = 5

# Conversation states
#ADD_GAME_DATE, ADD_GAME_START_TIME, ADD_GAME_END_TIME, ADD_GAME_VENUE, ADD_GAME_CAPACITY = range(5)
#SELECT_GAME, GAME_ACTIONS, SELECT_ATTRIBUTE_TO_EDIT, EDIT_GAME_ATTRIBUTE_VALUE, REGISTER_PLAYER, REMOVE_PLAYER = range(6)

async def add_new_game_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
#    user = update.effective_user.username
#    if user not in ADMIN_USERNAMES:
#        await update.message.reply_text("You do not have permission to add games.")
#        return ConversationHandler.END
#    query = update.callback_query
#    await query.answer()  # Acknowledge the callback
    logger.info(f"add_new_game_start function called")
    user = update.effective_user.username

    if user not in ADMIN_USERNAMES:
        await update.message.reply_text("You do not have permission to add games.")
        return ConversationHandler.END
        
    await update.message.reply_text("Please enter the date of the game (YYYY-MM-DD):")
    return ADD_GAME_DATE

async def add_game_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        date_text = update.message.text
        logger.info(f"add_game_date function called")
   
        datetime.datetime.strptime(date_text, '%Y-%m-%d')
        context.user_data['event_date'] = date_text

        await update.message.reply_text("Please enter the start time of the game (HH:MM in 24-hour format):")
        return ADD_GAME_START_TIME
        
    except ValueError:
        await update.message.reply_text("Invalid date format. Please enter the date in YYYY-MM-DD format:")
        return ADD_GAME_DATE
        
    except Exception as e:
        logger.exception("An error occurred in add_game_date.")
        await update.message.reply_text("An unexpected error occurred. Please try again later.")
        return ConversationHandler.END
        
    context.user_data['event_date'] = date_text

async def add_game_start_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    start_time_text = update.message.text
    logger.info(f"add_game_start_time function called")

    try:
        datetime.datetime.strptime(start_time_text, '%H:%M')
        context.user_data['start_time'] = start_time_text
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
        context.user_data['end_time'] = end_time_text
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
    return await show_admin_menu(update, context)

#Remove game function
async def remove_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user.username
    if user not in ADMIN_USERNAMES:
        await update.message.reply_text("You do not have permission to remove games.")
        return

    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, event_date, start_time, venue 
        FROM schedule 
        WHERE finished IS NULL
        ORDER BY event_date ASC            
        """)
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
        context.user_data.clear()
        return await show_admin_menu(update, context)
    else:
        await query.edit_message_text("Game removal canceled.")
        # Clear the remove game ID from context
        context.user_data.pop('remove_game_id', None)
        context.user_data.clear()
        return await show_admin_menu(update, context)

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

#edit_existing_game function
async def edit_existing_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("edit_existing_game called")
    user = update.message.from_user.username
    if user not in ADMIN_USERNAMES:
        await update.message.reply_text("You do not have permission to edit games.")
        return ConversationHandler.END  # End the conversation
        
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
            WHERE (event_date > CURDATE()) 
               OR (event_date = CURDATE() AND start_time > CURTIME())
            ORDER BY event_date ASC, start_time ASC
        """)
        games = cursor.fetchall()
        
        if not games:
            await update.message.reply_text("No games available to edit.")
            return ConversationHandler.END

        keyboard = []
        for game in games:
            game_id = game['id']
            event_date = game['event_date_str']
            start_time = game['start_time_str']
            end_time = game['end_time_str']
            venue = game['venue']

            button_text = f"{event_date} {start_time} - {end_time} - {venue}"
            callback_data = f"edit_game_{game['id']}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
        
        keyboard.append([InlineKeyboardButton('cancel', callback_data='cancel')])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Какую игру изменить?", reply_markup=reply_markup)
        logger.info(f"Selected game {game_id}. Return state {States.SELECT_GAME_TO_EDIT}")

        return States.SELECT_GAME_TO_EDIT  # Proceed to the next state

    except Exception as e:
        logger.exception("Error fetching games")
        await update.message.reply_text("An error occurred while fetching games.")
        return ConversationHandler.END

    finally:
        cursor.close()
        conn.close()
    
#handle_edit_game_callback function
async def handle_edit_game_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("handle_edit_game_callback called")
    
    # Ensure callback_query is available
    if not update.callback_query:
        await update.message.reply_text("An error occurred No update.callback_query. Please try again.")
        return States.SELECT_GAME

    query = update.callback_query
    await query.answer()

    user=update.message.from_user.username
    if not user or user not in ADMIN_USERNAMES:
        if update.callback_query:
            await update.callback_query.edit_message_text("You do not have permission to edit games.")
        else:
            await update.message.reply_text("You do not have permission to edit games.")
        return ConversationHandler.END

    # Fetch current game data   
#    game_id = context.user_data.get('selected_game_id') 
    game_id = int(query.data.split('_')[-1])
    if not game_id:
        await update.message.reply_text("No game selected. Please select a game first.")
        return States.GAME_ACTIONS    
    context.user_data['edit_game_id'] = game_id
        
    game = await get_game_data(game_id)
    if not game:
        await update.message.reply_text("Game not found.")
        return States.SELECT_GAME_TO_EDIT
        
    # Select the attribute to edit, and store that as well
#    attribute = query.data[len('edit_attr_'):]  
#    context.user_data['edit_attribute'] = attribute

    logger.info(f"User context after selecting attribute in handle_edit_game_callback: {context.user_data}")

        
    keyboard = [
        [InlineKeyboardButton(f"Event Date: {game['event_date_str']}", callback_data='edit_attr_event_date')],
        [InlineKeyboardButton(f"Start Time: {game['start_time_str']}", callback_data='edit_attr_start_time')],
        [InlineKeyboardButton(f"End Time: {game['end_time_str']}", callback_data='edit_attr_end_time')],
        [InlineKeyboardButton(f"Venue: {game['venue']}", callback_data='edit_attr_venue')],
        [InlineKeyboardButton(f"Capacity: {game['capacity']}", callback_data='edit_attr_capacity')],
        [InlineKeyboardButton("Finish", callback_data='edit_attr_finish')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Select an attribute to edit:", reply_markup=reply_markup)
    
    logger.info(f"Selected game {game_id} and attribute {reply_markup}. Return state {States.SELECT_ATTRIBUTE_TO_EDIT}")
    return States.SELECT_ATTRIBUTE_TO_EDIT # Return the next state

#Handle Attribute Selection            
async def handle_edit_attribute_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("handle_edit_attribute_callback called")
    
    # Handle both callback query and message updates
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        attribute = query.data[len('edit_attr_'):]
        message = query.message
    else:
        attribute = context.user_data.get('edit_attribute')
        message = update.message
        if not attribute:
            await update.message.reply_text("No attribute selected. Please try again.")
            return States.SELECT_GAME
    logger.info(f"Attribute extracted: {attribute}")
    context.user_data['edit_attribute'] = attribute

    if attribute == 'finish':
        # Fetch the game_id from user_data
        game_id = context.user_data.get('edit_game_id')
        if not game_id:
            await query.edit_message_text("No game selected. Please select a game first.")
            return States.GAME_ACTIONS  # Return to GAME_ACTIONS state

        # Fetch updated game data
        game = await get_game_data(game_id)
        if not game:
            await query.edit_message_text("Game not found.")
            return States.GAME_ACTIONS  # Return to GAME_ACTIONS state
        try:
            conn = connect_db()
            cursor = conn.cursor(dictionary=True)  # Use dictionary=True for easier access

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
        finally:
            cursor.close()
            conn.close()
        
        # Format the updated game details
        game_info = (
            f"✅ **Updated Game Details:**\n"
            f"**Event Date:** {game['event_date_str']}\n"
            f"**Start Time:** {game['start_time_str']}\n"
            f"**End Time:** {game['end_time_str']}\n"
            f"**Venue:** {game['venue']}\n"
            f"**Capacity:** {game['capacity']}\n"
            f"👤 **Registered**: {main_count} ({waiting_count} in waiting list)"

        )
        await context.bot.send_message(chat_id=DEDICATED_CHAT_ID, text=game_info, parse_mode='Markdown')
        
        if update.callback_query:
            await manage_games_menu(update.callback_query, context)
        elif update.message:
            await manage_games_menu(update.message, context)

        # Clear user_data
        context.user_data.pop('edit_attribute', None)
#        context.user_data.pop('edit_game_id', None)
        
        # Edit the current message to notify the user and remove the inline keyboard
        await query.edit_message_text("Editing finished. Returning to the game selection menu.")

        # Return to "Edit Existing Games" menu
        await manage_games_menu(update, context)
        logger.info(f"Returning to state: {States.SELECT_GAME}")
        return States.SELECT_GAME  # Transition back to SELECT_GAME state

    attribute_prompts = {
        'event_date': "Enter the new event date (YYYY-MM-DD):",
        'start_time': "Enter the new start time (HH:MM):",
        'end_time': "Enter the new end time (HH:MM):",
        'venue': "Enter the new venue:",
        'capacity': "Enter the new capacity:"
    }

    prompt = attribute_prompts.get(attribute)
    logger.info(f"Prompt found: {prompt}")
    if not prompt:
        await query.edit_message_text("Invalid attribute selected.")
        return States.SELECT_ATTRIBUTE_TO_EDIT  # Stay in the current state      

    await query.message.reply_text(prompt)
    context.user_data['edit_step'] = 'update_attribute'
    return States.EDIT_GAME_ATTRIBUTE_VALUE  # Return the next state

async def handle_new_attribute_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("handle_new_attribute_value called")
    new_value = update.message.text
    game_id = context.user_data['edit_game_id']
    attribute = context.user_data['edit_attribute']
    user_input = update.message.text


    if not attribute:
        await update.message.reply_text("No attribute selected. Please start over.")
        return States.GAME_ACTIONS
#        return await show_admin_menu(update, context)
        
    if not game_id:
        await update.message.reply_text("No game selected. Please start over.")
        return States.GAME_ACTIONS
#        return await show_admin_menu(update, context)
        
    try:
        # Validate and update the attribute as needed
        # Example: Update the database with the new value
        update_successful = await update_game_attribute(game_id, attribute, user_input)
        if not update_successful:
            await update.message.reply_text("Failed to update the attribute. Please try again.")
            return States.EDIT_GAME_ATTRIBUTE_VALUE  # Stay in the same state

        await update.message.reply_text(f"The {attribute.replace('_', ' ')} has been updated.")
        
        # Clear the attribute but keep the game ID to continue editing the same game
        context.user_data.pop('edit_attribute', None)
        
        game = await get_game_data(game_id)
        if not game:
            await update.message.reply_text("Failed to retrieve game data.")
            return States.GAME_ACTIONS
        
        keyboard = [
            [InlineKeyboardButton(f"Event Date: {game['event_date_str']}", callback_data='edit_attr_event_date')],
            [InlineKeyboardButton(f"Start Time: {game['start_time_str']}", callback_data='edit_attr_start_time')],
            [InlineKeyboardButton(f"End Time: {game['end_time_str']}", callback_data='edit_attr_end_time')],
            [InlineKeyboardButton(f"Venue: {game['venue']}", callback_data='edit_attr_venue')],
            [InlineKeyboardButton(f"Capacity: {game['capacity']}", callback_data='edit_attr_capacity')],
            [InlineKeyboardButton("Finish", callback_data='edit_attr_finish')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Select another attribute to edit or finish editing:",
            reply_markup=reply_markup
        )

    except Exception as e:
        logger.exception("Error updating game")
        await update.message.reply_text("An error occurred while updating the game.")
    
    return States.SELECT_ATTRIBUTE_TO_EDIT  # Return to attribute selection state

async def edit_game_finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("edit_game_cancel called")
    
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        
        # Fetch the updated game details
        game_id = context.user_data.get('edit_game_id')
        if not game_id:
            await query.message.reply_text("No game selected. Please select a game first.")
            return States.GAME_ACTIONS  # Or handle accordingly        
        
        # Fetch game data from the database
        game = await get_game_data(game_id)
        if not game:
            await query.message.reply_text("Game not found.")
            return States.GAME_ACTIONS  # Or handle accordingly

        try:
            conn = connect_db()
            cursor = conn.cursor()
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
        finally:
            cursor.close()
            conn.close()

        # Format and send the updated game details
        game_info = (
            f"📢 **Upcoming Game Update** 📢\n\n"
            f"📍 **Venue**: {game['venue']}\n"
            f"📅 **Date**: {game['event_date_str']}\n"
            f"🕒 **Time**: {game['start_time_str']} - {game['end_time_str']}\n"
            f"👥 **Capacity**: {game['capacity']} players\n"
            f"👤 **Registered**: {main_count} ({waiting_count} in waiting list)"
        )        
        
        
#        await query.message.reply_text(game_info, parse_mode='Markdown')
        await context.bot.send_message(chat_id=DEDICATED_CHAT_ID, text=game_info, parse_mode='Markdown')
        await send_game_status_update (game_id, context)
        
        # Clear context data
#        context.user_data.clear()        
        context.user_data.pop('edit_attribute', None)
        
        # Return to "Edit Existing Games" menu
        await manage_games_menu(update, context)
        logger.info(f"Returning to state: {States.SELECT_GAME}")
        return States.SELECT_GAME  # Return to SELECT_GAME state
    else:
        await update.message.reply_text("Editing finished.")
        
        # Clear context data
        context.user_data.clear()
        
        # Return to "Edit Existing Games" menu
        await manage_games_menu(update, context)
        logger.info(f"Returning to state: {States.SELECT_GAME}")
        return States.SELECT_GAME  # Return to SELECT_GAME state        

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
            await update.message.reply_text("New game has been added successfully.")
        except ValueError:
            await update.message.reply_text("Invalid capacity. Please enter a number.")
        finally:
            cursor.close()
            conn.close()
    context.user_data.clear()

async def cancel_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel the selected game and notify players if registered."""
    game_id = context.user_data['selected_game_id']
    # Check for registered players
    try:
        conn = connect_db()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM registrations WHERE game_id = %s", (game_id,))
        registered_count = cursor.fetchone()[0]
        
        # Set game as canceled
        cursor.execute("UPDATE schedule SET finished = TRUE WHERE id = %s", (game_id,))
        # Fetch game details
        cursor.execute("""
        SELECT event_date, venue
        FROM schedule
        WHERE id = %s
        """, (game_id,))
        game = cursor.fetchone()
        conn.commit()
    finally:
        cursor.close()
        conn.close()
    
    await update.message.reply_text("Game has been canceled.")
    
    # Notify chat if players were registered
    if registered_count > 0:
        # Send announcement in chat about game cancellation
        await context.bot.send_message(
            chat_id=DEDICATED_CHAT_ID,
            text=f"The game scheduled on {game['event_date']} at {game['venue']} has been canceled.", parse_mode='Markdown'
        )
        
    return States.GAME_ACTIONS

async def register_player_for_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Register a player for the selected game."""
    # Prompt admin to enter player's username for registration
    await update.callback_query.edit_message_text("Please enter the player's username to register:")
    context.user_data['registration_step'] = 'awaiting_username'

async def remove_player_from_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove a player from the selected game."""
    await update.callback_query.edit_message_text("Please enter the player's username to remove:")
    context.user_data['removal_step'] = 'awaiting_username'

async def manage_games_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Initial user context manage_games_menu: {context.user_data}")
    # Clear context data
#    context.user_data.clear()
    context.user_data['current_action'] = 'manage_games'
    context.user_data.pop('edit_attribute', None) 
    context.user_data.pop('edit_game_id', None)
    context.user_data.pop('selected_game_id', None)
    logger.info(f"User context show_manage_games_menu after cleaning: {context.user_data}")
    
    # Clear previous game ID if it exists
#    context.user_data.pop('edit_game_id', None)
    logger.info("manage_games_menu function called")
    try:
        """Display all upcoming games for selection."""
        conn = connect_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT id, event_date, start_time, venue, capacity
            FROM schedule
            WHERE finished IS NULL
            ORDER BY event_date, start_time
        """)
        games = cursor.fetchall()
    finally:    
        cursor.close()
        conn.close()

    if not games:
        if update.message:
            await update.message.reply_text("No upcoming games available.")
        elif update.callback_query:
            await update.callback_query.message.reply_text("No upcoming games available.")
        return ConversationHandler.END

    keyboard = []
    for game in games:
        callback_data = f"game_for_edit_select_{game['id']}"
        logger.info(f"Sending callback_data: {callback_data}")
        button_text = f"{game['event_date']} {game['start_time']} at {game['venue']} for {game['capacity']}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
    
    keyboard.append([InlineKeyboardButton('Go back', callback_data='go_back')])

    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        await update.message.reply_text("Select a game to edit:", reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.edit_message_text("Select a game to edit:", reply_markup=reply_markup)
        
    logger.info(f"After preparing reply manage_games_menu, context: {context.user_data}")
    logger.info(f"Transitioning to state: {States.SELECT_GAME}")
    return States.SELECT_GAME
    
async def show_game_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Initial user context show_game_details: {context.user_data}")

    """Show selected game details and options for actions."""
    logger.info("show_game_details function called")
    query = update.callback_query
    
    if query:
        await query.answer()
    else:
        logger.error("No callback_query found in update.")
        await update.message.reply_text("An error occurred while fetching game details.")
        return States.SELECT_GAME  # Or an appropriate state
    
    game_id = int(query.data.split('_')[-1])
    context.user_data['selected_game_id'] = game_id
    
    logger.info(f"User context show_game_details after update: {context.user_data}")
    
    logger.info(f"Callback data received: {query.data}")
    logger.info(f"Parsed game_id: {game_id}")
    
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
            await query.message.reply_text("Game not found.")
            return States.SELECT_GAME

        # Fetch registration details
        cursor.execute("""
            SELECT COUNT(CASE WHEN waiting = FALSE THEN 1 END) AS main_count,
                   COUNT(CASE WHEN waiting = TRUE THEN 1 END) AS waiting_count
            FROM registrations
            WHERE game_id = %s
        """, (game_id,))
        registration = cursor.fetchone()
        main_count = registration['main_count']
        waiting_count = registration['waiting_count']
    finally:
        cursor.close()
        conn.close()

    game_info = (
        f"Game at {game['venue']} on {game['event_date']} "
        f"from {game['start_time']} to {game['end_time']}\n"
        f"For: {game['capacity']} players\n"
        f"Registered Players: {main_count} ({waiting_count} in waiting list)\n"
    )
    
    keyboard = [
        ['Edit Game', 'Cancel Game', 'Announce Game'],
        ['Register Player', 'Unregister Player'],
        ['Back to Admin Menu']
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await query.message.reply_text(game_info, reply_markup=reply_markup)
    logger.info(f"Final user context show_game_details: {context.user_data}")

    return States.GAME_ACTIONS    

async def show_game_details_by_game_id(game_id, context: ContextTypes.DEFAULT_TYPE):
    logger.info("show_game_details_by_game_id function called")
    # Fetch details by game_id directly without relying on update.callback_query
    # Reuse the database retrieval logic, create an appropriate message, and send it
    try:
        conn = connect_db()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT event_date, start_time, end_time, venue, capacity, announced
            FROM schedule
            WHERE id = %s
        """, (game_id,))
        game = cursor.fetchone()
    finally:
        cursor.close()
        conn.close()

    if not game:
        await context.bot.send_message(
            chat_id=DEDICATED_CHAT_ID,
            text="Game not found.",
        )
        return

    game_info = (
        f"Game at {game['venue']} on {game['event_date']} "
        f"from {game['start_time']} to {game['end_time']}\n"
        f"For: {game['capacity']} players\n"
    )
    keyboard = [
        ['Edit Game', 'Cancel Game', 'Announce Game'],
        ['Register Player', 'Unregister Player'],
        ['Back to Admin Menu']
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await context.bot.send_message(chat_id=DEDICATED_CHAT_ID, text=game_info, reply_markup=reply_markup)
    return States.GAME_ACTIONS
    
async def start_register_player(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("start_register_player called")
    await update.message.reply_text("Please enter the Telegram nickname of the player to register:")
    return States.REGISTER_PLAYER
    
async def handle_register_player(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("handle_register_player called")
    game_id = context.user_data.get('selected_game_id')
    nickname = update.message.text.strip()

    if not nickname:
        await update.message.reply_text("Nickname cannot be empty. Please try again.")
        return States.REGISTER_PLAYER
        
#    # Validate nickname: allow only alphanumeric characters and underscores
#    if not re.match(r'^\w+$', nickname):
#        await update.message.reply_text("Invalid nickname. Please use only letters, numbers, and underscores.")
#        return States.REGISTER_PLAYER        
        
    # Fetch player ID from the database using the username
    conn = connect_db()
    cursor = conn.cursor(dictionary=True)

    
    try:
        cursor.execute("SELECT id FROM players WHERE nickname = %s", (nickname,))
        result = cursor.fetchone()   
        
        if not result:
            await update.message.reply_text("Player not found. Please try again.")
            return States.REGISTER_PLAYER

        player_id = result['id']
        
        # Check if the user is already registered for this game
        cursor.execute("SELECT * FROM registrations WHERE game_id = %s AND player_id = %s", (game_id, player_id))
        existing_registration = cursor.fetchone()
        if existing_registration:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Player is already registered for this game."
            )
            await show_game_details_by_game_id(game_id, context)  
            return States.REGISTER_PLAYER
            
        # Check the current number of non-waiting registrations
        cursor.execute("SELECT COUNT(*) AS count FROM registrations WHERE game_id = %s AND waiting = FALSE", (game_id,))
        current_count = cursor.fetchone()['count']

        # Get the game's capacity
        cursor.execute("SELECT capacity FROM schedule WHERE id = %s", (game_id,))
        game = cursor.fetchone()
        if not game:
            await update.message.reply_text("Game not found.")
            return States.GAME_ACTIONS
            
        capacity = game['capacity']

        if current_count < capacity:
            # Register the player normally
            cursor.execute("INSERT INTO registrations (player_id, game_id, is_confirmed, waiting) VALUES (%s, %s, %s, %s)",
                       (player_id, game_id, False, False))
            conn.commit()
            await update.message.reply_text("Player has been registered for the game. He shall confirm his registration by himself.")
        else:
            # Add the player to the waiting list
            cursor.execute("INSERT INTO registrations (player_id, game_id, is_confirmed, waiting) VALUES (%s, %s, %s, %s)",
                       (player_id, game_id, False, True))
            conn.commit()
            await update.message.reply_text("The game is currently full. Player has been added to the waiting list.")
    
        # Send the game status update
        await send_game_status_update(game_id, context)
        
    except Exception as e:
        logger.exception("Error in register_for_game")
        await update.message.reply_text("An error occurred while fetching games. Please try again later.")
        
    finally:
        cursor.close()
        conn.close()
        
    # Send the GAME_ACTIONS menu again    
    await show_game_details_by_game_id(game_id, context)
    await manage_games_menu(update, context)
    return States.GAME_ACTIONS

async def start_remove_player(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("start_remove_player called")
    await update.message.reply_text("Please enter the username of the player to remove:")
    return States.REMOVE_PLAYER
    
async def start_remove_player_from_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("start_remove_player called")
    
    # Fetch registered players for the selected game
    game_id = context.user_data.get('selected_game_id')
    if not game_id:
        await update.message.reply_text("No game selected. Please select a game first.")
        return States.GAME_ACTIONS
    
    try:
        conn = connect_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT p.id, p.nickname
            FROM players p
            JOIN registrations r ON p.id = r.player_id
            WHERE r.game_id = %s
        """, (game_id,))
        players = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    if not players:
        await update.message.reply_text("No players are registered for this game.")
        return States.GAME_ACTIONS

    # Create a list of player options
    keyboard = [[InlineKeyboardButton(f"{player['nickname']}", callback_data=f"game_remove_player_{player['id']}")] for player in players]
    keyboard.append([InlineKeyboardButton("Cancel", callback_data='cancel')])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text("Select the player to remove:", reply_markup=reply_markup)
    return States.REMOVE_PLAYER

async def handle_remove_player(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("handle_remove_player called")
    game_id = context.user_data.get('selected_game_id')
    nickname = update.message.text.strip()

    try:
        # Fetch player ID from the database using the username
        conn = connect_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM players WHERE nickname = %s", (nickname,))
        result = cursor.fetchone()
        if not result:
            await update.message.reply_text("Player not found. Please try again.")
            return States.REMOVE_PLAYER

        player_id = result[0]

        # Remove the player's registration for the game
        cursor.execute(
            "DELETE FROM registrations WHERE player_id = %s AND game_id = %s",
            (player_id, game_id)
        )        
        conn.commit()
    finally:
        cursor.close()
        conn.close()

    await update.message.reply_text(f"Player {nickname} has been removed from the game.")
    return States.GAME_ACTIONS

async def handle_remove_player_from_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("handle_remove_player_from_game called")
    query = update.callback_query
    await query.answer()

    # Extract player ID from callback data
    player_id = int(query.data.split('_')[-1])
    game_id = context.user_data.get('selected_game_id')

    try:
        # Remove the player's registration for the game
        conn = connect_db()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM registrations WHERE player_id = %s AND game_id = %s", (player_id, game_id))
        conn.commit()
    finally:
        cursor.close()
        conn.close()

    await query.edit_message_text(f"Player has been removed from the game.")
    await show_game_details_by_game_id(game_id, context)
    return States.GAME_ACTIONS
    
async def handle_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Operation canceled. Returning to Admin Menu.")
    return States.GAME_ACTIONS  # Or the appropriate state
    
async def send_game_actions_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends the GAME_ACTIONS menu to the user."""
    keyboard = [
        ['Edit Game', 'Cancel Game', 'Announce Game'],
        ['Register Player', 'Remove Player'],
        ['Back to Admin Menu']
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("Select an action:", reply_markup=reply_markup)
