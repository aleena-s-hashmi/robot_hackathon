"""GP receptionist practice partner: face-to-face check-in roleplay.

    python receptionist_chat.py            # type your side of the conversation
    python receptionist_chat.py --voice    # speak your side out loud

Uses the 'receptionist' persona from config.yaml. Swap to
setup(persona="receptionist_realistic") for the harder difficulty level.
"""

import argparse
import random
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from dateutil import parser as date_parser

from ohbot_kit import Ohbot, make_listener, setup
from ohbot_kit.voice import MicrophoneBlocked


def _action(say, emotion="neutral", gesture="nod", *, done=False):
    return {
        "say": say,
        "emotion": emotion,
        "gesture": gesture,
        "gaze_x": 5,
        "gaze_y": 5,
        "done": done,
    }


def _spoken_date(value: date) -> str:
    return f"{value.strftime('%A, %B')} {value.day}, {value.year}"


def _number_words(value: int) -> str:
    small = [
        "zero",
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
        "ten",
        "eleven",
        "twelve",
        "thirteen",
        "fourteen",
        "fifteen",
        "sixteen",
        "seventeen",
        "eighteen",
        "nineteen",
    ]
    tens = {20: "twenty", 30: "thirty", 40: "forty", 50: "fifty"}
    if value < 20:
        return small[value]
    return tens[value // 10 * 10] + (f" {small[value % 10]}" if value % 10 else "")


def _spoken_time(value: str) -> str:
    """Spell out clock digits so macOS say does not read 3:30 as three hundred thirty."""
    match = re.fullmatch(r"(\d{1,2}):(\d{2})(?:\s*(am|pm))?", value.lower())
    if not match:
        return value
    hour, minute, suffix = int(match.group(1)), int(match.group(2)), match.group(3)
    if hour > 12 and not suffix:
        hour = hour - 12
    words = _number_words(hour)
    if minute:
        words += f" {'oh ' if minute < 10 else ''}{_number_words(minute)}"
    else:
        words += " o'clock"
    if suffix:
        words += f" {suffix[0]} m"
    return words


def _upcoming_slots(today: date) -> list[tuple[date, str]]:
    """Return three plausible practice slots on upcoming weekdays."""
    weekdays = []
    candidate = today + timedelta(days=1)
    while len(weekdays) < 7:
        if candidate.weekday() < 5:
            weekdays.append(candidate)
        candidate += timedelta(days=1)
    days = sorted(random.sample(weekdays, 3))
    times = ["9:30 am", "10:45 am", "11:30 am", "2:30 pm", "3:45 pm"]
    return [(day, random.choice(times)) for day in days]


def _available_times(period: str | None = None) -> list[str]:
    times = [
        "9:00 am",
        "9:30 am",
        "10:45 am",
        "11:30 am",
        "2:00 pm",
        "2:30 pm",
        "3:45 pm",
        "4:15 pm",
    ]
    if period == "morning":
        times = [value for value in times if value.endswith("am")]
    elif period in {"afternoon", "evening"}:
        times = [value for value in times if value.endswith("pm")]
    return sorted(random.sample(times, 3), key=lambda value: datetime.strptime(value, "%I:%M %p"))


def _normalise_time(text: str) -> str | None:
    """Turn common speech-to-text time forms into a natural clock time."""
    raw = text.lower().strip(" .,!?;")
    raw = re.sub(r"[, ]+(?:works|would work|please|okay|ok|is fine|is good)(?: for me)?$", "", raw)
    raw = re.sub(r"^(?:it'?s\s+)?(?:at|about|around)\s+", "", raw)
    raw = re.sub(r"^(?:it'?s\s+)(?=\d)", "", raw)
    raw = re.sub(r"\ba\.?\s*m\.?$", "am", raw)
    raw = re.sub(r"\bp\.?\s*m\.?$", "pm", raw)
    cleaned = raw.replace(".", "")
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = cleaned.replace("a m", "am").replace("p m", "pm")

    # Whisper sometimes writes "three thirty" as 3.5: half an hour expressed
    # as a decimal fraction. Convert the fraction to clock minutes.
    decimal = re.fullmatch(r"(\d{1,2})\s*(?:point\s*5|\.5)\s*(am|pm)?", raw)
    if decimal:
        hour = int(decimal.group(1))
        if 1 <= hour <= 12:
            suffix = f" {decimal.group(2)}" if decimal.group(2) else ""
            return f"{hour}:30{suffix}"

    regular = re.fullmatch(r"(\d{1,2})(?::|\s)(\d{2})\s*(am|pm)?", cleaned)
    if regular:
        hour, minute = int(regular.group(1)), int(regular.group(2))
        if 1 <= hour <= 12 and 0 <= minute <= 59:
            suffix = f" {regular.group(3)}" if regular.group(3) else ""
            return f"{hour}:{minute:02d}{suffix}"

    hour_only = re.fullmatch(r"(\d{1,2})(?:\s*o'?clock)?\s*(am|pm)", cleaned)
    if hour_only:
        hour = int(hour_only.group(1))
        if 1 <= hour <= 12:
            return f"{hour}:00 {hour_only.group(2)}"

    word_hours = {
        word: number
        for number, word in enumerate(
            (
                "zero",
                "one",
                "two",
                "three",
                "four",
                "five",
                "six",
                "seven",
                "eight",
                "nine",
                "ten",
                "eleven",
                "twelve",
            )
        )
    }
    word_clock = re.fullmatch(
        r"(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
        r"\s+o'?clock(?:\s*(am|pm))?",
        cleaned,
    )
    if word_clock:
        suffix = f" {word_clock.group(2)}" if word_clock.group(2) else ""
        return f"{word_hours[word_clock.group(1)]}:00{suffix}"

    # Compact forms such as "305 pm" mean 3:05 pm, while "1530" is 15:30.
    compact = re.fullmatch(r"(\d{3,4})\s*(am|pm)?", cleaned)
    if compact:
        digits = compact.group(1)
        hour, minute = int(digits[:-2]), int(digits[-2:])
        max_hour = 12 if compact.group(2) else 23
        if 0 <= hour <= max_hour and 0 <= minute <= 59:
            suffix = f" {compact.group(2)}" if compact.group(2) else ""
            return f"{hour}:{minute:02d}{suffix}"

    # Preserve a small set of natural time phrases, but do not accept an
    # arbitrary sentence as a time merely because the conversation is on that step.
    if re.fullmatch(
        r"(?:(?:at|around)\s+)?(?:noon|midday|midnight|morning|afternoon|evening|"
        r"half past (?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve))",
        cleaned,
    ):
        return re.sub(r"^(?:at|around)\s+", "", cleaned)
    return None


def _extract_name(text: str) -> str | None:
    cleaned = re.sub(
        r"^(?:my name is|the name is|i am|i'm|this is)\s+",
        "",
        text.strip(),
        flags=re.IGNORECASE,
    ).strip(" .,!?")
    words = re.findall(r"[A-Za-z][A-Za-z'-]*", cleaned)
    if not 1 <= len(words) <= 4 or " ".join(words).lower() != cleaned.lower():
        return None
    blocked = {
        "i",
        "im",
        "my",
        "it",
        "the",
        "this",
        "that",
        "we",
        "you",
        "yes",
        "no",
        "turn",
        "book",
        "cancel",
        "repeat",
        "appointment",
    }
    if any(word.lower() in blocked for word in words):
        return None
    return " ".join(word.capitalize() for word in words)


def _parse_date(text: str, today: date, *, appointment: bool) -> date | None:
    """Parse an explicit date, without mistaking a time such as noon for one."""
    lowered = text.lower()
    if "today" in lowered:
        return today
    if "tomorrow" in lowered:
        return today + timedelta(days=1)

    months = (
        "january|february|march|april|may|june|july|august|september|"
        "october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec"
    )
    if not re.search(rf"\b(?:{months})\b|\b\d{{1,2}}[/-]\d{{1,2}}", lowered):
        return None
    try:
        parsed = date_parser.parse(
            text,
            fuzzy=True,
            dayfirst=True,
            default=datetime.combine(today, datetime.min.time()),
        ).date()
    except (ValueError, OverflowError):
        return None

    if appointment and parsed < today and not re.search(r"\b\d{4}\b", text):
        try:
            parsed = parsed.replace(year=parsed.year + 1)
        except ValueError:
            parsed = parsed.replace(year=parsed.year + 1, day=28)
    return parsed


def _parse_birth_date(text: str, today: date) -> date | None:
    """A DOB must include all three components; never invent a day or year."""
    if not re.search(r"\b\d{1,2}(?:st|nd|rd|th)?\b", text.lower()):
        return None
    if not re.search(r"\b\d{4}\b", text):
        return None
    return _parse_date(text, today, appointment=False)


@dataclass
class BookingState:
    """Keep booking fields separate so the model cannot merge the two dates."""

    step: str = "intent"
    reason: str | None = None
    appointment_date: date | None = None
    appointment_time: str | None = None
    full_name: str | None = None
    date_of_birth: date | None = None
    offered_slots: list[tuple[date, str]] | None = None
    offered_times: list[str] | None = None
    time_choice_next: str = "full_name"
    last_action: dict | None = None

    @property
    def first_name(self) -> str:
        return self.full_name.split()[0].title() if self.full_name else ""

    def confirmation(self) -> dict:
        return _action(
            f"Lovely, {self.first_name}. I have {_spoken_date(self.appointment_date)} "
            f"at {_spoken_time(self.appointment_time)} for you. Does that all sound right?",
            "happy",
            "nod",
        )

    def offer_times(self, next_step: str = "full_name", period: str | None = None) -> dict:
        self.offered_times = _available_times(period)
        self.time_choice_next = next_step
        self.step = "time_choice"
        spoken = [_spoken_time(value) for value in self.offered_times]
        return _action(
            f"I have {spoken[0]}, {spoken[1]}, or {spoken[2]}. Which time suits you best?",
            "curious",
            "perk_up",
        )

    def handle(self, text: str, today: date | None = None) -> dict:
        if re.search(
            r"\b(say that again|repeat that|could you repeat|pardon|what did you say)\b",
            text.lower(),
        ):
            return self.last_action or _action("Of course. How can I help you?", "happy")
        action = self._handle(text, today)
        self.last_action = action
        return action

    def _handle(self, text: str, today: date | None = None) -> dict:
        today = today or date.today()
        lowered = text.lower()

        if self.step == "confirmation" and re.search(r"\b(cancel|never mind|nevermind)\b", lowered):
            self.step = "cancelled"
            return _action(
                "No problem. I've cancelled this practice request. Take care!",
                "sympathetic",
                "nod",
                done=True,
            )

        if self.step == "confirmation" and re.search(r"\b(change|correct|different)\b", lowered):
            if re.search(r"\b(date|day)\b", lowered):
                value = _parse_date(text, today, appointment=True)
                if value is not None and value >= today:
                    self.appointment_date = value
                    return self.confirmation()
                self.step = "change_date"
                return _action("Of course. What new date would you like?", "curious", "tilt")
            if re.search(r"\btime\b", lowered):
                self.step = "change_time"
                return _action(
                    "Of course. What new time would you like? You can also ask what's available.",
                    "curious",
                    "tilt",
                )
            if re.search(r"\b(name)\b", lowered):
                self.step = "change_name"
                return _action("Of course. What name should I use?", "curious", "tilt")
            if re.search(r"\b(birth|dob)\b", lowered):
                self.step = "change_birth_date"
                return _action("Of course. What is the correct date of birth?", "curious", "tilt")

        if "date" in lowered and re.search(r"\b(change|move|reschedule)\b", lowered):
            value = _parse_date(text, today, appointment=True)
            if value is None:
                return _action("What new appointment date would you like?", "curious", "tilt")
            if value < today:
                return _action(
                    "Appointments must be today or later. What date would you prefer?",
                    "sympathetic",
                    "tilt",
                )
            self.appointment_date = value
            if all((self.appointment_time, self.full_name, self.date_of_birth)):
                self.step = "confirmation"
                return self.confirmation()
            return _action(
                f"I've changed the requested date to {_spoken_date(value)}. "
                "Let's carry on from there.",
                "happy",
            )

        if self.step == "intent":
            requested_date = _parse_date(text, today, appointment=True)
            if requested_date is not None and requested_date >= today:
                self.appointment_date = requested_date
            self.step = "reason"
            return _action("Of course. What is the reason for your appointment?", "happy")

        if self.step == "reason":
            self.reason = text
            if re.search(r"\b(flu|ill|unwell|pain|ache|sick|fever|cough)\b", lowered):
                acknowledgement = "I'm sorry you're feeling unwell."
            else:
                acknowledgement = "I can help with that."
            if self.appointment_date is not None:
                self.step = "appointment_time"
                day_words = (
                    "today"
                    if self.appointment_date == today
                    else f"on {self.appointment_date.strftime('%B')} {self.appointment_date.day}"
                )
                reply = f"{acknowledgement} What time {day_words} would suit you?"
            else:
                self.step = "appointment_date"
                reply = f"{acknowledgement} What day would work best for you?"
            return _action(reply, "sympathetic", "slow_nod")

        if self.step == "appointment_date":
            if re.search(
                r"\b(as soon as possible|asap|immediately|earliest|soonest|urgent)\b",
                lowered,
            ):
                self.offered_slots = _upcoming_slots(today)
                self.step = "slot_choice"
                labels = ("first", "second", "third")
                choices = []
                for label, (slot_date, slot_time) in zip(labels, self.offered_slots, strict=True):
                    choices.append(
                        f"{label}, {slot_date.strftime('%A, %B')} {slot_date.day} "
                        f"at {_spoken_time(slot_time)}"
                    )
                return _action(
                    "Let me find the earliest openings. I can offer "
                    + "; ".join(choices)
                    + ". Which one works best for you?",
                    "curious",
                    "perk_up",
                )
            value = _parse_date(text, today, appointment=True)
            if value is None:
                return _action(
                    "I didn't quite catch the date. Could you say the day and month again?",
                    "curious",
                    "tilt",
                )
            if value < today:
                return _action(
                    "Appointments must be today or later. What future date would you prefer?",
                    "sympathetic",
                    "tilt",
                )
            self.appointment_date = value
            self.step = "appointment_time"
            return _action(
                f"{value.strftime('%B')} {value.day} works. What time would suit you?",
                "happy",
                "nod",
            )

        if self.step == "slot_choice":
            choice_words = {
                0: r"\b(first|1st|option 1)\b|^(?:the )?one(?: please)?$",
                1: r"\b(second|two|2nd|option 2)\b",
                2: r"\b(third|three|3rd|option 3)\b",
            }
            selected = next(
                (index for index, pattern in choice_words.items() if re.search(pattern, lowered)),
                None,
            )
            if selected is None:
                requested_date = _parse_date(text, today, appointment=True)
                if requested_date is not None:
                    selected = next(
                        (
                            index
                            for index, (slot_date, _slot_time) in enumerate(self.offered_slots)
                            if slot_date == requested_date
                        ),
                        None,
                    )
            if selected is None:
                return _action(
                    "Which would you prefer: the first, second, or third appointment?",
                    "curious",
                    "tilt",
                )
            self.appointment_date, self.appointment_time = self.offered_slots[selected]
            self.step = "full_name"
            return _action(
                f"Great, {_spoken_date(self.appointment_date)} at "
                f"{_spoken_time(self.appointment_time)}. And what's your full name?",
                "happy",
                "nod",
            )

        if self.step == "appointment_time":
            revised_date = _parse_date(text, today, appointment=True)
            if revised_date is not None:
                if revised_date < today:
                    return _action(
                        "That date has already passed. What future date would work for you?",
                        "sympathetic",
                        "tilt",
                    )
                self.appointment_date = revised_date
                return _action(
                    f"Of course, {_spoken_date(revised_date)} works. What time would suit you?",
                    "happy",
                    "nod",
                )
            period_match = re.search(r"\b(morning|afternoon|evening)\b", lowered)
            if period_match:
                return self.offer_times(period=period_match.group(1))
            if re.search(r"\b(available|availability|free|open|options|times)\b", lowered):
                return self.offer_times()
            normalised = _normalise_time(text)
            if normalised is None:
                return _action(
                    "I didn't catch the time. Could you say it again?", "curious", "tilt"
                )
            self.appointment_time = normalised
            self.step = "full_name"
            return _action(
                f"Perfect, {_spoken_time(normalised)} it is. And what's your full name?",
                "happy",
                "perk_up",
            )

        if self.step == "time_choice":
            choice_patterns = (
                r"\b(first|1st|option 1)\b|^(?:the )?one(?: please)?$",
                r"\b(second|2nd|option 2)\b",
                r"\b(third|3rd|option 3)\b",
            )
            selected = next(
                (
                    index
                    for index, pattern in enumerate(choice_patterns)
                    if re.search(pattern, lowered)
                ),
                None,
            )
            normalised = _normalise_time(text)
            if selected is not None:
                normalised = self.offered_times[selected]
            elif normalised not in self.offered_times and normalised is not None:
                # If the user omitted a.m./p.m., accept the clock time only
                # when exactly one offered slot has that hour and minute.
                if not re.search(r"\s(?:am|pm)$", normalised):
                    matches = [
                        value for value in self.offered_times if value.startswith(normalised)
                    ]
                    normalised = matches[0] if len(matches) == 1 else None
                else:
                    understood = _spoken_time(normalised)
                    return _action(
                        f"I understood {understood}, but that time wasn't one of the available "
                        "options. Please choose the first, second, or third time.",
                        "curious",
                        "tilt",
                    )
            if normalised is None:
                return _action(
                    "Please choose the first, second, or third available time.",
                    "curious",
                    "tilt",
                )
            self.appointment_time = normalised
            self.step = self.time_choice_next
            if self.step == "confirmation":
                return self.confirmation()
            return _action(
                f"Great, {_spoken_time(normalised)}. And what's your full name?",
                "happy",
                "nod",
            )

        if self.step == "full_name":
            name = _extract_name(text)
            if name is None:
                return _action(
                    "Sorry, I didn't catch your name clearly. Could you say your full name again?",
                    "curious",
                    "tilt",
                )
            self.full_name = name
            self.step = "date_of_birth"
            return _action(
                f"Thanks, {self.first_name}. Just one last thing: what's your date of birth?",
                "happy",
                "nod",
            )

        if self.step == "date_of_birth":
            value = _parse_birth_date(text, today)
            if value is None:
                return _action(
                    "I need the day, month, and year. Could you say your full date of birth again?",
                    "curious",
                    "tilt",
                )
            if value > today:
                return _action(
                    "A date of birth cannot be in the future. Please try again.",
                    "sympathetic",
                    "tilt",
                )
            self.date_of_birth = value
            self.step = "confirmation"
            return self.confirmation()

        if self.step == "confirmation":
            if re.search(r"\b(yes|yeah|yep|correct|right|okay|ok|perfect|sure)\b", lowered):
                self.step = "finished"
                return _action(
                    f"Brilliant, {self.first_name}. That's the practice request complete. "
                    "I hope you feel better soon!",
                    "happy",
                    "perk_up",
                    done=True,
                )
            if re.search(r"\b(no|nope|wrong|change)\b", lowered):
                return _action(
                    "No problem at all. Tell me which detail you'd like to change.",
                    "curious",
                    "tilt",
                )
            return _action(
                "Just to check, do those appointment details sound right?",
                "curious",
                "tilt",
            )

        if self.step == "change_date":
            value = _parse_date(text, today, appointment=True)
            if value is None or value < today:
                return _action("Please choose today or a future date.", "curious", "tilt")
            self.appointment_date = value
            self.step = "confirmation"
            return self.confirmation()

        if self.step == "change_time":
            if re.search(r"\b(available|availability|free|open|options|times)\b", lowered):
                return self.offer_times(next_step="confirmation")
            value = _normalise_time(text)
            if value is None:
                return _action("What new appointment time would you like?", "curious", "tilt")
            self.appointment_time = value
            self.step = "confirmation"
            return self.confirmation()

        if self.step == "change_name":
            value = _extract_name(text)
            if value is None:
                return _action("Could you say the correct name again?", "curious", "tilt")
            self.full_name = value
            self.step = "confirmation"
            return self.confirmation()

        if self.step == "change_birth_date":
            value = _parse_birth_date(text, today)
            if value is None or value > today:
                return _action("Please give a valid past date of birth.", "curious", "tilt")
            self.date_of_birth = value
            self.step = "confirmation"
            return self.confirmation()

        return _action(
            f"Thanks again, {self.first_name}. Take care!",
            "happy",
            done=True,
        )


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--voice", action="store_true", help="speak instead of typing")
    args = p.parse_args()

    cfg, _convo, robot_kwargs = setup(persona="receptionist")
    listener = make_listener(cfg) if args.voice else None
    booking = BookingState()
    finished = False

    print("Receptionist practice. Ctrl-C to stop.\n")
    if listener is not None:
        try:
            listener.calibrate()
        except MicrophoneBlocked as e:
            print(f"[microphone] {e}", file=sys.stderr)
            return 1
        print("Listening. Speak when the robot's eyes are blue, then pause for a reply.\n")

    with Ohbot(**robot_kwargs) as bot:
        bot.speak(
            "Good morning! How can I help you today?",
            emotion="happy",
            gesture="nod",
        )
        try:
            while True:
                bot.listening(True)  # nod and blink while the learner talks
                if args.voice:
                    audio_in = listener.record_utterance(bot)
                    if audio_in is None:
                        continue
                    text = listener.transcribe(audio_in)
                    if not text:
                        continue
                    print(f"You: {text}")
                else:
                    text = input("You: ").strip()
                bot.listening(False)

                if not text or text in ("/quit", "/exit"):
                    break

                bot.set_state("thinking")
                bot.express("thinking")

                action = booking.handle(text)

                print(f"Ohbot [{action['emotion']}/{action['gesture']}]: {action['say']}")
                bot.gaze(action.get("gaze_x", 5), action.get("gaze_y", 5))
                bot.speak(action["say"], emotion=action["emotion"], gesture=action["gesture"])
                if action["done"]:
                    finished = True
                    break
        except MicrophoneBlocked as e:
            print(f"\n[microphone] {e}")
        except (KeyboardInterrupt, EOFError):
            print()

        if not finished:
            bot.speak(
                "Thanks for chatting. Take care!",
                emotion="happy",
                gesture="nod",
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
