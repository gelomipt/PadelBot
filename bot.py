from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder, 
    CommandHandler, 
    MessageHandler, 
    CallbackQueryHandler, 
    ContextTypes, 
    filters,
    ConversationHandler
    )

from admin_handlers import (
    add_player_start,
    add_new_game_start,
    add_game_date,
    add_game_start_time,
    add_game_end_time,
    add_game_venue,
    add_game_capacity,
    add_game_cancel,
    ADD_GAME_DATE,
    ADD_GAME_START_TIME,
    ADD_GAME_END_TIME,
    ADD_GAME_VENUE,
    ADD_GAME_CAPACITY,
    edit_existing_game,
    edit_player_start,
    edit_game_cancel,    
    handle_add_player,
    handle_edit_attribute_callback,    
    handle_edit_player_callback, 
    handle_edit_player_attribute_callback,
    handle_edit_game_callback,
    handle_game_creation,
    handle_new_attribute_value,
    handle_new_player_attribute_value,
    handle_remove_confirmation_callback, 
    handle_remove_player_callback,
    handle_remove_player_confirmation_callback,
    handle_remove_game_callback,
    SELECT_GAME_TO_EDIT,
    SELECT_ATTRIBUTE_TO_EDIT,
    EDIT_GAME_ATTRIBUTE_VALUE,    
    remove_game, 
    remove_player_start

)
    
from menu_handlers import (
    start, 
    button, 
    manage_players_menu,
    show_admin_menu, 
    show_manage_games_menu,
    show_player_menu
    )
    
from player_handlers import (
    register_player, 
    register_for_game,
    handle_register_game_callback,
    list_unconfirmed_registrations,
    handle_confirm_registration_callback,
    view_registrations,
    list_unconfirmed_registrations_for_cancellation,
    handle_cancel_registration_callback,
    list_confirmed_registrations_for_swap,
    handle_swap_registration_callback,
    handle_registration,
    register_player,
    handle_game_selection
    )
    
from registration_handlers import (
    start_registration,
    handle_registration,
    REGISTER_NAME,
    REGISTER_LEVEL
)
    
from utils import is_admin, is_registered_player
from config import TOKEN

import logging

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

def main():
    application = ApplicationBuilder().token(TOKEN).build()

    # Command Handlers
    application.add_handler(CommandHandler('start', start))
    
    # Conversation handler for adding a new game
    add_new_game_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^Add New Game$'), add_new_game_start)],
        states={
            ADD_GAME_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_game_date)],
            ADD_GAME_START_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_game_start_time)],
            ADD_GAME_END_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_game_end_time)],
            ADD_GAME_VENUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_game_venue)],
            ADD_GAME_CAPACITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_game_capacity)],
        },
        fallbacks=[CommandHandler('cancel', add_game_cancel)],
    )

    # Conversation handler for editing a game
    edit_game_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^Edit Existing Game$'), edit_existing_game)],
        states={
            SELECT_GAME_TO_EDIT: [CallbackQueryHandler(handle_edit_game_callback, pattern='^edit_game_\\d+$')],
            SELECT_ATTRIBUTE_TO_EDIT: [CallbackQueryHandler(handle_edit_attribute_callback, pattern='^edit_attribute_.*$')],
            EDIT_GAME_ATTRIBUTE_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_new_attribute_value)],
        },
        fallbacks=[CommandHandler('cancel', edit_game_cancel)],
    )
    #registration handler
    registration_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^Register Now$'), start_registration)],
        states={
            REGISTER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_registration)],
            REGISTER_LEVEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_registration)],
        },
        fallbacks=[],
    )
    async def test_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"Callback data received: {query.data}"
    )    
    application.add_handler(edit_game_handler)

    application.add_handler(add_new_game_handler)

    # Callback Query Handlers
    application.add_handler(CallbackQueryHandler(button))
    application.add_handler(CommandHandler('start', start))
    application.add_handler(registration_handler)
