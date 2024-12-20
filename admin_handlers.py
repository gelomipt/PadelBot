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
from menu_handlers import show_admin_menu, show_manage_games_menu
from database import connect_db, get_player_by_nickname, update_game_attribute
from config import ADMIN_USERNAMES, DEDICATED_CHAT_ID
from enum import IntEnum
from utils import get_game_data, send_game_status_update, day_of_week_in_russian, list_venues #, is_private_chat

from constants import States

logger.info(f"In admin_handlers.py, SELECT_GAME id: {id(States.SELECT_GAME)}")

# Conversation states
ADD_GAME_DATE, ADD_GAME_START_TIME, ADD_GAME_END_TIME, ADD_GAME_VENUE, ADD_GAME_CAPACITY = range(5)
EDIT_GAME, EDIT_ATTRIBUTE, EDIT_ATTRIBUTE_VALUE, EDIT_GAME_VENUE = range(4)
REGISTER_PLAYER, CONFIRM_ALIAS, ENTER_ALIAS = range(3)
REMOVE_PLAYER_SELECT, REMOVE_PLAYER_CONFIRM = range(2)

async def add_new_game_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info("Starting new game creation")
    query = update.callback_query
    await query.answer()
    user = query.from_user.username

    if user not in ADMIN_USERNAMES:
        await query.edit_message_text("You do not have permission to add games.")
        return ConversationHandler.END
    
    await query.message.reply_text("Дата игры (ГГГГ-ММ-ДД):")
    return ADD_GAME_DATE

async def add_game_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info(f"Called {add_game_date.__name__} with context: {context}")
    date_text = update.message.text
    
    try:
        datetime.datetime.strptime(date_text, '%Y-%m-%d')
        context.user_data['event_date'] = date_text
        await update.message.reply_text("Время начала (ЧЧ:ММ):")
        return ADD_GAME_START_TIME
    except ValueError:
        await update.message.reply_text("Invalid date format. Please enter the date in YYYY-MM-DD format:")
        return ADD_GAME_DATE
        
    except Exception as e:
        logger.exception("An error (1) occurred in add_game_date.")
        await update.message.reply_text("An unexpected error (1) occurred. Please try again later.")
        return ConversationHandler.END

async def add_game_start_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info(f"Called {add_game_start_time.__name__} with context: {context}")  
    time_text = update.message.text
    logger.info(f"add_game_start_time function called")

    try:
        datetime.datetime.strptime(time_text, '%H:%M')
        context.user_data['start_time'] = time_text
        await update.message.reply_text("Время окончания игры (ЧЧ:ММ в 24-часовом формате):")
        return ADD_GAME_END_TIME    
    except ValueError:
        await update.message.reply_text("Invalid time format. Please enter the start time in HH:MM format:")
        return ADD_GAME_START_TIME

async def add_game_end_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info(f"Called {add_game_end_time.__name__} with context: {context}")
    time_text = update.message.text
    try:
        datetime.datetime.strptime(time_text, '%H:%M')
        context.user_data['end_time'] = time_text
        await list_venues(update, context)
        return ADD_GAME_VENUE    
    except ValueError:
        await update.message.reply_text("Invalid time format. Please enter the end time in HH:MM format:")
        return ADD_GAME_END_TIME

async def add_game_venue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Called {add_game_venue.__name__} with context: {context}")
    # Trigger the list of available venues for the user to select
    await list_venues(update, context)
    return ADD_GAME_VENUE

async def add_game_venue_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Called {add_game_venue_selection.__name__} with context: {context}")
    query = update.callback_query
    await query.answer()
    # Extract the venue ID from callback data
    venue_id = int(query.data.split('_')[-1])
    context.user_data['venue_id'] = venue_id
    logger.info(f"Selected venue ID: {venue_id}")
    await query.message.reply_text("Количество игроков:")
    return ADD_GAME_CAPACITY

async def add_game_capacity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info(f"Called {add_game_capacity.__name__} with context: {context}")
    capacity_text = update.message.text
    if not capacity_text.isdigit():
        await update.message.reply_text("Количество участников должно быть числом. Введи число:")
        return ADD_GAME_CAPACITY
    
    capacity = int(capacity_text)
    context.user_data['capacity'] = capacity

        # Insert the game into the database
    try:
        conn = connect_db()
        cursor = conn.cursor()
        cursor.execute(
            '''INSERT INTO schedule (event_date, start_time, end_time, venue_id, capacity)
               VALUES (%s, %s, %s, %s, %s)''',
            (
                context.user_data["event_date"],
                context.user_data["start_time"],
                context.user_data["end_time"],
                context.user_data["venue_id"],
                context.user_data["capacity"],
            )
        )
        conn.commit()
        await update.message.reply_text("Новая игра успешно добавлена.")
    except Exception as e:
        logging.error(f"Error adding game: {e}")
        await update.message.reply_text("Произошла ошибка при добавлении игры. Попробуйте снова.")
    finally:
        cursor.close()
        conn.close()
    context.user_data.clear()
    await show_admin_menu(update, context)  # End the conversation
    return ConversationHandler.END

