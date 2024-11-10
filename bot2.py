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
#    add_player_start,
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
#    edit_existing_game,
#    edit_player_start,
#    edit_game_finish,    
#    handle_add_player,
    handle_cancel_callback,
#    handle_edit_attribute_callback,    
#    handle_edit_player_callback, 
#    handle_edit_player_attribute_callback,
    handle_edit_game_callback,
#    handle_game_creation,
#    handle_new_attribute_value,
#    handle_new_player_attribute_value,
#    handle_register_player,
#    handle_remove_confirmation_callback,
#    handle_remove_player,
#    handle_remove_player_from_game,    
#    handle_remove_player_callback,
#    handle_remove_player_confirmation_callback,
#    handle_remove_game_callback,
    manage_games_menu,
#    remove_game, 
#    remove_player_start,
    cancel_game,
#    remove_player_from_game,
#    register_player_for_game,
#    send_game_actions_menu,
    show_game_details,
#    show_game_details_by_game_id,
    start_register_player,
#    start_remove_player,
    start_remove_player_from_game
    )
    
from menu_handlers import (
    start, 
#    button, 
#    manage_players_menu,
    show_admin_menu, 
    show_manage_games_menu,
#    show_player_menu,
    admin_button,
    player_button
    )
    
#from player_handlers import (
#    register_player, 
#    register_for_game,
#    handle_register_game_callback,
#    list_unconfirmed_registrations,
#    handle_confirm_registration_callback,
#    view_registrations,
#    list_unconfirmed_registrations_for_cancellation,
#    handle_cancel_registration_callback,
#    list_confirmed_registrations_for_swap,
#    handle_swap_registration_callback,
#    handle_registration,
#    register_player,
#    handle_game_selection
#    )
    
#from registration_handlers import (
#    start_registration,
#    handle_registration,
#    REGISTER_NAME,
#    REGISTER_LEVEL
#)
    
from utils import (
#    is_admin, 
#    is_registered_player,
#    fallback_callback,
#    update_finished_games,
#    announce_upcoming_games,
    announce_game,
#    handle_unhandled_callback,
#    send_update_to_public_chat
)

from config import TOKEN, ADMIN_USERNAMES
from constants import States

logger.info(f"In bot2.py, SELECT_GAME id: {id(States.SELECT_GAME)}")

async def shutdown(application):
    await application.stop()
    await application.shutdown()
######################################
add_new_game_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(add_new_game_start, pattern='^add_new_game$')],
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
        CallbackQueryHandler(show_manage_games_menu, pattern='^manage_games$')
        ],
    states={
        States.SELECT_GAME: [
            CallbackQueryHandler(show_game_details, pattern=r"^game_for_edit_select_\d+$"),
            CallbackQueryHandler(manage_games_menu, pattern='^go_back$')            
        ],       
        States.GAME_ACTIONS: [
            CallbackQueryHandler(handle_edit_game_callback, pattern=r"^edit_game_\d+$"),
            CallbackQueryHandler(cancel_game, pattern=r"^cancel_game_\d+$"),
            CallbackQueryHandler(announce_game, pattern=r"announce_game_\d+$"),
            CallbackQueryHandler(start_register_player, pattern=r"^register_player_for_game_\d+$"),
            CallbackQueryHandler(start_remove_player_from_game, pattern=r"^unregister_player_from_game_\d+$"),
            CallbackQueryHandler(show_admin_menu, pattern='^back_to_admin_menu$'),
            CallbackQueryHandler(handle_cancel_callback, pattern='^cancel$'),
#            CallbackQueryHandler(handle_unhandled_callback, pattern='.*')  # Catch-all
        ],
#        States.SELECT_ATTRIBUTE_TO_EDIT: [
#            CallbackQueryHandler(handle_edit_attribute_callback, pattern='^edit_attr_\\w+$'),
#            CallbackQueryHandler(show_admin_menu, pattern='^cancel$')
#        ],
#        States.EDIT_GAME_ATTRIBUTE_VALUE: [
#            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_new_attribute_value)
#            CallbackQueryHandler(edit_game_finish, pattern='^edit_attr_finish$'),
#        ],
#        States.REGISTER_PLAYER: [
#            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_register_player),
#            CommandHandler('cancel', show_admin_menu)
#        ],
#        States.REMOVE_PLAYER: [
#            CallbackQueryHandler(handle_remove_player_from_game, pattern=r"^game_remove_player_\d+$"),
#            CommandHandler('cancel', show_admin_menu)
#        ],
    },
    fallbacks=[CommandHandler("cancel", show_admin_menu)],
    per_message=True  # Ensure this is set
)







#########################################




def main():
    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler('start', start))
    application.add_handler(manage_games_handler, group=0)     
    application.add_handler(add_new_game_handler, group=0)

    
    
    # Set up the scheduler
#    scheduler = AsyncIOScheduler()
##    scheduler.add_job(
#        announce_upcoming_games,
#        IntervalTrigger(minutes=60),
#        args=(application,),
#        max_instances=1,
#        coalesce=True
#    )
#    scheduler.add_job(
#        update_finished_games,
#        IntervalTrigger(minutes=60),
#        max_instances=1,
#        coalesce=True
#    )    
#    scheduler.start()

 
    # Command Handlers
    application.add_handler(CallbackQueryHandler(admin_button, pattern=r'^enter_admin$'), group=0)
    application.add_handler(CallbackQueryHandler(player_button, pattern=r'^enter_player$'), group=0)
    
    # Register ConversationHandlers and other handlers in higher groups
 
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