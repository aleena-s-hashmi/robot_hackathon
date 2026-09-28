"""Deterministic receptionist booking flow and date validation."""

from datetime import date

from receptionist_chat import BookingState, _normalise_time, _spoken_time

TODAY = date(2026, 9, 28)


def test_booking_keeps_appointment_date_separate_from_birth_date() -> None:
    booking = BookingState()

    booking.handle("I want help booking a GP appointment", TODAY)
    booking.handle("I have flu", TODAY)
    booking.handle("1 October 2026", TODAY)
    booking.handle("around noon", TODAY)
    booking.handle("Hannah Manoj", TODAY)
    result = booking.handle("29 September 2005", TODAY)

    assert booking.appointment_date == date(2026, 10, 1)
    assert booking.date_of_birth == date(2005, 9, 29)
    assert "October 1, 2026" in result["say"]
    assert "Hannah" in result["say"]
    assert booking.step == "confirmation"


def test_past_appointment_date_is_rejected() -> None:
    booking = BookingState(step="appointment_date")

    result = booking.handle("1 September 2025", TODAY)

    assert booking.appointment_date is None
    assert booking.step == "appointment_date"
    assert "today or later" in result["say"]


def test_completed_booking_can_move_to_a_future_date() -> None:
    booking = BookingState(
        step="confirmation",
        appointment_date=date(2026, 9, 29),
        appointment_time="noon",
        full_name="Hannah Manoj",
        date_of_birth=date(2005, 9, 29),
    )

    result = booking.handle("change the booking date to 1 October 2026", TODAY)

    assert booking.appointment_date == date(2026, 10, 1)
    assert "October 1, 2026" in result["say"]


def test_confirmation_finishes_conversation_naturally() -> None:
    booking = BookingState(step="confirmation", full_name="Hannah Manoj")

    result = booking.handle("okay", TODAY)

    assert result["done"] is True
    assert booking.step == "finished"
    assert "Hannah" in result["say"]


def test_decimal_half_hour_is_spoken_as_clock_time() -> None:
    assert _normalise_time("3.5 p.m.") == "3:30 pm"
    assert _normalise_time("3 point 5 pm") == "3:30 pm"
    assert _spoken_time("3:30 pm") == "three thirty p m"


def test_compact_time_gets_a_colon() -> None:
    assert _normalise_time("305 pm") == "3:05 pm"
    assert _normalise_time("1530") == "15:30"


def test_hour_only_time_matches_canonical_slot() -> None:
    assert _normalise_time("9 am") == "9:00 am"
    assert _normalise_time("9 o'clock a.m.") == "9:00 am"
    assert _normalise_time("It's 4 pm, okay?") == "4:00 pm"


def test_sentence_is_not_accepted_as_a_name() -> None:
    booking = BookingState(step="full_name")

    result = booking.handle("I love my nose", TODAY)

    assert booking.full_name is None
    assert booking.step == "full_name"
    assert "full name again" in result["say"]


def test_natural_name_intro_and_single_name_are_accepted() -> None:
    booking = BookingState(step="full_name")
    booking.handle("My name is Mark Stewart", TODAY)
    assert booking.full_name == "Mark Stewart"

    booking = BookingState(step="full_name")
    booking.handle("Alina", TODAY)
    assert booking.full_name == "Alina"


def test_repeat_request_replays_question_without_advancing() -> None:
    booking = BookingState(step="appointment_date")
    booking.handle("tomorrow", TODAY)
    assert booking.step == "appointment_time"

    repeated = booking.handle("Could you say that again please?", TODAY)

    assert booking.step == "appointment_time"
    assert "What time would suit you?" in repeated["say"]
    assert booking.appointment_time is None


def test_today_in_opening_request_is_remembered() -> None:
    booking = BookingState()
    booking.handle("I would like to book an appointment today", TODAY)
    result = booking.handle("I've had a fever for two weeks", TODAY)

    assert booking.appointment_date == TODAY
    assert booking.step == "appointment_time"
    assert "What time today" in result["say"]

    changed = booking.handle("Could you do it tomorrow?", TODAY)
    assert booking.appointment_date == date(2026, 9, 29)
    assert booking.step == "appointment_time"
    assert "September 29" in changed["say"]


