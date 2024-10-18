# registration_handlers.py

from database import connect_db
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
import logging

logger = logging.getLogger(__name__)

# Define conversation states
REGISTER_NAME, REGISTER_LEVEL = range(2)

async def start_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['registration_step'] = 'name'
    await update.message.reply_text("Please enter your full name:")
    return REGISTER_NAME

async def handle_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    step = context.user_data.get('registration_step')

    if step == 'name':
        context.user_data['name'] = update.message.text
        context.user_data['registration_step'] = 'level'
        await update.message.reply_text("Enter your level (Novice, D-, D, D+, C-, C, C+):")
        return REGISTER_LEVEL
    elif step == 'level':
        level = update.message.text.strip()
        valid_levels = ['Novice', 'D-', 'D', 'D+', 'C-', 'C', 'C+']
        if level in valid_levels:
            name = context.user_data['name']
            nickname = update.message.from_user.username
            user_id = update.effective_user.id

            conn = connect_db()
            cursor = conn.cursor()
            try:
                cursor.execute('''INSERT INTO players (telegram_id, name, nickname, level)
                                  VALUES (%s, %s, %s, %s)''',
                               (user_id, name, nickname, level))
                conn.commit()
                await update.message.reply_text("You have been registered successfully.")
                logger.info("Registration successful.")
                context.user_data.clear()
            except Exception as e:
                logger.exception("Error during registration")
                await update.message.reply_text("An error occurred during registration. Please try again.")
                return ConversationHandler.END
            finally:
                cursor.close()
                conn.close()

            context.user_data.clear()
            # Proceed to show the player menu
            await show_player_menu(update, context)
            return ConversationHandler.END
        else:
            await update.message.reply_text(
                "Invalid level. Please enter one of the following: Novice, D-, D, D+, C-, C, C+."
            )
            return REGISTER_LEVEL
    else:
        # If for some reason the step is not set, start over
        await start_registration(update, context)
        return REGISTER_NAME
