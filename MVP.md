# MVP plan: who builds what

This is the plan for after the scaffolding (`SCAFFOLD.md`) is built. Each person owns one part of the app, swaps its mocks for the real thing, and doesn't touch anyone else's files. Everything talks through the interfaces in `shared/events.py`, so you can each work and test alone using the mocks for everyone else's parts.

**Deadline:** submissions are due **Sunday Oct 25, 9:00 AM PT**, and we have to be at the venue by 8:00 AM. Judging needs a public GitHub repo, an image, and a live or recorded demo (3-minute pitch plus 2 minutes of questions).

**Tracks we're entering:**
- Anthropic (Claude does the translation and drives Claude Code)
- Cartesia (voice output and captions)
- Meta, "Bringing People Closer Together with AI" (the Meet story)
- Cal Hacks general prizes (Overall, People-First Social Impact, Most Technically Complex, Most Creative, Hacker's Choice)
- Commit Fellowship (opt in on the submission form)

**What it is:** a native Mac menu-bar app, not a web page: SignBridge's SwiftUI front end (`ui/macos`) driving our Python engine. Its **Preview** window shows the webcam feed with tracking, the recognized signs, the English, the confirm step, the output-mode picker, Claude Code's reply, and captions. **Demo Mode** is the same live view as a fullscreen stage with recent phrases. For the demo, Demo Mode goes fullscreen on a second display plugged into the laptop, so judges see the signing and tracking there while the laptop's own screen shows Claude Code, Siri, and Meet actually doing the work.

**Who it's for:** Deaf ASL signers. Not hearing ASL learners. Don't describe the product as "giving Deaf people a voice" or call them "silent"; describe it as access to voice-only tools and parity in calls. Don't claim it replaces interpreters.

**What Deaf users told us:** Professor Lance Forshay (UW, Deaf ASL faculty) answered our survey. He'd use this for **video calls only**. His biggest frustrations with calls are interpreter quality and hearing people hanging up because they don't know who's calling. What would stop him from trusting it: **"accuracy, government recording, privacy."** His full answers and what we changed are in `docs/user-research.md`. They set three rules for everyone:
- **Meet is the centerpiece.** It's demo moment 3, after Claude Code kick-off and Siri, so the strongest part comes last before the Claude Code payoff, and it gets the most time and polish.
- **Video never leaves the laptop.** Our app never sends video anywhere: tracking and recognition run on the device. The translator sends Claude only the recognized sign words (text). Cartesia gets only the final English to speak, plus the other side's call audio for captions. Nothing is recorded or saved to disk, and the app always shows whether the camera is on. Don't add logging that saves frames or transcripts: log the user's text at DEBUG at most, never at INFO.
- **The signer sees the English before anyone hears it** wherever we can manage it (YES/NO for Claude Code, an optional review step in Meet).

## What the MVP must do

The MVP is four demo moments that work live, end to end, with a real webcam, in this order. **We open with Claude Code** so it has time to build while we show the rest, then come back to it at the end. Siri comes before Meet so the demo builds up to the strongest part instead of following it with a smaller one. **The Meet call is the centerpiece:** it's the one use the Deaf ASL professor who answered our survey said he'd actually want (see `docs/user-research.md`), so it gets the most time and polish.

1. **Claude Code (kick-off).** A teammate signs a request that starts a small build, the app shows the English, they sign `YES`, and Claude Code starts working on a small demo website. Pick a request that takes Claude Code a couple of minutes and that can be signed from the vocabulary plus fingerspelling (`docs/asl-vocab-check.md`). We leave it running.
2. **Siri.** A teammate signs a question (for example `TOMORROW RAIN`), the app opens Siri by holding ⌘Space and types "Will it rain tomorrow?" with Type to Siri, and Siri answers on screen. Siri can't be triggered through the virtual mic ("Hey Siri" doesn't work from one), so Siri gets text, not speech.
3. **Google Meet (centerpiece).** A teammate starts a Meet call. As soon as they switch to Meet mode, the app introduces them in a Cartesia voice ("Hi, this is <name>. I'm Deaf and signing through <app>, so there may be a short pause before I answer."), because hearing people hang up on relay calls when they don't know who's calling. The teammate signs a greeting (for example `HELLO`, `THANKYOU`), the other side hears it in the Cartesia voice, and what they say back appears as live captions in our app.
4. **Back to Claude Code (re-prompt).** We show what Claude Code built, then sign a short follow-up to change one component (for example `MAKE TITLE RED` with `TITLE` fingerspelled), sign `YES`, and watch the page update. This shows signed back-and-forth, not just one command.