def test_asap_request_offers_and_remembers_three_slots() -> None:
    booking = BookingState(step="appointment_date")

    result = booking.handle("As soon as possible", TODAY)

    assert booking.step == "slot_choice"
    assert booking.offered_slots is not None
    assert len(booking.offered_slots) == 3
    assert "first" in result["say"]
    assert "second" in result["say"]
    assert "third" in result["say"]

    chosen = booking.offered_slots[1]
    result = booking.handle("the second one please", TODAY)

    assert (booking.appointment_date, booking.appointment_time) == chosen
    assert booking.step == "full_name"
    assert "full name" in result["say"]


def test_user_can_ask_for_available_times_and_choose_one() -> None:
    booking = BookingState(step="appointment_time", appointment_date=date(2026, 9, 29))

    result = booking.handle("What times are available?", TODAY)
    assert booking.step == "time_choice"
    assert len(booking.offered_times) == 3
    assert "Which time" in result["say"]

    expected = booking.offered_times[1]
    booking.handle("the second one", TODAY)
    assert booking.appointment_time == expected
    assert booking.step == "full_name"


def test_afternoon_request_offers_only_afternoon_times() -> None:
    booking = BookingState(step="appointment_time", appointment_date=date(2026, 9, 29))

    result = booking.handle("Somewhere in the afternoon please", TODAY)

    assert booking.step == "time_choice"
    assert len(booking.offered_times) == 3
    assert all(value.endswith("pm") for value in booking.offered_times)
    assert "Which time" in result["say"]


def test_user_can_choose_offered_time_by_saying_it() -> None:
    booking = BookingState(
        step="time_choice",
        appointment_date=date(2026, 9, 29),
        offered_times=["9:00 am", "2:00 pm", "3:45 pm"],
    )

    booking.handle("9 o'clock a.m.", TODAY)

    assert booking.appointment_time == "9:00 am"
    assert booking.step == "full_name"


def test_conversational_time_matches_an_offered_slot() -> None:
    for phrase, expected in (
        ("1045 am works", "10:45 am"),
        ("It's about two o'clock", "2:00 pm"),
    ):
        booking = BookingState(
            step="time_choice",
            appointment_date=date(2026, 9, 29),
            offered_times=["10:45 am", "11:30 am", "2:00 pm"],
        )
        booking.handle(phrase, TODAY)
        assert booking.appointment_time == expected
        assert booking.step == "full_name"


def test_recognized_but_unavailable_time_is_explained() -> None:
    booking = BookingState(
        step="time_choice",
        appointment_date=date(2026, 9, 29),
        offered_times=["10:45 am", "11:30 am", "2:00 pm"],
    )

    result = booking.handle("11.30 pm", TODAY)

    assert booking.step == "time_choice"
    assert "understood eleven thirty p m" in result["say"].lower()
    assert "wasn't one of" in result["say"]


def test_confirmation_allows_time_change_and_cancel() -> None:
    booking = BookingState(
        step="confirmation",
        appointment_date=date(2026, 9, 29),
        appointment_time="3:30 pm",
        full_name="Mark Stewart",
        date_of_birth=date(2005, 9, 29),
    )

    booking.handle("Can I change the time?", TODAY)
    assert booking.step == "change_time"
    booking.handle("4:15 pm", TODAY)
    assert booking.appointment_time == "4:15 pm"
    assert booking.step == "confirmation"

    booking.handle("Can I change the time?", TODAY)
    booking.handle("What times are available?", TODAY)
    offered = booking.offered_times[0]
    booking.handle("the first one", TODAY)
    assert booking.appointment_time == offered
    assert booking.step == "confirmation"

    result = booking.handle("Actually, cancel it", TODAY)
    assert booking.step == "cancelled"
    assert result["done"] is True


def test_command_fragment_is_not_accepted_as_name() -> None:
    booking = BookingState(step="full_name")
    booking.handle("Turn up", TODAY)
    assert booking.full_name is None
    assert booking.step == "full_name"


def test_birth_date_cannot_be_in_the_future() -> None:
    booking = BookingState(step="date_of_birth")

    result = booking.handle("1 October 2026", TODAY)

    assert booking.date_of_birth is None
    assert booking.step == "date_of_birth"
    assert "cannot be in the future" in result["say"]


def test_incomplete_birth_date_is_rejected() -> None:
    booking = BookingState(step="date_of_birth")

    result = booking.handle("I was born in April", TODAY)

    assert booking.date_of_birth is None
    assert booking.step == "date_of_birth"
    assert "full date of birth" in result["say"]
