from abc import abstractmethod, ABC
from pyrogram.types import Message as PyroMessage, MessageOrigin, MessageOriginUser, MessageOriginHiddenUser, \
    MessageOriginChat, MessageOriginChannel, MessageImportInfo


class BaseComponent(ABC):
    @abstractmethod
    def to_html(self) -> str: ...

    @staticmethod
    def resolve_forward_origin_name(origin: MessageOrigin) -> str:
        if isinstance(origin, MessageOriginUser):
            return origin.sender_user.first_name if origin.sender_user else "Unknown User"
        elif isinstance(origin, MessageOriginHiddenUser):
            return origin.sender_user_name or "Hidden User"
        elif isinstance(origin, (MessageOriginChat, MessageOriginChannel)):
            typ = "Chat" if isinstance(origin, MessageOriginChat) else "Channel"
            chat = origin.sender_chat if isinstance(origin, MessageOriginChat) else origin.chat

            name = chat.title if chat and chat.title else f"Unknown {typ}"
            if origin.author_signature:
                name = f"{origin.author_signature} in {name}"
            return name
        elif isinstance(origin, MessageImportInfo):
            return origin.sender_user_name or "Imported User"

        return "Unknown Origin"


class BaseMessage(BaseComponent, ABC):
    def __init__(self, message_id: int):
        self.message_id = message_id


EXPORT_FMT = """
<html>
<head>
    <meta charset="utf-8">
    <title>Exported Data</title>
    <meta content="width=device-width, initial-scale=1.0" name="viewport">
    <link href="css/style.css" rel="stylesheet">
    <script src="js/script.js" type="text/javascript">
    </script>
</head>
<body onload="CheckLocation();">
<div class="page_wrap">
    <div class="page_header">
        <div class="content">
            <div class="text bold">{title}</div>
        </div>
    </div>
    <div class="page_body chat_page">
        <div class="history">{messages}</div>
    </div>
</div>
</body>
</html>
"""
EXPORT_FMT_BEFORE_MESSAGES, EXPORT_AFTER_MESSAGES = EXPORT_FMT.split("{messages}", 1)


class Export(BaseComponent):
    def __init__(self, title: str, messages: str):
        self.title = title
        self.messages = messages

    def to_html(self) -> str:
        return EXPORT_FMT.format(title=self.title, messages=self.messages)


class HtmlMedia(BaseComponent, ABC):
    @abstractmethod
    def __init__(self, media_path: str, media_thumb: str | None, message: PyroMessage): ...

    @abstractmethod
    def no_media(self) -> str: ...
