# Handoff: getting the three of us started

**Start here.** If you were told "pull and read HANDOFF.md", this doc is everything you need: it gets each person from zero to working on their part. The scaffolding is done: every part of the app runs on a mock, and `make test`, `make mock`, and `make lint` pass on `main`. The plan itself is in `MVP.md` (who builds what, in what order); this doc doesn't repeat it, beyond the key dates and the demo in short.

**How to use it:**
1. The lead does the "Before anyone starts" list once.
2. Each person does "Everyone: first 15 minutes" (it includes what to read, in order, and picking your role).
3. Each person opens Claude Code in the repo and pastes their prompt from "Starter prompts".

## Before anyone starts (lead)

- [x] **Repo push access.** The repo (`SacchinS/calhacks-2026`) is public, so anyone can clone it, but only collaborators can push. Invites are sent (GitHub > Settings > Collaborators); each teammate accepts theirs (step 1 below).
- [ ] **SignBridge access for Person A.** Person A's stretch goal ports `signbridge/gestures.py` from the earlier project, and `SacchinS/signbridge` is private. Add Person A as a collaborator there, or copy that one file over.
- [ ] **API keys.** Send keys privately (a DM, never the repo or a public channel). Person B needs `ANTHROPIC_API_KEY`. Person C needs `CARTESIA_API_KEY`. Person A needs none.
- [ ] **Who is A, B, and C.** Decide and write it here:
  - Person A (Recognition): ____
  - Person B (Language and Claude Code): ____
  - Person C (Voice, Siri, Meet, and UI): ____

## Everyone: first 15 minutes

1. Accept the GitHub invite to `SacchinS/calhacks-2026` (it comes by email and shows at github.com/notifications). You can clone without it, but you can't push your branch until you accept.
2. Install what the README's "Getting started" lists that you need. Everyone needs macOS on Apple Silicon, Xcode command-line tools (`xcode-select --install`), and uv (`brew install uv`).
3. Clone and run the mocks (already cloned? `git checkout main && git pull` instead of the clone):
   ```bash
   git clone https://github.com/SacchinS/calhacks-2026.git
   cd calhacks-2026
   make install && make test && make mock
   ```
   `make mock` opens the Mac app (hand icon in the menu bar). Click through setup with "Skip for now", open Preview, and type `me want fix bug login page /send /yes` in the box at the bottom. You should see the English, the confirm step, and a mock Claude Code reply.
4. Read, in this order: this file (all of it); `MVP.md` ("What the MVP must do", "How we work", "Checkpoints", then your own Person section); `SCAFFOLD.md` ("Core interfaces" and "The mock recognizer"); `README.md`; `docs/user-research.md` (why Meet is the centerpiece, and the privacy rules); and for A and B, `docs/asl-demo-script-research.md` (the draft glosses and the source video for every sign). Your starter prompt has Claude Code read the first four too.
5. Pick your role with the team: A (Recognition), B (Language and Claude Code), or C (Voice, Siri, Meet, and UI). Write your name in "Who is A, B, and C" above, then make your branch: `git checkout -b person-a` (or `person-b`, `person-c`).
6. If you use API keys: get yours from the lead in a DM, then `cp .env.example .env` and fill it in. `.env` is gitignored. Never commit it; Cartesia's rules disqualify that.
7. Open Claude Code in the repo on your branch and paste your prompt from "Starter prompts" below.
8. From then on, follow "Team rules" below: keep `config.yaml` on `mock` on `main`, merge through a PR to `main`, and run `make test` and `make lint` before every PR (without `make`: `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .`).

## Key dates

From `MVP.md` ("Checkpoints" has the full list):
- **Saturday night:** all four demo moments work on the real two-screen setup, and we record a backup demo video.
- **Sunday ~3 AM:** feature freeze.
- **Sunday Oct 25, 8:00 AM:** at the venue. **9:00 AM PT:** Devpost submission deadline. It's hard: nothing gets in after it.
- **Sunday 10:30 AM–12:30 PM:** judging. The whole team is there.

## The demo, in short

