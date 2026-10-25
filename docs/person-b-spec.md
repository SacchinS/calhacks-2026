# Person B (Eleyn): the remaining work, with the Jira ticket demo

Prompts 1 and 2 are done; they're in PR #2. Three prompts are left:
- **Prompt 3** (ThinkPad) builds the Claude ticket agent and Jira.
- **Prompt 4** (demo laptop) checks everything on the Mac, takes the final numbers and rehearses the new script.
- **Prompt 5** follows the Deaf review.

Person C (Julian) builds the ticket card; his list is in "Handoff to Person C". Person A (Sacchin) adds five signs.

Updated Oct 25, 2026, ~3:05 AM PDT, on `person-b` (PR #2). The feature freeze was ~3:00 AM, so the Jira demo is a team call. It ships off by default (`tickets.enabled: false`), with a mock Jira when the Jira keys are missing, and the current Pranav greeting stays as the backup demo. Devpost is due at 9:00 AM PT.

## Done (PR #2, not merged yet)

- **Prompt 1:**
  - Moss runs against the real SDK, and both live Moss tests pass.
  - `tools/seed_vocab.py --bench`.
  - A live tagger check.
  - Translator live cases for the Meet demo, timed under 2 s.
  - `Translator.warm()`.
  - Windows numbers in `docs/person-b-numbers.md`.
- **Prompt 2:**
  - YES or NO spent on a suggestion no longer also decides the reviewed sentence.
  - Remembered words go to Cartesia Ink as keyterms.
- **Since then:**
  - The keyterms test words fixed for macOS.
  - The demo name changed from Priyanka to Pranav.

**Checking a PR on a Mac.** Moss can't install on the Intel Mac, so leave it out:

```bash
git fetch && git checkout person-b && git pull
```
```bash
uv sync --no-install-package moss --no-install-package inferedge-moss-core
```
```bash
uv run --no-sync pytest -q --ignore=tests/test_moss_search.py
```

## The demo script (about 2 minutes 20 seconds)

Sacchin signs. A and B are on the other laptop in the Meet call. Sacchin's name is set in Settings > Calls.

**1. B gives an update** (0:05)
B: "Hi guys, I just wanted to go over some changes. The dashboard's ready. Pranav redesigned the charts in Figma last night, so I think we ship tomorrow."
The captions show it, and the app remembers Pranav and Figma.

**2. Sacchin raises a problem** (0:20)
Sacchin signs WAIT, spells F-I, and signs YES to take Figma. Then he signs COLOR PROBLEM and FINISH.
The app waits for B to stop talking, then says: "Wait, there's a color problem in Figma." Claude may phrase it a little differently: it translates what was signed and adds nothing.

**3. A asks Sacchin to handle it** (0:50)
A: "Good catch. Sacchin, can you sort it out with Pranav?"
Sacchin's name banner flashes.

**4. Sacchin agrees** (0:58)
Sacchin signs ME MEET, spells P-R, and signs YES to take Pranav. Then he signs TOMORROW and FINISH.
The app says: "I'll meet with Pranav tomorrow."

**5. A holds the release** (1:25)
A: "Great, then we hold the release."

**6. Claude drafts a Jira ticket** (1:30)
A card appears: "Claude drafted a Jira ticket from this call."
- Summary: Fix the color problem in the Figma dashboard design
- Assignee: Sacchin
- Due: October 26, 2026
- Label: release-blocker
- Description: Raised in the dashboard release call. Sacchin meets Pranav tomorrow; the release is on hold until it's fixed.

Presenter: "Claude wrote this from what was just said, plus the names Moss already knew: Pranav and Figma, spelled right. Nothing goes to Jira until he approves it."

**7. Sacchin approves it** (1:55)
Sacchin signs YES. The card shows the new ticket number, for example SB-12. The presenter clicks "Open in Jira", and the ticket is there.

**8. Wrap-up** (2:05)
A: "Anything else before we wrap up?"
Sacchin signs THANK-YOU, FINISH. The app says: "Thank you."

With 2:20 of live call, the 3-minute pitch becomes: problem 0:00–0:15, demo 0:15–2:35, one "how it works" slide 2:35–2:50, close 2:50–3:00.

## How the ticket agent works

- **What Claude sees.** Two things, and only once the signer has been asked something and has answered:
  - The call's notes: the other side's final captions and the signer's spoken sentences. They're held in memory for this call only, never written to disk or the logs, and cleared when the app stops.
  - The remembered words that fit the call, with their tags, found by a Moss query over the session index. That's how "Pranav" and "Figma" come out spelled the signer's way.
- **Moss isn't the meeting's memory.** The long-term memory is still the local SQLite word file. Moss is the search index rebuilt from it at each launch.
- **When it drafts.** A mention of the signer (step 3) arms the agent for 90 s. The signer's next spoken sentence (step 4) starts a short wait, so the other side's reply (step 5) is in the notes too. Then Claude decides whether there's a task. If there isn't, nothing appears. There's at most one draft at a time, and a backup key drafts on demand.
- **Model.** Claude Opus 5.5 at effort low, with structured JSON output and server-side refusal fallbacks (`tickets.model`, so it can be switched).
  - If the card takes over 5 s in rehearsal, switch to `claude-sonnet-5-5`. That keeps the fallbacks.
  - Or switch to `claude-haiku-5-5`. That means no `fallbacks` parameter (it 400s there) and thinking disabled.
- **Approval.** The app creates the issue only after a signed YES, the card's Approve & Create button, or the confirm key. A YES goes, in this order, to:
  1. a word being spelled,
  2. a sentence waiting for review,
  3. the ticket draft.

  All three are resolved in the router, so they can't race.
- **The assignee** is the signer's own Jira account (`JIRA_ASSIGNEE_ACCOUNT_ID`), and only when the draft says the task is theirs. The agent never looks up or guesses anyone else. Pranav is named in the description only.

## Prompt 3: the ticket agent and Jira (ThinkPad)

Done when: the new tests pass and a mock run of the script produces the draft and then a mock ticket after YES. It's off by default, it's pushed to `person-b` (PR #2), and Julian has the protocol below.

Before pasting:
- Tell Julian you're adding the `ticket` protocol to `ui/server.py` and rewriting `fixtures/captions_sample.txt`. Tell the team you're changing two lines of `app.py` and the demo sections of `MVP.md` and `HANDOFF.md`.
- Put `JIRA_BASE_URL` (for example `https://yourteam.atlassian.net`), `JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_PROJECT_KEY` and `JIRA_ASSIGNEE_ACCOUNT_ID` (Sacchin's Jira account ID) in `.env` yourself. Without them, it uses the mock Jira.

```text
I'm Person B (Eleyn): Language and autocomplete on our Cal Hacks 2026 team, on the Windows ThinkPad, branch person-b (PR #2 is open from it). Read HANDOFF.md, MVP.md, README.md and docs/person-b-spec.md first; the spec's "The demo script" and "How the ticket agent works" are what this prompt builds. Pull person-b first.

Rules: Windows, no make (uv run pytest -q, uv run ruff check ., uv run ruff format --check .). Some tests may fail here only because macOS's /usr/share/dict/words is missing; list them, don't change the heuristics. No stdout in engine code. Never log what anyone signs or says at INFO, and never log captions, notes or ticket text at all. Never commit .env, print keys or put them in a command line. I've told Julian and the team about these files, so you may edit: ui/server.py (protocol only, no Swift), fixtures/captions_sample.txt, app.py (wiring only), config.yaml (new disabled sections), config.demo.yaml, .env.example, MVP.md and HANDOFF.md (the demo sections). Don't touch shared/, Makefile or tests/contracts/. Use the claude-api skill before writing the Claude call, and verify the call shape against it and the installed anthropic SDK. Ask me before anything that needs a live call or creates a real Jira issue.

Build, in order, committing after each step:

1. Call notes, in memory only: language/tickets.py, class CallNotes. It subscribes to Caption (is_final only, speaker "them") and OutputSent (speaker "me"), and keeps (ts, speaker, text) in a deque (tickets.notes_max, default 400). It's never written anywhere, it's cleared on app stop and on `{"cmd": "ticket", "action": "clear_notes"}`, and `text()` renders "them: ..." / "me: ..." lines.

2. Remembered words for the call. Add `async def related(self, text: str, top_k: int) -> dict[str, float]` to VocabSearch in language/vocab_search.py:
   - MossSearch: session.query with QueryOptions(top_k, alpha) and no filter.
   - KeywordSearch: the same overlap score it uses now, over all docs.
   - Base class: return {}.
   Then add `async def related_words(self, text, k=8) -> list[dict]` to Autocompleter: [{"term", "kind", "tags"}] from self.stats. Include every remembered word that appears literally in the text (case-insensitive) first, then the search's best matches, skipping common English (vocab_terms.is_common). If the search isn't ready or is slow, fall back to the literal matches alone. Unit-test both searches and the fallback with the existing fakes.

3. The drafter: language/tickets.py, class TicketDrafter, `async def draft(notes_text, words, today, signer) -> TicketDraft | None`.
   The call:
   - Model: tickets.model, default "claude-opus-5-5", through anthropic.AsyncAnthropic(timeout=20, max_retries=1).
   - No `thinking` parameter: it can't be disabled on Opus 5.5.
   - output_config = {"effort": tickets.effort (default "low"), "format": {"type": "json_schema", "schema": SCHEMA}}.
   - max_tokens 4000.
   - For Opus and Sonnet 5.5 models only: client.beta.messages.create with betas=["server-side-fallback-2026-07-01"] and fallbacks="default". For a Haiku model, the plain messages.create, thinking={"type": "disabled"} and no fallbacks.
   - The system prompt is a constant with cache_control ephemeral.
   - Check stop_reason == "refusal" before reading content, and read only text blocks.
   SCHEMA: {"ticket": null or {"summary": str (an action, max 120 chars), "description": str (2-3 plain sentences), "due": "YYYY-MM-DD" or "", "labels": [up to 3 lowercase-hyphenated], "people": [names from the notes, spelled as in the remembered words], "assign_to_signer": bool, "reasons": [1-3 short phrases saying where it came from]}}.
   The system prompt says:
   - Draft a ticket only when someone asked the signer to do something and the signer agreed or committed in the notes. Otherwise, null.
   - Never invent work, people or dates.
   - Resolve relative dates ("tomorrow", "by Friday") against `today`.
   - Spell names and tools exactly as in the remembered words.
   - No direct quotes of other people.
   - The signer is `signer`.
   The user message is JSON: {"today", "signer", "notes", "remembered_words"}.
   Unit-test with a fake client:
   - the request shape for an Opus model and for a Haiku model (no fallbacks);
   - that only the notes and words are sent;
   - refusal → None plus a Notice;
   - null → None;
   - schema-valid JSON → a TicketDraft.
   Add tests/test_tickets_live.py (marked live): it runs the drafter on the demo script's notes (steps 1-5 of the spec, with Sacchin as the signer and today = 2026-10-25) and asserts:
   - a summary about the color problem;
   - due 2026-10-26;
   - "Pranav" in people;
   - assign_to_signer is true.
   It also asserts the same notes without step 4 give null, and prints the time per draft.

4. The agent: class TicketAgent in language/tickets.py.
   - It subscribes to Mention, OutputSent and Caption.
   - A Mention arms it for tickets.armed_seconds (default 90).
   - An OutputSent while armed schedules a draft after tickets.settle_seconds (default 6) with no new final caption, at most tickets.max_wait_seconds (default 15) after the OutputSent.
   - `{"cmd": "ticket", "action": "draft"}` drafts now. It's the backup key.
   - States: none → drafting → draft → creating → created | failed. dismissed returns to none.
   - At most one draft at a time; there's no new draft while one waits.
   - It publishes a TicketUpdate. If adding an event to shared/events.py is needed, ask me first; otherwise keep the dataclass in language/tickets.py and have ui/server.py subscribe to it.
   - `approve()` creates the issue, only from the draft state, and only once. `dismiss()` drops the draft.
   - Measure draft_ms for the numbers file.

5. Jira: a new file, outputs/jira.py.
   - JiraClient uses only the standard library (urllib.request in asyncio.to_thread; no new dependency).
   - It POSTs {JIRA_BASE_URL}/rest/api/3/issue with Basic auth (base64 of email:token) and fields: project.key = JIRA_PROJECT_KEY, summary, issuetype.name = jira.issue_type (default "Task"), description as an Atlassian Document Format doc (one paragraph per sentence, plus "Drafted by Claude from a SignBridge call and approved by the signer."), duedate if set, and labels.
   - assignee.accountId = JIRA_ASSIGNEE_ACCOUNT_ID, only when assign_to_signer is true and the ID is set.
   - If Jira answers 400 naming duedate or labels (the field isn't on the create screen), retry once without that field and add a Notice saying so.
   - Return (key, f"{base}/browse/{key}").
   - Errors become a failed state with Jira's message, never the token.
   - MockJira (whenever a JIRA_* value is missing) returns MOCK-1, MOCK-2, and so on, and the card is told it's a mock.
   - Add the five JIRA_* names, with empty values, to .env.example.
   - Test with a fake opener: the URL, the auth header, the body, the assignee rules, the 400 retry, and that errors never contain the token. Add a live test that creates one real issue labeled signbridge-test and prints its key; it's skipped without the keys, and I'll run it myself.

6. YES and NO for the draft, in outputs/router.py.
   - The Router gets an optional `tickets` attribute (the TicketAgent), set in app.py next to router.spelling.
   - In Router.handle, after spent_on_spelling: if self.pending, confirm as now. Elif tickets has a draft waiting, YES approves and NO dismisses.
   - In ui/server.py gesture(): "confirm" approves and "cancel" dismisses a waiting draft when the state is idle (not confirming and no gloss).
   - Tests in tests/test_router_confirm.py:
     - YES while spelling never touches the draft;
     - YES with a pending review approves the sentence and leaves the draft;
     - YES with only a draft approves it once;
     - a second YES does nothing;
     - NO dismisses.

7. Protocol in ui/server.py, documented in its docstring; Julian builds the view from this:
   - Event {"type": "ticket", "state": "drafting|draft|creating|created|failed|dismissed", "draft": {"summary", "description", "assignee" ("Sacchin" or ""), "due", "labels", "people", "reasons", "words": [{"term", "tags"}]}, "key", "url", "error", "mock": bool, "draft_ms"}.
   - The same object, or null, goes in status as "ticket".
   - Command {"cmd": "ticket", "action": "draft|approve|dismiss|clear_notes"}.
   - Test the whole flow through the engine protocol with the mock captions, a fake drafter and MockJira: mention → sentence → draft → approve → created MOCK-1.

8. Wiring and config.
   - app.py: build CallNotes and TicketAgent only when tickets.enabled.
   - config.yaml: a `tickets:` section (enabled: false, model, effort, settle_seconds, max_wait_seconds, armed_seconds, notes_max) and a `jira:` section (issue_type: Task), with comments in the file's style.
   - config.demo.yaml: tickets: {enabled: true}.

9. Demo content.
   - Rewrite fixtures/captions_sample.txt to the spec's script: B's line, then A's two lines, then "Anything else before we wrap up?", with header comments saying to set the name to Sacchin.
   - Check that tools/seed_vocab.py --bench still finds Pranav and Figma in it, and that the mention and autocomplete tests still pass.
   - Add the new glosses to language/prompts/gloss_to_english.md (drafts until the Deaf review): `WAIT fs-FIGMA COLOR PROBLEM` → "Wait, there's a color problem in Figma." and `ME MEET fs-PRANAV TOMORROW` → "I'll meet with Pranav tomorrow."
   - Add both glosses to LIVE_CASES with regexes that accept natural variants. Run the live translator tests.

10. Docs.
   - Replace "The demo" in MVP.md and "The demo, in short" in HANDOFF.md with the spec's script, and update the pitch timing line.
   - Add a "Jira tickets" paragraph to the README's "How we use Claude": what Claude sees (the call's notes in memory, never stored, and the remembered words from Moss), what it can get wrong, and that nothing reaches Jira without the signer's YES.
   - Add the live draft time to docs/person-b-numbers.md (Windows, provisional).

11. Run the suite and lint, push person-b, and add a "Jira ticket agent" section to PR #2's description (gh pr edit 2 --body-file, keeping what's there). Then give me, in a few lines, what to tell Julian and Sacchin.
```

## Prompt 4: Mac checks, the rehearsal, final numbers and the README (demo laptop)

Run it on the Apple Silicon demo laptop once PR #2 is merged, Julian's ticket card is on main, and Sacchin's new signs are in. Measuring and docs only: change code just to fix a bug, and say so first. Open a new Claude Code session there, on a new branch `person-b-numbers`.

```text
I'm Person B (Eleyn): Language and autocomplete on our Cal Hacks 2026 team. Read README.md, MVP.md, HANDOFF.md, docs/person-b-spec.md and docs/person-b-numbers.md first. This is the Apple Silicon demo laptop, after the freeze: measure, tune config values, rehearse and write docs; change code only to fix a bug, and tell me first.

Rules: flip config component lines only locally and never commit them (main stays on mock); you may commit tuned values under `autocomplete:` and `tickets:`. No stdout in engine code. Never log what anyone signs or says at INFO. Never commit .env or print keys. Don't change shared/, app.py, Makefile or tests/contracts/. Ask me to run anything that needs the webcam, a live keystroke, the call or a real Jira issue.

1. Install and check. Run `git checkout main && git pull && git checkout -b person-b-numbers`, then `uv sync --extra camera`, `make test`, `make lint` and `swift build --package-path ui/macos`. These must all pass; this is the run that counts. Confirm the keys are set without printing them: `uv run python -c "from shared.config import Config; print({k: bool(Config.secret(k)) for k in ['ANTHROPIC_API_KEY','MOSS_PROJECT_ID','MOSS_PROJECT_KEY','CARTESIA_API_KEY','JIRA_BASE_URL','JIRA_EMAIL','JIRA_API_TOKEN','JIRA_PROJECT_KEY','JIRA_ASSIGNEE_ACCOUNT_ID']})"`. Then run `uv run pytest --live tests/test_moss_search.py tests/test_tagger_live.py tests/test_claude_translator.py tests/test_tickets_live.py tests/contracts -s`. Have me run the Jira live test myself: it creates one real issue.

2. Numbers on this machine:
   - `uv run python tools/seed_vocab.py --bench 50` with vocab_search: moss;
   - `--synthetic 500 --time` with CALHACKS_VOCAB_DB pointed at a temp file;
   - the translator's p50 and p95 per call, and the first call after warm-up;
   - the ticket drafter's time per draft over 5 runs.
   If the bench shows the Moss query over autocomplete.search_timeout_ms (40 ms) often, raise it to about 80 ms and rerun. If a draft takes over 5 s, try tickets.model: claude-sonnet-5-5 and compare.

3. Tune on real letters. Have me run `make seed-vocab`, then `make demo`. Delete any Priyanka left in Settings > Remembered words first. Then I spell P-R and F-I ten times each with the camera, with the demo captions playing. If Pranav or Figma isn't the top suggestion from the second letter, tune `autocomplete:` (weights, similar_handshapes, substitution_penalty, context_spread) and repeat. Keep the J-U test passing. Record letters saved per accepted word (Pranav: 6 letters, 2 spelled; Figma: 5, 2 spelled) and the accept rate.

4. Rehearse the spec's script with Julian and Sacchin in the real two-laptop call, three times, with tickets.enabled and the real Jira. Check each time:
   - the captions spell Pranav and Figma;
   - "Sacchin" raises the banner;
   - the step 2 sentence waits for B to stop;
   - the card appears within 5 s of A's "we hold the release";
   - YES creates exactly one issue, and "Open in Jira" shows it with the right summary, due date, label and assignee.
   Time the whole script. If it runs over 2:30, tell me which step to shorten. Delete the rehearsal issues in Jira afterwards; I'll do it, so list their keys.

5. README sections with the measured numbers, labeled with this machine (model and chip), short and factual:
   - "Autocomplete with Moss": suggestion latency p50/p95, Moss query p50/p95, 500-word startup, letters saved in the demo, and the keyterms. Update "Try it" for Pranav and Figma.
   - "How we use Claude": the translator, the tagger, the ticket agent (model, time per draft, what it sees, approval), and "Where it can go wrong".
   Move the final numbers into docs/person-b-numbers.md under "Demo laptop (final)", keeping the Windows table below. Give me a 5-line summary of the numbers for the lead's Devpost entry.

6. Commit, push and open a PR. The description says it changes docs and config values only.
```

## Prompt 5: final glosses after the Deaf review (blocked until then)

Paste it once Professor Forshay, or another Deaf signer, has approved or rewritten the demo glosses. That includes the new ones: WAIT fs-FIGMA COLOR PROBLEM, ME MEET fs-PRANAV TOMORROW and THANK-YOU. Put them where the brackets are.

```text
Same rules as before. The Deaf review is back. These are the approved demo glosses and the English each should become:

[paste each approved gloss → English here]

Update language/prompts/gloss_to_english.md so its examples match these exactly, and remove any example the reviewer rejected. Update LIVE_CASES in tests/test_claude_translator.py to cover each approved gloss. Run `uv run pytest --live tests/test_claude_translator.py tests/contracts -s` until every case passes in under 2 s. Check that docs/asl-demo-script-research.md (Moment 3), the demo script in MVP.md and the app's demo phrases still match. List for Sacchin any sign he needs to re-record, and for Julian any Demo Mode phrase to change. Commit, push and open a PR.
```

## Handoff to Person C (Julian)

Julian owns `ui/`, `captions/`, `outputs/turn_taking.py` and `fixtures/captions_sample.txt`. These are everything the new script needs from him. Items 1–4 can start now from the protocol below. Items 5–8 need the real call.

1. **The ticket card (Swift).**
   - **Where:** in Preview's call panel and in Demo Mode, big enough to read on the projector. It must not take focus from Meet.
   - **Its states, from the `ticket` event:**
     - `drafting`: "Claude is drafting a ticket from this call…"
     - `draft`: the summary as the title, then assignee (or "Unassigned"), due date, labels, the 2–3 sentence description, a small "From this call" line built from `reasons`, and the remembered words as chips (Pranav, Figma, with their tags on hover). Then "Sign YES to create", plus two buttons: Approve & Create and Dismiss.
     - `creating`: a spinner.
     - `created`: the key, large (SB-12), plus an "Open in Jira" button that opens `url` in the browser.
     - `failed`: the error, plus a Retry button that sends approve again.
     - `dismissed`: hide it.
   - When `mock` is true, show a small "mock Jira" badge.
2. **The protocol (EngineClient.swift).**
   - Decode the event `{"type": "ticket", "state": ..., "draft": {"summary", "description", "assignee", "due", "labels", "people", "reasons", "words": [{"term", "tags"}]}, "key", "url", "error", "mock", "draft_ms"}`, and the same object (or null) in `status.ticket`.
   - Buttons send `{"cmd": "ticket", "action": "approve"}` or `{"cmd": "ticket", "action": "dismiss"}`.
   - Person B writes the engine side in `ui/server.py`. Review that diff in PR #2.
3. **Demo Mode backup keys (Theme.swift, DemoScript.phrases).**
   - Replace the phrases with the new script: `["WAIT,", "#FIGMA,", "COLOR", "PROBLEM"]`, `["ME", "MEET", "#PRANAV,", "TOMORROW"]`, `["THANK-YOU"]`.
   - Add key 4, which sends `{"cmd": "ticket", "action": "draft"}` in case the automatic draft doesn't come.
   - The confirm key already approves a waiting draft (Person B adds that to `gesture()`).
4. **Review Person B's edits to your files** in PR #2. `fixtures/captions_sample.txt` becomes the new script's lines (B, then A twice, then the wrap-up), with the name set to Sacchin. `ui/server.py` gains the ticket protocol and the confirm/cancel handling for a waiting draft.
5. **Turn-taking for step 2.** B talks for about 15 s while Sacchin signs, and the script says the voice waits for B to stop. At `meet.chime_in_seconds: 8`, the app would say "Sorry, can I jump in?" partway through. Either raise it above B's line (about 20 s) for the demo, or keep it and change the script's step 2 to match. Decide in rehearsal.
6. **Mention banner.** Set Sacchin's name in Settings > Calls on the demo laptop. Check that A's "Sacchin, can you sort it out with Pranav?" raises the banner over fullscreen Meet. Captions already get "Sacchin", "Pranav" and "Figma" as Ink keyterms once they're remembered.
7. **Showing the ticket.** Plan the projector layout so judges see the card, then Jira after "Open in Jira". For example, Demo Mode with the card on the projector, and the browser opening on the same screen. The other laptop only needs Meet.
8. **Packaged app.** If the demo runs from `make app`, the five `JIRA_*` values go into `~/Library/Application Support/calhacks-2026/.env` with the other keys.

## Handoff to Person A (Sacchin)

- **New signs.** Add WAIT, COLOR, PROBLEM, ME and TOMORROW to `recognition.asl_citizen_signs` (THANKYOU is already there), after checking each one is in the ASL Citizen vocabulary. Tune them with the rest. Learn each from the source videos or a Deaf signer, never by guessing.
- **Recording script.** Update `SCRIPT` in `tools/record_script.py` to the new phrases: `WAIT, ~fi YES COLOR PROBLEM`, `ME MEET ~pr YES TOMORROW`, `THANK-YOU`. Then record and tune.
- **Letters are unchanged:** F-I and P-R, `letter_set: PRFI`.
- **The Deaf review needs the new glosses**, along with the old ones.

## The team, before the rehearsal

- **Go or no-go:** decide whether the Jira demo goes in after the freeze. If not, `tickets.enabled` stays false and the Pranav greeting is the demo.
- **Jira:** a project (for example key SB), an Atlassian API token for the account that creates issues, and Sacchin's Jira account ID for `JIRA_ASSIGNEE_ACCOUNT_ID`.
- **Who plays what:** who plays A and B on the other laptop, and who presents.

## Sources

- [inferedge-moss-core on PyPI](https://pypi.org/project/inferedge-moss-core/): wheel platforms
- [Cartesia keyterm prompting](https://docs.cartesia.ai/use-the-api/stt/keyterms)
- Jira Cloud REST API v3, `POST /rest/api/3/issue`, with an Atlassian Document Format description
- The claude-api skill reference: Opus 5.5 can't disable thinking, its effort defaults to medium, and it takes `fallbacks: "default"` under `server-side-fallback-2026-07-01`. Haiku 5.5 has no server-side fallback. `max_tokens: 0` pre-warms the cache.
