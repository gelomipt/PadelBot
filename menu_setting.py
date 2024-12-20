import httpx

TOKEN = "8175985461:AAHBYoM-juaM1X01fgLIDhniQQlcu1rHHNE"
url = f"https://api.telegram.org/bot{TOKEN}/setMyCommands"

commands = [
    {"command": "start", "description": "Начало работы с ботом"},
    {"command": "help", "description": "Справка"},
#    {"command": "edit_game", "description": "Edit an existing game"},
#    {"command": "add_game", "description": "Add a new game"},
    {"command": "cancel", "description": "Отменить текущее действие"},
]

response = httpx.post(url, json={"commands": commands})

if response.status_code == 200:
    print("Commands set successfully.")
else:
    print(f"Failed to set commands: {response.json()}")