Four moments, in this order (details in `MVP.md`, "What the MVP must do"):
1. **Claude Code kick-off:** sign a build request, sign YES, and leave it building.
2. **Siri:** sign a reminder; the app types it to Siri and Siri sets it.
3. **Google Meet, the centerpiece:** the app introduces the signer in a Cartesia voice, the signer signs a greeting the other side hears, and the reply shows as captions.
4. **Claude Code re-prompt:** sign a small change to what it built, sign YES, and watch the page update.

Why this order: Claude Code goes first so it has minutes to build while we show the rest. Siri comes before Meet so the demo builds up to the strongest part. Meet is the centerpiece because Professor Lance Forshay (Deaf ASL faculty at UW), who answered our survey, said video calls are the one place he'd use this, and that hearing people hang up on relay calls when they don't know who's calling (hence the intro). His answers and what we changed are in `docs/user-research.md`.

The glosses for all four moments are drafts (`docs/asl-demo-script-research.md`). A Deaf signer must approve or rewrite them before the demo. Nobody on the team knows ASL, so learn every sign from the source videos linked there (or from a Deaf signer), never by guessing.

## What's already real, and what's still mocked

| Part | Owner | State |
|---|---|---|
| Bus, events, config, app wiring (`shared/`, `app.py`) | shared | Done. Change only after telling the others. |
| Mac app (`ui/macos`) and its engine bridge (`ui/server.py`) | C | Works on mocks: Preview, Demo Mode, setup wizard, mode picker, panels for Claude Code, Siri, Voice, and Meet. |
| Webcam and landmarks (`recognition/camera.py`, `gating.py`) | A | Camera and MediaPipe landmarks run (`uv sync --extra camera`). The signing-space box is simple. |
| Sign models (`recognition/isolated.py`, `fingerspelling.py`) | A | Stubs: no signs come out of the camera yet. |
| Segmenter (`recognition/segmenter.py`) | A | Basic version works; needs tuning against the real model. |
| Replay (`recognizer: replay`) | A | Works, but `fixtures/landmarks_sample.jsonl` is fake data. |
| Translator (`language/claude.py`) | B | Stub. The mock lowercases the gloss, swaps a few words, and reads the face-marker tags; it's only a stand-in so the app runs (it turns `WW` into "ww"). A first-draft prompt is in `language/prompts/gloss_to_english.md`. |
| Confirm flow and router (`outputs/router.py`) | B | Works on mocks: Claude Code waits for YES/NO; Siri, Voice, and Meet send straight away; console fallback. |
| Claude Code output (`outputs/claude_code.py`) | B | Stub. The mock streams a fake reply. |
| Type to Siri (`outputs/siri.py`) | C | **Real and tested** (`siri: real`). |
| `say` voice into BlackHole (`outputs/tts_say.py`) | C | Real (`tts: say`). |
| Cartesia voice (`outputs/tts_cartesia.py`) | C | Stub. |
| Meet captions (`captions/cartesia_stt.py`) | C | Stub. The mock replays `fixtures/captions_sample.txt`. |

## Recent changes

- **Face markers in the event contract** (Oct 23, commits 19c09f5, ac8be2c, e391e5a). `shared/events.py` changed: `SignEvent` has a new field, `markers`, the facial grammar seen during the sign (`brows_raised`, `brows_furrowed`, `head_shake`, `head_nod`). It defaults to empty, so existing code and recognizers work unchanged. Control signs never carry markers. `Utterance.gloss` writes a tag after each run of signs that share a marker: `/\` (raised brows, topic), `[yes/no question]` (raised brows that run to the end), `[wh-question]`, `[negation]`, `[affirmation]`. Examples: `TITLE /\ RED`, `YOU LIKE COFFEE [yes/no question]`. Tests are in `tests/test_face_markers.py`.
  - **Person A:** when live detection lands (a stretch), pass the markers to `make_sign_event(..., markers=...)` in `recognition/base.py`. Until then, leave them empty.
  - **Person B:** those exact tags are what the translator receives. Handle them in the prompt and the on-demand tests.
  - **Mock-sign box and terminal:** markers go after the signs they cover, back to the line start, a comma, or the previous marker: `title /\ red`, `you like coffee [q]`, `where you live [wh]`, `[neg]`, `[nod]`. The long forms work too. Commas, periods, and question marks on signs are dropped. `#sarah` is fingerspelled. The mock translator turns `[negation]` into "not", ends questions with "?", and drops the other tags.

