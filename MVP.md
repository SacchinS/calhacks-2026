# MVP plan: who builds what

**Scope change (Oct 24):** the project is now **Google Meet only**: signing spoken in the call, captions back, and fingerspelling autocomplete with Moss. Claude Code and Siri are gone from `main`; the earlier version is on the `archive/claude-code-siri` branch. Each person owns one part of the app, swaps its mocks for the real thing, and doesn't touch anyone else's files. Everything talks through the interfaces in `shared/events.py`, so each of you can work and test alone using the mocks for everyone else's parts. `HANDOFF.md` ("What's built" and "What still needs a person") says what's tested.

**Deadline:** submissions are due **Sunday Oct 25, 9:00 AM PT**, and we have to be at the venue by 8:00 AM. Judging needs a public GitHub repo, an image, and a live or recorded demo (3-minute pitch plus 2 minutes of questions).

**Tracks we're entering:**
- Anthropic (Claude turns ASL gloss into English and tags the words autocomplete remembers)
- Cartesia (the signer's voice in the call, captions, and turn detection)
- Moss (the autocomplete's search, run on the Mac; check the track's rules)
- Meta, "Bringing People Closer Together with AI" (the Meet story)
- Cal Hacks general prizes (Overall, People-First Social Impact, Most Technically Complex, Most Creative, Hacker's Choice)
- Commit Fellowship (opt in on the submission form)

**What it is:** a native Mac menu-bar app, not a web page: SignBridge's SwiftUI front end (`ui/macos`) driving our Python engine. Its **Preview** window shows the webcam feed with tracking, the recognized signs, the autocomplete while spelling, the English, and the call (your words, the other side's captions, quick replies). **Demo Mode** is the same live view as a fullscreen stage. For the demo, Demo Mode goes fullscreen on a second display plugged into the laptop, so judges see the signing and tracking there while the laptop's own screen shows the Meet call.

**Who it's for:** Deaf ASL signers. Not hearing ASL learners. Don't describe the product as "giving Deaf people a voice" or call them "silent"; describe it as parity in calls. Don't claim it replaces interpreters.

**What Deaf users told us:** Professor Lance Forshay (UW, Deaf ASL faculty) answered our survey. He'd use this for **video calls only**. His biggest frustrations with calls are interpreter quality and hearing people hanging up because they don't know who's calling. What would stop him from trusting it: **"accuracy, government recording, privacy."** His full answers and what we changed are in `docs/user-research.md`. They set the rules for everyone:
- **Calls are the whole product.** That's why we cut everything else.
- **Video never leaves the laptop.** Our app never sends video anywhere: tracking and recognition run on the device. Claude gets only the recognized sign words (text), plus a remembered word and the last ~30 seconds of conversation for autocomplete tags. Cartesia gets only the final English to speak, plus the other side's call audio for captions. The autocomplete keeps words and tags in a local file, never sentences. The app always shows whether the camera is on. Don't add logging that saves frames or transcripts: log the user's text at DEBUG at most, never at INFO.
- **The signer sees the English before or as it's spoken**, and "Review before speaking" makes it wait for a signed YES.

## What the MVP must do

**The pitch is 3 minutes:** a problem slide, the live demo, two slides on how it works, a close.

| Time | What |
|---|---|
| 0:00–0:20 | **Problem** (1 slide): meetings run on speech; signers wait for an interpreter or type in the chat. Prof. Forshay's quote. |
| 0:20–1:40 | **Live demo** (below) |
| 1:40–2:35 | **How it works** (2 slides): the stack (webcam → MediaPipe on the Mac → sign models + letter model → Moss autocomplete, local → Claude Haiku → Cartesia Sonic into Meet; back: Cartesia Ink captions and turn-taking), then features and privacy with the measured numbers (letters saved, latency) |
| 2:35–3:00 | **Close:** testing with Deaf users after Cal Hacks |

**The demo** is a release check-in on Google Meet between two laptops, live, with a real webcam; Demo Mode is on the projector. A (product manager) and B (engineer) are hearing teammates; the signer is on the design side:

1. **The meeting runs on speech.** B: *"The dashboard's ready. Pranav redesigned the charts in Figma last night, so I think we ship tomorrow."* The captions appear, and the autocomplete remembers Pranav and Figma.
2. **Getting the floor.** A and B keep talking quickly. The signer taps **"Sorry, can I jump in?"** (said right away), or turn-taking says it after a few seconds of waiting.
3. **Signing, fingerspelling, voice.** The signer signs `WAIT`, spells **F-I** (`YES` takes **Figma**), signs `COLOR PROBLEM`, `FINISH`: *"Wait, there's a color problem in the Figma design."* in the Cartesia voice, at the next pause.
4. **Being asked.** A: *"Good catch. Sacchin, can you sort it out with Pranav?"* The name banner flashes over every window.
5. **The answer.** The signer signs `ME MEET`, spells **P-R** (`YES` takes **Pranav**), signs `TOMORROW`, `FINISH`: *"I'll meet with Pranav tomorrow."*
6. **The outcome.** A: *"Great, then we hold the release until that's fixed."* The signer changed the decision.

The fingerspelled words use letters the letter model reads well on our signer (P, R, F, I; `recognition.letter_set: PRFI`), and both are heard in the meeting before they're spelled. The signs are our signer's recorded custom signs: WAIT, COLOR, PROBLEM, ME, TOMORROW still need recording (MEET, YES, FINISH are done). YES can't be a word in a sentence: it's a control sign (it takes a suggestion or approves a review). Backups: Demo Mode's keys 1–3 send the phrases, typed letters still drive the autocomplete, and a backup video is recorded the night before. The Jira agent and meeting memory from the v5 script are a "what's next" slide.

**Open:** how long each letter is held in the demo (5 s now, for testing with people new to ASL; 2–3 s once the signer has practiced), and who signs, plays A and B, and presents. The signer's name in the script has to match Settings > Calls for the banner.

**The demo glosses are drafts.** The greeting (`HELLO, NICE MEET-you`) is attested on Lifeprint (`docs/asl-demo-script-research.md`, Moment 3). The fingerspelled names are standard ASL practice. A Deaf signer must approve or rewrite the exact sentences before the demo. Nobody on the team knows ASL, so learn every demo sign from the source videos linked in the research doc (or from a Deaf signer), never by guessing, and keep the demo script short and fixed.

**Control signs for the MVP:**
- `YES` and `NO` are signed. While a word is being spelled, YES takes the suggestion and NO dismisses it; with review on, they decide whether the English is spoken.
- `FINISH` is signed and acts as SEND (it needs a hold, because FINISH also means "already" inside a sentence).
- `CLEAR` is in the UI: Cancel while signing clears.

## How we work

- Each person works on their own branch (`person-a`, `person-b`, `person-c`), merges to `main` through a pull request, and pulls `main` often.
- While developing, flip only your own line in `config.yaml` from `mock` to the real thing. `make mock` must keep working for everyone at all times.
- Your real implementation must pass the contract test for its interface in `tests/contracts/`.
- Don't change `shared/`, `app.py`, `Makefile`, or `tests/contracts/` without telling the other two first.
- Secrets go in `.env` only (`ANTHROPIC_API_KEY`, `CARTESIA_API_KEY`, `MOSS_PROJECT_ID`, `MOSS_PROJECT_KEY`). Never commit keys; Cartesia's rules disqualify that.

## Checkpoints

- **Saturday evening:** the scope change is on `main`; everyone has pulled it and run `make mock`.
- **Saturday night:** the whole call works on the real two-laptop, two-screen setup, with live recognition and camera letters. Record a backup demo video.
- **Sunday ~3 AM:** feature freeze. Only bug fixes, README, Devpost write-up, and pitch practice after this.
- **Sunday 8 AM:** at the venue. **9 AM PT:** submitted on Devpost. This is a hard deadline.
- **Sunday 10:30 AM–12:30 PM:** judging. The whole team is there.

---

## Person A: Recognition

**You own:** `recognition/`, `tools/record_*.py`, `tools/tune_recognition.py`, `fixtures/landmarks_sample.jsonl`. Config line: `recognizer`.

**Your job:** turn the webcam into `SignEvent`s and fingerspelled `Letter`s, accurately enough for the demo call.

**MVP (in this order):**
1. **Camera, landmarks, gating, segmenter, control signs.** *(Built.)* MediaPipe Holistic landmarks, the signing-space box, one `SignEvent` per sign, and held YES / NO / FINISH.
2. **Fingerspelled letters from the camera.** *(Next.)* A static-handshape letter model on the 21 hand landmarks (an ONNX MLP from Hugging Face, A–Z; check its license) that publishes one `Letter` per letter when a handshape is held still, only once two letters come in a row (so a sign's starting handshape isn't read as a letter). J and Z move, so keep them out of the demo words. The autocomplete already allows for look-alike handshapes (M/N, U/V/R, A/S/T/E). Done when spelling P-R and F-I live brings up Pranav and Figma.
3. **A bigger sign vocabulary.** *(Next.)* Add the ASL Citizen ST-GCN model (Microsoft, MIT code, 2,731 signs, MediaPipe Holistic points, ~20 ms per sign on an M1) next to the Kaggle model, limited to the demo's signs so it only chooses among them, with a "nothing" cutoff so other movement isn't forced into a demo sign. Weights go in `models/asl_citizen/` (gitignored). Done when the greeting comes out right most of the time.
4. **Record and tune.** Record the demo phrases with `tools/record_script.py` and tune the thresholds with `tools/tune_recognition.py` (on the `person-a` branch until its PR merges). Record a real fixture to replace `fixtures/landmarks_sample.jsonl`.
5. **Custom signs.** *(Built: `recognition/custom_signs.py`, `tools/record_signs.py`.)* Only for demo signs neither model knows (likely the MEET-you form). Learn each from the videos in `docs/asl-demo-script-research.md`.

**Stretch:** facial grammar markers (built, off until a Deaf signer checks them).

**Test alone with:** `recognizer: camera` and everything else on `mock`. Preview shows the signs and the letters you produce.

**Needs:** a laptop webcam and good lighting. No API keys.

## Person B: Language and autocomplete

**You own:** `language/`, `outputs/router.py`, `tools/seed_vocab.py`. Config lines: `translator` and `vocab_search`.

**Your job:** turn gloss into English with Claude, and make the fingerspelling autocomplete fast and right. This is the core of the **Anthropic** and **Moss** stories.

**MVP (in this order):**
1. **Claude translator.** *(Works: live tests pass, under 1 s.)* Keep `language/prompts/gloss_to_english.md` matched to the final demo glosses once a Deaf signer approves them, and rerun `uv run pytest --live tests/test_claude_translator.py`.
2. **Moss live.** *(Built, not run: needs keys.)* Put `MOSS_PROJECT_ID` and `MOSS_PROJECT_KEY` in `.env` and run `uv run pytest --live tests/test_moss_search.py`: real ranking, suggestion latency under 50 ms, startup with 500 words (`tools/seed_vocab.py --synthetic 500 --time`). These are the pitch's numbers.
3. **Tune autocomplete.** Check Claude's tags on real words, then tune the weights and look-alike groups in `config.yaml` (`autocomplete:`) on A's real letters.
4. **Review before speaking.** *(Built: Settings > Calls.)* Keep it working with the autocomplete's YES/NO.

**Should do:** pass remembered names and jargon to Cartesia Ink so captions spell them right and mention alerts match (check Ink's docs for the exact option first).

**Stretch:** a "what's on me" recap after the call, from captions held in memory only.

**Test alone with:** `recognizer: mock` (type `~pri`), `translator: claude`, `vocab_search: moss`.

**Needs:** `ANTHROPIC_API_KEY` and the Moss keys in `.env`.

**You also write:** the README's "How we use Claude" and "Autocomplete with Moss" sections, with the measured numbers.

## Person C: Voice, Meet, and the Mac app

**You own:** `outputs/tts_*.py`, `outputs/mock_tts.py`, `outputs/turn_taking.py`, `outputs/call_host.py`, `captions/`, `ui/`, `fixtures/captions_sample.txt`. Config lines: `tts` and `captions`.

**Your job:** make the signer heard in the call, show the call as captions, and make the screen clear for a Deaf user. This is the core of the **Cartesia** and **Meta** tracks.

**MVP (in this order):**
1. **The real two-laptop call.** *(Each piece works on a loopback.)* Meet's microphone = BlackHole 2ch, Meet's speakers = a Multi-Output Device with BlackHole 16ch (README "Audio for Meet"). Check the other laptop hears the Cartesia voice and our captions show their speech within a couple of seconds.
2. **Turn-taking in the real call.** Tune `meet.chime_in_seconds`, `barge_in_seconds` and `yield_seconds` until the voice neither waits too long nor talks over people.
3. **Demo Mode on the second screen.** The camera, the signs, the autocomplete bar, the captions and the floor status, readable from the back of the room.
4. **The new UI.** Look over the mention banner over fullscreen Meet, the autocomplete bar, and Settings > Remembered words; fix spacing and sizes.
5. **Packaged app.** `make app`, keys and a `config.yaml` in `~/Library/Application Support/calhacks-2026/`, and run the demo from it.

**Test alone with:** `recognizer: mock`, `translator: mock`, `tts: cartesia`, `captions: cartesia`.

**Needs:** `CARTESIA_API_KEY` in `.env`, BlackHole 2ch and 16ch, Xcode or its command-line tools (the app is Swift), a second laptop for the call, and the second display for the demo.

**You also write:** the "Cartesia features we use" section of the README, which Cartesia's rules require.

## Everyone, Sunday morning

- The README is complete: setup steps, how it works, the Claude, Cartesia and Moss sections, and honest limitations (small vocabulary, facial grammar only partly read).
- Devpost submission with the repo link, an image, the demo video, and all our tracks selected, plus the Commit Fellowship opt-in.
- The pitch tells the real story: "A Deaf ASL professor told us the only place he'd use this is video calls, so we built only that." Show the call, the name spelled in three letters, the captions, and the banner. Quote him on hang-ups and on privacy, give review-before-speaking and on-device video as our answers to "where can this go wrong", and close with the plan to test with him after Cal Hacks.
