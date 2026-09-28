# Ohbot AI and Robotics Hackathon project

an english-speaking companion that helps learners practise difficult real-world
conversations face to face. The current scenario covers booking a GP appointment, but the
idea can extend to job interviews, landlord conversations and other everyday situations.

<img width="1152" height="2048" alt="WhatsApp Image 2026-09-28 at 4 19 48 PM" src="https://github.com/user-attachments/assets/e7846839-02ce-4c2d-8070-c9a21616cbcd" />

## why we built it

many learners understand English but freeze when they must speak under pressure.
Practising with a person can feel embarrassing, while a chatbot does not recreate a
face-to-face conversation. Ohbot provides a safe step between practising alone and
speaking to someone in the real world.

this gives learners:

- A safe space to make mistakes and try again.
- Visible encouragement through nods and expressions.
- Time to think without another person filling the silence.
- Practice speaking aloud and taking turns.
- More confidence for real conversations.

basically: **a chatbot helps learners practise what to say; Ohbot helps them practise what
it feels like to say it to someone.**

## how it works

Whisper transcribes the learner's speech locally. An interaction controller remembers key
details and handles repetition, corrections and cancellation. Ohbot replies through
text-to-speech, moving its mouth and using expressions, gaze and small nods to make the
conversation feel responsive.

The project also includes conversational examples powered by Microsoft's Phi-4-mini
through Ollama. Whisper, Phi-4-mini and the receptionist controller run locally, keeping
voice recordings, transcripts and personal details on the laptop. The separate
kids'-content panel can optionally use Claude through Amazon Bedrock.

## what is included

The GP receptionist scenario can offer practice appointments, repeat questions, correct
details and cancel a request. It is a simulation and does not connect to a real booking
system. The repository also provides tools for building more English-practice scenarios.

```python
from ohbot_kit import Ohbot, setup

cfg, convo, robot_kwargs = setup()
with Ohbot(**robot_kwargs) as bot:
    bot.speak("I'm sorry to hear that.", emotion="sympathetic", gesture="slow_nod")
```

The robot speaks **and moves at the same time** — the gesture plays underneath the audio,
which is the difference between a robot and a speaker with a face.

## quickstart

Full instructions, including Windows: **[docs/SETUP.md](docs/SETUP.md)**

```bash
uv venv --python 3.11 && source .venv/bin/activate
uv pip install -r requirements.txt

ollama serve &                     # leave it running
ollama pull phi4-mini              # 2.5 GB

python tools/check_setup.py        # downloads models, warms up, checks everything
python examples/01_hello_robot.py  # it should move and talk
```

Run everything **from the repository root**.

## then try this

Run the GP receptionist with typed input:

```bash
python receptionist_chat.py
```

Or speak to it through the microphone:

```bash
python receptionist_chat.py --voice
```

The robot's blue eyes indicate that it is listening. Pause when you have finished speaking.

Other included demonstrations:

```bash
python examples/08_empathy_chat.py
```

Type *"I had a really rough day, my cat died last night."* Watch the face, not the words.

```bash
python examples/08_empathy_chat.py --voice   # talk to it out loud
python examples/11_multi_beat.py             # expression changes mid-reply
python examples/02_expressions.py            # every pose and gesture, demonstrated
```

## start building

```bash
cp template.py my_project.py
python my_project.py
```

| where | what |
| --- | --- |
| **[docs/API.md](docs/API.md)** | Every call, pose, gesture and motor. Keep it open. |
| **[docs/CHALLENGES.md](docs/CHALLENGES.md)** | Project ideas, easy → ambitious, if you're still deciding |
| [docs/TEAMS.md](docs/TEAMS.md) | Put the robot in a Teams call: it listens, and speaks when named. Works with you on a second device; sharing one Mac with it is WIP |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Every failure we hit, and its fix |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | How it works, and why some odd-looking things are load-bearing |

## examples

Numbered in the order worth reading them.

