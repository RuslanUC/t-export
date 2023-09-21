from .base import BaseComponent


class Reply(BaseComponent):
    def __init__(self, message_id: int):
        self.message_id = message_id

    def to_html(self) -> str:
        reply_id = self.message_id
        return f"""
        <div class="reply_to details">
            In reply to <a href="#go_to_message{reply_id}" onclick="return GoToMessage({reply_id})">this message</a>
        </div>
        """
