#!/usr/bin/env python3

import telegram
import logging
import asyncio

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger


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
    edit_game_finish,    
    handle_add_player,
    handle_cancel_callback,
    handle_edit_attribute_callback,    
    handle_edit_player_callback, 
    handle_edit_player_attribute_callback,
    handle_edit_game_callback,
    handle_game_creation,
    handle_new_attribute_value,
    handle_new_player_attribute_value,
    handle_register_player,
    handle_remove_confirmation_callback,
    handle_remove_player,
    handle_remove_player_from_game,    
    handle_remove_player_callback,
    handle_remove_player_confirmation_callback,
    handle_remove_game_callback,
    manage_games_menu,
    remove_game, 
    remove_player_start,
    cancel_game,
    remove_player_from_game,
    register_player_for_game,
    send_game_actions_menu,
    show_game_details,
    show_game_details_by_game_id,
    start_register_player,
    start_remove_player,
    start_remove_player_from_game
    )
    
from menu_handlers import (
    start, 
    button, 
    manage_players_menu,
    show_admin_menu, 
    show_manage_games_menu,
    show_player_menu,
    admin_button,
    player_button
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
    
from utils import (
    is_admin, 
    is_registered_player,
    fallback_callback,
    update_finished_games,
    announce_upcoming_games,
    announce_game,
    handle_unhandled_callback,
    send_update_to_public_chat
)

from config import TOKEN

from constants import States

logger.info(f"In bot.py, SELECT_GAME id: {id(States.SELECT_GAME)}")

async def shutdown(application):
    await application.stop()
    await application.shutdown()

#async def get_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
#    chat_id = update.effective_chat.id
#    print(f"Chat ID: {chat_id}") 

#async def test_send_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
#    from config import DEDICATED_CHAT_ID
#    try:
#        await context.bot.send_message(chat_id=DEDICATED_CHAT_ID, text="Test message from bot.")
#        await update.message.reply_text("Test message sent to the dedicated chat.")
#    except Exception as e:
#        await update.message.reply_text(f"Failed to send message: {e}")
#        logger.exception("Error sending test message.")
        
async def log_unhandled_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.warning(f"Unhandled callback data: {update.callback_query.data}")
    await update.callback_query.answer("Sorry, I didn't understand that action.")
    
 
#registration handler
registration_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex('^Register Now$'), start_registration)],
    states={
        REGISTER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_registration)],
        REGISTER_LEVEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_registration)],
    },
    fallbacks=[],
#        per_message=True  # Ensure this is set       
)

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
#        per_message=True  # Ensure this is set
)

manage_games_handler = ConversationHandler(
    entry_points=[
        MessageHandler(filters.Regex('^Edit Existing Game$'), manage_games_menu), 
#        CallbackQueryHandler(show_manage_games_menu, pattern='^go_back$'),
        ],
    states={
        States.SELECT_GAME: [
            CallbackQueryHandler(show_game_details, pattern=r"^game_for_edit_select_\d+$"),
            CallbackQueryHandler(show_manage_games_menu, pattern='^go_back$'),            
        ],
        States.GAME_ACTIONS: [
            MessageHandler(filters.Regex('^Edit Game$'), handle_edit_game_callback),
            MessageHandler(filters.Regex('^Cancel Game$'), cancel_game),
            MessageHandler(filters.Regex('^Announce Game$'), announce_game),
            MessageHandler(filters.Regex('^Register Player'), start_register_player),
            MessageHandler(filters.Regex('^Unregister Player'), start_remove_player_from_game),
            MessageHandler(filters.Regex('^Back to Admin Menu'), show_admin_menu),
            CallbackQueryHandler(handle_cancel_callback, pattern='^cancel$'),
            CallbackQueryHandler(handle_unhandled_callback, pattern='.*'),  # Catch-all
        ],
        States.SELECT_ATTRIBUTE_TO_EDIT: [
            CallbackQueryHandler(handle_edit_attribute_callback, pattern='^edit_attr_\\w+$'),
            CallbackQueryHandler(show_admin_menu, pattern='^cancel$'),
        ],
        States.EDIT_GAME_ATTRIBUTE_VALUE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_new_attribute_value),
#            CallbackQueryHandler(edit_game_finish, pattern='^edit_attr_finish$'),
        ],
        States.REGISTER_PLAYER: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_register_player),
            CommandHandler('cancel', show_admin_menu)
        ],
        States.REMOVE_PLAYER: [
            CallbackQueryHandler(handle_remove_player_from_game, pattern=r"^game_remove_player_\d+$"),
            CommandHandler('cancel', show_admin_menu)
        ],
    },
    fallbacks=[CommandHandler("cancel", show_admin_menu)],
#    per_message=True  # Ensure this is set

)
    
def main():
    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler('start', start))
    
    # Set up the scheduler
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        announce_upcoming_games,
        IntervalTrigger(minutes=60),
        args=(application,),
        max_instances=1,
        coalesce=True
    )
    scheduler.add_job(
        update_finished_games,
        IntervalTrigger(minutes=60),
        max_instances=1,
        coalesce=True
    )    
    scheduler.start()

 
    # Command Handlers
#    application.add_handler(CallbackQueryHandler(show_game_details, pattern=r"^game_for_edit_select_\d+$"), group=0)

#    application.add_handler(CommandHandler('test_send', test_send_message))
    application.add_handler(CallbackQueryHandler(log_unhandled_callback), group=99)
