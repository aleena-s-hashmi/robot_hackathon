"""GP receptionist practice partner: face-to-face check-in roleplay.

    python receptionist_chat.py            # type your side of the conversation
    python receptionist_chat.py --voice    # speak your side out loud

Uses the 'receptionist' persona from config.yaml. Swap to
setup(persona="receptionist_realistic") for the harder difficulty level.
"""

import argparse
import re
import sys

from ohbot_kit import Ohbot, llm, make_listener, setup
from ohbot_kit.voice import MicrophoneBlocked

# Nothing here should ever read as impatient, alarmed, or mocking -- this is
# a supportive listener, not a full emotional range.
RECEPTIONIST_EMOTIONS = ["neutral", "happy", "curious", "sympathetic", "thinking"]
RECEPTIONIST_GESTURES = ["nod", "slow_nod", "tilt", "lean_in", "perk_up", "blink"]


def _is_echo(reply: str, user_text: str) -> bool:
    """True if the model just handed the user's own words back to them,
    allowing for small filler-word differences. Skipped for short replies,
    where word overlap is likely coincidence rather than a real echo."""
    strip = lambda s: re.sub(r"[^\w\s]", "", s.strip().lower())
    r, u = strip(reply), strip(user_text)
    if not r or len(r.split()) < 3:
        return False
    return r == u or r in u or u in r


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--voice", action="store_true", help="speak instead of typing")
    args = p.parse_args()

    cfg, convo, robot_kwargs = setup(persona="receptionist")
    listener = make_listener(cfg) if args.voice else None
    convo.warm_up()

    last_reply = None  # tracks the previous spoken line, to catch the model repeating itself

    print("Receptionist practice. Ctrl-C to stop.\n")

    with Ohbot(**robot_kwargs) as bot:
        bot.speak(
            "Good morning! Are you checking in for an appointment today?",
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

                try:
                    action = convo.respond_with_action(
                        text, RECEPTIONIST_EMOTIONS, RECEPTIONIST_GESTURES
                    )
                except llm.OllamaError as e:
                    print(f"[llm] {e}", file=sys.stderr)
                    continue

                if action["say"] == last_reply or _is_echo(action["say"], text):
                    # Model got stuck repeating itself or echoing the user --
                    # recover visibly rather than showing the learner the same
                    # line twice or their own words handed back to them.
                    action = {
                        "say": "Sorry, could you say that once more for me?",
                        "emotion": "sympathetic",
                        "gesture": "tilt",
                        "gaze_x": 5,
                        "gaze_y": 5,
                    }
                    # Keep the model's own memory consistent with what was
                    # actually said -- otherwise the next turn is built on a
                    # reply the user never heard.
                    if convo.messages and convo.messages[-1]["role"] == "assistant":
                        convo.messages[-1]["content"] = action["say"]
                last_reply = action["say"]

                print(f"Ohbot [{action['emotion']}/{action['gesture']}]: {action['say']}")
                bot.gaze(action.get("gaze_x", 5), action.get("gaze_y", 5))
                bot.speak(action["say"], emotion=action["emotion"], gesture=action["gesture"])
        except MicrophoneBlocked as e:
            print(f"\n[microphone] {e}")
        except (KeyboardInterrupt, EOFError):
            print()

        bot.speak(
            "Please take a seat, they'll call you through shortly.",
            emotion="happy",
            gesture="nod",
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())