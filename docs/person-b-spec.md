# Person B (Eleyn): the remaining work, with the live Jira ticket demo

Prompts 1 and 2 are done; they're in PR #2. Three prompts are left:
- **Prompt 3** (ThinkPad) builds the live ticket agent and Jira. During the meeting, Claude drafts a tentative Jira ticket from what's being said and keeps it updated as the conversation goes on. The signer approves it with a signed YES while everyone is still in the call.
- **Prompt 4** (demo laptop) checks everything on the Mac, takes the final numbers and rehearses the script.
- **Prompt 5** follows the Deaf review.

Person C (Julian) builds the live ticket card; his list is in "Handoff to Person C". Person A (Sacchin) adds five signs.

Updated Oct 25, 2026, ~3:20 AM PDT, on `person-b` (PR #2). The feature freeze was ~3:00 AM, so the Jira demo is a team call. It ships off by default (`tickets.enabled: false`), with a mock Jira when the Jira keys are missing, and the current Pranav greeting stays as the backup demo. Devpost is due at 9:00 AM PT.

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

Sacchin signs. A and B are on the other laptop in the Meet call. Sacchin's name is set in Settings > Calls. The ticket card is on Sacchin's screen, which the projector shows, and it builds up while the conversation is still going.

**1. B gives an update** (0:05)
B: "Hi guys, I just wanted to go over some changes. The dashboard's ready. Pranav redesigned the charts in Figma last night, so I think we ship tomorrow."
The captions show it, and the app remembers Pranav and Figma.

**2. Sacchin raises a problem, and a tentative ticket appears** (0:20)
Sacchin signs WAIT, spells F-I, and signs YES to take Figma. Then he signs COLOR PROBLEM and FINISH.
The app waits for B to stop talking, then says: "Wait, there's a color problem in Figma." Claude may phrase it a little differently: it translates what was signed and adds nothing.
A few seconds later, a card marked **Tentative** appears: "Fix the color problem in the Figma design." The owner and due date are still empty, and it says "Listening…".

**3. A asks Sacchin to handle it** (0:50)
A: "Good catch. Sacchin, can you sort it out with Pranav?"
Sacchin's name banner flashes. The card updates: "Asked: Sacchin."

**4. Sacchin agrees, and the ticket fills in** (0:58)
Sacchin signs ME MEET, spells P-R, and signs YES to take Pranav. Then he signs TOMORROW and FINISH.
The app says: "I'll meet with Pranav tomorrow."
The card updates while the call goes on, with each change highlighted:
- Assignee: Sacchin
- Due: October 26, 2026
- The description now mentions meeting Pranav.
It now says "Sign YES to create".

**5. A holds the release, and the ticket picks it up** (1:25)
A: "Great, then we hold the release."
The card adds the label release-blocker, and the description now says the release is on hold until it's fixed.

Presenter: "Claude has been drafting this ticket live from the meeting, using the names Moss already knew: Pranav and Figma, spelled right. It's still tentative. Nothing goes to Jira until Sacchin approves it."

**6. Sacchin approves it in the meeting** (1:45)
Sacchin signs YES. The card shows the new ticket number, for example SB-12.
In the call, the app says: "I've added it to Jira as SB-12."

**7. The team sees it** (1:55)
A: "Got it, I see it on the board." The presenter clicks "Open in Jira", and the ticket is there with the right owner, due date and label.

**8. Wrap-up** (2:05)
A: "Anything else before we wrap up?"
Sacchin signs THANK-YOU, FINISH. The app says: "Thank you."

With 2:20 of live call, the 3-minute pitch becomes: problem 0:00–0:15, demo 0:15–2:35, one "how it works" slide 2:35–2:50, close 2:50–3:00.

## How the live ticket agent works

- **When it starts.** The agent arms when the signer speaks (step 2) or is named (step 3). From then on, for `tickets.armed_seconds` (default 120), it redrafts after each new final caption or spoken sentence. It waits `tickets.settle_seconds` (default 3) of quiet first, so it doesn't redraft mid-sentence. It keeps at most one Claude call in flight; anything said meanwhile goes into the next one.
- **What Claude sees:**
  - The call's notes from the start of the call: the other side's final captions and the signer's spoken sentences.
  - The current tentative draft.
  - Any draft the signer dismissed, so it isn't proposed again.
  - The remembered words that fit the call, with their tags, found by a Moss query over the session index. That's how "Pranav" and "Figma" come out spelled the signer's way.

  The notes are held in memory for this call only, never written to disk or the logs, and cleared when the app stops. **With ticket drafting on, the call's captions go to Claude while the call is happening.** That's new, and the README and Settings must say so.
- **What it returns.** Each time, Claude returns either the whole updated ticket or null (no task yet).
  - The ticket has a summary, description, due date, labels, people, whether it's the signer's task, and `ready`.
  - `ready` is true only once someone has asked the signer, and the signer has agreed or committed.
  - The app compares each version with the last and marks the changed fields, so the card can highlight them.
- **Moss isn't the meeting's memory.** The long-term memory is still the local SQLite word file. Moss is the search index rebuilt from it at each launch.
- **Model.** Claude Opus 5.5 at effort low, with structured JSON output and server-side refusal fallbacks (`tickets.model`). The card has to update within about 4 s of each turn.
  - If it's slower in rehearsal, switch to `claude-sonnet-5-5`. That keeps the fallbacks.
  - Or switch to `claude-haiku-5-5`. That means no `fallbacks` parameter (it 400s there) and thinking disabled.
- **Approval, during the meeting.** The issue is created only after a signed YES, the card's Approve & Create button, or the confirm key, and only while the card says "Sign YES to create" (`ready`).
  - A YES goes, in this order, to:
    1. a word being spelled,
    2. a sentence waiting for review,
    3. the ready ticket.

    All three are resolved in the router, so they can't race. A YES before the ticket is ready does nothing to it.
  - YES creates exactly the version on the card at that moment. Redrafting stops while it's being created.
  - A NO dismisses the ticket. Claude won't propose the same one again in this call.
- **Telling the room.** Once the issue is created, the app says one fixed sentence in the call: "I've added it to Jira as SB-12." It goes through the voice and turn-taking like any reply, so it waits for a pause. The card shows that sentence before YES, so the signer knows what will be said. It's on in the demo (`tickets.announce: true`).
- **The assignee** is the signer's own Jira account (`JIRA_ASSIGNEE_ACCOUNT_ID`), and only when the ticket is the signer's task. The agent never looks up or guesses anyone else. Pranav is named in the description only.

## Prompt 3: the live ticket agent and Jira (ThinkPad)

Done when: the new tests pass, and a mock run of the script shows a tentative ticket after step 2 that fills in at steps 3–5, becomes ready at step 4, and is created as a mock ticket on YES, with the announcement spoken. It's off by default, it's pushed to `person-b` (PR #2), and Julian has the protocol below.

Before pasting:
- Tell Julian you're adding the `ticket` protocol to `ui/server.py` and rewriting `fixtures/captions_sample.txt`. Tell the team you're changing a few lines of `app.py` and the demo sections of `MVP.md` and `HANDOFF.md`.
- Put `JIRA_BASE_URL` (for example `https://yourteam.atlassian.net`), `JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_PROJECT_KEY` and `JIRA_ASSIGNEE_ACCOUNT_ID` (Sacchin's Jira account ID) in `.env` yourself. Without them, it uses the mock Jira.

```text
I'm Person B (Eleyn): Language and autocomplete on our Cal Hacks 2026 team, on the Windows ThinkPad, branch person-b (PR #2 is open from it). Read HANDOFF.md, MVP.md, README.md and docs/person-b-spec.md first; the spec's "The demo script" and "How the live ticket agent works" are what this prompt builds. The key idea: during the meeting, Claude keeps a tentative Jira ticket up to date from the conversation, and the signer approves it in the meeting with a signed YES. Pull person-b first.

Rules: Windows, no make (uv run pytest -q, uv run ruff check ., uv run ruff format --check .). Some tests may fail here only because macOS's /usr/share/dict/words is missing; list them, don't change the heuristics. No stdout in engine code. Never log what anyone signs or says at INFO, and never log captions, notes or ticket text at all. Never commit .env, print keys or put them in a command line. I've told Julian and the team about these files, so you may edit: ui/server.py (protocol only, no Swift), fixtures/captions_sample.txt, app.py (wiring only), config.yaml (new disabled sections), config.demo.yaml, .env.example, MVP.md and HANDOFF.md (the demo sections). Don't touch shared/, Makefile or tests/contracts/. Use the claude-api skill before writing the Claude call, and verify the call shape against it and the installed anthropic SDK. Ask me before anything that needs a live call or creates a real Jira issue.

Build, in order, committing after each step:

1. Call notes, in memory only: language/tickets.py, class CallNotes. It subscribes to Caption (is_final only, speaker "them") and OutputSent (speaker "me"), and keeps (ts, speaker, text) in a deque (tickets.notes_max, default 400) from the start of the call. It's never written anywhere, it's cleared on app stop and on `{"cmd": "ticket", "action": "clear_notes"}`, and `text()` renders "them: ..." / "me: ..." lines.

2. Remembered words for the call. Add `async def related(self, text: str, top_k: int) -> dict[str, float]` to VocabSearch in language/vocab_search.py:
   - MossSearch: session.query with QueryOptions(top_k, alpha) and no filter.
   - KeywordSearch: the same overlap score it uses now, over all docs.
   - Base class: return {}.
   Then add `async def related_words(self, text, k=8) -> list[dict]` to Autocompleter: [{"term", "kind", "tags"}] from self.stats. Include every remembered word that appears literally in the text (case-insensitive) first, then the search's best matches, skipping common English (vocab_terms.is_common). If the search isn't ready or takes over 100 ms, fall back to the literal matches alone. Unit-test both searches and the fallback with the existing fakes.

3. The drafter: language/tickets.py, class TicketDrafter, `async def draft(notes_text, current, dismissed, words, today, signer) -> TicketDraft | None`.
   - `current` is the tentative ticket on the card, or None.
   - `dismissed` lists the summaries the signer said NO to.
   - It returns the whole updated ticket, or None when there's no task yet.
   The call:
   - Model: tickets.model, default "claude-opus-5-5", through anthropic.AsyncAnthropic(timeout=15, max_retries=1).
   - No `thinking` parameter: it can't be disabled on Opus 5.5.
   - output_config = {"effort": tickets.effort (default "low"), "format": {"type": "json_schema", "schema": SCHEMA}}.
   - max_tokens 4000.
   - For Opus and Sonnet 5.5 models only: client.beta.messages.create with betas=["server-side-fallback-2026-07-01"] and fallbacks="default". For a Haiku model, the plain messages.create, thinking={"type": "disabled"} and no fallbacks.
   - The system prompt is a constant with cache_control ephemeral, so the repeated calls during a meeting read it from cache.
   - Check stop_reason == "refusal" before reading content, and read only text blocks.
   SCHEMA: {"ticket": null or {"summary": str (an action, max 120 chars), "description": str (2-3 plain sentences), "asked": str (who was asked to do it, as said, or ""), "due": "YYYY-MM-DD" or "", "labels": [up to 3 lowercase-hyphenated], "people": [names from the notes, spelled as in the remembered words], "assign_to_signer": bool, "ready": bool, "reasons": [1-3 short phrases saying where it came from]}}.
   The system prompt says:
   - You're keeping one tentative work ticket up to date during a live meeting.
   - Propose a ticket as soon as a concrete problem or task comes up.
   - Update it as the conversation adds an owner, a date or a decision; keep the current ticket's wording unless something new changes it.
   - `ready` is true only when someone has asked the signer to do it and the signer has agreed or committed.
   - Never propose anything in `dismissed` again.
   - Never invent work, people or dates.
   - Resolve relative dates ("tomorrow", "by Friday") against `today`.
   - Spell names and tools exactly as in the remembered words.
   - No direct quotes of other people.
   - The signer is `signer`.
   The user message is JSON: {"today", "signer", "notes", "current_ticket", "dismissed", "remembered_words"}.
   Unit-test with a fake client:
   - the request shape for an Opus model and for a Haiku model (no fallbacks);
   - that only these fields are sent;
   - refusal → None plus a Notice;
   - null → None;
   - schema-valid JSON → a TicketDraft.
   Add tests/test_tickets_live.py (marked live): with Sacchin as the signer and today = 2026-10-25, it runs the drafter on the demo script's notes step by step, passing each result back as `current`, and asserts:
   - After step 2: a ticket about the color problem in Figma, with ready false and no due date.
   - After step 4: ready true, assign_to_signer true, due 2026-10-26, and "Pranav" in people.
   - After step 5: the release hold is in the description or the labels.
   - With the step-2 ticket in `dismissed`, the step-2 notes give null.
   It prints the time per draft.

4. The agent: class TicketAgent in language/tickets.py.
   - It subscribes to Mention, OutputSent and Caption.
   - The signer's first OutputSent, or a Mention, arms it for tickets.armed_seconds (default 120), renewed by each new turn.
   - While armed, each final caption or OutputSent schedules a redraft after tickets.settle_seconds (default 3) of no new final caption. At most one drafter call is in flight; if more was said meanwhile, run once more after it returns.
   - `{"cmd": "ticket", "action": "draft"}` redrafts now. It's the backup key.
   - States: none → tentative (each new version increments `version`, and `changed` lists the fields that differ from the last) → creating → created | failed. Dismissed returns to none, and the summary is remembered for `dismissed`.
   - Redrafting stops in creating and created. After created, the agent can propose a new, different ticket later in the call.
   - It publishes a TicketUpdate. If adding an event to shared/events.py is needed, ask me first; otherwise keep the dataclass in language/tickets.py and have ui/server.py subscribe to it.
   - `approve(version)` creates exactly that version, only if it's the version on the card, it's ready, and it's still tentative; it does so only once. `dismiss()` drops it.
   - After a successful create with tickets.announce on, the agent asks the router to say tickets.announce_text (default "I've added it to Jira as {key}.") through the normal voice and turn-taking. The card shows this text before approval (field `announce`).
   - Measure draft_ms per version for the numbers file.

5. Jira: a new file, outputs/jira.py.
   - JiraClient uses only the standard library (urllib.request in asyncio.to_thread; no new dependency).
   - It POSTs {JIRA_BASE_URL}/rest/api/3/issue with Basic auth (base64 of email:token) and fields: project.key = JIRA_PROJECT_KEY, summary, issuetype.name = jira.issue_type (default "Task"), description as an Atlassian Document Format doc (one paragraph per sentence, plus "Drafted by Claude during a SignBridge call and approved by the signer in the meeting."), duedate if set, and labels.
   - assignee.accountId = JIRA_ASSIGNEE_ACCOUNT_ID, only when assign_to_signer is true and the ID is set.
   - If Jira answers 400 naming duedate or labels (the field isn't on the create screen), retry once without that field and add a Notice saying so.
   - Return (key, f"{base}/browse/{key}").
   - Errors become a failed state with Jira's message, never the token. There's no announcement on failure.
   - MockJira (whenever a JIRA_* value is missing) returns MOCK-1, MOCK-2, and so on, and the card is told it's a mock.
   - Add the five JIRA_* names, with empty values, to .env.example.
   - Test with a fake opener: the URL, the auth header, the body, the assignee rules, the 400 retry, and that errors never contain the token. Add a live test that creates one real issue labeled signbridge-test and prints its key; it's skipped without the keys, and I'll run it myself.

6. YES and NO for the ticket, in outputs/router.py.
   - The Router gets an optional `tickets` attribute (the TicketAgent), set in app.py next to router.spelling.
   - In Router.handle, after spent_on_spelling:
     - If self.pending, confirm as now.
     - Elif the ticket is tentative and ready, YES approves the version on the card.
     - Elif the ticket is tentative, NO dismisses it, whether it's ready or not.
     - A YES on a ticket that isn't ready does nothing.
   - Add Router.announce(text) for the agent: it delivers to the voice like a normal (not urgent) quick reply, without a review step, because the YES was the approval.
   - In ui/server.py gesture(): "confirm" approves a ready ticket and "cancel" dismisses a tentative one when the state is idle (not confirming and no gloss).
   - Tests in tests/test_router_confirm.py:
     - YES while spelling never touches the ticket;
     - YES with a pending review approves the sentence and leaves the ticket;
     - YES on a ready ticket creates the shown version once;
     - YES on a ticket that isn't ready does nothing;
     - a second YES does nothing;
     - NO dismisses, and the same ticket isn't proposed again;
     - a version that arrives after the YES isn't the one created.

7. Protocol in ui/server.py, documented in its docstring; Julian builds the card from this:
   - Event {"type": "ticket", "state": "tentative|creating|created|failed|dismissed", "version": int, "ready": bool, "changed": [field names], "draft": {"summary", "description", "asked", "assignee" ("Sacchin" or ""), "due", "labels", "people", "reasons", "words": [{"term", "tags"}]}, "announce": str, "key", "url", "error", "mock": bool, "draft_ms"}.
   - The same object, or null, goes in status as "ticket".
   - Command {"cmd": "ticket", "action": "draft|approve|dismiss|clear_notes", "version": int (approve only)}.
   - Test the whole flow through the engine protocol with the mock captions, a fake drafter that returns the step-by-step versions, and MockJira: tentative v1 → v2 (asked) → v3 (ready) → v4 (label) → YES → created MOCK-1 → the announcement is sent to the voice.

8. Wiring and config.
   - app.py: always build CallNotes and TicketAgent, but they do nothing (no notes kept, nothing sent to Claude) unless `agent.enabled` is set, from tickets.enabled at startup.
   - ui/server.py: Settings can flip it at runtime, the same way `review_before_speaking` is applied from the UI config today. Turning it off clears the notes and drops any tentative ticket.
   - config.yaml: a `tickets:` section (enabled: false, model, effort, settle_seconds, armed_seconds, notes_max, announce: true, announce_text) and a `jira:` section (issue_type: Task), with comments in the file's style. The tickets comment says plainly that while it's on, the call's captions go to Claude during the call.
   - config.demo.yaml: tickets: {enabled: true}.

9. Demo content.
   - Rewrite fixtures/captions_sample.txt to the spec's script lines: B's update; A's "Good catch. Sacchin, can you sort it out with Pranav?"; "Great, then we hold the release."; "Got it, I see it on the board."; "Anything else before we wrap up?". Add header comments saying to set the name to Sacchin.
   - Check that tools/seed_vocab.py --bench still finds Pranav and Figma in it, and that the mention and autocomplete tests still pass.
   - Add the new glosses to language/prompts/gloss_to_english.md (drafts until the Deaf review): `WAIT fs-FIGMA COLOR PROBLEM` → "Wait, there's a color problem in Figma." and `ME MEET fs-PRANAV TOMORROW` → "I'll meet with Pranav tomorrow."
   - Add both glosses to LIVE_CASES with regexes that accept natural variants. Run the live translator tests.

10. Docs.
   - Replace "The demo" in MVP.md and "The demo, in short" in HANDOFF.md with the spec's script, and update the pitch timing line.
   - Add a "Live Jira tickets" paragraph to the README's "How we use Claude": Claude drafts a tentative ticket during the meeting from the call's notes (sent to Claude while the call is happening, held in memory, never stored) and the remembered words from Moss. Say what it can get wrong, and that nothing reaches Jira without the signer's YES in the meeting.
   - Update the README's "Privacy" section with the same fact.
   - Add the live draft times to docs/person-b-numbers.md (Windows, provisional).

11. Run the suite and lint, push person-b, and add a "Live Jira ticket agent" section to PR #2's description (gh pr edit 2 --body-file, keeping what's there). Then give me, in a few lines, what to tell Julian and Sacchin.
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
   - the ticket drafter's time per version, p50 and p95, over 5 step-by-step runs.
   If the bench shows the Moss query over autocomplete.search_timeout_ms (40 ms) often, raise it to about 80 ms and rerun. If a draft version takes over 4 s, try tickets.model: claude-sonnet-5-5 and compare.

3. Tune on real letters. Have me run `make seed-vocab`, then `make demo`. Delete any Priyanka left in Settings > Remembered words first. Then I spell P-R and F-I ten times each with the camera, with the demo captions playing. If Pranav or Figma isn't the top suggestion from the second letter, tune `autocomplete:` (weights, similar_handshapes, substitution_penalty, context_spread) and repeat. Keep the J-U test passing. Record letters saved per accepted word (Pranav: 6 letters, 2 spelled; Figma: 5, 2 spelled) and the accept rate.

4. Rehearse the spec's script with Julian and Sacchin in the real two-laptop call, three times, with tickets.enabled and the real Jira. Check each time:
   - the captions spell Pranav and Figma;
   - "Sacchin" raises the banner;
   - the step 2 sentence waits for B to stop;
   - the tentative card appears within about 4 s of the step 2 sentence and updates within about 4 s of each later turn;
   - the card says "Sign YES to create" only after step 4;
   - a stray YES before that does nothing;
   - YES creates exactly one issue, and the announcement is heard on the other laptop;
   - "Open in Jira" shows the ticket with the right summary, due date, label and assignee.
   Time the whole script. If it runs over 2:30, tell me which step to shorten. Delete the rehearsal issues in Jira afterwards; I'll do it, so list their keys.

5. README sections with the measured numbers, labeled with this machine (model and chip), short and factual:
   - "Autocomplete with Moss": suggestion latency p50/p95, Moss query p50/p95, 500-word startup, letters saved in the demo, and the keyterms. Update "Try it" for Pranav and Figma.
   - "How we use Claude": the translator, the tagger, the live ticket agent (model, time per update, what it sees, in-meeting approval), and "Where it can go wrong".
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

1. **The live ticket card (Swift).** It appears during the meeting and updates while people talk.
   - **Where:** in Preview's call panel and in Demo Mode, big enough to read on the projector. It must not take focus from Meet.
   - **Its states, from the `ticket` event:**
     - `tentative` while `ready` is false: a **Tentative** badge, the summary as the title, the other fields (blank ones shown as "—"), "Asked: …" when `asked` is set, and "Listening…". There's a Dismiss button but no Approve.
     - `tentative` once `ready` is true: the same card with "Sign YES to create". Show Approve & Create and Dismiss buttons, and the line "When it's created, I'll say: …" with the `announce` text.
     - **Every new `version`:** briefly highlight the fields named in `changed` (about 1.5 s), so the signer sees what Claude just added. Don't animate anything else.
     - `creating`: a spinner, with the fields frozen.
     - `created`: the key, large (SB-12), plus an "Open in Jira" button that opens `url` in the browser.
     - `failed`: the error, plus a Retry button that sends approve again with the same version.
     - `dismissed`: hide it.
   - Show the remembered words as chips (Pranav, Figma, with their tags on hover), and the `reasons` as a small "From this call" line.
   - When `mock` is true, show a small "mock Jira" badge.
2. **The protocol (EngineClient.swift).**
   - Decode the event `{"type": "ticket", "state": ..., "version", "ready", "changed": [...], "draft": {"summary", "description", "asked", "assignee", "due", "labels", "people", "reasons", "words": [{"term", "tags"}]}, "announce", "key", "url", "error", "mock", "draft_ms"}`, and the same object (or null) in `status.ticket`.
   - The Approve button sends `{"cmd": "ticket", "action": "approve", "version": <the version shown>}`. Dismiss sends `{"cmd": "ticket", "action": "dismiss"}`.
   - Person B writes the engine side in `ui/server.py`. Review that diff in PR #2.
3. **Demo Mode backup keys (Theme.swift, DemoScript.phrases).**
   - Replace the phrases with the new script: `["WAIT,", "#FIGMA,", "COLOR", "PROBLEM"]`, `["ME", "MEET", "#PRANAV,", "TOMORROW"]`, `["THANK-YOU"]`.
   - Add key 4, which sends `{"cmd": "ticket", "action": "draft"}` to redraft now if an update doesn't come.
   - The confirm key already approves a ready ticket (Person B adds that to `gesture()`).
4. **Review Person B's edits to your files** in PR #2. `fixtures/captions_sample.txt` becomes the new script's lines, with the name set to Sacchin. `ui/server.py` gains the ticket protocol and the confirm/cancel handling for the ticket.
5. **Turn-taking for step 2 and the announcement.**
   - B talks for about 15 s while Sacchin signs, and the script says the voice waits for B to stop. At `meet.chime_in_seconds: 8`, the app would say "Sorry, can I jump in?" partway through. Either raise it above B's line (about 20 s) for the demo, or keep it and change the script's step 2 to match. Decide in rehearsal.
   - Check that "I've added it to Jira as SB-12." also waits for a pause, and that the other laptop hears it.
6. **Mention banner.** Set Sacchin's name in Settings > Calls on the demo laptop. Check that A's "Sacchin, can you sort it out with Pranav?" raises the banner over fullscreen Meet, and that the banner doesn't cover the ticket card. Captions already get "Sacchin", "Pranav" and "Figma" as Ink keyterms once they're remembered.
7. **Showing the ticket.** Plan the projector layout so judges watch the card fill in during steps 2–5, then see Jira after "Open in Jira". For example, Demo Mode with the card beside the captions on the projector, and the browser opening on the same screen. The other laptop only needs Meet, plus the Jira board if A is going to say "I see it on the board".
8. **Settings and packaged app.**
   - Add a "Draft Jira tickets during calls" switch to Settings > Calls, for `tickets.enabled`. Under it, add one line: "While on, the call's captions go to Claude during the call. Nothing is stored, and nothing reaches Jira until you approve."
   - If the demo runs from `make app`, the five `JIRA_*` values go into `~/Library/Application Support/calhacks-2026/.env` with the other keys.

## Handoff to Person A (Sacchin)

- **New signs.** Add WAIT, COLOR, PROBLEM, ME and TOMORROW to `recognition.asl_citizen_signs` (THANKYOU is already there), after checking each one is in the ASL Citizen vocabulary. Tune them with the rest. Learn each from the source videos or a Deaf signer, never by guessing.
- **Recording script.** Update `SCRIPT` in `tools/record_script.py` to the new phrases: `WAIT, ~fi YES COLOR PROBLEM`, `ME MEET ~pr YES TOMORROW`, `YES` (approving the ticket), `THANK-YOU`. Then record and tune. The ticket YES is a held control sign like the others, so it must not fire from a passing handshape.
- **Letters are unchanged:** F-I and P-R, `letter_set: PRFI`.
- **The Deaf review needs the new glosses**, along with the old ones.

## The team, before the rehearsal

- **Go or no-go:** decide whether the live Jira demo goes in after the freeze. If not, `tickets.enabled` stays false and the Pranav greeting is the demo.
- **Jira:** a project (for example key SB), an Atlassian API token for the account that creates issues, and Sacchin's Jira account ID for `JIRA_ASSIGNEE_ACCOUNT_ID`.
- **Who plays what:** who plays A and B on the other laptop, and who presents.

## Sources

- [inferedge-moss-core on PyPI](https://pypi.org/project/inferedge-moss-core/): wheel platforms
- [Cartesia keyterm prompting](https://docs.cartesia.ai/use-the-api/stt/keyterms)
- Jira Cloud REST API v3, `POST /rest/api/3/issue`, with an Atlassian Document Format description
- The claude-api skill reference: Opus 5.5 can't disable thinking, its effort defaults to medium, and it takes `fallbacks: "default"` under `server-side-fallback-2026-07-01`. Haiku 5.5 has no server-side fallback. `max_tokens: 0` pre-warms the cache.
