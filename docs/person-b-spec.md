# Person B (Eleyn): the remaining work as four prompts

Four prompts finish Person B's part of HANDOFF.md. Prompts 1 and 2 run on the Windows ThinkPad, one after the other in one Claude Code session. Prompt 3 runs on the Apple Silicon demo laptop, and Prompt 4 runs after the Deaf review. Paste each prompt as written. Each one ends with something to check before you move on.

Written Oct 25, 2026, 1:15 AM PDT, against `main` at `b0affca` plus Sacchin's unmerged `person-a` branch. Feature freeze is ~3:00 AM; Devpost is due at 9:00 AM PT.

| # | Prompt | Runs on | Needs | Before the freeze? |
|---|---|---|---|---|
| 1 | Live check: Moss, tagger, translator, plus a latency bench | ThinkPad | Anthropic + Moss keys | Yes, first |
| 2 | YES-while-spelling fix and caption keyterms | ThinkPad | Nothing live | Yes |
| 3 | Mac checks, real-letter tuning, final numbers, README | Demo laptop | All keys, webcam, the real call | After the merges (numbers and docs only) |
| 4 | Final glosses after the Deaf review | ThinkPad or demo laptop | The approved glosses | When the review lands |

Out of scope for now: the "What's on me" recap and Jira tickets. The demo is the one in HANDOFF.md: Pranav and Figma, spelled P-R and F-I. The translator and tagger stay on Claude Haiku 5.5, the team's choice for speed.

## Why the work is split this way

- **Moss can't install on the Intel Mac.** Its core package, `inferedge-moss-core`, has never shipped an Intel Mac build (none in 49 versions) and has no source package. It does ship `cp310-abi3-win_amd64`, which works with the project's Python 3.11 on a 64-bit Intel/AMD ThinkPad.
- **Mac-only parts.** The SwiftUI app, BlackHole audio, the real Meet call and the camera letters exist only on the Mac. So the Mac checks and the numbers the pitch quotes come from the demo laptop (Prompt 3), not from Windows.
- **Expected test failures on Windows.** Some tests may fail on Windows only because `language/vocab_terms.py` reads macOS's word list (`/usr/share/dict/words`). That's expected; the Mac run is the one that counts.

## Before Prompt 1 (about 15 minutes, by hand)

1. **Ask Sacchin to merge `person-a` into `main` now.** It changes the demo words to Pranav and Figma and edits your files: `language/prompts/gloss_to_english.md`, `config.yaml`, and `tests/test_autocomplete_flow.py`. Branching before the merge means merge conflicts near the freeze.
2. **Make a Moss project** on the Moss Portal; code CALHACKS on the billing page gives credits. Copy its project ID and key.
3. **On the ThinkPad**, in PowerShell:
   - Check it's an x64 machine: `$env:PROCESSOR_ARCHITECTURE` should print `AMD64`. If it prints `ARM64`, Moss runs under emulation and the timings are slower.
   - Install Git for Windows, then uv: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`.
   - Install Claude Code and log in.
   - Clone the repo and switch to the `person-b` branch (it already holds this spec), then bring in the merged main:
     ```powershell
     git clone https://github.com/SacchinS/calhacks-2026.git
     cd calhacks-2026
     git checkout person-b
     git merge origin/main
     ```
   - Create `.env` with `copy .env.example .env`, then fill in `ANTHROPIC_API_KEY`, `MOSS_PROJECT_ID` and `MOSS_PROJECT_KEY` yourself. `CARTESIA_API_KEY` is optional here.
   - Run `uv sync`. It should install `moss` and `inferedge-moss-core` without errors.
4. **Open Claude Code in that folder** and paste Prompt 1.

**Checking a PR on a Mac.** Some tests may fail on Windows only because the macOS word list is missing. Before you merge each PR, run the suite on the Intel Mac. Moss can't install there, so leave it out:

```bash
git fetch && git checkout person-b && git pull
```
```bash
uv sync --no-install-package moss --no-install-package inferedge-moss-core
```
```bash
uv run --no-sync pytest -q --ignore=tests/test_moss_search.py
```

## Prompt 1: live check of Moss, the tagger and the translator (ThinkPad)

Done when: `docs/person-b-numbers.md` has Windows numbers for Moss and the translator, the live tests pass, and a PR is open.

```text
I'm Person B (Eleyn): Language and autocomplete on our Cal Hacks 2026 team. Read README.md, MVP.md and HANDOFF.md in full first, then docs/person-b-spec.md (this plan). The project is Google Meet only. I own language/, outputs/router.py, tools/seed_vocab.py, and the `translator` and `vocab_search` lines in config.yaml.