#    application.add_handler(CallbackQueryHandler(fallback_callback))

    application.add_handler(CallbackQueryHandler(test_callback, pattern='.*'))
    application.add_handler(CallbackQueryHandler(handle_game_selection, pattern='^select_game_\\d+$'))
    
    application.add_handler(CallbackQueryHandler(handle_register_game_callback, pattern=r'^register_game_\d+$'))
    application.add_handler(CallbackQueryHandler(handle_confirm_registration_callback, pattern=r'^confirm_registration_\d+$'))
    application.add_handler(CallbackQueryHandler(handle_cancel_registration_callback, pattern=r'^cancel_registration_\d+$'))
    application.add_handler(CallbackQueryHandler(handle_swap_registration_callback, pattern=r'^swap_registration_\d+$'))
#    application.add_handler(CallbackQueryHandler(handle_edit_game_callback, pattern=r'^edit_game_\d+$'))
#    application.add_handler(CallbackQueryHandler(handle_edit_attribute_callback, pattern=r'^edit_attr_.*'))
    application.add_handler(CallbackQueryHandler(handle_remove_game_callback, pattern=r'^remove_game_\d+$'))
    application.add_handler(CallbackQueryHandler(handle_remove_confirmation_callback, pattern=r'^confirm_remove_.*'))

    application.add_handler(CallbackQueryHandler(handle_edit_player_callback, pattern=r'^edit_player_\d+$'))
    application.add_handler(CallbackQueryHandler(handle_edit_player_attribute_callback, pattern=r'^edit_player_attr_.*'))
    application.add_handler(CallbackQueryHandler(handle_remove_player_callback, pattern=r'^remove_player_\d+$'))
    application.add_handler(CallbackQueryHandler(handle_remove_player_confirmation_callback, pattern=r'^confirm_remove_player_.*'))

    application.add_handler(CallbackQueryHandler(handle_edit_game_callback, pattern=r'^edit_game_\d+$'))
    application.add_handler(CallbackQueryHandler(handle_remove_game_callback, pattern=r'^remove_game_\d+$'))
    application.add_handler(CallbackQueryHandler(handle_remove_confirmation_callback, pattern=r'^confirm_remove_.*'))
    application.add_handler(CallbackQueryHandler(handle_add_player, pattern=r'^add_player\d+$'))                    # ?
    application.add_handler(CallbackQueryHandler(handle_register_game_callback, pattern=r'^register_to_game\d+$'))  # ?
    application.add_handler(CallbackQueryHandler(handle_registration, pattern=r'^register\d+$'))                    # ?
    application.add_handler(CallbackQueryHandler(handle_game_creation, pattern=r'^create_new_game\d+$'))                    # ?

    
# Message Handlers 
    application.add_handler(MessageHandler(filters.Regex('^Manage Games$'), show_manage_games_menu))
    application.add_handler(MessageHandler(filters.Regex('^Add New Game$'), add_new_game_start))

    application.add_handler(MessageHandler(filters.Regex('^Player Menu$'), show_player_menu))
    application.add_handler(MessageHandler(filters.Regex('^Back to Main Menu$'), start))
    application.add_handler(MessageHandler(filters.Regex('^Register for the Game$'), register_for_game))

#    application.add_handler(MessageHandler(filters.Regex('^Manage Games Schedule$'), show_manage_games_menu))

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_game_creation))

    application.add_handler(MessageHandler(filters.Regex('^Register$'), register_player))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_registration))


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
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_new_attribute_value))

    application.add_handler(MessageHandler(filters.Regex('^Edit Existing Game$'), edit_existing_game))
    application.add_handler(MessageHandler(filters.Regex('^Remove Game$'), remove_game))

    application.add_handler(MessageHandler(filters.Regex('^Back to Admin Menu$'), show_admin_menu))

    # ... other handlers ...

    application.run_polling()



if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        logging.error(f"An error occurred: {e}")