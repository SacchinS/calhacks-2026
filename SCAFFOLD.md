# Scaffolding brief for `calhacks-2026`

You're setting up the skeleton of a hackathon project (Cal Hacks 13.0, 3-person team, ~36 hours). **This task is scaffolding only.** The goal: every component exists behind an interface, every component has a working mock, the whole app runs end to end on mocks, and the remaining work splits cleanly across 3 teammates who can each swap their mocks for real implementations without touching anyone else's code. Don't implement real ML models, real LLM calls, or real audio routing yet. Leave clear `TODO` stubs where they'll go.

Read `README.md` first for the product context. `MVP.md` describes what each teammate builds after the scaffolding; read it so the structure you create matches that split.

## Product in one paragraph

A laptop app for Deaf ASL signers. A webcam feed is turned into hand and pose landmarks (MediaPipe). Isolated signs and fingerspelling are recognized from the landmarks, and Claude turns the resulting gloss (e.g. `ME WANT FIX BUG LOGIN PAGE`) into natural English. A router then sends that English to the active target. **Claude Code** gets it after the signer confirms with a signed YES/NO. **Siri** gets it typed in with Type to Siri (the app holds ⌘Space and types; "Hey Siri" can't be triggered through a virtual mic). **Text-to-speech (Cartesia) through a virtual microphone** (BlackHole on macOS) lets system dictation and Google Meet hear it as normal mic input. In Meet mode, incoming speech is also shown as live captions (Cartesia speech-to-text).

## How it's shown

It's a Mac menu-bar app: the SwiftUI front end from our earlier SignBridge project, driving this repo's Python engine. It's built for a two-screen demo:

- **Demo Mode:** a fullscreen stage with the camera and tracking, the signs as they land, the English, the confirm step, recent phrases, and captions in Meet mode. In the demo it goes fullscreen on a second display connected to the laptop, so judges watch the signing and tracking there. It remembers which display it was on and can be sent to any display (menu bar > Demo Mode On).
- **Preview:** stays on the main laptop screen next to the apps being driven (Claude Code, the demo website, Siri, Meet). It has the same live view plus the output-mode picker (Claude Code, Voice, Meet), Claude Code's reply, captions, and the mock-sign box.
- **Setup wizard, Settings, and Sign Guide** come from SignBridge as they were.

Everything the signer needs must also fit in Demo Mode alone, since a Deaf signer gets no audio feedback.

## Hackathon tracks this stack is built for

We're entering the Anthropic and Cartesia sponsor tracks, Meta's "Bringing People Closer Together with AI," and the Cal Hacks general prizes. That's why the stack is fixed:

- **Claude (Anthropic API)** does gloss-to-English, and **Claude Code** is an output. Claude must do something that matters, and we must show we know where it can go wrong (hence the YES/NO confirm).
- **Cartesia** is the voice layer: Sonic for text-to-speech, Ink for speech-to-text captions. Cartesia's rules: voice must be core to the product, the README must list which Cartesia features we use, and no API keys may be committed.
- Don't add Gemini or any other LLM or voice provider.

## Tech defaults (change only if there's a strong reason, and say why)

- Python 3.11, managed with `uv` (fall back to `pip` + `requirements.txt` if needed).
- Target: macOS (Apple Silicon) first. Keep the OS-specific parts behind interfaces.
- UI: a **native macOS app in SwiftUI**, reused from SignBridge (`ui/macos`, a Swift package; needs Xcode or its command-line tools). It launches the Python engine (`app.py`) as a child process and talks to it in JSON lines: commands on stdin, events on stdout, in SignBridge's protocol (`ui/server.py`). No web server, no localhost, no browser.
- Packaging: `make app` runs `packaging/build.sh`, which builds `dist/SignBridge.app` with the Swift app, a bundled Python, the engine's packages, and the MediaPipe model, using `packaging/Info.plist` (camera and microphone usage descriptions). It installs to `~/Applications` only with `--install`.
- LLM: Claude via the official `anthropic` Python SDK. Model name lives in `config.yaml` (default to a fast, low-latency Claude model).
- Voice: Cartesia via the official `cartesia` Python SDK. Sonic for TTS, Ink for streaming STT. Check docs.cartesia.ai for current model IDs and put them in `config.yaml`.
- Audio devices: `sounddevice` for playing TTS into the "BlackHole 2ch" device and for capturing Meet's audio for captions.
- Config: one `config.yaml` plus `.env` for secrets (`ANTHROPIC_API_KEY`, `CARTESIA_API_KEY`). Commit a `.env.example`, never `.env`. Add `.env` to `.gitignore` before the first commit.
- Tests: `pytest`. Lint/format: `ruff`.

## Repo structure to create

```
calhacks-2026/
  README.md                 # exists, don't rewrite. Only fill in "Getting started" at the end
  pyproject.toml
  config.yaml
  .env.example
  .gitignore
  Makefile                  # make run, make mock, make test, make lint, make app
  MVP.md                    # exists: what Person A, B, and C each build. Don't rewrite it
  fixtures/
    landmarks_sample.jsonl  # a few seconds of fake or recorded landmark frames for replay
    captions_sample.txt     # scripted incoming-speech lines for Meet mode
  shared/
    events.py               # dataclasses for every message passed between modules
    bus.py                  # tiny in-process pub/sub (asyncio queues)
    config.py               # loads config.yaml + .env
  recognition/
    base.py                 # Recognizer interface
    mock.py                 # keyboard-driven mock recognizer (see below)
    replay.py               # replays fixtures/landmarks_sample.jsonl as LandmarkFrames (no webcam needed)
    camera.py               # webcam capture + MediaPipe landmarks (stub OK, but runnable if easy)
    gating.py               # signing-area gating: only recognize when hands are in the signing space
    isolated.py             # stub: isolated sign model (Kaggle ISLR 1st place, TFLite)
    fingerspelling.py       # stub: fingerspelling model
    segmenter.py            # turns a stream of per-frame predictions into discrete SignEvents
  language/
    base.py                 # Translator interface: list[gloss] -> English
    mock.py                 # rule-based mock (join tokens, light cleanup) for offline demo
    claude.py               # stub: Claude translator (Anthropic API)
    prompts/gloss_to_english.md
  outputs/
    base.py                 # Output interface
    router.py               # chooses output by current mode; handles YES/NO confirmation
    claude_code.py          # stub: send text to Claude Code (subprocess `claude -p` or terminal paste)
    tts_cartesia.py         # stub: Cartesia Sonic TTS -> BlackHole virtual mic
    tts_say.py              # offline backup: macOS `say` -> BlackHole (works with no API key)
    console.py              # prints to terminal, always available, used in tests
    mock_claude_code.py     # pretends to be Claude Code: streams a canned reply back to the UI
    mock_tts.py             # logs the text it "spoke" (optionally plays it on speakers with `say`)
  captions/
    base.py                 # CaptionSource interface (incoming speech -> Caption events)
    mock.py                 # emits lines from fixtures/captions_sample.txt on a timer
    cartesia_stt.py         # stub: Cartesia Ink streaming speech-to-text of the Meet audio
  ui/
    server.py               # the engine side of the app: SignBridge's JSON-lines protocol on top of the bus, preview frames
    macos/                  # SignBridge's SwiftUI app (Swift package): menu bar, setup, Preview, Demo Mode, Sign Guide, Settings
  packaging/
    Info.plist              # the .app's Info.plist: NSCameraUsageDescription and NSMicrophoneUsageDescription
    build.sh                # builds dist/SignBridge.app: Swift app + bundled Python engine (make app)
  app.py                    # engine entry point: wires bus + recognizer + translator + router + captions, serves the app
  tools/
    record_landmarks.py     # records webcam landmarks to a .jsonl fixture (stub if MediaPipe won't install)
  tests/
    contracts/              # one contract test per interface; mocks AND real implementations must pass them
    test_bus.py
    test_segmenter.py
    test_router_confirm.py
    test_end_to_end_mock.py
```

## Core interfaces (define these precisely, everything else depends on them)

In `shared/events.py`, as frozen dataclasses with timestamps:

- `LandmarkFrame`: per-frame hand/pose/face landmarks, the `hands_in_signing_space` flag, and the camera image for that frame (optional, `None` in mock mode) so the UI can draw the feed and overlay without opening the camera itself.
- `SignEvent`: `gloss: str`, `confidence: float`, `kind: "isolated" | "fingerspell" | "control"`.
- `Utterance`: the list of `SignEvent`s between an utterance start and end.
- `Translation`: `gloss: list[str]`, `english: str`, `provider: str`.
- `ConfirmRequest` / `ConfirmResult`: for the YES/NO step before anything is sent to Claude Code.
- `ModeChanged`: `mode: "claude_code" | "voice" | "meet"`.
- `Caption`: incoming speech text for Meet mode (stub source for now).

Control signs are ordinary `SignEvent`s with `kind="control"`: `YES`, `NO`, `SEND` (end of utterance), `CLEAR`, and `MODE` (cycle modes). They must never be sent to the translator.

Interfaces:

- `Recognizer`: async, `start()`, `stop()`, publishes `SignEvent`s to the bus.
- `Translator`: `async translate(gloss: list[str]) -> Translation`.
- `Output`: `async send(text: str) -> None`, plus `name` and `available()`.

## The mock recognizer (most important piece for the team)

The team needs to build and demo everything downstream before the models work. `recognition/mock.py` takes input from the mock-sign box in the Preview window (and from the terminal under `make mock`) and publishes `SignEvent`s:

- Typing a word + Enter publishes an isolated sign with that gloss (uppercased).
- `#hello` publishes a fingerspelled word.
- `/yes`, `/no`, `/send`, `/clear`, `/mode` publish control signs.
- `make mock` runs the whole app with the mock recognizer, mock translator, and console output, so it works with no webcam, no API keys, and no BlackHole.

## Every component has a mock, chosen in config

`config.yaml` picks the implementation for each component independently, and every default is the mock:

```yaml
recognizer: mock        # mock | replay | camera
translator: mock        # mock | claude
claude_code: mock       # mock | real
tts: mock               # mock | say | cartesia
captions: mock          # mock | cartesia
```

`make mock` uses all mocks. Each teammate flips only their own line while developing, so one person's half-finished code never breaks anyone else's run. Add a contract test in `tests/contracts/` for each interface (`Recognizer`, `Translator`, `Output`, `CaptionSource`) that the mock passes now and the real implementation must pass later.

## Flow to wire up end to end

1. The recognizer publishes `SignEvent`s.
2. An utterance buffer collects them until `SEND`. `CLEAR` empties it.
3. The translator turns the utterance's gloss into English.
4. The router checks the mode:
   - `claude_code`: publish a `ConfirmRequest` showing the English, wait for `YES` or `NO`, and only send on `YES`.
   - `voice` and `meet`: send straight to the TTS output.
5. The UI shows the live gloss, the English preview, the confirm prompt, the current mode, and captions.

If an output isn't available (e.g. BlackHole isn't installed), fall back to `console` and show a warning in the UI. Never crash.