## Team rules (from `MVP.md`)

- Work on your branch; merge to `main` through a pull request; pull `main` often.
- While developing, flip only your own lines in `config.yaml` from `mock`. Don't commit your flipped lines: `main` keeps every line on `mock`, so `make mock` always works for everyone.
- Your real implementation must pass its contract test in `tests/contracts/` (run real ones with `uv run pytest --live`).
- Don't change `shared/`, `app.py`, `Makefile`, or `tests/contracts/` without telling the other two first.
- Before every PR: `make test` and `make lint` pass.

## Known issues to fix first

Found when checking the code against the new demo order and the privacy promises (Oct 23), and checked again against `main` after the face-marker commits: both are still open. Both are in the owners' starter prompts below.

1. **A long Claude Code build holds up Siri and Meet** (Person B, with a small part for C). The router waits for each output to finish before it handles the next thing (`outputs/router.py`, `_run` and `deliver`). With a 3-second fake build, a Siri question signed during the build was only typed after the build finished. The demo leaves Claude Code building while we do Siri and Meet, so it has to run in the background: start Claude Code's send as a background task, keep routing, and publish `OutputSent` / replies when it finishes. `ui/server.py` (C) then needs to show "Claude Code is working" while other modes keep sending, instead of "Sending…" for minutes.
2. **The packaged app saves transcripts to disk** (Person C to lead it, agreed with the team since `app.py` is shared). In the `.app`, engine logging goes to `~/Library/Logs/calhacks-2026/engine.log` at INFO, and several outputs log the user's exact text at INFO (`outputs/siri.py`, `outputs/tts_say.py`, the mocks, and the router's error message, which includes the event). That breaks "nothing is recorded or saved". Log the user's text at DEBUG at most (or only its length), and make sure the real Cartesia voice and captions don't log text at INFO either.

Smaller ones:
- **FINISH as the send signal** (Person A, still open). FINISH also means "already" or "done" inside a sentence (`FINISH BUY` = "already bought"), so a mid-sentence FINISH could send by accident. Require a short hold or pause around it, or have a Deaf advisor choose the send signal.
- **The mock-sign box's placeholder** (Person C) still shows `#title` as its example (`ui/macos/Sources/SignBridge/PreviewView.swift`, the `TextField` and the comment above it). TITLE is a sign now, not fingerspelled. Replace it with a draft gloss from the demo script and the marker syntax, for example `food store /\ ww make · #sarah · /send /yes /no /clear`.
- **Demo Mode's backup keys 1–6** (Person C) still fake SignBridge's old phrases (`ui/macos/Sources/SignBridge/DemoView.swift`). Change them to the new demo script once B has picked the kick-off request and re-prompt.
- **Continuing the Claude Code session** (Person B): rather than `--continue` (the most recent session in that folder, which any other `claude` run there would change), read the session id from the stream-json output and pass `--resume <id>` for the re-prompt. Run it with `--permission-mode acceptEdits` with `--allowedTools` limited to what the demo site needs (for a static site, file tools such as `Read,Edit,Write,Glob,Grep`; no `Bash` unless the site truly needs it), never `--dangerously-skip-permissions`, and Claude Code confined to the demo project folder (run it with that folder as its working directory, no `--add-dir`).

## Things we learned the hard way