I'm on a Windows ThinkPad, in PowerShell, on branch person-b. Windows has no `make`: use `uv run pytest -q`, `uv run ruff check .` and `uv run ruff format --check .`. Some tests may fail here only because language/vocab_terms.py reads macOS's /usr/share/dict/words. Don't change the heuristics to make them pass; list those tests in the PR description as "Windows only: missing macOS word list".

How to work, for this prompt and the next ones: commit in small steps. Flip only my own config.yaml lines while testing and never commit them (main stays on mock). Never print to stdout in engine code (it's the app protocol). Never log what anyone signs or says at INFO. Never commit .env, never print key values, and never paste them into a command line. Don't change shared/, app.py, Makefile or tests/contracts/ without asking me first, because the other two depend on them. If something needs a live keystroke, the webcam or a call, tell me the command and let me run it. Use the claude-api skill before writing or changing any Claude API call. The translator and tagger stay on claude-haiku-5-5 with thinking disabled and effort low (valid on Haiku 5.5). Don't add `fallbacks`, `temperature`, `top_p` or `top_k` to Haiku requests: they return 400s.

Do these in order:

1. Baseline. Run `uv sync` and `uv run pytest -q`. Confirm the keys are set without showing them: `uv run python -c "from shared.config import Config; print({k: bool(Config.secret(k)) for k in ['ANTHROPIC_API_KEY','MOSS_PROJECT_ID','MOSS_PROJECT_KEY','CARTESIA_API_KEY']})"`. Tell me which tests fail and why, in a few lines.

2. Moss against the real SDK. Moss has never run with real keys; language/vocab_search.py (MossSearch) was written against a fake client in tests/test_moss_search.py. Read the installed SDK source (.venv\Lib\site-packages\moss, and inferedge_moss_core if it has Python stubs) and check every call MossSearch makes: MossClient(project_id, project_key); `await client.session(index_name, model_id, auto_load_on_init=False)`; session.add_docs([DocumentInfo(id, text, metadata)]); session.delete_docs(ids); `session.query(text, QueryOptions(top_k, alpha, filter={"field": ..., "condition": {"$in": [...]}}))` and result.docs[i].metadata / .score; session.doc_count; session.close() and client.close(). Fix MossSearch wherever the real API differs, and update FakeClient/FakeSession in tests/test_moss_search.py to match the real shapes, so the fake keeps testing the truth. Two rules must survive: the session is never pushed (no push_index or any cloud write of our documents), and metadata values are strings. While you're in the SDK source, check the README's privacy claims ("Queries run in memory with no cloud call", "telemetry sends counts and timings, never document or query text"). If the source says otherwise, tell me and correct the README's "Autocomplete with Moss" section to match the code.
   Then run `uv run pytest --live tests/test_moss_search.py -s` until both live tests pass. The ranking test needs J-U to give Julian in a tennis conversation, Jupyter in a data one, and letter-to-suggestion under 50 ms.

3. A latency bench we can rerun on the Mac. Add `--bench N` to tools/seed_vocab.py. It loads the demo words (demo_occurrences) plus the conversation from fixtures/captions_sample.txt into an Autocompleter with the configured vocab_search, spells P-R and F-I N times each (default 50), and prints p50 and p95 of letter-to-suggestion latency (Autocompleter.latency_ms), p50 and p95 of the Moss query (search_ms), the startup build time, and whether the top suggestion was Pranav and Figma every time. It must never touch the real memory: use a temporary SQLite file (or ":memory:") unless --db is given. Run `uv run python tools/seed_vocab.py --bench 50` with `vocab_search: moss` flipped locally, and `--synthetic 500 --time` with CALHACKS_VOCAB_DB pointed at a temp file ($env:CALHACKS_VOCAB_DB = "$env:TEMP\vocab-bench.sqlite"), so the 500 made-up words never land in my real vocab.sqlite.

4. Tagger live check. Add tests/test_tagger_live.py (marked live) that runs ClaudeTagger on the demo's words with the demo caption as context ("Hi, I'm Pranav, I'm designing the new app. The mockups are all in Figma."), plus "Julian" with a tennis sentence and "API" with a backend sentence. Assert: kind is name for Pranav and Julian and acronym for API; display spells Pranav, Figma, API; 3 to 5 tags, lowercase, 1 to 3 words each; no tag contains another person's name or copies a sentence. Run it. If tags are vague or leak names, tighten SYSTEM in language/tagger.py and rerun.

5. Translator test set for the Meet demo. The prompt (language/prompts/gloss_to_english.md) is now written for speech in a meeting, but LIVE_CASES in tests/test_claude_translator.py still has Claude Code and Siri cases (FOOD STORE WW MAKE, TITLE /\ RED, YOU-REMIND-ME, fs-CSS FILE fs-NAVBAR BLUE, ME WANT FIX BUG LOGIN PAGE). Replace those with meeting cases from the demo and docs/asl-demo-script-research.md (Moment 3): HELLO fs-PRANAV NICE MEET-YOU; fs-FIGMA; HOW YOU [wh-question]; FINE; THANK-YOU; a fingerspelled word mid-sentence the way the autocomplete inserts it (check Utterance.gloss for the exact form); and two recognition-mistake cases. Keep the face-marker cases. Make the live test time each call and assert under 2 s. Run `uv run pytest --live tests/test_claude_translator.py tests/contracts -s` until it passes. If a case fails, fix the prompt, not the regex, unless the regex is wrong.

6. First-sentence latency. The first translation pays for the TLS connection and the cache write. Add `async def warm(self) -> None` to language/base.py (a no-op by default). ClaudeTranslator.warm sends the same system prompt with `max_tokens=0`: no stream and no structured output, because both are rejected with max_tokens 0. Have UtteranceBuffer.start run translator.warm() as a background task that logs at DEBUG and never raises. Unit-test it with the fake client. Check live that a translation right after warm-up reports usage.cache_read_input_tokens > 0, and write the before/after first-call time in the numbers file.

7. Write docs/person-b-numbers.md: a table with the date, the machine (ThinkPad, Windows, CPU from `Get-CimInstance Win32_Processor`), and every number from steps 2 to 6. Label the section "Windows, provisional: the README uses the demo laptop's numbers".

8. Run `uv run ruff check .` and `uv run ruff format --check .`, commit, push person-b, and open a PR to main with `gh pr create`. Put the numbers and the Windows-only test failures in the description.

Start by telling me in a few lines what you found in step 1, then keep going through step 8 without waiting for me unless something needs my keys or a decision.
```

## Prompt 2: YES while spelling, and caption keyterms (ThinkPad)

Done when: both fixes have tests, the suite passes on the Mac check above, and a PR is open. Before pasting, tell Julian you're adding a `keyterm` list to `captions/cartesia_stt.py`, and tell Sacchin and Julian you're changing two lines in `app.py`.

```text
Same rules as before (Windows, no make, my files, no stdout, no keys in commands, ask before shared/ or app.py; I've told Julian and Sacchin about the two changes below, so app.py's two wiring lines and captions/cartesia_stt.py are OK to edit). Pull main first and rebase person-b if Prompt 1's PR merged.

1. YES while spelling (HANDOFF "Known edge"). With meet.review_before_speaking on, a signed YES while a word is being spelled and a sentence is waiting for review does both: the utterance buffer (language/utterance.py) accepts the suggestion, and the router (outputs/router.py) also approves the pending sentence. NO has the same problem. The cause: both subscribe to SignEvent on the bus (shared/bus.py), and each gets its own copy of the event in its own queue, so either can run first.
   Fix it so the result is the same whichever runs first:
   - The Autocompleter keeps a small `consumed` deque (maxlen 16) of the control SignEvent objects the buffer used while spelling. UtteranceBuffer.handle adds the event before it accepts or dismisses.
   - The Router gets an optional `spelling` attribute (the Autocompleter), set in app.py next to `self.buffer.spelling = self.autocomplete`.
   - Router.handle ignores YES and NO when `spelling.active` is true or the event is in `spelling.consumed` (compare by identity, `is`). That covers both orders: if the router runs first, spelling is still active; if the buffer runs first, the event is already consumed.
   - The app's on-screen confirm and cancel gestures (ui/server.py "gesture") must behave the same; check how they reach the router and the buffer.
   Tests in tests/test_router_confirm.py: YES while spelling with a pending review accepts the word and leaves the sentence pending, in both processing orders (call the two handlers directly, both ways round); NO while spelling dismisses only the suggestion; YES with nothing being spelled still approves the sentence; quick replies are unchanged.

2. Remembered words as Cartesia Ink keyterms, so captions spell names like Pranav and Figma right and the mention alerts match. Ink takes `keyterm=[...]` on `client.stt.auto_finalize.websocket(...)` (installed cartesia SDK: cartesia/types/stt/auto_finalize_websocket_params.py). The rules: up to 100 terms totaling 1200 characters, set when the connection opens, and they can't change mid-stream.
   - In language/vocab_terms.py, add `keyterms(occurrences, names, limit=100, max_chars=1200) -> list[str]`. Order: the signer's name and meet.mention_names first, then remembered names, acronyms and terms, ranked by uses and then by last use, in their display form. Dedupe case-insensitively, skip common English words (is_common), and stop at the limits. Unit-test the order, dedupe and limits.
   - In captions/cartesia_stt.py, add `self.keyterms: list[str] = []` to CartesiaCaptionSource and pass `keyterm=self.keyterms` to the websocket only when it's non-empty. The FakeWebsocket in tests/test_cartesia_captions.py already records its kwargs (`.kwargs`); use it to test both cases.
   - In app.py, before `await self.captions.start()`, set `self.captions.keyterms` from `keyterms(self.vocab.all(), [meet.signer_name, *meet.mention_names])` when the source has that attribute. The mock captions ignore it.
   - Words learned during a call only reach Ink on the next start. Say so in one sentence in the README's "Cartesia features we use".
   - Don't log the terms at INFO. Log only how many were sent, at DEBUG.

3. Run the suite and lint, commit, push, and open a PR. In the description, give Julian the command to check captions live on the Mac: `captions: cartesia` flipped locally and `make seed-vocab`, then a caption that says "Pranav" and "Figma".
```

## Prompt 3: Mac checks, real-letter tuning, final numbers and the README (demo laptop)

Run this on the Apple Silicon demo laptop after Prompts 1 and 2 and Sacchin's letter model are on main. Measuring and documenting are fine after the freeze; only fixes go in. Open a separate Claude Code session in the repo on the demo laptop, on a new branch `person-b-numbers`.

```text
I'm Person B (Eleyn): Language and autocomplete on our Cal Hacks 2026 team. Read README.md, MVP.md, HANDOFF.md and docs/person-b-spec.md first, plus docs/person-b-numbers.md (the provisional Windows numbers). I own language/, outputs/router.py, tools/seed_vocab.py, and the `translator` and `vocab_search` lines. This is the Apple Silicon demo laptop, after the feature freeze: measure, tune config values and write docs; change code only to fix a bug, and tell me first.

Rules: flip config component lines only locally and never commit them (main stays on mock); you may commit tuned values under `autocomplete:`. No stdout in engine code. Never log what anyone signs or says at INFO. Never commit .env or print keys. Don't change shared/, app.py, Makefile or tests/contracts/. Ask me to run anything that needs the webcam, a live keystroke or the call.

1. Install and check. Run `git checkout main && git pull && git checkout -b person-b-numbers`. Then `uv sync --extra camera`, `make test`, `make lint`. These must all pass here; this is the run that counts. Confirm the keys are set without printing them (same one-liner as docs/person-b-spec.md Prompt 1). Then run `uv run pytest --live tests/test_moss_search.py tests/test_tagger_live.py tests/test_claude_translator.py tests/contracts -s`.

2. Numbers on this machine: `uv run python tools/seed_vocab.py --bench 50` (vocab_search: moss), and `--synthetic 500 --time` with CALHACKS_VOCAB_DB pointed at a temp file. Also the translator: p50 and p95 per call over the live cases, and the first call after warm-up.

3. Tune on real letters. Have me run `make seed-vocab`, then `make demo` with the camera (Sacchin's letter model, letter_set PRFI), and play the demo call's captions (or have the other laptop say them). Then I spell P-R and F-I ten times each. Read the autocomplete_stats and the logs at DEBUG. If Pranav or Figma isn't the top suggestion from the second letter, tune `autocomplete:` in config.yaml (weights, similar_handshapes, substitution_penalty, context_spread, search_timeout_ms) and repeat. Keep the J-U test passing: Julian with tennis, Jupyter with data. Record letters saved per accepted word (Pranav: 6 letters, 2 spelled; Figma: 5, 2 spelled) and the accept rate.

4. With Julian, in the real two-laptop call: check that captions spell Pranav and Figma with the keyterms on, and that saying "Sam" raises the mention banner. With review before speaking on, sign a word with YES while a sentence waits, and check that the sentence stays pending.

5. Write the README sections with the measured numbers, all labeled with this machine (model and chip), and keep them short and factual:
   - "Autocomplete with Moss": suggestion latency p50/p95, Moss query p50/p95, 500-word startup, letters saved in the demo, and the keyterms. Update "Try it" for Pranav and Figma; the Kubernetes line is stale.
   - "How we use Claude": the translator (model, time per sentence, how the prompt handles fingerspelling and face markers), the tagger (structured JSON, what it sees, what's stored), and "Where it can go wrong".
   Move the final numbers into docs/person-b-numbers.md under "Demo laptop (final)", keeping the Windows table below it. Give me a 5-line summary of the numbers for the lead's Devpost entry.

6. Commit, push and open a PR. The description says it changes docs and config values only.
```

## Prompt 4: final glosses after the Deaf review (blocked until then)

Paste this once Professor Forshay, or another Deaf signer, has approved or rewritten the demo glosses. Put the approved glosses where the brackets are.

```text
Same rules as before. The Deaf review is back. These are the approved demo glosses and the English each should become:

[paste each approved gloss → English here]

Update language/prompts/gloss_to_english.md: replace or add the examples so they match these exactly, and remove any example the reviewer rejected. Update LIVE_CASES in tests/test_claude_translator.py to cover each approved gloss. Run `uv run pytest --live tests/test_claude_translator.py tests/contracts -s` until every case passes in under 2 s. Check docs/asl-demo-script-research.md (Moment 3) and the app's demo phrases still match; list for Sacchin any sign he needs to re-record. Commit, push and open a PR.
```

## Sources

- [inferedge-moss-core on PyPI](https://pypi.org/project/inferedge-moss-core/) (wheel platforms) and [moss on PyPI](https://pypi.org/project/moss/)
- [Cartesia keyterm prompting](https://docs.cartesia.ai/use-the-api/stt/keyterms), and the installed `cartesia` 4.2.0 SDK (`keyterm` on the STT websocket)
- Claude API behavior per the bundled claude-api reference (cached Oct 6, 2026): Haiku 5.5 accepts disabled thinking at low effort and has no server-side fallback; `max_tokens: 0` pre-warms the cache; the minimum cacheable prompt on these models is 512 tokens.
