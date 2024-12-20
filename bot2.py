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

from filters import edit_attribute_filter, register_player_filter, remove_player_filter

from admin_handlers import (
#    add_player_start,
#    add_new_game_start,
    add_new_game_start,
    add_game_date,
    add_game_start_time,
    add_game_end_time,
    add_game_venue,
    add_game_capacity,
    add_game_cancel,
    add_game_venue_selection,
    ADD_GAME_DATE,
    ADD_GAME_START_TIME,
    ADD_GAME_END_TIME,
    ADD_GAME_VENUE,
    ADD_GAME_CAPACITY,
    EDIT_GAME, 
    EDIT_ATTRIBUTE, 
    EDIT_ATTRIBUTE_VALUE,
    EDIT_GAME_VENUE,
    REGISTER_PLAYER,
    CONFIRM_ALIAS,
    ENTER_ALIAS,
    REMOVE_PLAYER_SELECT, 
    REMOVE_PLAYER_CONFIRM,
    cancel_registration,
    cancel_edit_game,
    edit_game_venue_selection,
    display_attribute_selection_menu,
#    edit_player_start,
    edit_game_finish,    
#    handle_add_player,
    handle_cancel_callback,
    handle_confirm_alias,
    handle_enter_alias,
    handle_edit_attribute_callback,    
#    handle_edit_player_callback, 
#    handle_edit_player_attribute_callback,
    handle_edit_game_callback,
#    handle_game_creation,
    handle_new_attribute_value,
#    handle_new_player_attribute_value,
    handle_register_player,
#    handle_remove_confirmation_callback,
    handle_remove_player,
    handle_remove_player_selection,
    handle_remove_player_confirmation,
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
    button, 
    manage_players_menu,
    show_admin_menu, 
    show_manage_games_menu,
    show_player_menu,
    admin_button,
    player_button
    )
    
from player_handlers import (
#    register_player, 
    register_for_game,
    cancel_game_registration,
    handle_game_selection,
    handle_register_game_callback,
    list_unconfirmed_registrations,
    handle_confirm_registration_callback,
    view_registrations,
    PLAYER_REGISTER_FOR_GAME,
    PLAYER_GAME_SELECTION,
    cancel_player_for_game_registration,
    GAME_FOR_REGISTRATION_CONFIRMATION_SELECTION,
    GAME_FOR_CANCELLATION_CONFIRMATION_SELECTION 
#    list_unconfirmed_registrations_for_cancellation,
#    handle_cancel_registration_callback,
#    list_confirmed_registrations_for_swap,
#    handle_swap_registration_callback,
#    handle_registration,
#    register_player,
#    handle_game_selection
    )
    
from registration_handlers import (
    start_registration,
    handle_registration,
    cancel_registration,
    REGISTER_NAME,
    REGISTER_LEVEL
)
    
from utils import (
#    is_admin, 
#    is_registered_player,
#    fallback_callback,
    update_finished_games,
    announce_upcoming_games,
    announce_game,
    shutdown,
#    list_venues
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
registration_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(start_registration, pattern='^player_registration$')],
    states={
        REGISTER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_registration)],
        REGISTER_LEVEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_registration)],
    },
    fallbacks=[CommandHandler('cancel', cancel_registration)],    
)

add_new_game_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(add_new_game_start, pattern='^add_new_game$')],
    states={
        ADD_GAME_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, add_game_date)],
        ADD_GAME_START_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, add_game_start_time)],
        ADD_GAME_END_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, add_game_end_time)],
        ADD_GAME_VENUE: [CallbackQueryHandler(add_game_venue_selection, pattern=r'^select_venue_\d+$')],
        ADD_GAME_CAPACITY: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, add_game_capacity)],
#        ADD_GAME_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, add_game_url)],
    },
    fallbacks=[CommandHandler('cancel', add_game_cancel)],
)

edit_existing_game_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(handle_edit_game_callback, pattern=r'^edit_game_\d+$')],
    states={
        EDIT_ATTRIBUTE: [CallbackQueryHandler(handle_edit_attribute_callback, pattern=r'^edit_attr_\w+$')],
        EDIT_GAME_VENUE: [CallbackQueryHandler(edit_game_venue_selection, pattern=r'^select_venue_\d+$')],
        EDIT_ATTRIBUTE_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, handle_new_attribute_value)],
    },
    fallbacks=[CommandHandler('cancel', cancel_edit_game)],  
)

register_player_for_game = ConversationHandler(
    entry_points=[CallbackQueryHandler(start_register_player, pattern=r'^register_player_for_game_\d+$')],
    states={
        REGISTER_PLAYER: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, handle_register_player)],
        CONFIRM_ALIAS: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, handle_confirm_alias)],
        ENTER_ALIAS: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, handle_enter_alias)],

    },
    fallbacks=[CommandHandler('cancel', cancel_registration)],
)