- **Siri can't hear a virtual mic.** "Hey Siri" doesn't trigger from one, and even with BlackHole set as the Mac's input, voice Siri listens only to the built-in mic (tested). So Siri gets text through Type to Siri. Type to Siri shows a text box, not the animated Siri orb; that's normal.
- **Don't test Siri with Terminal in front.** The Siri output pastes with ⌘V, and the app in front catches it. Start the test, then click into Finder or the SignBridge window.
- **With Siri's default shortcut, ⌘Space opens Spotlight.** Set Siri's shortcut to "Hold Command Space" first.
- **Mode picker:** the app sets the mode directly. Don't go back to "press MODE N times"; it raced and landed on the wrong mode.
- **stdout belongs to the app protocol.** The engine talks to the Mac app in JSON lines on stdout. Debug prints go to stderr (or `logging`), or the app breaks.

## Starter prompts

Paste your prompt into Claude Code, opened in the repo folder on your branch. Each one is complete on its own.

### Person A: Recognition

```text
I'm Person A (Recognition) on our Cal Hacks 2026 team. Read README.md, SCAFFOLD.md, MVP.md, and HANDOFF.md in full before writing any code. My section of MVP.md ("Person A: Recognition") is my scope, in that order; HANDOFF.md says what's already built.

What I own: recognition/, tools/record_landmarks.py, fixtures/landmarks_sample.jsonl, and the `recognizer` line in config.yaml. Don't edit files owned by Person B or C. Don't change shared/, app.py, Makefile, or tests/contracts/; if one of those needs to change, stop and tell me why so I can check with the team.

Goal: turn the webcam into SignEvents accurate enough for the demo script. The MVP order is: camera and landmarks at a steady frame rate in the Preview window; signing-space gating (hands down = no events); the Kaggle ISLR 1st-place TFLite model (sign/kaggle-asl-signs-1st-place on Hugging Face, MIT, 250 signs); a segmenter that gives one event per sign with a confidence threshold in config.yaml; YES, NO, and FINISH as control signs (FINISH = SEND); the Kaggle ASL Fingerspelling model; and finally a real landmark recording of the demo script replacing fixtures/landmarks_sample.jsonl. docs/asl-vocab-check.md lists which demo words are in the vocabulary. The draft demo glosses are in docs/asl-demo-script-research.md (a Deaf signer must approve them before the demo). Train the signs the Kaggle model lacks (WW, REMIND, BUY, MEET, NICE or map CLEAN, HOW, YOU, TITLE) on the same Holistic landmarks it uses (hands, pose, and face), learning each sign from the linked source videos, never by guessing. Person B picks the exact Claude Code kick-off request and re-prompt; ask them for it early so I know which signs have to work. Still open: FINISH also means "already" or "done" inside a sentence, so require a hold or pause before it counts as SEND (or a Deaf advisor picks the send signal). Stretch, after the core items: facial grammar markers (raised brows, furrowed brows, head shake and nod, calibrated per signer) set on each SignEvent as `markers` (shared/events.py: brows_raised, brows_furrowed, head_shake, head_nod); `Utterance.gloss` already turns them into `/\`, `[yes/no question]`, `[wh-question]`, `[negation]`, `[affirmation]` for the translator.

How to work:
- I'm on branch person-a. Commit in small steps with clear messages. Open a PR to main when a piece works.
- Run `uv sync --extra camera` first. Test with `recognizer: camera` and every other line on mock, but don't commit my config.yaml change; main stays on mock.
- My real recognizer must pass tests/contracts/ (`uv run pytest --live` for the camera). `make test` and `make lint` must pass before every PR, and `make mock` must keep working.
- Don't print to stdout in engine code (it's the app protocol); use logging.
- Model files are large: download them to models/ at runtime or with a script; don't commit them.
- Privacy is a promise to our Deaf users (docs/user-research.md): never save or send video or camera images, and don't log signs at INFO. The landmark fixture is teammates' body-tracking data in a public repo, so record only teammates who agree.

Start with MVP item 1. First, tell me in a few lines what's already in recognition/ and your plan for item 1, then build it.
```

### Person B: Language and Claude Code

