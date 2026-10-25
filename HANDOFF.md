# Handoff: getting the three of us started

**Start here.** If you were told "pull and read HANDOFF.md", this doc is everything you need: it gets each person from zero to working on their part. **Most of the code is now built** (Oct 24): every part has a real implementation behind its mock, and `make test`, `make mock`, and `make lint` pass on `main`. What's left is the work only a person with the hardware, the keys, or ASL can do: testing on a real webcam, a real Meet call, and real API keys, recording our custom signs, and tuning. "What's built" and "What still needs a person" below say exactly what. The plan itself is in `MVP.md`; this doc doesn't repeat it, beyond the key dates and the demo in short.

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

## What's built, and how well it's tested

| Part | Owner | State |
|---|---|---|
| Bus, events, config, app wiring (`shared/`, `app.py`) | shared | Done. Change only after telling the others. |
| Mac app (`ui/macos`) and its engine bridge (`ui/server.py`) | C | Works on mocks: Preview, Demo Mode, setup wizard (Save This Position now fits the signing space), mode picker, panels for Claude Code, Siri, Voice, and Meet (a You/Them conversation with "Introduce me"), "Claude Code is working" pill, camera-on indicator, Settings > Calls and Privacy. |
| Webcam and landmarks (`recognition/camera.py`, `gating.py`) | A | Camera and MediaPipe landmarks run (`uv sync --extra camera`). Not tested live since the model went in. |
| Kaggle sign model (`recognition/isolated.py`) | A | **Built.** Downloads to `models/islr/` on first use, runs with LiteRT (~9 ms per window). Not yet tested on a real webcam: thresholds need tuning. |
| Custom signs (`recognition/custom_signs.py`, `tools/record_signs.py`) | A | **Built.** Few-shot matching from recorded examples. Nothing recorded yet: WW, YOU-REMIND-ME, MEET-YOU, BUY, HOW, YOU, TITLE. |
| Segmenter and control signs (`recognition/segmenter.py`) | A | Works. YES / NO / FINISH need a hold (2x `min_frames`), so a mid-sentence FINISH doesn't send. |
| Face markers (`recognition/face_markers.py`) | A | **Built, off by default** (`recognition.face_markers`). Heuristic; untested on a real face. |
| Fingerspelling (`recognition/fingerspelling.py`) | A | Stub. No released Kaggle winner on Hugging Face; the demo script doesn't need it. |
| Replay (`recognizer: replay`) | A | Works, but `fixtures/landmarks_sample.jsonl` is fake data. |
| Claude translator (`language/claude.py`, prompt) | B | **Built** (Haiku 5.5, no thinking). Prompt has the glossary, face-marker tags, and demo examples. Not run against the API yet (no key on the build machine): run `uv run pytest --live tests/test_claude_translator.py`. |
| Confirm flow and router (`outputs/router.py`) | B | Works. Claude Code runs in the background (Siri and Meet keep working during a build). Optional review before speaking in Meet and Voice. |
| Claude Code output (`outputs/claude_code.py`) | B | **Real and tested**: "Build a website for a grocery store." built a site in 61 s, then "Make the title red." edited it in 6 s in the same session (`--resume`). |
| Demo site (`demo/site`, `tools/demo_site.py`) | B | Works: `make demo-reset`, `make demo-serve` (auto-reload at http://localhost:8765). |
| Type to Siri (`outputs/siri.py`) | C | **Real and tested** (`siri: real`). |
| `say` voice into BlackHole (`outputs/tts_say.py`) | C | Real (`tts: say`). |
| Cartesia voice (`outputs/tts_cartesia.py`) | C | **Built**: Sonic over SSE, streamed into BlackHole 2ch, falls back to `say`. Playback into BlackHole tested; Cartesia itself not run yet (no key). Set `cartesia.voice_id`. |
| Meet captions (`captions/cartesia_stt.py`) | C | **Built**: Ink realtime STT from BlackHole 16ch, partial captions update in place. Not run yet (no key, BlackHole 16ch not installed on the build machine). |
| Turn-aware speaking (`outputs/turn_taking.py`) | C | **Works**, tested live with Cartesia Ink on a BlackHole loopback: the approved sentence waited for the other side's `turn.end` and started the moment it came. Chime-in and talked-over handling are unit-tested. Tune `meet.chime_in_seconds` and `barge_in_seconds` in a real call. |
| Call intro and signing cue (`outputs/call_host.py`) | C | Works on mocks: the intro when Meet starts, "Introduce me", and "One moment, I'm signing." after 5 s of unsent signing. |

## Recent changes

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

These need hardware, keys, or ASL, so they couldn't be done on the build machine. In rough demo order:

1. **Keys** (lead): put `ANTHROPIC_API_KEY` and `CARTESIA_API_KEY` in `.env` on the demo laptop. Then `uv run pytest --live` runs the real translator cases and the Cartesia outputs.
2. **Translator check** (B): run `uv run pytest --live tests/test_claude_translator.py` and fix the prompt where a case fails; check it's under ~2 s.
3. **Custom signs** (A): learn WW, YOU-REMIND-ME, MEET-YOU, BUY, HOW, YOU, and TITLE from the source videos (or a Deaf signer), record 5+ takes each with `tools/record_signs.py`, and run `--check`. The signer who demos should record them.
4. **Live recognition** (A): `recognizer: camera`, sign the demo script, and tune `confidence_threshold`, `isolated_floor`, `min_frames`, and `control_min_frames` until each phrase comes out right. Then record a real fixture to replace `fixtures/landmarks_sample.jsonl`.
5. **Cartesia voice** (C): pick a voice (`cartesia.voice_id`), check a Meet call hears it through BlackHole 2ch.
6. **Captions** (C): install BlackHole 16ch, set up the Multi-Output Device (README "Audio for Meet"), check captions in a real two-laptop call.
7. **Demo rehearsal** (everyone): `make demo-reset`, `make demo-serve`, then `make demo`; run all four moments on the two-screen setup and record the backup video.
8. **Deaf review**: the four draft glosses, the setup wizard's "Signs to try" (`signs.json`), and face markers before turning them on.

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
I'm Person A: Recognition on our Cal Hacks 2026 team. Read README.md, MVP.md, and HANDOFF.md in full first. Most of the code is already built; HANDOFF.md "What's built" says what's tested and what isn't, and "What still needs a person" lists the remaining work. I own recognition/, tools/record_signs.py, tools/record_landmarks.py, fixtures/landmarks_sample.jsonl, and the `recognizer` line.

My job now: get the demo script recognized live. Help me record the custom signs (WW, YOU-REMIND-ME, MEET-YOU, BUY, HOW, YOU, TITLE) with tools/record_signs.py and check they separate; then run `recognizer: camera` while I sign the four draft glosses in docs/asl-demo-script-research.md, and tune the thresholds in config.yaml (confidence_threshold, isolated_floor, min_frames, control_min_frames, custom_threshold_scale) from what we see. Add a way to mark sign boundaries in tools/record_landmarks.py and record a real fixture to replace fixtures/landmarks_sample.jsonl. Only then, and with a Deaf signer's check, try `recognition.face_markers: true`. Video and images must never be saved or sent; record only teammates who agree.

How to work: I'm on branch person-a. Commit in small steps and open a PR to main when a piece works. Flip only my own config.yaml lines while testing and don't commit them (main stays on mock). `make test` and `make lint` must pass before every PR. Never print to stdout in engine code (it's the app protocol), never log what the user signs or says at INFO, and never commit .env. Don't change shared/, app.py, Makefile, or tests/contracts/ without asking me first. If something needs a live keystroke, the webcam, or a call, tell me the command and let me run it.

Start by telling me in a few lines what's built in my area and your plan, then begin.
```

### Person B: Language and Claude Code

```text
I'm Person B: Language and Claude Code on our Cal Hacks 2026 team. Read README.md, MVP.md, and HANDOFF.md in full first. Most of the code is already built; HANDOFF.md "What's built" says what's tested and what isn't, and "What still needs a person" lists the remaining work. I own language/, outputs/claude_code.py, outputs/mock_claude_code.py, outputs/router.py, demo/site, tools/demo_site.py, and the `translator` and `claude_code` lines.

My job now: make the Claude side demo-ready with real keys. Run `uv run pytest --live tests/test_claude_translator.py` and improve language/prompts/gloss_to_english.md until every case passes and translation takes under ~2 s; add cases for anything A's live recognition gets wrong. Then rehearse demo moments 1 and 4 with `translator: claude` and `claude_code: real`: `make demo-reset`, `make demo-serve`, sign (or type) the kick-off and the re-prompt, and adjust demo/site/CLAUDE.md so the build looks good and finishes in a couple of minutes. Send A the final kick-off and re-prompt glosses as soon as they're fixed.

How to work: I'm on branch person-b. Commit in small steps and open a PR to main when a piece works. Flip only my own config.yaml lines while testing and don't commit them (main stays on mock). `make test` and `make lint` must pass before every PR. Never print to stdout in engine code (it's the app protocol), never log what the user signs or says at INFO, and never commit .env. Don't change shared/, app.py, Makefile, or tests/contracts/ without asking me first. If something needs a live keystroke, the webcam, or a call, tell me the command and let me run it.

Start by telling me in a few lines what's built in my area and your plan, then begin.
```

### Person C: Voice, Siri, Meet, and UI

```text
I'm Person C: Voice, Siri, Meet, and UI on our Cal Hacks 2026 team. Read README.md, MVP.md, and HANDOFF.md in full first. Most of the code is already built; HANDOFF.md "What's built" says what's tested and what isn't, and "What still needs a person" lists the remaining work. I own outputs/tts_cartesia.py, outputs/tts_say.py, outputs/mock_tts.py, outputs/siri.py, outputs/mock_siri.py, outputs/call_host.py, captions/, ui/, fixtures/captions_sample.txt, and the `tts`, `siri`, and `captions` lines.

My job now: make the Meet call, our centerpiece, work for real. With CARTESIA_API_KEY in .env, pick a Sonic voice for cartesia.voice_id and check `tts: cartesia` is heard in a Meet call through BlackHole 2ch. Install BlackHole 16ch, set up the Multi-Output Device from the README's "Audio for Meet", and check `captions: cartesia` in a real two-laptop call (captions within a couple of seconds, partials updating in place). Check the call intro and the signing cue sound right, then polish Demo Mode fullscreen on the external display. Build the app with `swift build --package-path ui/macos` after Swift changes.

How to work: I'm on branch person-c. Commit in small steps and open a PR to main when a piece works. Flip only my own config.yaml lines while testing and don't commit them (main stays on mock). `make test` and `make lint` must pass before every PR. Never print to stdout in engine code (it's the app protocol), never log what the user signs or says at INFO, and never commit .env. Don't change shared/, app.py, Makefile, or tests/contracts/ without asking me first. If something needs a live keystroke, the webcam, or a call, tell me the command and let me run it.

Start by telling me in a few lines what's built in my area and your plan, then begin.
```
