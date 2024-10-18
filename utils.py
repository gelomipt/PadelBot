from database import get_player_by_nickname
import datetime

#ADMIN_USERNAMES = ["admin_username1", "admin_username2"]

def is_admin(username):
    return username in ADMIN_USERNAMES

def is_registered_player(nickname):
    player = get_player_by_nickname(nickname)
    return player is not None
    
def format_timedelta(td):
    total_seconds = int(td.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}"