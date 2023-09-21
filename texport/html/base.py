from abc import abstractmethod, ABC
from typing import Optional
from pyrogram.types import Message as PyroMessage


class BaseComponent(ABC):
    @abstractmethod
    def to_html(self) -> str: ...


class BaseMessage(BaseComponent, ABC):
    def __init__(self, message_id: int):
        self.message_id = message_id


class Export(BaseComponent):
    def __init__(self, title: str, messages: str):
        self.title = title
        self.messages = messages

    def to_html(self) -> str:
        return f"""
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
                    <div class="text bold">{self.title}</div>
                </div>
            </div>
            <div class="page_body chat_page">
                <div class="history">{self.messages}</div>
            </div>
        </div>
        </body>
        </html>
        """


class HtmlMedia(BaseComponent, ABC):
    @abstractmethod
    def __init__(self, media_path: str, media_thumb: Optional[str], message: PyroMessage): ...

    @abstractmethod
    def no_media(self) -> str: ...
