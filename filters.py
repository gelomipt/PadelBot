from telegram.ext import filters

class EditAttributeFilter(filters.BaseFilter):
    def filter(self, message, context):
        return message and message.from_user and 'edit_attribute_process' in context.user_data

class RegisterPlayerFilter(filters.BaseFilter):
    def filter(self, message, context):
        return message and message.from_user and 'registration_in_progress' in context.user_data

class RemovePlayerFilter(filters.BaseFilter):
    def filter(self, message, context):
        return message and message.from_user and 'player_removal' in context.user_data

# Optionally create instances if they will be reused often
edit_attribute_filter = EditAttributeFilter()
register_player_filter = RegisterPlayerFilter()
remove_player_filter = RemovePlayerFilter()

# Custom filter definitions
#register_player_filter = filters.create(lambda _, context: context.user_data.get('registration_in_progress'))
#edit_attribute_filter = filters.create(lambda _, context: context.user_data.get('edit_attribute_process'))
#remove_player_filter = filters.create(lambda _, context: context.user_data.get('player_removal'))