```text
I'm Person B (Language and Claude Code) on our Cal Hacks 2026 team. Read README.md, SCAFFOLD.md, MVP.md, and HANDOFF.md in full before writing any code. My section of MVP.md ("Person B: Language and Claude Code") is my scope, in that order; HANDOFF.md says what's already built.

What I own: language/, outputs/claude_code.py, outputs/mock_claude_code.py, outputs/router.py, and the `translator` and `claude_code` lines in config.yaml. Don't edit files owned by Person A or C. Don't change shared/, app.py, Makefile, or tests/contracts/; if one of those needs to change, stop and tell me why so I can check with the team.

Goal: turn ASL gloss into natural English with Claude, and send coding requests to Claude Code only after the signer signs YES. First, fix known issue 1 in HANDOFF.md: a long Claude Code build must run in the background so Siri and Meet keep working while it builds (tell Person C, who owns ui/server.py, so the app can show "Claude Code is working"). Then the MVP order is: language/claude.py calling Claude through the Anthropic SDK with language/prompts/gloss_to_english.md (under ~2 s for the demo script; use the claude-api skill for the current model and SDK usage); gloss-to-English test cases (demo script, fingerspelled words, recognition mistakes, coding requests, plain Siri requests without "Hey Siri", including the demo reminder `TOMORROW MORNING, you-REMIND-me BUY MILK` → "Remind me tomorrow morning to buy milk."; plus `/\` topic marking and facial grammar markers (the gloss format is fixed in shared/events.py `Utterance.gloss`, and the mock-sign box already accepts them: `title /\ red`, `tomorrow rain [q]`, `[wh]`, `[neg]`; Person A adds live detection as a stretch) like `YOU LIKE COFFEE [yes/no question]` → "Do you like coffee?" and `[negation]`, which flips the meaning) that run against the real API only on demand, not in `make test`; checking the YES/NO confirm flow, which already works on mocks; outputs/claude_code.py running `claude -p "<text>"` in a configured demo project folder and streaming the reply back to the app, with a follow-up request continuing the same session (the demo opens with a signed build request and re-prompts it at the end; read the session id from the stream-json output and use `--resume <id>` rather than `--continue`, and run it with `--permission-mode acceptEdits` with `--allowedTools` limited to what the demo site needs (for a static site, file tools such as `Read,Edit,Write,Glob,Grep`; no `Bash` unless the site truly needs it), never `--dangerously-skip-permissions`, and Claude Code confined to the demo project folder (run it with that folder as its working directory, no `--add-dir`), so the minutes-long build never stops for an approval nobody can answer); a starting folder for the small demo website Claude Code builds, plus a tested kick-off request and re-prompt, starting from the draft glosses in docs/asl-demo-script-research.md (send both to Person A as soon as they're picked, so A knows which signs have to work); checking the router, which already sends claude_code / siri / voice / meet correctly on mocks; and an optional review-before-speaking step for Meet and Voice (MVP item 7). I also write the README's "How we use Claude" section for the Anthropic judges: what Claude does, where it can go wrong (a mistranslation spoken in a Deaf person's name), how the YES/NO confirm and review-before-speaking handle that, and that the translator only ever sees sign words as text, never video (Claude Code also reads its project folder's files).

Glossary: the demo uses custom signs Person A trains, and the translator must map their gloss words: `WW` = website; `YOU-REMIND-ME` (the directional you-REMIND-me) = remind me; `MEET-YOU` = meet you; `CLEAN` right before `MEET` = nice (Lifeprint: NICE and CLEAN are the same sign, and the Kaggle model only knows it as clean). Agree the exact class names with Person A (they may arrive as plain `REMIND` or `MEET`), and put all of them in the prompt and the test cases. The mock translator (language/mock.py) is only a stand-in so the app runs; don't build on it.

How to work:
- I'm on branch person-b. Commit in small steps with clear messages. Open a PR to main when a piece works.
- My ANTHROPIC_API_KEY is in .env (gitignored; never commit it). The Claude Code CLI is installed and logged in.
- Test with `recognizer: mock` (I type gloss in the Preview box), `translator: claude`, `claude_code: real`, but don't commit my config.yaml change; main stays on mock.
- My real pieces must pass tests/contracts/ (`uv run pytest --live`). `make test` and `make lint` must pass before every PR, and `make mock` must keep working.
- Don't print to stdout in engine code (it's the app protocol); use logging. Never log the user's text at INFO (known issue 2 in HANDOFF.md); DEBUG at most.

Start with known issue 1, then MVP item 1. First, tell me in a few lines what's already in language/ and outputs/, and your plan for item 1, then build it.
```