async def add_game_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info(f"Called {add_game_cancel.__name__} with context: {context}")
    await update.message.reply_text("Game addition has been canceled.")
    context.user_data.clear()
    return await show_admin_menu(update, context)

#Remove game function
async def remove_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info(f"Called {remove_game.__name__} with context: {context}")
    
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
    logging.info(f"Called {handle_remove_game_callback.__name__} with context: {context}")
    
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
    logging.info(f"Called {handle_remove_confirmation_callback.__name__} with context: {context}")
    
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
    logging.info(f"Called {add_player_start.__name__} with context: {context}")
    
    user = update.message.from_user.username
    if user not in ADMIN_USERNAMES:
        await update.message.reply_text("You do not have permission to add players.")
        return

    await update.message.reply_text("Имя игрока:")

#Handle Player Addition Steps
async def handle_add_player(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info(f"Called {handle_add_player.__name__} with context: {context}")
    
    step = context.user_data.get('add_player_step')
    if not step:
        return  # Not in the process of adding a player

    if step == 'name':
        context.user_data['player_name'] = update.message.text
        await update.message.reply_text("Nickname игрока в Telegram:")
    elif step == 'nickname':
        context.user_data['player_nickname'] = update.message.text
        await update.message.reply_text("Уровень игрока (Novice, D-, D, D+, C-, C, C+):")
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
    logging.info(f"Called {edit_player_start.__name__} with context: {context}")
    
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
    logging.info(f"Called {handle_edit_player_callback.__name__} with context: {context}")
    
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
    logging.info(f"Called {handle_edit_player_attribute_callback.__name__} with context: {context}")
    
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
        'name': "Новое имя:",
        'nickname': "Новый ник в Telegram:",
        'level': "Новый уровень (Novice, D-, D, D+, C-, C, C+):"
    }

    prompt = attribute_prompts.get(attribute, "Invalid attribute.")
    if prompt == "Invalid attribute.":
        await query.edit_message_text("Invalid attribute selected.")
        return

    await query.edit_message_text(prompt)

#Handle New Attribute Value
async def handle_new_player_attribute_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info(f"Called {handle_new_player_attribute_value.__name__} with context: {context}")

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
    logging.info(f"Called {remove_player_start.__name__} with context: {context}")
    
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
    logging.info(f"Called {handle_remove_player_callback.__name__} with context: {context}")
    
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
    logging.info(f"Called {handle_remove_player_confirmation_callback.__name__} with context: {context}")
    
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
    logger.info(f"Called {handle_edit_game_callback.__name__} with context: {context}")  
    logger.info("handle_edit_game_callback called")

    query = update.callback_query
    await query.answer()  # Acknowledge the callback

    user=query.from_user.username
    if not user or user not in ADMIN_USERNAMES:
        await query.edit_message_text("You do not have permission to edit games.")
        return ConversationHandler.END
    
    # Extract game ID from callback data
    game_id = int(query.data.split('_')[-1])
    context.user_data['edit_game_id'] = game_id  # Store game ID      
    if not game_id:
        await query.message.reply_text("No game selected. Please select a game first.")
        return await show_manage_games_menu(update, context) # Exit if no game is selected   
    game = await get_game_data(game_id)
    if not game:
        await query.message.reply_text("Game not found.")
        await show_manage_games_menu(update, context)
    
    # Select the attribute to edit, and store that as well
    logger.info(f"User context after selecting attribute in handle_edit_game_callback: {context.user_data}")
        
    await display_attribute_selection_menu(update, context)
    return EDIT_ATTRIBUTE # Return the next state

#Handle Attribute Selection            
async def handle_edit_attribute_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Called {handle_edit_attribute_callback.__name__} with context: {context}")
    logger.info("handle_edit_attribute_callback called")

    query = update.callback_query  
    await query.answer()  # Acknowledge the callback

    attribute = query.data[len('edit_attr_'):]
    logger.info(f"Attribute extracted: {attribute}")
    context.user_data['edit_attribute'] = attribute

    if attribute == 'venue':
        # Trigger venue selection for editing
        await edit_game_venue(update, context)
        return EDIT_GAME_VENUE

    if attribute == 'finish':
        # Clear the editing state and exit
        context.user_data.clear()
        await query.message.reply_text("Редактирование завершено.")
        await show_manage_games_menu(update, context)  # Exit the conversation
        return ConversationHandler.END

    # Clear user_data
    attribute_prompts = {
        'event_date': "Новый день игры (ГГГГ-ММ-ДД):",
        'start_time': "Новое начало игры (ЧЧ:MM):",
        'end_time': "Новое время окончания (ЧЧ:MM):",
        'venue': "Новая площадка:",
        'capacity': "Новое количество игроков:"
    }
    prompt = attribute_prompts.get(attribute)
    await query.message.reply_text(prompt)
    logger.info(f"Prompting user to edit attribute {attribute} for game_id {context.user_data['edit_game_id']}")
    return EDIT_ATTRIBUTE_VALUE

