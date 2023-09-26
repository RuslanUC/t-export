from pyrogram.enums import PollType
from pyrogram.types import Message as PyroMessage, Poll as PyroPoll

from .base import HtmlMedia, BaseComponent


class PollOption(BaseComponent):
    def __init__(self, poll: PyroPoll, option: int):
        self.poll = poll
        self.option_id = option
        self.option = poll.options[option]

    def to_html(self) -> str:
        details = []
        if self.option.voter_count:
            details.append(f"{self.option.voter_count} votes")
        if self.option_id == self.poll.chosen_option_id:
            details.append("chosen vote")
        if self.poll.type == PollType.QUIZ and self.option_id == self.poll.correct_option_id:
            details.append("correct vote")
        details = ", ".join(details)
        details = "" if not details else f"""<span class="details">{details}</span>"""

        return f"""
        <div class="answer">- {self.option.text} {details}</div>
        """


class Poll(HtmlMedia):
    def __init__(self, *args, message: PyroMessage):
        self.poll = message.poll

    def no_media(self) -> str:
        return ""

    def to_html(self) -> str:
        poll_details = None
        if self.poll.is_anonymous:
            poll_details = "<div class=\"details\">Anonymous poll</div>"
        if self.poll.is_closed:
            poll_details = "<div class=\"details\">Closed poll</div>"

        options = ""
        for idx, opt in enumerate(self.poll.options):
            options += PollOption(self.poll, idx).to_html()

        return f"""
        <div class="media_poll">
            <div class="question bold">{self.poll.question}</div>

            {"" if poll_details is None else poll_details}

            {options}
            
            <div class="total details"{self.poll.total_voter_count} votes</div>
        </div>
        """