remove_player_from_game = ConversationHandler(
    entry_points=[CallbackQueryHandler(start_remove_player_from_game, pattern=r'^remove_player_\d+$')],
    states={
        REMOVE_PLAYER_SELECT: [CallbackQueryHandler(handle_remove_player_selection, pattern=r'^remove_player_confirm_\d+$')],
        REMOVE_PLAYER_CONFIRM: [CallbackQueryHandler(handle_remove_player_confirmation, pattern=r'^confirm_remove_player_(yes|no)$')],
    },
    fallbacks=[CommandHandler('cancel', cancel_registration)],
)

register_for_game_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(register_for_game, pattern=r'^player_register_for_game$')],
    states={
        PLAYER_GAME_SELECTION: [CallbackQueryHandler(handle_game_selection, pattern=r'^select_game_\d+$')],    },
    fallbacks=[CommandHandler('cancel', cancel_player_for_game_registration)],
)

comfirm_registration = ConversationHandler(
    entry_points=[CallbackQueryHandler(list_unconfirmed_registrations, pattern=r'^confirm_registration$')],
    states={
        GAME_FOR_REGISTRATION_CONFIRMATION_SELECTION: [CallbackQueryHandler(handle_confirm_registration_callback, pattern=r'^confirm_registration_\d+$')],
    },
    fallbacks=[CommandHandler('cancel', cancel_game_registration)],
)

cancel_registration_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(list_unconfirmed_registrations, pattern=r'^cancel_registration$')],
    states={
        GAME_FOR_CANCELLATION_CONFIRMATION_SELECTION: [CallbackQueryHandler(handle_confirm_registration_callback, pattern=r'^confirm_registration_\d+$')],
    },
    fallbacks=[CommandHandler('cancel', cancel_game_registration)],
)




#########################################

def main():
    private_chat_filter = filters.ChatType.PRIVATE

    application = ApplicationBuilder().token(TOKEN).build()


#    application.add_handler(manage_games_handler, group=0)     
    
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
    application.add_handler(CommandHandler('start', start)) #start menu
    application.add_handler(CallbackQueryHandler(start, pattern=r'^start_menu')) #start menu


    #Admin menu
    application.add_handler(CallbackQueryHandler(admin_button, pattern=r'^enter_admin$'), group=0)
    application.add_handler(CallbackQueryHandler(show_admin_menu, pattern=r'^go_back$'), group=0) #Admin -> Main Menu
    
    application.add_handler(CallbackQueryHandler(show_manage_games_menu, pattern=r'^manage_games$'), group=0) #Admin -> Manage Games -> 
    application.add_handler(add_new_game_handler, group=0) # Admin -> Manage Games -> Add new game
    application.add_handler(edit_existing_game_handler, group=0) # Admin -> Manage Games -> Add new game
    application.add_handler(register_player_for_game, group=0) # Register player for game
    application.add_handler(remove_player_from_game, group=0) # Remove player from game
    application.add_handler(registration_handler, group=0) # Register bot user
    application.add_handler(register_for_game_handler, group=0) # Register player for game
    application.add_handler(comfirm_registration, group=0) # Confirm player registration
    application.add_handler(cancel_registration_handler, group=0) # Cancel player registration

    application.add_handler(CallbackQueryHandler(manage_games_menu, pattern=r'^manage_game$'), group=0) # Admin -> Manage Games -> Manage Existing Game
    application.add_handler(CallbackQueryHandler(show_game_details, pattern=r"^game_for_edit_select_\d+$")) #Show game menu
#    application.add_handler(CallbackQueryHandler(handle_edit_game_callback, pattern=r"^edit_game_\d+$")) # Edit game menu
#    application.add_handler(CallbackQueryHandler(handle_edit_attribute_callback, pattern=r'^edit_attr_\w+$')) #Edit Attribute
#    application.add_handler(CallbackQueryHandler(edit_game_finish, pattern='^edit_attr_finish$'))
    application.add_handler(CallbackQueryHandler(cancel_game, pattern=r"^cancel_game_\d+$")) #Cancel game
    application.add_handler(CallbackQueryHandler(announce_game, pattern=r"^announce_game_\d+$")) #Announce game    
#    application.add_handler(CallbackQueryHandler(start_register_player, pattern=r"^remove_player_\d+$")) #Remove player from game
#    application.add_handler(CallbackQueryHandler(start_register_player, pattern=r'^register_player_for_game_\d+$')) #register player
    application.add_handler(CommandHandler("cancel_registration", cancel_registration))
    application.add_handler(CallbackQueryHandler(start_remove_player_from_game, pattern=r'^remove_player_\d+$')) #Remove player from game

#    application.add_handler(MessageHandler(register_player_filter, handle_register_player))
#    application.add_handler(MessageHandler(remove_player_filter, handle_remove_player))

    #Player Menu
    application.add_handler(CallbackQueryHandler(player_button, pattern=r'^enter_player$'), group=0)
    application.add_handler(CallbackQueryHandler(view_registrations, pattern=r'^view_registrations$'), group=1) #Player -> View Registrations
#    application.add_handler(CallbackQueryHandler(register_for_game, pattern=r'^register_for_game$'), group=1) #Player -> Register for game

 #   application.add_handler(CallbackQueryHandler(edit_existing_game, pattern='^edit_game$'))  

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