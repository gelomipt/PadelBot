# registration_handlers.py
import logging

from database import connect_db
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

logger = logging.getLogger(__name__)

# Define conversation states
REGISTER_NAME, REGISTER_LEVEL = range(2)

async def start_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['registration_step'] = 'name'
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("Ввведите свое имя как оно будет показываться в списках игроков:")
    return REGISTER_NAME

async def handle_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        query = update.callback_query
        await query.answer()  # Acknowledge the callback
        message = query.message
    elif update.message:
        message = update.message
    else:
        # Unexpected update type
        return ConversationHandler.END
    step = context.user_data.get('registration_step')
    if step == 'name':
        if update.callback_query:
            # Set the next step
            context.user_data['registration_step'] = 'name'
            await message.reply_text("Пожалуйста, введите ваше имя:")
            return REGISTER_NAME
        else:
            # Store the name provided by the user
            context.user_data['name'] = message.text.strip()
            context.user_data['registration_step'] = 'level'
            await message.reply_text("Ваш уровень игры (Новичок, D-, D, D+, C-, C, C+):")
            return REGISTER_LEVEL
    elif step == 'level':
        level = update.message.text.strip()
        valid_levels = ['Новичок', 'D-', 'D', 'D+', 'C-', 'C', 'C+']
        if level in valid_levels:
            name = context.user_data['name']
            nickname = update.message.from_user.username
            user_id = update.effective_user.id
            chat_id = update.effective_chat.id  # Get chat ID from context

            conn = connect_db()
            cursor = conn.cursor()
            try:
                cursor.execute('''INSERT INTO players (telegram_id, name, nickname, level, chat_id)
                                  VALUES (%s, %s, %s, %s, %s)''',
                               (user_id, name, nickname, level, chat_id))
                conn.commit()
                await message.reply_text("Вы успешно зарегистрированы.")
                logger.info("Registration successful.")
                context.user_data.clear()
            except Exception as e:
                logger.exception("Error during registration")
                await message.reply_text("Ошибка, попробуем еще раз.")
                return ConversationHandler.END
            finally:
                cursor.close()
                conn.close()

#            context.user_data.clear()
            # Proceed to show the player menu
            from menu_handlers import show_player_menu
            await show_player_menu(update, context)
            return ConversationHandler.END
        else:
            await message.reply_text(
                "Неверно указан уровень. Принимаются только такие значения (Новичок, D-, D, D+, C-, C, C+)"
            )
            return REGISTER_LEVEL
    else:
        # If for some reason the step is not set, start over
        context.user_data['registration_step'] = 'name'
        await message.reply_text("Пожалуйста, введите ваше имя:")
        return REGISTER_NAME

async def cancel_registration (update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info(f"Called {cancel_registration.__name__} with context: {context}")
    await update.message.reply_text("Game addition has been canceled.")
    context.user_data.clear()
    return ConversationHandler.END