from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton 
from telegram.error import BadRequest
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters, ConversationHandler
from config import ADMIN_USERNAMES
from constants import States
from database import connect_db
from registration_handlers import start_registration
import logging
#from utils import is_private_chat

logger = logging.getLogger(__name__)



#Start Command Handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info(f"Called {start.__name__} with context: {context}")
    
    # Extract user information in a context-agnostic way
    user = update.effective_user.username
    context.user_data['user_id'] = user
    logger.info(f"Initial user context: {context.user_data}")

    # Determine if we're handling a callback query or a direct message
    if update.callback_query:
        await update.callback_query.answer()
        message = update.callback_query.message
    else:
        message = update.message
    
        # Check if the command is from a private chat
    if message.chat.type == "private":
        await message.reply_text("Добро пожаловать в Падел Бот!")
    else:
        # Ignore the command in public or group chats
        await message.reply_text("The /start command can only be used in private chats with the bot.")
        return ConversationHandler.END
    logger.info(f"Initial user context: {context.user_data}")
    
    # Check if user is admin
    if user in ADMIN_USERNAMES:
        keyboard = [
            [InlineKeyboardButton("\U00002699 Продолжить как Админ", callback_data='enter_admin')],
            [InlineKeyboardButton("\U0001F3BE Продолжить как Игрок", callback_data='enter_player')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await message.reply_text("Падел Бот приветствует тебя. Выбирай маршрут:", reply_markup=reply_markup)
    else:
        await show_player_menu(update, context)

#admin buttons
async def admin_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await show_admin_menu(update, context)
        
#player buttons
async def player_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await show_player_menu(update, context)
        
#buttons
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info(f"Called {button.__name__} with context: {context}")
    
    query = update.callback_query
    await query.answer()

    if query.data == 'enter_admin':
        context.user_data['mode']='admin'
        await show_admin_menu(update, context)
    elif query.data == 'enter_player':
        context.user_data['mode']='player'
        await show_player_menu(update, context)
        
# show_admin_menu function
async def show_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != 'private':
        logger.info("Ignoring message in group chat.")
        return
    logger.info(f"Called {show_admin_menu.__name__} with context: {context}")
    logger.info("show_admin_menu function called")
    context.user_data.clear()

    logger.info(f"User context starting Admin menu: {context.user_data}")

    # Determine if using message or callback
    message = update.message if update.message else update.callback_query.message

    keyboard = [
        [InlineKeyboardButton("\U0001F4C5 Управление играми", callback_data='manage_games')],
        [InlineKeyboardButton("\U0001F4CB Управление игроками", callback_data='manage_players')],
        [InlineKeyboardButton("\U0001F519 Назад в стартовое меню", callback_data='start_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
 
    # Determine the appropriate response method based on the update type
    logger.info("Determining the appropriate response method based on the update type")
    try:
        # Check for a callback query and use `edit_message_text` only if content differs
        if update.callback_query and (message.text != "\U00002699 Меню администратора:" or message.reply_markup != reply_markup):
            await update.callback_query.edit_message_text("\U00002699 Меню администратора:", reply_markup=reply_markup)
        else:
            await message.reply_text("\U00002699 Меню администратора:", reply_markup=reply_markup)
    except BadRequest as e:
        if "Message is not modified" in str(e):
            logger.info("No changes in message; skipping edit.")
        else:
            logging.error("Neither message nor callback_query found in update for show_admin_menu.")
            raise

#show manage games menu
async def show_manage_games_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != 'private':
        logger.info("Ignoring message in group chat.")
        return
    
    logger.info("show_manage_games_menu function called")    
    logging.info(f"Called {show_manage_games_menu.__name__} with context: {context}")
    logger.info(f"Initial user context show_manage_games_menu: {context.user_data}")

    user = update.effective_user.username
    # Clear previous game ID if it exists
    context.user_data.pop('edit_game_id', None)
    context.user_data.pop('selected_game_id', None)
    context.user_data['current_menu'] = 'manage_games_menu'

    logger.info(f"User context show_manage_games_menu after cleaning: {context.user_data}")
    
    if user not in ADMIN_USERNAMES:
        if update.message:
            await update.message.reply_text("You do not have permission to manage games.")
        elif update.callback_query:
            await update.callback_query.answer("You do not have permission to manage games.", show_alert=True)
        return  # Exit if the user is not an admin
        
    keyboard = [
        [InlineKeyboardButton("\U00002795 Добавить новую игру", callback_data='add_new_game')],
        [InlineKeyboardButton("\U0000267E Изменить текущую игру", callback_data='manage_game')],
        [InlineKeyboardButton("\U0001F519 Назад в стартовое меню", callback_data='start_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Use edit_message_text consistently for callback queries
    try:
        # Check for a callback query and update only if content has changed
        if update.callback_query and (update.callback_query.message.text != "Меню управления играми:" or update.callback_query.message.reply_markup != reply_markup):
            await update.callback_query.edit_message_text("Меню управления играми:", reply_markup=reply_markup)
        else:
            await update.message.reply_text("Меню управления играми:", reply_markup=reply_markup)
    except BadRequest as e:
        if "Message is not modified" in str(e):
            logger.info("No changes in message; skipping edit.")
        else:
            raise
    

#manage_players_menu function
async def manage_players_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != 'private':
        logger.info("Ignoring message in group chat.")
        return
    logging.info(f"Called {manage_players_menu.__name__} with context: {context}")
    
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

#show_player_menu function
async def show_player_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != 'private':
        logger.info("Ignoring message in group chat.")
        return
    logging.info(f"Called {show_player_menu.__name__} with context: {context}")
    
    try:
        logger.info("show_player_menu function called")

        # Retrieve user information
        if update.message:
            user = update.message.from_user
            chat_id = update.message.chat_id
        elif update.callback_query:
            user = update.callback_query.from_user
            chat_id = update.callback_query.message.chat_id
        else:
            user = update.effective_user
            chat_id = update.effective_chat.id

        if user is None:
            await context.bot.send_message(
                chat_id=chat_id,
                text="Unable to retrieve user information."
            )
            return

        user_id = user.id
        username = user.username or 'No Username'

        logger.info(f"User ID: {user_id}, Username: {username}")

        # Check if the user is registered
        conn = connect_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM players WHERE telegram_id = %s", (user_id,))
        player = cursor.fetchone()
        cursor.close()
        conn.close()

        if player:
            # User is registered, show player menu
            logger.info(f"User {user_id} is registered")

            keyboard = [
                [InlineKeyboardButton("\U0001F4C5 Зарегистрироваться на игру", callback_data='player_register_for_game')],
                [InlineKeyboardButton("\U0001F4CB Подтвердить регистрацию", callback_data='confirm_registration')],
                [InlineKeyboardButton("\U0001F6AB Отменить регистрацию", callback_data='cancel_registration')],
                [InlineKeyboardButton("\U0001F501 Поменяться регистрацией", callback_data='swap_registration')],
                [InlineKeyboardButton("\U0001F4C3 Посмотреть свои регистрации", callback_data='view_registrations')],
#                [InlineKeyboardButton("\U0001F519 Назад в стартовое меню", callback_data='start__player_menu')] #add logic to add this button for admins to be able to come back for admin menu
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await context.bot.send_message(
                chat_id=chat_id,
                text="Player Menu:",
                reply_markup=reply_markup
            )
            logger.info("Sent player menu to user")
        else:
            # User is not registered, prompt to register
            logger.info(f"User {user_id} is not registered")
            keyboard = [
                [InlineKeyboardButton("\U0001F4DD Зарегистрироваться", callback_data='player_registration')],
                [InlineKeyboardButton("\U0001F519 Назад в стартовое меню", callback_data='start_menu')],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await context.bot.send_message(
                chat_id=chat_id,
                text="Вы не зарегистрированы. Для работы с ботом необходимо зарегистрироваться:",
                reply_markup=reply_markup
            )
            logger.info("Sent registration prompt to user")
    except Exception as e:
        logger.exception("An error occurred in show_player_menu")      
