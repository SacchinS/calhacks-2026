# MVP plan: who builds what

This is the plan for after the scaffolding (`SCAFFOLD.md`) is built. Each person owns one part of the app, swaps its mocks for the real thing, and doesn't touch anyone else's files. Everything talks through the interfaces in `shared/events.py`, so you can each work and test alone using the mocks for everyone else's parts.

**Deadline:** submissions are due **Sunday Oct 25, 9:00 AM PT**, and we have to be at the venue by 8:00 AM. Judging needs a public GitHub repo, an image, and a live or recorded demo (3-minute pitch plus 2 minutes of questions).

**Tracks we're entering:**
- Anthropic (Claude does the translation and drives Claude Code)
- Cartesia (voice output and captions)
- Meta, "Bringing People Closer Together with AI" (the Meet story)
- Cal Hacks general prizes (Overall, People-First Social Impact, Most Technically Complex, Most Creative, Hacker's Choice)
- Commit Fellowship (opt in on the submission form)

**Who it's for:** Deaf ASL signers. Not hearing ASL learners. Don't describe the product as "giving Deaf people a voice" or call them "silent"; describe it as access to voice-only tools and parity in calls.

## What the MVP must do

The MVP is three demo moments that work live, end to end, with a real webcam:

1. **Claude Code.** A teammate signs a short request (for example `MAKE TITLE RED` with `TITLE` fingerspelled), the app shows the English ("Make the title red."), they sign `YES`, and Claude Code makes the change in a small demo website, visible on screen.
2. **Siri.** A teammate signs a question (for example `TOMORROW RAIN`), the app speaks "Hey Siri, will it rain tomorrow?" through the virtual mic, and Siri answers on screen.
3. **Google Meet.** A teammate signs a greeting (for example `HELLO`, `THANKYOU`) into a Meet call. The other side hears it in a Cartesia voice, and what they say back appears as live captions in our app.

Demo signs must come from the Kaggle 250-sign vocabulary or fingerspelling unless Person A adds custom signs. `docs/asl-vocab-check.md` lists which demo words are in the vocabulary. Nobody on the team knows ASL, so learn each demo sign from a reputable source (for example Lifeprint or Handspeak) and keep the demo script short and fixed.

**Control signs for the MVP:**
- `YES` and `NO` are signed (both are in the vocabulary).
- `FINISH` is signed and acts as SEND (it's in the vocabulary and is a natural end-of-thought sign).
- `CLEAR` and `MODE` are buttons in the UI. Making them signs is a stretch goal.

## How we work

- Each person works on their own branch (`person-a`, `person-b`, `person-c`), merges to `main` through a pull request, and pulls `main` often.
- While developing, flip only your own line in `config.yaml` from `mock` to the real thing. `make mock` must keep working for everyone at all times.
- Your real implementation must pass the contract test for its interface in `tests/contracts/`.
- Don't change `shared/`, `app.py`, `Makefile`, or `tests/contracts/` without telling the other two first.
- Secrets go in `.env` only (`ANTHROPIC_API_KEY`, `CARTESIA_API_KEY`). Never commit keys; Cartesia's rules disqualify that.

## Checkpoints

- **Friday night:** scaffolding merged to `main`. Everyone has run `make mock` and `make test` on their own laptop.
- **Saturday midday:** each person's first real piece works alone (A: live landmarks plus a few recognized signs; B: real Claude translation; C: speech into BlackHole heard by Siri).
- **Saturday evening:** first full integration. A real sign goes all the way through to Claude Code and to voice. Fix what breaks.
- **Saturday night:** all three demo moments work. Record a backup demo video.
- **Sunday ~3 AM:** feature freeze. Only bug fixes, README, Devpost write-up, and pitch practice after this.
- **Sunday 8 AM:** at the venue. **9 AM:** submitted.

---

## Person A: Recognition

**You own:** `recognition/`, `tools/record_landmarks.py`, `fixtures/landmarks_sample.jsonl`. Config line: `recognizer`.

**Your job:** turn the webcam into a stream of `SignEvent`s that are accurate enough for the demo script.

**MVP (in this order):**
1. **Camera and landmarks.** Webcam capture with MediaPipe Holistic landmarks, published as `LandmarkFrame`s. Done when the UI's webcam preview shows landmarks at a steady frame rate.
2. **Signing-space gating.** Only recognize while the hands are up in front of the chest and face, so resting hands and typing aren't read as signs. Done when putting your hands down produces no events.
3. **Isolated signs.** Run the Kaggle ISLR 1st-place TFLite model (`sign/kaggle-asl-signs-1st-place` on Hugging Face, MIT, 250 signs). Done when every in-vocabulary sign in the demo script is recognized correctly most of the time.
4. **Segmenter.** Turn per-frame predictions into one `SignEvent` per sign: no duplicates, no events while the hands are still, and a confidence threshold in `config.yaml`. Done when signing the demo script produces the right gloss sequence.
5. **Control signs.** `YES`, `NO`, and `FINISH` are published with `kind="control"` (`FINISH` maps to SEND).
6. **Fingerspelling.** The Kaggle ASL Fingerspelling model, for demo words that aren't in the vocabulary. Done when the fingerspelled demo words come through, even if they need a retry.
7. **Landmark fixture.** Use `tools/record_landmarks.py` to record the demo script and replace the fake `fixtures/landmarks_sample.jsonl`, so B and C can test with real data via `recognizer: replay`.

**Stretch:** custom signs for missing demo words, trained on landmarks you record yourself (a small classifier on top of the recorded landmarks); `CLEAR` and `MODE` as signs; better accuracy in bad lighting.

**Test alone with:** `recognizer: camera` and everything else on `mock`. The UI shows the gloss you produced.

**Needs:** a laptop webcam and good lighting. No API keys.

## Person B: Language and Claude Code

**You own:** `language/`, `outputs/claude_code.py`, `outputs/mock_claude_code.py`, `outputs/router.py`. Config lines: `translator` and `claude_code`.

**Your job:** turn gloss into natural English with Claude, and send coding requests to Claude Code safely. This is the core of the **Anthropic** track: Claude has to do something that matters, and we have to show we know where it can go wrong.

**MVP (in this order):**
1. **Claude translator.** `language/claude.py` calls Claude through the Anthropic SDK with `language/prompts/gloss_to_english.md`. Done when the demo script's gloss comes back as clean English in under ~2 seconds.
2. **Prompt and test cases.** A set of gloss-to-English examples, covering the demo script, fingerspelled words, recognition mistakes, and coding requests, in a test that can run against the real API on demand (not in `make test`). The prompt keeps the signer's meaning, adds nothing, and phrases coding requests as clear instructions. Siri requests start with "Hey Siri".
3. **Confirm flow.** In Claude Code mode, nothing is sent until the signer signs `YES`; `NO` discards it. The UI shows the exact English that will be sent.
4. **Real Claude Code output.** `outputs/claude_code.py` runs `claude -p "<text>"` in a configured demo project folder and streams Claude Code's reply back to the UI. Done when demo moment 1 works with typed mock signs.
5. **Demo project.** A tiny website (one HTML page with a title) that Claude Code edits during the demo, open in a browser next to the app.
6. **Router.** Sends English to Claude Code in `claude_code` mode and to Person C's voice output in `voice` and `meet` modes, falling back to console output if an output is unavailable.

**Stretch:** low-confidence handling (when recognition confidence is low, Claude asks the signer to confirm or re-sign instead of guessing); keeping short context between utterances; the README's Claude section.

**Test alone with:** `recognizer: mock` (type gloss), `translator: claude`, `claude_code: real`.

**Needs:** `ANTHROPIC_API_KEY` in `.env`, and the Claude Code CLI installed and logged in.

**You also write:** the "How we use Claude" section of the README for the Anthropic judges, covering what Claude does, where it can go wrong, and how the YES/NO confirm handles that.

## Person C: Voice, Meet, and UI

**You own:** `outputs/tts_cartesia.py`, `outputs/tts_say.py`, `outputs/mock_tts.py`, `captions/`, `ui/`, `fixtures/captions_sample.txt`. Config lines: `tts` and `captions`.

**Your job:** make the app's English heard as a real microphone, show incoming speech as captions, and make the screen clear for a Deaf user. This is the core of the **Cartesia** and **Meta** tracks.

**MVP (in this order):**
1. **BlackHole setup.** Install BlackHole 2ch and write down the exact macOS audio setup in the README. Done when `tts: say` speaks into BlackHole and Siri, dictation, or Meet hears it after selecting BlackHole as the microphone.
2. **Cartesia TTS.** `tts_cartesia.py` streams Cartesia Sonic audio into BlackHole, falling back to `say` if Cartesia fails. Done when demo moment 2 (Siri) works with typed mock signs.
3. **Meet captions.** `captions/cartesia_stt.py` captures the Meet call's audio from a separate device (not the one our voice goes into, or we caption ourselves) and streams it to Cartesia Ink. Done when the other person's speech shows up as captions within a couple of seconds.
4. **UI.** Large, high-contrast text; the webcam preview; the live gloss; the English preview; a clear YES/NO confirm prompt; the current mode; `CLEAR` and `MODE` buttons; captions in Meet mode; Claude Code's streamed reply in Claude Code mode. Every state must be visible, because the user gets no audio feedback.
5. **Demo moment 3.** A real Meet call between two laptops: our side signs, the other side hears it, and their reply appears as captions.

**Stretch:** choosing a voice in the UI; showing when the app is speaking; a visual cue when a sign is recognized; a polished look for judging photos.

**Test alone with:** `recognizer: mock`, `translator: mock`, `tts: cartesia`, `captions: cartesia`.

**Needs:** `CARTESIA_API_KEY` in `.env`, BlackHole installed, and a second device for the Meet test.

**You also write:** the "Cartesia features we use" section of the README, which Cartesia's rules require.

## Everyone, Sunday morning

- The README is complete: setup steps, how it works, the Claude and Cartesia sections, and honest limitations (small vocabulary, no facial grammar).
- Devpost submission with the repo link, an image, the demo video, and all our tracks selected, plus the Commit Fellowship opt-in.
- The pitch tells the real story: who it's for, the UW Deaf faculty input and survey, the three demo moments, and the YES/NO confirm as our answer to "where can this go wrong."