### Person C: Voice, Siri, Meet, and UI

```text
I'm Person C (Voice, Siri, Meet, and UI) on our Cal Hacks 2026 team. Read README.md, SCAFFOLD.md, MVP.md, and HANDOFF.md in full before writing any code. My section of MVP.md ("Person C: Voice, Siri, Meet, and UI") is my scope, in that order; HANDOFF.md says what's already built. Type to Siri (item 3) and the setup wizard's Siri test are already done, so skip them.

What I own: outputs/tts_cartesia.py, outputs/tts_say.py, outputs/mock_tts.py, outputs/siri.py, outputs/mock_siri.py, captions/, ui/ (the SwiftUI Mac app in ui/macos and the engine bridge ui/server.py), fixtures/captions_sample.txt, and the `tts`, `siri`, and `captions` lines in config.yaml. Don't edit files owned by Person A or B. Don't change shared/, app.py, Makefile, or tests/contracts/; if one of those needs to change, stop and tell me why so I can check with the team.

Goal: make the app's English heard as a real microphone in Google Meet, show the other side's speech as live captions, and make every state visible for a Deaf user. The MVP order is: BlackHole 2ch setup written into the README (done when `tts: say` is heard in dictation or Meet); tts_cartesia.py streaming Cartesia Sonic into BlackHole with a fallback to `say`; captions/cartesia_stt.py capturing the Meet call's audio from a separate device (never the one our voice goes into) and streaming it to Cartesia Ink; Demo Mode polished fullscreen on an external display; Preview and setup fitting our engine (including wiring the Position step's "Save This Position"); demo moment 3, a real Meet call between two laptops; a spoken call intro and "one moment, I'm signing" cue (item 8); and an always-visible camera-on indicator plus a privacy line (item 9). The Meet call is the centerpiece of the demo, so it gets the most polish (see docs/user-research.md for why). I also write the README's "Cartesia features we use" section, which Cartesia's rules require. Use Cartesia's current docs for the TTS and STT APIs.

Also on my list, from "Known issues to fix first" in HANDOFF.md: stop the packaged app from saving transcripts (issue 2: don't log the user's text or captions at INFO; app.py is shared, so agree the change with the team first); show "Claude Code is working" in the app while other modes keep sending, once Person B makes Claude Code run in the background (issue 1); change Demo Mode's backup keys 1–6 to the new demo script; and replace the mock-sign box's placeholder in PreviewView.swift, which still shows `#title` (TITLE is a sign now), with a draft gloss from the demo script and the marker syntax (`/\`, `[q]`, `[wh]`, `[neg]`, `[nod]`). Do issue 2 right after item 2, before any real Cartesia text gets logged.

How to work:
- I'm on branch person-c. Commit in small steps with clear messages. Open a PR to main when a piece works.
- My CARTESIA_API_KEY is in .env (gitignored; never commit it). BlackHole is installed.
- Test with `recognizer: mock`, `translator: mock`, `tts: cartesia`, `siri: real`, `captions: cartesia`, but don't commit my config.yaml change; main stays on mock.
- My real pieces must pass tests/contracts/ (`uv run pytest --live`). `make test` and `make lint` must pass before every PR, `make mock` must keep working, and the Swift app must build (`swift build` in ui/macos).
- The engine talks to the app in JSON lines on stdout; keep debug output on stderr or logging. If I change the protocol, update both ui/server.py and ui/macos/Sources/SignBridge/EngineClient.swift, plus tests/test_ui_server.py.
- Never send keystrokes, paste, or press Escape while a terminal may be in front; that types into my terminal. For anything that needs a live keystroke or Siri test, tell me the command and let me run it.

Start with MVP item 1. First, tell me in a few lines what's already in outputs/, captions/, and ui/, and your plan for item 1, then build it.
```