| | |
| --- | --- |
| `01_hello_robot.py` | move, speak, look around — **start here** |
| `02_expressions.py` | the full catalogue of poses and gestures |
| `03_speech.py` | 54 voices, speed, and how lip sync works |
| `04_chat_basic.py` | the smallest possible talking robot |
| `05_personas.py` | one robot, different characters |
| `06_voice_chat.py` | talk to it with your voice |
| `07_sensors.py` | react to someone approaching |
| **`08_empathy_chat.py`** | **the flagship** — reacts with face and body, not just words |
| `09_vision.py` | webcam + a vision model: it describes what it sees — needs `ollama pull moondream` |
| `11_multi_beat.py` | expression that changes *within* a single reply |
| `10_teams_call.py` | it sits in a Teams call and answers when named — [docs/TEAMS.md](docs/TEAMS.md) |

`09_vision.py` is the only example needing anything extra: a vision model
(`ollama pull moondream`, 1.7 GB) and camera permission. `python tools/check_setup.py`
reports on both. Everything else runs with just `phi4-mini`.

`streamlit_app.py` is a presenter control panel with two jobs. **Kids' Content** is a
kids'-content demo (nursery rhymes, jokes, short stories with matching expressions) —
it's the one thing in this repo that calls out to the internet, via Claude on Amazon
Bedrock. It authenticates with the AWS CLI profile named in `config.yaml`'s
`kids_content.aws_profile` (default: `genai-agent-user`) — no API key needed, just
`aws configure --profile genai-agent-user` (or equivalent SSO login) done once. Its "Use
fallback instead" button works even without AWS credentials configured at all.
**Examples** and **Full App** launch any `examples/*.py` script or `ohbot_chat.py` as a
real subprocess, streaming its output into the page — scripts that read `input()` get a
text box wired to their stdin, and mic/camera-driven ones just use the machine's real
hardware, same as running them from a terminal. Pick a category from the sidebar, then
`streamlit run streamlit_app.py`. A "🔊 Audio devices" sidebar control lets you switch
input/output devices from the browser (persisted to `config.local.yaml`), instead of
editing it by hand.

## what it can do

**Face and body** — 15 emotions, 14 gestures, coordinated looking (eyes lead, head
follows), backchannel nodding while *you* talk. All eight motors, including the head tilt
that isn't in the vendor's docs.

**Voice** — Kokoro-82M, 54 voices, with lip sync. Faster than the macOS built-in voice.

**Ears** — local Whisper. It won't transcribe its own speech.

**Brain** — any Ollama model. The LLM picks the emotion and gesture to go with its words.

Add a pose or gesture to `ohbot_kit/expression.py` and it immediately becomes a choice the
LLM can make — the schema is built from those tables.

## notes on the underlying `ohbot` library

- Lip sync comes from the `ohbot` Python library's `say()` call (used internally by
  `bot.speak()`) and is on by default. Which voices are available depends on your
  environment; you can use Azure for speech in any environment if you have an Azure key —
  see [`ohbot-python`'s Mac voice docs](https://github.com/ohbot/ohbot-python/blob/master/Docs/VoiceDoc_Mac.md).
- The library leaves motors powered after a move. `bot.__exit__` (the end of a `with
  Ohbot(...) as bot:` block) already calls `ohbot.reset()` for you, so this isn't an issue
  for the examples here. If you hold a session open for a long idle period, or wire up a
  stop button, calling `ohbot.reset()` yourself to de-energise the motors is good practice
  — it isn't necessary for the event, but it saves motor wear.

## is it working properly?

```bash
python tools/check_empathy.py --robot
```

Scores emotion choice against five labelled language-practice cases, performs them all on the robot, and
verifies gestures actually overlap speech. `--repeats 3` shows which cases are unstable
between runs — a single run is a sample, not a measurement.

## layout

```text
ohbot_kit/     the library          examples/   01-11
tools/         diagnostics          docs/       guides
template.py    copy this to start   receptionist_chat.py  GP practice app
config.yaml    settings + personas
```

Machine-specific settings (audio devices) go in `config.local.yaml`, which is git-ignored.

## contributing

```bash
pip install -r requirements.txt -r requirements-dev.txt
pre-commit install
pytest                       # ~2s, no robot needed
```

The test suite fakes the hardware, so it runs anywhere. See
[CONTRIBUTING.md](CONTRIBUTING.md), and read
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) before changing anything that looks odd —
several strange-looking things are load-bearing.

Licensed under [Apache 2.0](LICENSE). Third-party components are listed in [NOTICE](NOTICE).