## Stubs: what "done" looks like for each

Each stub must import cleanly, have the right signature, log that it's a stub, and contain a `TODO` comment that says exactly what to implement and which model or library to use:

- `isolated.py`: Kaggle ISLR 1st-place model (`sign/kaggle-asl-signs-1st-place` on Hugging Face, MIT license), 250-sign vocabulary, TFLite.
- `fingerspelling.py`: Kaggle ASL Fingerspelling competition model.
- `claude.py`: Claude via the Anthropic SDK, using `language/prompts/gloss_to_english.md`. Write a first draft of that prompt: ASL gloss in, natural English out, keep the signer's meaning, don't add content, and when the input is a coding request, phrase it as a clear instruction.
- `claude_code.py`: run `claude -p "<text>"` in a configured project directory and stream the output back to the UI.
- `tts_cartesia.py`: stream Cartesia Sonic audio and play it into the "BlackHole 2ch" output device with `sounddevice`. If Cartesia fails at runtime, fall back to `tts_say.py` and warn in the UI.
- `tts_say.py`: implement this one for real (it's small): macOS `say` rendered to audio and played into "BlackHole 2ch".
- `captions/cartesia_stt.py`: capture Meet's audio from a separate capture device (not the device our TTS writes to, or we'll caption ourselves) and stream it to Cartesia Ink. The device name lives in `config.yaml`.