async def edit_game_venue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Called {edit_game_venue.__name__} with context: {context}")
    # Trigger the list of available venues for the user to select
    await list_venues(update, context)
    return EDIT_GAME_VENUE

async def edit_game_venue_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Called {edit_game_venue_selection.__name__} with context: {context}")
    query = update.callback_query
    await query.answer()
    # Extract the venue ID from callback data
    venue_id = int(query.data.split('_')[-1])
    context.user_data['venue_id'] = venue_id
    game_id = context.user_data.get('edit_game_id')
    logger.info(f"Selected venue ID for editing: {venue_id}")
    
    # Update the venue for the selected game in the database
    conn = connect_db()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("UPDATE schedule SET venue_id = %s WHERE id = %s", (venue_id, game_id))
        conn.commit()
        await query.message.reply_text("Место проведения игры успешно обновлено.")
    except Exception as e:
        logger.exception("Error updating game venue")
        await query.message.reply_text("Произошла ошибка при обновлении места проведения. Пожалуйста, попробуйте позже.")
    finally:
        cursor.close()
        conn.close()

    # Return to the attribute selection menu
    await display_attribute_selection_menu(update, context)
    return EDIT_ATTRIBUTE

async def handle_new_attribute_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Called {handle_new_attribute_value.__name__} with context: {context}")
    logger.info("handle_new_attribute_value called")
    
    new_value = update.message.text
    game_id = context.user_data['edit_game_id']
    attribute = context.user_data['edit_attribute']

    if not attribute:
        await update.message.reply_text("No attribute selected. Please start over.")
        return EDIT_ATTRIBUTE  # Return to attribute selection  
    if not game_id:
        await update.message.reply_text("No game selected. Please start over.")
        await show_manage_games_menu(update, context)
        return ConversationHandler.END  # Return to SELECT_GAME state
        
        # Example: Update the database with the new value
    update_successful = await update_game_attribute(game_id, attribute, new_value)
    if update_successful:
        await update.message.reply_text(f"{attribute.replace('_', ' ').capitalize()} успешно обновлен.")
    else:
        await update.message.reply_text("Failed to update the attribute. Please try again.")
        return EDIT_ATTRIBUTE_VALUE  # Prompt the user to enter the value again
    # Display the attribute selection menu again
    await display_attribute_selection_menu(update, context)
    return EDIT_ATTRIBUTE