Moments 1 and 4 are the same Claude Code session, so the re-prompt has to continue it (keep the session going, for example with `claude -p --continue`, rather than starting fresh).

Demo signs must come from the Kaggle 250-sign vocabulary or fingerspelling unless Person A adds custom signs. `docs/asl-vocab-check.md` lists which demo words are in the vocabulary. Nobody on the team knows ASL, so learn each demo sign from a reputable source (for example Lifeprint or Handspeak) and keep the demo script short and fixed.

**Control signs for the MVP:**
- `YES` and `NO` are signed (both are in the vocabulary).
- `FINISH` is signed and acts as SEND (it's in the vocabulary and is a natural end-of-thought sign).
- `CLEAR` and `MODE` are in the UI: Cancel while signing clears, and the Claude Code / Siri / Voice / Meet picker sets the mode. Making them signs is a stretch goal.

## How we work

- Each person works on their own branch (`person-a`, `person-b`, `person-c`), merges to `main` through a pull request, and pulls `main` often.
- While developing, flip only your own line in `config.yaml` from `mock` to the real thing. `make mock` must keep working for everyone at all times.
- Your real implementation must pass the contract test for its interface in `tests/contracts/`.
- Don't change `shared/`, `app.py`, `Makefile`, or `tests/contracts/` without telling the other two first.
- Secrets go in `.env` only (`ANTHROPIC_API_KEY`, `CARTESIA_API_KEY`). Never commit keys; Cartesia's rules disqualify that.

## Checkpoints

- **Friday night:** scaffolding merged to `main`. Everyone has run `make mock` and `make test` on their own laptop.
- **Saturday midday:** each person's first real piece works alone (A: live landmarks plus a few recognized signs; B: real Claude translation; C: speech into BlackHole heard in a Meet call, and a question typed to Siri).
- **Saturday evening:** first full integration. A real sign goes all the way through to Claude Code and to voice. Fix what breaks.
- **Saturday night:** all four demo moments work on the real two-screen setup. Record a backup demo video.
- **Sunday ~3 AM:** feature freeze. Only bug fixes, README, Devpost write-up, and pitch practice after this.
- **Sunday 8 AM:** at the venue. **9 AM:** submitted.

---

## Person A: Recognition

**You own:** `recognition/`, `tools/record_landmarks.py`, `fixtures/landmarks_sample.jsonl`. Config line: `recognizer`.

**Your job:** turn the webcam into a stream of `SignEvent`s that are accurate enough for the demo script.

**MVP (in this order):**
1. **Camera and landmarks.** Webcam capture with MediaPipe Holistic landmarks, published as `LandmarkFrame`s. Publish the camera image with each frame so the app can draw it. Done when Preview shows the feed with landmarks at a steady frame rate.
2. **Signing-space gating.** Only recognize while the hands are up in front of the chest and face, so resting hands and typing aren't read as signs. Done when putting your hands down produces no events.
3. **Isolated signs.** Run the Kaggle ISLR 1st-place TFLite model (`sign/kaggle-asl-signs-1st-place` on Hugging Face, MIT, 250 signs). Done when every in-vocabulary sign in the demo script is recognized correctly most of the time.
4. **Segmenter.** Turn per-frame predictions into one `SignEvent` per sign: no duplicates, no events while the hands are still, and a confidence threshold in `config.yaml`. Done when signing the demo script produces the right gloss sequence.
5. **Control signs.** `YES`, `NO`, and `FINISH` are published with `kind="control"` (`FINISH` maps to SEND).
6. **Fingerspelling.** The Kaggle ASL Fingerspelling model, for demo words that aren't in the vocabulary. Done when the fingerspelled demo words come through, even if they need a retry.
7. **Landmark fixture.** Use `tools/record_landmarks.py` to record the demo script and replace the fake `fixtures/landmarks_sample.jsonl`, so B and C can test with real data via `recognizer: replay`.

**Stretch:** custom signs for missing demo words, trained on landmarks you record yourself (a small classifier on top of the recorded landmarks); `CLEAR` and `MODE` as signs; SignBridge's control gestures (both open palms to start, thumbs up to send, thumbs down to cancel; port `signbridge/gestures.py` from the earlier project), which the app's setup wizard and hints already expect; better accuracy in bad lighting.

**Test alone with:** `recognizer: camera` and everything else on `mock`. Preview shows the gloss you produced.

**Needs:** a laptop webcam and good lighting. No API keys.

## Person B: Language and Claude Code

**You own:** `language/`, `outputs/claude_code.py`, `outputs/mock_claude_code.py`, `outputs/router.py`. Config lines: `translator` and `claude_code`.

**Your job:** turn gloss into natural English with Claude, and send coding requests to Claude Code safely. This is the core of the **Anthropic** track: Claude has to do something that matters, and we have to show we know where it can go wrong.

**MVP (in this order):**
1. **Claude translator.** `language/claude.py` calls Claude through the Anthropic SDK with `language/prompts/gloss_to_english.md`. Done when the demo script's gloss comes back as clean English in under ~2 seconds.
2. **Prompt and test cases.** A set of gloss-to-English examples, covering the demo script, fingerspelled words, recognition mistakes, and coding requests, in a test that can run against the real API on demand (not in `make test`). The prompt keeps the signer's meaning, adds nothing, and phrases coding requests as clear instructions. Siri requests are plain questions, without "Hey Siri" (Siri is opened with ⌘Space, not by voice).
3. **Confirm flow.** In Claude Code mode, nothing is sent until the signer signs `YES`; `NO` discards it. The UI shows the exact English that will be sent.
4. **Real Claude Code output.** `outputs/claude_code.py` runs `claude -p "<text>"` in a configured demo project folder and streams Claude Code's reply back to the UI. Run it with `--permission-mode acceptEdits` with `--allowedTools` limited to what the demo site needs (for a static site, file tools such as `Read,Edit,Write,Glob,Grep`; no `Bash` unless the site truly needs it), never `--dangerously-skip-permissions`, and Claude Code confined to the demo project folder (run it with that folder as its working directory, no `--add-dir`). Done when demo moments 1 and 4 (Claude Code kick-off, then a re-prompt that continues the same session) work with typed mock signs.
5. **Demo project.** A starting folder for the small website Claude Code builds during the demo, open in a browser next to the app (auto-reload helps). Choose the kick-off request (a couple of minutes of building, signable from the vocabulary plus fingerspelling) and the re-prompt (one visible component change), and test both end to end.
6. **Router.** Sends English to Claude Code in `claude_code` mode, to Person C's Type to Siri output in `siri` mode, and to Person C's voice output in `voice` and `meet` modes, falling back to console output if an output is unavailable.
7. **Review before speaking (Meet).** An option, off by default for the demo, that makes Meet and Voice mode wait for `YES` like Claude Code does, so a misrecognized sign isn't spoken in the signer's name. Accuracy was the first thing our Deaf respondent said would stop him trusting the tool. Adding its config line touches `config.yaml`, so give the team a heads-up.

**Stretch:** low-confidence handling (when recognition confidence is low, Claude asks the signer to confirm or re-sign instead of guessing); keeping short context between utterances; the README's Claude section.

**Test alone with:** `recognizer: mock` (type gloss), `translator: claude`, `claude_code: real`.

**Needs:** `ANTHROPIC_API_KEY` in `.env`, and the Claude Code CLI installed and logged in.

**You also write:** the "How we use Claude" section of the README for the Anthropic judges, covering what Claude does, where it can go wrong (a mistranslation spoken in a Deaf person's name), how the YES/NO confirm and review-before-speaking handle that, and that Claude only ever sees sign words as text, never video.

## Person C: Voice, Siri, Meet, and UI

**You own:** `outputs/tts_cartesia.py`, `outputs/tts_say.py`, `outputs/mock_tts.py`, the Siri output (`outputs/siri.py`, `outputs/mock_siri.py`), `captions/`, `ui/`, `fixtures/captions_sample.txt`. Config lines: `tts`, `siri`, and `captions`.

**Your job:** make the app's English heard as a real microphone, type questions to Siri, show incoming speech as captions, and make the screen clear for a Deaf user. This is the core of the **Cartesia** and **Meta** tracks.

**MVP (in this order):**
1. **BlackHole setup.** Install BlackHole 2ch and write down the exact macOS audio setup in the README. Done when `tts: say` speaks into BlackHole and dictation or Meet hears it after selecting BlackHole as the microphone.
2. **Cartesia TTS.** `tts_cartesia.py` streams Cartesia Sonic audio into BlackHole, falling back to `say` if Cartesia fails. Done when the other side of a Meet call hears it with typed mock signs.
3. **Type to Siri.** *(Done: `siri: real` works, tested on macOS 26.2.)* `outputs/siri.py` opens Siri by holding ⌘Space (Siri's keyboard shortcut set to Hold Command Space), types the English, and presses Return, the way SignBridge's engine did. It needs Type to Siri on (Accessibility > Siri) and Accessibility permission for the app. Done when demo moment 2 (Siri) works with typed mock signs.
4. **Meet captions.** `captions/cartesia_stt.py` captures the Meet call's audio from a separate device (not the one our voice goes into, or we caption ourselves) and streams it to Cartesia Ink. Done when the other person's speech shows up as captions within a couple of seconds.
5. **Demo Mode.** The fullscreen stage on the second display: camera with tracking, signs as they land, the English, the confirm step, captions in Meet mode, and recent phrases. It remembers its display (menu bar > Demo Mode On). Done when it looks good fullscreen on an external screen.
6. **Preview and setup.** Preview has the output-mode picker (with Siri), Claude Code's streamed reply, captions in Meet mode, and the mock-sign box. Every state must be visible, because the user gets no audio feedback. Make the setup wizard fit our engine: its Position step's "Save This Position" isn't wired up yet (the signing space is in `config.yaml`), and its Siri test goes through the Type to Siri output *(done)*.
7. **Demo moment 3 (Meet).** A real Meet call between two laptops: our side signs, the other side hears it, and their reply appears as captions.
8. **Call intro and signing cue.** When Meet mode starts, speak a short introduction once in the Cartesia voice, built from the signer's name in Settings ("Hi, this is <name>. I'm Deaf and signing through <app>, so there may be a short pause before I answer."), plus an "Introduce me" button to replay it. If the signer has been signing for more than a few seconds without sending, say "One moment, I'm signing." at most once per utterance. Done when the other side of a test call hears both.
9. **Privacy on screen.** A camera-on indicator that's always visible in Preview and Demo Mode, and a short line in Settings and the README: our app never sends video anywhere, only sign words go to Claude, only the English (and the other side's call audio, for captions) goes to Cartesia, and nothing is recorded.

**Stretch:** a "download and run it" `.app` (`make app` builds one; it still needs a place for API keys outside the bundle); choosing a voice; showing when the app is speaking; a polished look for judging photos.

**Test alone with:** `recognizer: mock`, `translator: mock`, `tts: cartesia`, `siri: real`, `captions: cartesia`.

**Needs:** `CARTESIA_API_KEY` in `.env`, BlackHole installed, Xcode or its command-line tools (the app is Swift), a second device for the Meet test, and the second display for the demo.

**You also write:** the "Cartesia features we use" section of the README, which Cartesia's rules require.

## Everyone, Sunday morning

- The README is complete: setup steps, how it works, the Claude and Cartesia sections, and honest limitations (small vocabulary, no facial grammar).
- Devpost submission with the repo link, an image, the demo video, and all our tracks selected, plus the Commit Fellowship opt-in.
- The pitch tells the real story and opens by signing a build request to Claude Code, does Siri, then spends the most time on the Meet call: "A Deaf ASL professor told us the only place he'd use this is video calls, so we built for that." Quote him on hang-ups and on privacy, then come back to what Claude Code built and re-prompt it, and give the YES/NO confirm and on-device video as our answers to "where can this go wrong." Close with the plan to test with him after Cal Hacks.
