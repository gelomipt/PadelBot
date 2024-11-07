from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from config import ADMIN_USERNAMES
from database import connect_db
from registration_handlers import start_registration
import logging

logger = logging.getLogger(__name__)



#Start Command Handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user.username
    context.user_data['user_id']=user
    
        # Check if the command is from a private chat
    if update.message.chat.type == "private":
        await update.message.reply_text("Welcome! You're now chatting with the bot in a private conversation.")
    else:
        # Ignore the command in public or group chats
        await update.message.reply_text("The /start command can only be used in private chats with the bot.")
        return ConversationHandler.END
    logger.info(f"Initial user context: {context.user_data}")
    
    # Check if user is admin
    if user in ADMIN_USERNAMES:
        keyboard = [
            [InlineKeyboardButton("Продолжить как Админ", callback_data='enter_admin')],
            [InlineKeyboardButton("Продолжить как Игрок", callback_data='enter_player')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Падел Бот приветствует тебя. Выбирай маршрут:", reply_markup=reply_markup)
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
    logger.info("show_admin_menu function called")
    
    logger.info(f"User context starting Admin menu: {context.user_data}")
 
    keyboard = [
        ['Manage Games', 'Manage Players'],
        ['Back to Admin Menu']
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    
    if update.callback_query:
        await update.callback_query.answer()
        # Optionally delete the original message
#        await update.callback_query.message.delete()
        # Send a new message with the reply keyboard
        await context.bot.send_message(
            chat_id=update.callback_query.message.chat_id,
            text="Администрирование:",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text("Возможности Администратора:", reply_markup=reply_markup)

#show manage games menu
async def show_manage_games_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("show_manage_games_menu function called")
    logger.info(f"Initial user context show_manage_games_menu: {context.user_data}")

    user = update.effective_user.username
    # Clear previous game ID if it exists
#    context.user_data.pop('edit_game_id', None)
#    context.user_data.pop('selected_game_id', None)

    context.user_data.clear()
    logger.info(f"User context show_manage_games_menu after cleaning: {context.user_data}")
    
    if user not in ADMIN_USERNAMES:
        await update.message.reply_text("You do not have permission to manage games.")
        return

    keyboard = [
        ['Add New Game', 'Edit Existing Game'],
        ['Back to Admin Menu']
    ]

    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    if update.message:
        await update.message.reply_text("Manage Games Menu:", reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.message.reply_text("Manage Games Menu:", reply_markup=reply_markup)
    logger.info(f"Final user context show_manage_games_menu: {context.user_data}")
    

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

#show_player_menu function
async def show_player_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
                ['Register for the Game'],
                ['Confirm Registration for the Game'],
                ['View Your Registrations', 'Cancel Your Registrations'],
                ['Swap Your Confirmed Registration'],
                ['Back to Main Menu']
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

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
                ['Register Now'],
                ['Back to Main Menu']
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            await context.bot.send_message(
                chat_id=chat_id,
                text="You are not registered. Please register to continue:",
                reply_markup=reply_markup
            )
            logger.info("Sent registration prompt to user")
    except Exception as e:
        logger.exception("An error occurred in show_player_menu")