#    application.add_handler(CallbackQueryHandler(unhandled_callback_query), group=99)


    
    # Register ConversationHandlers and other handlers in higher groups
#    application.add_handler(edit_game_handler, group=0)
    application.add_handler(manage_games_handler, group=0) 
    application.add_handler(add_new_game_handler, group=0)
    application.add_handler(registration_handler, group=0)
#    application.add_handler(CallbackQueryHandler(show_game_details, pattern=r"^game_for_edit_select_\d+$"), group=0)
    application.add_handler(CallbackQueryHandler(admin_button, pattern=r'^enter_admin$'), group=0)
    application.add_handler(CallbackQueryHandler(player_button, pattern=r'^enter_player$'), group=0)
#    application.add_handler(CallbackQueryHandler(show_manage_games_menu, pattern='^go_back$'), group=0)

    
    # Register CallbackQueryHandlers in group -1 
#    application.add_handler(CallbackQueryHandler(fallback_callback), group=-1)
#    application.add_handler(CallbackQueryHandler(test_callback, pattern='.*'), group=-1)

    application.add_handler(CallbackQueryHandler(handle_registration, pattern=r'^register\d+$'), group=-1)  

#    application.add_handler(CallbackQueryHandler(handle_edit_game_callback, pattern=r'^edit_game_\d+$'), group=-1)
    application.add_handler(CallbackQueryHandler(handle_remove_game_callback, pattern=r'^remove_game_\d+$'), group=-1)

    application.add_handler(CallbackQueryHandler(handle_add_player, pattern=r'^add_player\d+$'), group=-1)                    # ?
    application.add_handler(CallbackQueryHandler(handle_edit_player_callback, pattern=r'^edit_player_\d+$'), group=-1)
    application.add_handler(CallbackQueryHandler(handle_edit_player_attribute_callback, pattern=r'^edit_player_attr_.*'), group=-1)
    application.add_handler(CallbackQueryHandler(handle_remove_player_callback, pattern=r'^remove_player_\d+$'), group=-1)
    application.add_handler(CallbackQueryHandler(handle_remove_player_confirmation_callback, pattern=r'^confirm_remove_player_.*'), group=-1)

    application.add_handler(CallbackQueryHandler(handle_register_game_callback, pattern=r'^register_game_\d+$'), group=-1)
    application.add_handler(CallbackQueryHandler(handle_confirm_registration_callback, pattern=r'^confirm_registration_\d+$'), group=-1)
    application.add_handler(CallbackQueryHandler(handle_cancel_registration_callback, pattern=r'^cancel_registration_\d+$'), group=-1)
    application.add_handler(CallbackQueryHandler(handle_swap_registration_callback, pattern=r'^swap_registration_\d+$'), group=-1)
    application.add_handler(CallbackQueryHandler(handle_remove_confirmation_callback, pattern=r'^confirm_remove_.*'), group=-1)
#    application.add_handler(CallbackQueryHandler(handle_edit_attribute_callback, pattern=r'^edit_attr_.*'), group=-1)
    
#    application.add_handler(CallbackQueryHandler(show_admin_menu, pattern=r'^enter_admin*'), group=-1)
    
    # Message Handlers in group 1
    application.add_handler(CallbackQueryHandler(handle_game_selection, pattern='^select_game_\\d+$'), group=1)
#    application.add_handler(CallbackQueryHandler(button), group=1)
   
    application.add_handler(MessageHandler(filters.Regex('^Manage Games$'), show_manage_games_menu), group=1)
    application.add_handler(MessageHandler(filters.Regex('^Manage Players$'), manage_players_menu), group=1)
    application.add_handler(MessageHandler(filters.Regex('^Back to Admin Menu$'), show_admin_menu), group=1)

    application.add_handler(MessageHandler(filters.Regex('^Remove Game$'), remove_game), group=1)
    application.add_handler(MessageHandler(filters.Regex('^Add Player$'), add_player_start), group=1)
    application.add_handler(MessageHandler(filters.Regex('^Edit Player$'), edit_player_start), group=1)
    application.add_handler(MessageHandler(filters.Regex('^Remove Player$'), remove_player_start), group=1)

    application.add_handler(MessageHandler(filters.Regex('^Player Menu$'), show_player_menu), group=1)
    application.add_handler(MessageHandler(filters.Regex('^Register$'), register_player))
    application.add_handler(MessageHandler(filters.Regex('^Register for the Game$'), register_for_game), group=1)
    application.add_handler(MessageHandler(filters.Regex('^Confirm Registration for the Game$'), list_unconfirmed_registrations), group=1)
    application.add_handler(MessageHandler(filters.Regex('^View Your Registrations$'), view_registrations), group=1)
    application.add_handler(MessageHandler(filters.Regex('^Cancel Your Registrations$'), list_unconfirmed_registrations_for_cancellation), group=1)
    application.add_handler(MessageHandler(filters.Regex('^Swap Your Confirmed Registration$'), list_confirmed_registrations_for_swap), group=1)
    application.add_handler(MessageHandler(filters.Regex('^Back to Main Menu$'), start), group=1)
  
# Message Handlers 

    application.add_handler(CallbackQueryHandler(log_unhandled_callback))


  
    try:
        application.run_polling(
            allowed_updates=['message', 'callback_query'],
            drop_pending_updates=True
        )
    except KeyboardInterrupt:
        asyncio.run(shutdown(application))    


if __name__ == '__main__':
    import asyncio
    
    try:
        asyncio.run(main())
    except Exception as e:
        logging.error(f"An error occurred: {e}")