async def display_attribute_selection_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Displaying attribute selection menu")
    
    game_id = context.user_data.get('edit_game_id')
    if not game_id:
        await update.message.reply_text("No game selected. Please start over.")
        return ConversationHandler.END

    # Fetch game details
    game = await get_game_data(game_id)
    if not game:
        await update.message.reply_text("Game not found.")
        return ConversationHandler.END
    # Handle the case where the venue might be missing
    venue_name = game.get('venue_name', 'Не указано')

    # Create the attribute selection menu
    keyboard = [
        [InlineKeyboardButton(f"Дата игры: {game['event_date']}", callback_data='edit_attr_event_date')],
        [InlineKeyboardButton(f"Начало в: {str(game['start_time'])[:-3]}", callback_data='edit_attr_start_time')],
        [InlineKeyboardButton(f"Игра до: {str(game['end_time'])[:-3]}", callback_data='edit_attr_end_time')],
        [InlineKeyboardButton(f"Клуб: {venue_name}", callback_data='edit_attr_venue')],
        [InlineKeyboardButton(f"{game['capacity']} игроков", callback_data='edit_attr_capacity')],
        [InlineKeyboardButton("Завершить редактирование", callback_data='edit_attr_finish')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Determine whether to edit the existing message or send a new one
    if update.callback_query:
        await update.callback_query.edit_message_text("Выберите атрибут для редактирования:", reply_markup=reply_markup)
    else:
        await update.message.reply_text("Выберите атрибут для редактирования:", reply_markup=reply_markup)
    
    return EDIT_ATTRIBUTE

async def cancel_edit_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Редактирование игры отменено.")
    context.user_data.clear()
    return ConversationHandler.END

async def edit_game_finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Called {edit_game_finish.__name__} with context: {context}")
    logger.info("edit_game_finish called")
    
#    if update.callback_query:
    query = update.callback_query
    await query.answer()
    
    # Fetch the updated game details
    game_id = context.user_data.get('edit_game_id')
    if not game_id:
        await query.message.reply_text("No game selected. Please select a game first.")
        return ConversationHandler.END #States.GAME_ACTIONS  # Or handle accordingly        
    
    # Fetch game data from the database
    game = await get_game_data(game_id)
    if not game:
        await query.message.reply_text("Game not found.")
        return ConversationHandler.END #States.GAME_ACTIONS  # Or handle accordingly

    try:
        conn = connect_db()
        cursor = conn.cursor(dictionary=True)
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
#            main_count, waiting_count = registration  # Unpack the tuple values directly

    finally:
        cursor.close()
        conn.close()

    # Format and send the updated game details
    game_info = (
        f"📢 **Анонс предстоящей игры в {day_of_week_in_russian(game['event_date'])}** 📢\n\n"
        f"📍 **Venue**: {game['venue']}\n"   
        f"📅 **Date**: {game['event_date_str']}\n"
        f"🕒 **Time**: {game['start_time_str']} - {game['end_time_str']}\n"
        f"👥 **Capacity**: {game['capacity']} players\n"
        f"👤 **Registered**: {main_count} ({waiting_count} in waiting list)"
    )        
    # Add URL if it exists
    if game.get('url'):
        game_info += f"🌐 [Game URL]({game['url']})\n"
        
#       await query.message.reply_text(game_info, parse_mode='Markdown')
    await context.bot.send_message(chat_id=DEDICATED_CHAT_ID, text=game_info, parse_mode='Markdown')
    await send_game_status_update (game_id, context)
    await query.message.reply_text(f"Game editing finished.\n\n{game_info}")

    
    # Clear context data
    context.user_data.clear()        
    logger.info("Editing finished and context cleared.")
    return ConversationHandler.END #States.GAME_ACTIONS  # Or handle accordingly
    # Return to "Edit Existing Games" menu

#Handle Game Creation Steps
async def handle_game_creation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info(f"Called {handle_game_creation.__name__} with context: {context}")
    
    step = context.user_data.get('game_creation_step')

    if step == 'event_date':
        context.user_data['event_date'] = update.message.text
        await update.message.reply_text("Время начала (ЧЧ:ММ):")
    elif step == 'start_time':
        context.user_data['start_time'] = update.message.text
        await update.message.reply_text("Время окончания (ЧЧ:ММ):")
    elif step == 'end_time':
        context.user_data['end_time'] = update.message.text
        await update.message.reply_text("Площадка:")
    elif step == 'venue':
        context.user_data['venue'] = update.message.text
        await update.message.reply_text("Количество игроков:")
    elif step == 'capacity':
        try:
            capacity = int(update.message.text)  # Ensure capacity is an integer
            context.user_data["capacity"] = capacity
            await update.message.reply_text("Ссылка на локацию:")
        except ValueError:
            await update.message.reply_text("Please enter a valid number for capacity.")
            return  # Stay in this step if input is invalid
    elif step == 'url':
        url = update.message.text
        try:
            capacity = context.user_data['capacity']
            event_date = context.user_data['event_date']
            start_time = context.user_data['start_time']
            end_time = context.user_data['end_time']
            venue = context.user_data['venue']

            conn = connect_db()
            cursor = conn.cursor()
            cursor.execute('''INSERT INTO schedule (event_date, start_time, end_time, venue, capacity, url)
                              VALUES (%s, %s, %s, %s, %s, %s)''',
                           (event_date, start_time, end_time, venue, capacity, url))
            conn.commit()
            await update.message.reply_text("New game has been added successfully. (handle_game_creation)")
        finally:
            cursor.close()
            conn.close()
    context.user_data.clear()

async def cancel_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info(f"Called {cancel_game.__name__} with context: {context}")
    
     # Get the callback query if present
    query = update.callback_query
    await query.answer()  # Acknowledge the callback query
    
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
        success_message = "Игра успешно удалена."
    except Exception as e:
        logging.error(f"Failed to delete game: {e}")
        success_message = "Не удалось удалить игру. Попробуйте еще раз."
    finally:
        cursor.close()
        conn.close()
    
    if query:
        await query.message.reply_text(success_message)  # Use callback query message if available
    else:
        await update.message.reply_text(success_message)  # Fallback to update.message if no callback query
    
    # Notify chat if players were registered
    if registered_count > 0:
        # Send announcement in chat about game cancellation
        await context.bot.send_message(
            chat_id=DEDICATED_CHAT_ID,
            text=f"Игра {game['event_date']} в {game['venue']} отменена.", parse_mode='Markdown'
        )
        
    return await manage_games_menu(update, context)

async def remove_player_from_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info(f"Called {remove_player_from_game.__name__} with context: {context}")
    """Remove a player from the selected game."""
    await update.callback_query.edit_message_text("Введите ник игрока для отмены регистрации:")

async def manage_games_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Called {manage_games_menu.__name__} with context: {context}")
    logger.info(f"Initial user context manage_games_menu: {context.user_data}")
    # Clear context data
    context.user_data.clear()
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
            SELECT s.id, s.event_date, s.start_time, v.short_name as venue_name, s.capacity
            FROM schedule s
            JOIN venue v ON s.venue_id = v.id
            WHERE event_date >= CURDATE() AND finished IS NULL
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
        return #ConversationHandler.END

#    end_time_str = game['end_time'].strftime('%H-%M') if isinstance(game['end_time'], datetime.time) else str(game['end_time'])

    keyboard = []
    for game in games:
        start_time_str = game['start_time'].strftime('%H:%M') if isinstance(game['start_time'], datetime.time) else str(game['start_time'])[:-3]
        callback_data = f"game_for_edit_select_{game['id']}"
        logger.info(f"Sending callback_data: {callback_data}")
        button_text = (
            f"{game['event_date']} в {game['venue_name']}, старт в {start_time_str} на {game['capacity']}"
        )
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
    
    keyboard.append([InlineKeyboardButton('\U0001F519 Назад ', callback_data='go_back')])

    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        await update.message.reply_text("Выбери игру для редактирования:", reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.edit_message_text("Выбери игру для редактирования:", reply_markup=reply_markup)
        
    logger.info(f"After preparing reply manage_games_menu, context: {context.user_data}")
    
async def show_game_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Called {show_game_details.__name__} with context: {context}")  
    logger.info(f"Initial user context show_game_details: {context.user_data}")

    """Show selected game details and options for actions."""
    logger.info("show_game_details function called")
    query = update.callback_query
    await query.answer()
    
    game_id = int(query.data.split('_')[-1])
    context.user_data['selected_game_id'] = game_id
    
    logger.info(f"User context show_game_details after update: {context.user_data}")
    
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
            await query.message.reply_text("Game not found.")
            return show_admin_menu

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
        f"Игра в {game['event_date']} в {day_of_week_in_russian(game['event_date'])}\n"
        f"В {game['venue_name']}\n"
        f"Игра с {str(game['start_time'])[:-3]} до {str(game['end_time'])[:-3]}\n"
        f"Зарегистрировано: {main_count} из {game['capacity']}\n"
        f"Лист ожидания: {waiting_count}\n"
        f"{game['venue_url']}"
    )
    keyboard = [
        [InlineKeyboardButton("\U0001F4DD Редактировать игру", callback_data = f"edit_game_{game_id}")],
        [InlineKeyboardButton("\U000026D4 Отменить игру", callback_data=f"cancel_game_{game_id}")],
        [InlineKeyboardButton("\U0001F4E2 Отправить анонс в чат", callback_data=f"announce_game_{game_id}")],
        [InlineKeyboardButton("\U00002714 Зарегистрировать игрока", callback_data=f"register_player_for_game_{game_id}")],
        [InlineKeyboardButton("\U0000274C Удалить игрока из регистрации", callback_data=f"unregister_player_from_game_{game_id}")],
        [InlineKeyboardButton("\U0001F519 Назад", callback_data='go_back')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text(game_info, reply_markup=reply_markup)
    logger.info(f"Final user context show_game_details: {context.user_data}")

async def show_game_details_by_game_id(update: Update, game_id, context: ContextTypes.DEFAULT_TYPE):
    logging.info(f"Called {show_game_details_by_game_id.__name__} with context: {context}")
    
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
    return 
    
async def register_player_for_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info(f"Called {register_player_for_game.__name__} with context: {context}")
    """Register a player for the selected game."""
    # Prompt admin to enter player's username for registration
    await update.callback_query.edit_message_text("Введите ник игрока для продолжения регистрации:")

async def start_register_player(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Called {start_register_player.__name__} with context: {context}")
    logger.info("start_register_player called")
    query = update.callback_query
    await query.answer()
    # Extract game ID from callback data
    game_id = int(query.data.split('_')[-1])
    context.user_data['selected_game_id'] = game_id
    logger.info(f"Game ID set for registration: {game_id}")
    await query.message.reply_text("Введите ник игрока в Telegram (без @) для продолжения регистрации:")
    return REGISTER_PLAYER
   
async def handle_register_player_1(update: Update, context: ContextTypes.DEFAULT_TYPE):   
    logger.info(f"Called {handle_register_player.__name__} with context: {context}")    
    logger.info("handle_register_player called")
    
    game_id = context.user_data.get('selected_game_id')
    nickname = update.message.text.strip()
    if not nickname:
        await update.message.reply_text("Телеграм ник не может быть пустым. Пожалуйста, попробуйте снова.")
        return REGISTER_PLAYER

    conn = connect_db()
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("SELECT id FROM players WHERE nickname = %s", (nickname,))
        result = cursor.fetchone()   
        
        if not result:
            await update.message.reply_text("Игрок не наден. Пожалуйста, попробуйте снова.")
            return REGISTER_PLAYER

        player_id = result['id']
        context.user_data['player_id'] = player_id
        # Check if the user is already registered for this game
        cursor.execute("SELECT * FROM registrations WHERE game_id = %s AND player_id = %s", (game_id, player_id))
        existing_registration = cursor.fetchall()
        if existing_registration:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Игрок уже зарегистирован.Зарегистрировать его еще раз с другим именем? (да/нет)"
            )
            return CONFIRM_ALIAS  
        # Proceed with registration
        await register_player_logic(update, context, conn, cursor, player_id, game_id)
        return REGISTER_PLAYER  # Allow user to register more players instead of ending conversation
    except Exception as e:
        logger.exception("Error in handle_register_player")
        await update.message.reply_text("Произошла ошибка при регистрации. Пожалуйста, попробуйте позже.")
        return REGISTER_PLAYER  # Allow user to register more players instead of ending conversation
        
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

async def handle_register_player(update: Update, context: ContextTypes.DEFAULT_TYPE):   
    logger.info(f"Called {handle_register_player.__name__} with context: {context}")    
    logger.info("handle_register_player called")
    
    game_id = context.user_data.get('selected_game_id')
    nickname = update.message.text.strip()
    if not nickname:
        await update.message.reply_text("Телеграм ник не может быть пустым. Пожалуйста, попробуйте снова.")
        return REGISTER_PLAYER

    conn = connect_db()
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("SELECT id FROM players WHERE nickname = %s", (nickname,))
        result = cursor.fetchone()   
        
        if not result:
            await update.message.reply_text("Игрок не найден. Пожалуйста, попробуйте снова.")
            return REGISTER_PLAYER

        player_id = result['id']
        context.user_data['player_id'] = player_id

        # Check if the user is already registered for this game
        cursor.execute("SELECT * FROM registrations WHERE game_id = %s AND player_id = %s", (game_id, player_id))
        existing_registrations = cursor.fetchall()

        if existing_registrations:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Игрок уже зарегистрирован. Зарегистрировать его еще раз с другим именем? (да/нет)"
            )
            return CONFIRM_ALIAS  

        # Proceed with registration if no existing registration found
        await register_player_logic(update, context, conn, cursor, player_id, game_id)
        return REGISTER_PLAYER  # Allow user to register more players instead of ending conversation

    except Exception as e:
        logger.exception("Error in handle_register_player")
        await update.message.reply_text("Произошла ошибка при регистрации. Пожалуйста, попробуйте позже.")
        return REGISTER_PLAYER  # Allow user to register more players instead of ending conversation
        
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

async def handle_confirm_alias(update: Update, context: ContextTypes.DEFAULT_TYPE):
    response = update.message.text.strip().lower()
    if response in ['да', 'yes']:
        await update.message.reply_text("Пожалуйста, введите псевдоним для игрока:")
        return ENTER_ALIAS
    elif response in ['нет', 'no']:
        await update.message.reply_text("Регистрация отменена. Вы можете ввести другой ник или завершить процесс.")
        return REGISTER_PLAYER
    else:
        await update.message.reply_text("Пожалуйста, ответьте 'да/yes' или 'нет/no'.")
        return CONFIRM_ALIAS

async def handle_enter_alias(update: Update, context: ContextTypes.DEFAULT_TYPE):
    alias = update.message.text.strip()
    if not alias:
        await update.message.reply_text("Псевдоним не может быть пустым. Пожалуйста, введите псевдоним для игрока:")
        return ENTER_ALIAS

    game_id = context.user_data.get('selected_game_id')
    player_id = context.user_data.get('player_id')

    if not game_id or not player_id:
        await update.message.reply_text("Произошла ошибка. Попробуйте снова.")
        return ConversationHandler.END

    # Establish connection and cursor
    conn = connect_db()
    cursor = conn.cursor(dictionary=True)

    try:
        # Proceed with registration using the alias
        await register_player_logic(update, context, conn, cursor, player_id, game_id, alias)
        return ConversationHandler.END

    except Exception as e:
        logger.exception("Error in handle_enter_alias")
        await update.message.reply_text("Произошла ошибка при регистрации. Пожалуйста, попробуйте позже.")
        return ConversationHandler.END

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

async def register_player_logic(update, context, conn, cursor, player_id, game_id, alias=None):
    logger.info("register_player_logic called")
    try:
        # Check if player is already registered for the game with the same alias
        if alias:
            cursor.execute(
                "SELECT * FROM registrations WHERE game_id = %s AND player_id = %s AND alias = %s",
                (game_id, player_id, alias),
            )
        else:
            # If no alias is provided, we treat it as a null value in the database.
            cursor.execute(
                "SELECT * FROM registrations WHERE game_id = %s AND player_id = %s AND alias IS NULL",
                (game_id, player_id),
            )
        existing_registration = cursor.fetchone()

        # Allow multiple registrations under different aliases
        if existing_registration and not alias:
            await update.message.reply_text(
                "Игрок уже зарегистрирован на игру без псевдонима. Пожалуйста, используйте другой псевдоним для повторной регистрации."
            )
            return REGISTER_PLAYER  # Allow the user to enter a different alias

        # Check the current number of non-waiting registrations
        cursor.execute(
            "SELECT COUNT(*) AS count FROM registrations WHERE game_id = %s AND waiting = FALSE", (game_id,)
        )
        current_count = cursor.fetchone()['count']
        if current_count is None:
            current_count = 0

        # Get the game's capacity
        cursor.execute("SELECT capacity FROM schedule WHERE id = %s", (game_id,))
        game = cursor.fetchone()
        if not game:
            await update.message.reply_text("Game not found.")
            return ConversationHandler.END

        capacity = game['capacity']

        if current_count < capacity:
            # Register the player normally
            cursor.execute(
                "INSERT INTO registrations (player_id, game_id, is_confirmed, waiting, alias) VALUES (%s, %s, %s, %s, %s)",
                (player_id, game_id, False, False, alias),
            )
            conn.commit()
            await update.message.reply_text(
                "Игрок зарегистрирован на игру под псевдонимом '{}'. Подтвердить регистрацию он должен сам.".format(alias if alias else "без псевдонима")
            )
        else:
            # Add the player to the waiting list
            cursor.execute(
                "INSERT INTO registrations (player_id, game_id, is_confirmed, waiting, alias) VALUES (%s, %s, %s, %s, %s)",
                (player_id, game_id, False, True, alias),
            )
            conn.commit()
            await update.message.reply_text(
                "Игра заполнена. Игрок добавлен в лист ожидания под псевдонимом '{}'.".format(alias if alias else "без псевдонима")
            )

        # Send the game status update
        await send_game_status_update(game_id, context)

    except Exception as e:
        logger.exception("Error in register_player_logic")
        await update.message.reply_text(
            "An error occurred while processing the registration. Please try again later."
        )

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    # Clear the registration progress flag and context data
    keys_to_clear = ['alias', 'registration_in_progress', 'selected_game_id']
    for key in keys_to_clear:
        context.user_data.pop(key, None)

    # Send the GAME_ACTIONS menu again    
    await manage_games_menu(update, context)
    return ConversationHandler.END

async def cancel_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Регистрация игрока отменена.")
    context.user_data.clear()
    await manage_games_menu(update, context)

async def start_remove_player(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Called {start_remove_player.__name__} with context: {context}")
    logger.info("start_remove_player called")
    await update.message.reply_text("Для удаления игрока, введите его ник в Telegram (без @)")
    return
    
async def start_remove_player_from_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Called {start_remove_player_from_game.__name__} with context: {context}")  
    logger.info("start_remove_player called")

    query = update.callback_query
    await query.answer()    

    # Fetch registered players for the selected game
    game_id = context.user_data.get('selected_game_id')
    if not game_id:
        await update.message.reply_text("No game selected. Please select a game first.")
        return ConversationHandler.END
    
    conn = connect_db()
    cursor = conn.cursor(dictionary=True)    
    try:
        cursor.execute("""
            SELECT r.id AS registration_id, p.nickname, r.waiting, r.alias
            FROM registrations r
            JOIN players p ON r.player_id = p.id
            WHERE r.game_id = %s
            ORDER BY r.waiting, r.id           
        """, (game_id,))
        players = cursor.fetchall()

        if not players:
            await query.message.reply_text("На эту игру еще нет зарегистрированных игроков.")
            return ConversationHandler.END
                
        keyboard = []
        for player in players:
            status = "Ожидает" if player['waiting'] else "Подтвержден"
            alias = player['alias'] if player['alias'] else None
            display_name = player['nickname']
            button_text = f"@{display_name} {alias} ({status})"
            callback_data = f"remove_player_confirm_{player['registration_id']}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text("Выберите игрока для удаления:", reply_markup=reply_markup)
        return REMOVE_PLAYER_SELECT
    except Exception as e:
        logger.exception("Error in start_remove_player_from_game")
        await query.message.reply_text("Произошла ошибка при получении списка игроков. Пожалуйста, попробуйте позже.")
        return ConversationHandler.END
    finally:
        cursor.close()
        conn.close()

async def handle_remove_player_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Called {handle_remove_player_selection.__name__} with context: {context}")
    logger.info("handle_remove_player_selection called")
    
    query = update.callback_query
    await query.answer()
    
    # Extract registration ID from callback data
    registration_id = int(query.data.split('_')[-1])
    context.user_data['registration_id_to_remove'] = registration_id
    
    # Optionally, ask for confirmation
    keyboard = [
        [
            InlineKeyboardButton("Да", callback_data="confirm_remove_player_yes"),
            InlineKeyboardButton("Нет", callback_data="confirm_remove_player_no")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text("Вы уверены, что хотите удалить этого игрока?", reply_markup=reply_markup)
    return REMOVE_PLAYER_CONFIRM

async def handle_remove_player_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Called {handle_remove_player_confirmation.__name__} with context: {context}")
    logger.info("handle_remove_player_confirmation called")
    
    query = update.callback_query
    await query.answer()
    
    if query.data == "confirm_remove_player_yes":
        registration_id = context.user_data.get('registration_id_to_remove')
        if not registration_id:
            await query.message.reply_text("Произошла ошибка. Попробуйте снова.")
            return ConversationHandler.END
        
        conn = connect_db()
        cursor = conn.cursor(dictionary=True)
        
        try:
            # Remove the player from the registrations
            cursor.execute("DELETE FROM registrations WHERE id = %s", (registration_id,))
            conn.commit()
            
            # After deleting the player
            # Check if there's space in the game
            cursor.execute("SELECT capacity FROM schedule WHERE id = %s", (game_id,))
            capacity = cursor.fetchone()['capacity']

            # Count current confirmed registrations
            cursor.execute("SELECT COUNT(*) AS count FROM registrations WHERE game_id = %s AND waiting = FALSE", (game_id,))
            current_count = cursor.fetchone()['count']

            if current_count < capacity:
                # Move the next player from waiting list to confirmed
                cursor.execute("""
                    UPDATE registrations
                    SET waiting = FALSE
                    WHERE id = (
                        SELECT id FROM registrations
                        WHERE game_id = %s AND waiting = TRUE
                        ORDER BY id ASC
                        LIMIT 1
                    )
                """, (game_id,))
                next_waiting_player = cursor.fetchone()
                
                if next_waiting_player:
                    next_registration_id = next_waiting_player['id']
                    cursor.execute("""
                        UPDATE registrations
                        SET waiting = FALSE
                        WHERE id = %s
                    """, (next_registration_id,))
                    conn.commit()
                    
                    # Notify the player that they have been moved from the waiting list
                    cursor.execute("""
                        SELECT p.chat_id
                        FROM registrations r
                        JOIN players p ON r.player_id = p.id
                        WHERE r.id = %s
                    """, (next_registration_id,))
                    player_info = cursor.fetchone()
                    if player_info and player_info['chat_id']:
                        await context.bot.send_message(
                            chat_id=player_info['chat_id'],
                            text="Вы были переведены из листа ожидания в подтвержденные участники игры."
                        )
                conn.commit()         
            await query.message.reply_text("Игрок был удален из игры.")
            
            # Update game status
            game_id = context.user_data.get('selected_game_id')
            await send_game_status_update(game_id, context)
            
            # Clear context data
            context.user_data.clear()
            
            # Return to the game management menu
            await manage_games_menu(update, context)
            return ConversationHandler.END
        
        except Exception as e:
            logger.exception("Error in handle_remove_player_confirmation")
            await query.message.reply_text("Произошла ошибка при удалении игрока. Пожалуйста, попробуйте позже.")
            return ConversationHandler.END
        
        finally:
            cursor.close()
            conn.close()
    
    elif query.data == "confirm_remove_player_no":
        await query.message.reply_text("Удаление отменено.")
        # Optionally, return to the player list to select another player
        await start_remove_player_from_game(update, context)
        return REMOVE_PLAYER_SELECT
    
    else:
        await query.message.reply_text("Неверный выбор. Пожалуйста, попробуйте снова.")
        return REMOVE_PLAYER_CONFIRM

async def handle_remove_player(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Called {handle_remove_player.__name__} with context: {context}")
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
            await update.message.reply_text("Игрок с таким ником не найден.")
            return 

        player_id = result[0]
        player_name = result[1]

        # Remove the player's registration for the game
        cursor.execute(
            "DELETE FROM registrations WHERE player_id = %s AND game_id = %s",
            (player_id, game_id)
        )        
        conn.commit()
    finally:
        cursor.close()
        conn.close()
    await update.message.reply_text(f"Игрок @{nickname} - {player_name}  был удален из игры.")
    await show_manage_games_menu(game_id, context)
    return 

async def handle_remove_player_from_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info(f"Called {handle_remove_player_from_game.__name__} with context: {context}")
    
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
    logging.info(f"Called {handle_cancel_callback.__name__} with context: {context}")
    
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Operation canceled. Returning to Admin Menu.")
    return States.GAME_ACTIONS  # Or the appropriate state
    
async def send_game_actions_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info(f"Called {send_game_actions_menu.__name__} with context: {context}")
    
    """Sends the GAME_ACTIONS menu to the user."""
    keyboard = [
        ['Edit Game', 'Cancel Game', 'Announce Game'],
        ['Register Player', 'Remove Player'],
        ['Back to Admin Menu']
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("Select an action:", reply_markup=reply_markup)