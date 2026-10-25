# Handoff: getting the three of us started

**Start here.** If you were told "pull and read HANDOFF.md", this doc is everything you need: it gets each person from zero to working on their part. **The project is now Google Meet only** (Oct 24): signing spoken in the call, captions back, and fingerspelling autocomplete with Moss. Claude Code and Siri were cut; the old code is on the `archive/claude-code-siri` branch. Every part on `main` has a real implementation behind its mock, and `make test`, `make mock`, and `make lint` pass. What's left: camera fingerspelling, a bigger sign vocabulary, Moss with real keys, a real two-laptop call, and tuning. "What's built" and "What still needs a person" below say exactly what. The plan itself is in `MVP.md`; this doc doesn't repeat it, beyond the key dates and the demo in short.

**How to use it:**
1. The lead does the "Before anyone starts" list once.
2. Each person does "Everyone: first 15 minutes" (it includes what to read, in order, and picking your role).
3. Each person opens Claude Code in the repo and pastes their prompt from "Starter prompts".

## Before anyone starts (lead)

- [x] **Repo push access.** The repo (`SacchinS/calhacks-2026`) is public, so anyone can clone it, but only collaborators can push. Invites are sent (GitHub > Settings > Collaborators); each teammate accepts theirs (step 1 below).
- [ ] **API keys.** Send keys privately (a DM, never the repo or a public channel). Person B needs `ANTHROPIC_API_KEY` and the Moss keys (`MOSS_PROJECT_ID`, `MOSS_PROJECT_KEY`). Person C needs `CARTESIA_API_KEY`. Person A needs none.
- [x] **Who is A, B, and C** (from the team's work-split doc):
  - Person A (Recognition): Sacchin
  - Person B (Language and autocomplete): Eleyn
  - Person C (Voice, Meet, and the Mac app): Julian

## Everyone: first 15 minutes

1. Accept the GitHub invite to `SacchinS/calhacks-2026` (it comes by email and shows at github.com/notifications). You can clone without it, but you can't push your branch until you accept.
2. Install what the README's "Getting started" lists that you need. Everyone needs macOS on Apple Silicon, Xcode command-line tools (`xcode-select --install`), and uv (`brew install uv`).
3. Clone and run the mocks (already cloned? `git checkout main && git pull` instead of the clone):
   ```bash
   git clone https://github.com/SacchinS/calhacks-2026.git
   cd calhacks-2026
   make install && make test && make mock
   ```
   `make mock` opens the Mac app (hand icon in the menu bar). Click through setup with "Skip for now", open Preview, and type `~pr` in the box at the bottom: the autocomplete suggests Pranav (from the mock captions). Then `/yes nice meet-you /send`, and the call panel shows what the mock voice said.
4. Read, in this order: this file (all of it); `MVP.md` ("What the MVP must do", "How we work", "Checkpoints", then your own Person section); `SCAFFOLD.md` ("Core interfaces" and "The mock recognizer"); `README.md`; `docs/user-research.md` (why the app is only about calls, and the privacy rules); and for A and B, `docs/asl-demo-script-research.md` (Moment 3, the Meet greeting: the draft glosses and the source video for every sign). Your starter prompt has Claude Code read the first four too.
5. Find your role in "Who is A, B, and C" above, then make your branch from the new `main`: `git checkout -b person-a` (or `person-b`, `person-c`).
6. If you use API keys: get yours from the lead in a DM, then `cp .env.example .env` and fill it in. `.env` is gitignored. Never commit it; Cartesia's rules disqualify that.
7. Open Claude Code in the repo on your branch and paste your prompt from "Starter prompts" below.
8. From then on, follow "Team rules" below: keep `config.yaml` on `mock` on `main`, merge through a PR to `main`, and run `make test` and `make lint` before every PR (without `make`: `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .`).

## Key dates

From `MVP.md` ("Checkpoints" has the full list):
- **Saturday night:** the whole demo call works on the real two-laptop, two-screen setup, and we record a backup demo video.
- **Sunday ~3 AM:** feature freeze.
- **Sunday Oct 25, 8:00 AM:** at the venue. **9:00 AM PT:** Devpost submission deadline. It's hard: nothing gets in after it.
- **Sunday 10:30 AM–12:30 PM:** judging. The whole team is there.

## The demo, in short

A release check-in on Google Meet between two laptops (details in `MVP.md`, "What the MVP must do"):
1. **Speech and captions.** "The dashboard's ready. Pranav redesigned the charts in Figma last night, so I think we ship tomorrow." The autocomplete remembers Pranav and Figma.
2. **Signing while they talk.** F-I (Figma), COLOR PROBLEM, FINISH: the sentence waits for B to stop, then "There's a color problem in Figma." (NOW instead of FINISH says it right away.)
3. **Being asked.** "Sacchin, can you sort it out with Pranav?" flashes the name banner; the signer answers ME MEET, P-R (Pranav), TOMORROW, FINISH: "I'll meet with Pranav tomorrow."
4. **The outcome:** the release is held.

Why only calls: Professor Lance Forshay (Deaf ASL faculty at UW), who answered our survey, said video calls are the one place he'd use this. His answers and what we changed are in `docs/user-research.md`.

The glosses are drafts (`docs/asl-demo-script-research.md`, Moment 3). A Deaf signer must approve or rewrite them before the demo. Nobody on the team knows ASL, so learn every sign from the source videos linked there (or from a Deaf signer), never by guessing.

## What's built, and how well it's tested

| Part | Owner | State |
|---|---|---|
| Bus, events, config, app wiring (`shared/`, `app.py`) | shared | Done. Change only after telling the others. |
| Mac app (`ui/macos`) and its engine bridge (`ui/server.py`) | C | Works on mocks: Preview with the call panel always showing (a You/Them conversation, quick replies, "Introduce me"), Demo Mode, the autocomplete bar, setup wizard (Save This Position fits the signing space), camera-on indicator, Settings > Calls, Privacy and Remembered words. |
| Webcam and landmarks (`recognition/camera.py`, `gating.py`) | A | Camera and MediaPipe landmarks run (`uv sync --extra camera`). Not tested live since the model went in. |
| Kaggle sign model (`recognition/isolated.py`) | A | **Built.** Downloads to `models/islr/` on first use, runs with LiteRT (~9 ms per window). Not yet tested on a real webcam: thresholds need tuning. |
| ASL Citizen sign model (`recognition/asl_citizen.py`, `tools/setup_asl_citizen.py`) | A | **Built, off for the demo:** it didn't recognize our signer live (NICE ranked 13th to 1,800th on six takes; `tools/try_signs.py` shows why), so `recognition.sign_models` is `[custom]`. What it is: 2,731 signs, limited to the demo's (`asl_citizen_signs`), with the training code's own preprocessing (checked against it in the tests) and a "nothing" check. On in `recognition.sign_models`; each machine runs the setup tool once (it needs torch only for that). |
| Recording and tuning tools (`tools/record_script.py`, `tools/tune_recognition.py`) | A | **Built on `person-a`**, waiting on a PR and real takes. |
| Custom signs (`recognition/custom_signs.py`, `tools/record_signs.py`) | A | **The demo's sign model.** Our signer's HELLO, NICE, MEET, YOU, YES and FINISH, 5–6 takes each, all separate (`--check`). New takes also save raw landmarks. |
| Segmenter and control signs (`recognition/segmenter.py`) | A | Works. YES / NO / FINISH need a hold (2x `min_frames`), so a mid-sentence FINISH doesn't send. |
| Face markers (`recognition/face_markers.py`) | A | **Built, off by default** (`recognition.face_markers`). Heuristic; untested on a real face. |
| Fingerspelling (`recognition/fingerspelling.py`, `tools/try_letters.py`) | A | **Built on `person-a`**, not tried live: a pretrained letter model on the hand landmarks (ONNX, CC BY-NC) publishes one `Letter` per held handshape; spelling starts at the second letter, and other signs are ignored while spelling. Settings under `recognition.letter_*`. |
| Fingerspelling autocomplete (`language/autocomplete.py`, `vocab.py`, `vocab_search.py`, `vocab_terms.py`, `tagger.py`) | B | **Built and tested on typed letters** (`~pri` in the mock box, or the app's "Fingerspell by typing" box). It ranks words by letters, the conversation (Moss session or keyword mock), frequency and recency; learns words from your spelling and from captions; keeps its memory in a local SQLite file; and lets you list and delete words in Settings. Moss itself isn't run yet (no keys): `uv run pytest --live tests/test_moss_search.py` once they're in `.env`. |
| Replay (`recognizer: replay`) | A | Works, but `fixtures/landmarks_sample.jsonl` is fake data. |
| Claude translator (`language/claude.py`, prompt) | B | **Works**: live tests pass, 0.6 to 1.0 s each (Haiku 5.5, no thinking). The prompt is now written for speech in a meeting. |
| Router (`outputs/router.py`) | B | Works. Everything goes to the voice; optional review before speaking (YES / NO). |
| `say` voice into BlackHole (`outputs/tts_say.py`) | C | Real (`tts: say`). |
| Cartesia voice (`outputs/tts_cartesia.py`) | C | **Works** on a loopback (voice "Skylar"): Sonic over SSE, streamed into BlackHole 2ch, falls back to `say`. |
| Meet captions (`captions/cartesia_stt.py`) | C | **Works** on a loopback: Ink realtime STT from BlackHole 16ch, partial captions update in place. They start with the app now. A real two-laptop call is next. |
| Turn-aware speaking (`outputs/turn_taking.py`) | C | **Works**, tested live with Cartesia Ink on a BlackHole loopback: the approved sentence waited for the other side's `turn.end` and started the moment it came. Chime-in and talked-over handling are unit-tested. Tune `meet.chime_in_seconds` and `barge_in_seconds` in a real call. |
| Call intro and signing cue (`outputs/call_host.py`) | C | Works on mocks: "Introduce me", the intro at startup with `meet.intro_on_start`, and "One moment, I'm signing." with `meet.signing_cue_seconds`. |

## Recent changes

- **Turn-based speaking and NOW** (Oct 25). `shared/events.py`: a new control sign `NOW` (SEND, said right away; on its own it says a sentence that's waiting for the pause) and `Translation.urgent`. `meet.chime_in_seconds: 0` is turn-based: a sentence waits for silence and the voice never interjects on its own. The router speaks urgent translations with `send_now`; `TurnTakingOutput.hurry()` releases a waiting one. App: a "Say now" button in Preview, N in Demo Mode, `gesture: now` in the protocol. Mock box: `/now`.
- **Meet only** (Oct 24). Claude Code, Siri, the Voice mode and the demo website are gone from `main` (kept on `archive/claude-code-siri`).
  - **Events and config:** `shared/events.py` lost `Mode`, `ModeChanged`, `OutputReply`, and the `MODE` control sign; `ConfirmRequest` lost `target`. The `claude_code`, `siri` and `mode` config lines and the `claude_code_cli` / `type_to_siri` sections are gone, and so is pyobjc.
  - **Behavior:** every translation goes to the voice (after YES with review on). Captions start with the app. The call intro is said at startup when `meet.intro_on_start` is on. The autocomplete keeps one meeting id per run.
  - **Protocol:** the `output_mode` command and the `reply` event are gone; `status` lost `output_mode` and `claude_code_working`; `sent` lost `mode`; `test_route` is voice only.
  - **App:** no mode picker; Preview always shows the call panel; setup lost the Accessibility, Siri and Claude steps (the API key is ours, in `.env`) and the control-gesture step (the gestures were never detected), and the engine lost its gestures mode; the demo phrases are the Meet greeting with fingerspelled Priyanka and Figma.
- **Fingerspelling autocomplete with Moss** (Oct 24). `shared/events.py` gained `Letter`, `Suggestion`, and `AutocompleteUpdate`. A new component line, `vocab_search: mock | moss`, is on `moss` in `config.demo.yaml` and needs `MOSS_PROJECT_ID` and `MOSS_PROJECT_KEY`.
  - **Flow:** the utterance buffer hands letters to the autocompleter in order with the signs. While a word is being spelled, YES accepts it and NO dismisses it, and the app's Send and Cancel buttons (C / X in Demo Mode) do the same. A sign or SEND keeps the letters as spelled.
  - **Storage:** the memory is `~/Library/Application Support/calhacks-2026/vocab.sqlite` (`vocab-mock.sqlite` for the mock search). The Moss session is built from it at startup, never pushed.
  - **New protocol:** status fields `autocomplete` and `autocomplete_stats`; commands `letters`, `autocomplete`, `vocab_list` and `vocab_delete`; event `vocab`.
  - **Mock and tools:** `~abc` in the mock box spells letters, the mock captions mention Pranav and Figma (the demo meeting), and `make seed-vocab` loads demo words.
  - **Known edge:** with review before speaking, YES while spelling and while a sentence waits for review acts on both.

- **Mention alerts** (Oct 24). `captions/mentions.py` watches the captions for the signer's name (Settings > Calls, plus `meet.mention_names`) and publishes a new `Mention` event in `shared/events.py`: once per turn as soon as the name is heard, then again with the full sentence and whether it's a question. The app shows a flashing yellow banner above every window, fullscreen Meet included, without taking focus (`MentionBanner.swift`). `meet.alert_on_questions` alerts on every question, for 1:1 calls. New protocol event `mention`. The mock captions are now a short sprint check-in that says "Sam, can you take the filters ticket by Friday?".
- **Meetings first: quick replies, quieter defaults** (Oct 24). The Meet panel has one-tap replies (`meet.quick_replies`): pressing one is the approval, normal ones wait for a pause, urgent ones ("Can you repeat that?", "Please slow down a little.", "One at a time, please.") are said right away. New command `quick_reply`; `ready` now lists the replies. The call intro and "One moment, I'm signing." are off by default (`meet.intro_on_start`, `meet.signing_cue_seconds`): they help on calls with strangers, not team meetings where people know you and can see you sign. "Introduce me" still works.
- **Turn-aware speaking** (Oct 24, a64cba7, d7c8122). `shared/events.py` has two new events: `TurnEvent` (the other side's turns from Cartesia Ink: start, eager_end, resume, end) and `SpeechStatus` (our voice: idle, waiting, interjecting, speaking). The captions publish TurnEvents; `outputs/turn_taking.py` wraps the voice so the signer's approved words wait for the pause, chime in after 8 s, and stop if talked over. New status fields `speech` and `them_talking`; config `meet.turn_taking`, `chime_in_seconds`, `interjection`, `yield_seconds`, `barge_in_seconds`, and optional `cartesia.turn_*` tuning.
- **Everything built at once** (Oct 24, commits a9930c8 to the latest on `main`). Instead of waiting for each person, every part got its real implementation; see "What's built" above. Both earlier known issues are fixed: Claude Code runs in the background, and the user's text is never logged at INFO (the console fallback no longer prints to the log file either). New protocol fields: `status.claude_code_working`, `status.camera_on`, `caption.final`, and the `introduce` command. New config: `claude_code_cli.allowed_tools / model / timeout_seconds`, the `meet:` section, the `recognition:` model, custom-sign, and face-marker lines, and `control_min_frames`. Also: `make demo` runs every real component (`config.demo.yaml` on top of `config.yaml`); `shared/config.py` gained that overlay and reads keys from `~/Library/Application Support/calhacks-2026/.env` (for the packaged app); without a Cartesia key the voice uses `say` instead of going silent; Claude Code never gets the translator's `ANTHROPIC_API_KEY`, so it uses the account `claude` is logged in with.
- **Face markers in the event contract** (Oct 23, commits 19c09f5, ac8be2c, e391e5a). `shared/events.py` changed: `SignEvent` has a new field, `markers`, the facial grammar seen during the sign (`brows_raised`, `brows_furrowed`, `head_shake`, `head_nod`). It defaults to empty, so existing code and recognizers work unchanged. Control signs never carry markers. `Utterance.gloss` writes a tag after each run of signs that share a marker: `/\` (raised brows, topic), `[yes/no question]` (raised brows that run to the end), `[wh-question]`, `[negation]`, `[affirmation]`. Examples: `TITLE /\ RED`, `YOU LIKE COFFEE [yes/no question]`. Tests are in `tests/test_face_markers.py`.
  - **Person A:** live detection is now in `recognition/face_markers.py` (off by default); `FrameRecognizer` attaches the markers seen during each sign.
  - **Person B:** those exact tags are what the translator receives. Handle them in the prompt and the on-demand tests.
  - **Mock-sign box and terminal:** markers go after the signs they cover, back to the line start, a comma, or the previous marker: `title /\ red`, `you like coffee [q]`, `where you live [wh]`, `[neg]`, `[nod]`. The long forms work too. Commas, periods, and question marks on signs are dropped. `#sarah` is fingerspelled. The mock translator turns `[negation]` into "not", ends questions with "?", and drops the other tags.

## Team rules (from `MVP.md`)

- Work on your branch; merge to `main` through a pull request; pull `main` often.
- While developing, flip only your own lines in `config.yaml` from `mock`. Don't commit your flipped lines: `main` keeps every line on `mock`, so `make mock` always works for everyone.
- Your real implementation must pass its contract test in `tests/contracts/` (run real ones with `uv run pytest --live`).
- Don't change `shared/`, `app.py`, `Makefile`, or `tests/contracts/` without telling the other two first.
- Before every PR: `make test` and `make lint` pass.

## What still needs a person

In rough demo order:

1. **Keys** (lead): `ANTHROPIC_API_KEY` and `CARTESIA_API_KEY` are in `.env` on the build machine. `MOSS_PROJECT_ID` and `MOSS_PROJECT_KEY` are still needed, from a Moss project (code CALHACKS on the Portal's billing page). Then `uv run pytest --live` runs the real translator, Cartesia and Moss tests, including the 500-word startup timing.
2. **Camera letters** (A): `uv run python tools/try_letters.py`, spell P-R and F-I, set `recognition.letter_orientation` to what it prints, and tune `letter_threshold` / `letter_hold_seconds`; then check P-R and F-I in the app bring up Priyanka and Figma.
3. **Custom signs live** (A): `tools/try_signs.py`, sign HELLO, NICE, MEET, YES and FINISH, and check each comes through; the signer who demos records them (`tools/record_signs.py`).
4. **Record and tune** (A): `uv run python tools/record_script.py` records 3 takes of each demo phrase to `models/takes/` (gitignored), with the glosses each should give; then `uv run python tools/tune_recognition.py --details` replays them through the models, tries every threshold combination, and prints the best `config.yaml` lines. Takes double as real replay fixtures. The signer who demos should record them.
5. **Moss numbers** (B): ranking and latency with the real Moss session; tune the autocomplete weights on real letters.
6. **The real call** (C): two laptops, BlackHole 2ch as Meet's mic, the Multi-Output Device with BlackHole 16ch as Meet's speakers (README "Audio for Meet"); captions within a couple of seconds; tune turn-taking.
7. **Demo rehearsal** (everyone): `make demo` on the two-laptop, two-screen setup, and record the backup video.
8. **Deaf review**: the demo glosses, the quick-reply phrases, the setup wizard's "Signs to try" (`signs.json`), and face markers before turning them on.

## Things we learned the hard way

- **Our voice and Meet's audio need different devices.** Our voice goes into BlackHole 2ch (Meet's mic); Meet's audio has to come out on BlackHole 16ch for captions, or we caption ourselves.
- **stdout belongs to the app protocol.** The engine talks to the Mac app in JSON lines on stdout. Debug prints go to stderr (or `logging`), or the app breaks.

## Starter prompts

Paste your prompt into Claude Code, opened in the repo folder on your branch. Each one is complete on its own.

### Person A: Recognition

```text
I'm Person A: Recognition on our Cal Hacks 2026 team. Read README.md, MVP.md, and HANDOFF.md in full first. The project is Google Meet only now; HANDOFF.md "What's built" says what's tested, and "What still needs a person" lists the remaining work. I own recognition/, tools/record_*.py, tools/tune_recognition.py, fixtures/landmarks_sample.jsonl, and the `recognizer` line.

My job now: fingerspelled letters from the camera and a bigger sign vocabulary. Add a letter recognizer on the hand landmarks (a pretrained A-Z model; check its license) that publishes one `Letter` event per held handshape, so spelling P-R live brings up the autocomplete's Pranav. Then add the ASL Citizen ST-GCN model (weights in models/asl_citizen/) next to the Kaggle model, limited to the demo's signs, with a cutoff so other movement isn't forced into a demo sign. Then help me record takes with tools/record_script.py and tune the thresholds with tools/tune_recognition.py. Video and images must never be saved or sent; record only teammates who agree.

How to work: I'm on branch person-a. Commit in small steps and open a PR to main when a piece works. Flip only my own config.yaml lines while testing and don't commit them (main stays on mock). `make test` and `make lint` must pass before every PR. Never print to stdout in engine code (it's the app protocol), never log what the user signs or says at INFO, and never commit .env. Don't change shared/, app.py, Makefile, or tests/contracts/ without asking me first. If something needs a live keystroke, the webcam, or a call, tell me the command and let me run it.

Start by telling me in a few lines what's built in my area and your plan, then begin.
```

### Person B: Language and autocomplete

```text
I'm Person B: Language and autocomplete on our Cal Hacks 2026 team. Read README.md, MVP.md, and HANDOFF.md in full first. The project is Google Meet only now; HANDOFF.md "What's built" says what's tested, and "What still needs a person" lists the remaining work. I own language/, outputs/router.py, tools/seed_vocab.py, and the `translator` and `vocab_search` lines.

My job now: make the fingerspelling autocomplete demo-ready with real keys. With MOSS_PROJECT_ID and MOSS_PROJECT_KEY in .env, run `uv run pytest --live tests/test_moss_search.py` and `uv run python tools/seed_vocab.py --synthetic 500 --time`, and write down the real numbers (suggestion latency, startup time, letters saved) for the README's "Autocomplete with Moss" section. Check Claude's tags on real words and tune the `autocomplete:` weights in config.yaml. Keep language/prompts/gloss_to_english.md matched to the demo glosses and rerun `uv run pytest --live tests/test_claude_translator.py` after any prompt change. If there's time, pass remembered names and jargon to Cartesia Ink so captions spell them right (check Ink's docs for the exact option first).

How to work: I'm on branch person-b. Commit in small steps and open a PR to main when a piece works. Flip only my own config.yaml lines while testing and don't commit them (main stays on mock). `make test` and `make lint` must pass before every PR. Never print to stdout in engine code (it's the app protocol), never log what the user signs or says at INFO, and never commit .env. Don't change shared/, app.py, Makefile, or tests/contracts/ without asking me first. If something needs a live keystroke, the webcam, or a call, tell me the command and let me run it.

Start by telling me in a few lines what's built in my area and your plan, then begin.
```

### Person C: Voice, Meet, and the Mac app

```text
I'm Person C: Voice, Meet, and the Mac app on our Cal Hacks 2026 team. Read README.md, MVP.md, and HANDOFF.md in full first. The project is Google Meet only now; HANDOFF.md "What's built" says what's tested, and "What still needs a person" lists the remaining work. I own outputs/tts_*.py, outputs/mock_tts.py, outputs/turn_taking.py, outputs/call_host.py, captions/, ui/, fixtures/captions_sample.txt, and the `tts` and `captions` lines.

My job now: make the real two-laptop Meet call work, the whole demo. Set Meet's microphone to BlackHole 2ch and its speakers to a Multi-Output Device with BlackHole 16ch (README "Audio for Meet"), check the other laptop hears `tts: cartesia` and our `captions: cartesia` show their speech within a couple of seconds, and tune meet.chime_in_seconds, barge_in_seconds and yield_seconds in the real call. Then polish Demo Mode fullscreen on the external display, and look over the mention banner over fullscreen Meet, the autocomplete bar, and Settings > Remembered words. Build the app with `swift build --package-path ui/macos` after Swift changes.

How to work: I'm on branch person-c. Commit in small steps and open a PR to main when a piece works. Flip only my own config.yaml lines while testing and don't commit them (main stays on mock). `make test` and `make lint` must pass before every PR. Never print to stdout in engine code (it's the app protocol), never log what the user signs or says at INFO, and never commit .env. Don't change shared/, app.py, Makefile, or tests/contracts/ without asking me first. If something needs a live keystroke, the webcam, or a call, tell me the command and let me run it.

Start by telling me in a few lines what's built in my area and your plan, then begin.
```