`camera.py` and `gating.py`: if MediaPipe installs cleanly, make the camera actually run and publish `LandmarkFrame`s with a simple signing-space box. If not, stub them.

## Team split (already written in `MVP.md`)

`MVP.md` assigns ownership. Make the scaffolding match it exactly:

- **Person A: Recognition** owns `recognition/`, `tools/`, and `fixtures/landmarks_sample.jsonl`. Config line: `recognizer`.
- **Person B: Language + Claude Code** owns `language/`, `outputs/claude_code.py`, `outputs/mock_claude_code.py`, and `outputs/router.py`. Config lines: `translator`, `claude_code`.
- **Person C: Voice, Meet, and UI** owns `outputs/tts_*.py`, `outputs/mock_tts.py`, `captions/`, `ui/`, and `fixtures/captions_sample.txt`. Config lines: `tts`, `captions`.

Shared files (`shared/`, `app.py`, `config.yaml`, `Makefile`, `tests/contracts/`) should change rarely. Put a comment at the top of `shared/events.py` saying changes need a heads-up to the whole team. Don't create a separate `TASKS.md`.

## Constraints

- Keep modules independent: they talk only through the bus and the interfaces above, so Persons A, B, and C can work in parallel without conflicts.
- No real API calls in tests.
- Don't edit the README beyond filling in "Getting started" with the real commands (including installing BlackHole and the Claude Code CLI, and setting `ANTHROPIC_API_KEY` and `CARTESIA_API_KEY`).
- Don't add features that aren't listed here.

## Definition of done

- `make test` passes, including an end-to-end mock test: gloss `ME WANT FIX BUG LOGIN PAGE` + `SEND` in `claude_code` mode produces a `ConfirmRequest`, and then `YES` sends it to the console output while `NO` sends nothing.
- `make mock` builds and opens the Mac app (setup wizard on first run, then Preview), and it updates live as you type mock signs: Claude Code mode shows the confirm prompt and then the canned mock reply, voice mode shows what was "spoken", and Meet mode shows the scripted captions.
- Setting `recognizer: replay` runs the app from the landmark fixture with no webcam.
- All contract tests pass for every mock.
- Every file `MVP.md` assigns to a person exists, and `make mock` runs with each person's config line still on `mock`.
- `make lint` is clean.
- Commit in small logical commits and push to `main`.

When you're done, reply with a short summary: what runs, what's stubbed, and the 3 to 5 next tasks you'd suggest, one set per person (A, B, C).
