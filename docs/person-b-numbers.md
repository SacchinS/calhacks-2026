# Person B: measured numbers

What the language and autocomplete parts actually do, measured rather than estimated. Every
number here is rerunnable with the commands given; nothing in this file is from a benchmark
score or a guess.

## Windows, provisional: the README uses the demo laptop's numbers

The pitch and the README quote the demo laptop (Apple Silicon). These are from the ThinkPad,
and they exist because Moss can't install on the team's Intel Mac: `inferedge-moss-core` has
never shipped an Intel Mac build, so this is the only machine that could run Moss at all
before the demo. Expect the Mac to be faster on the Moss numbers (its embedding model runs on
Apple Silicon) and about the same on the Claude ones, which are network-bound.

| | |
|---|---|
| Date | 2026-10-25 |
| Machine | Lenovo ThinkPad, Windows 11 Pro, AMD64 |
| CPU | 11th Gen Intel Core i7-1185G7 @ 3.00 GHz (4 cores, 8 threads) |
| Python | 3.11.17, `moss` 1.21.0, `inferedge-moss-core` 0.35.0, `anthropic` 2.1.0 |
| Models | Moss `moss-minilm` session index; Claude `claude-haiku-5-5` (thinking disabled, effort low) |

### Autocomplete with Moss

`uv run python tools/seed_vocab.py --bench 50` (the demo call: demo words plus Priyanka and
Figma learned from `fixtures/captions_sample.txt`, spelling P-R and F-I 50 times each).

| | P-R to Priyanka | F-I to Figma |
|---|---|---|
| Top suggestion correct | 50/50 rounds | 50/50 rounds |
| Letter to suggestion, p50 | 31.5 ms | 29.4 ms |
| Letter to suggestion, p95 | 52.6 ms | 44.1 ms |
| Moss query, p50 | 29.7 ms | 28.8 ms |
| Moss query, p95 | 39.1 ms | 38.0 ms |
| Startup build (20 words) | 1,469 ms | |

**The one thing worth fixing before the demo.** The Moss query came in over
`autocomplete.search_timeout_ms` (40 ms) on 19 of 50 rounds, so those rounds fell back to
ranking on letters, frequency and recency alone. The top suggestion was still right every
time, because for P-R and F-I the letters already decide it — but context is what makes the
J-U case work (Julian with tennis, Jupyter with data), so a timeout there would cost the
ranking the pitch describes. Query time tracks the length of the conversation text, not the
number of words remembered:

| Query text | Moss query |
|---|---|
| One short sentence (the live ranking test) | 10.5 to 19.5 ms |
| Four words (`--synthetic 500 --time`) | 10.4 ms |
| The demo call's whole 30-second window, 6 captions | 28.8 to 39.1 ms |

So on this machine 40 ms is too tight for a full `context_seconds: 30` window. Worth
re-measuring on the Mac first (step 3 of `docs/person-b-spec.md`); if it's close there too,
raise `autocomplete.search_timeout_ms` to about 80 ms, which still keeps a suggestion inside
one video frame.

Startup with 500 remembered words, `uv run python tools/seed_vocab.py --synthetic 500 --time`
with `CALHACKS_VOCAB_DB` pointed at a temp file:

| | |
|---|---|
| Moss session ready, 500 occurrences | 3,703 ms (tool), 6,922 to 7,265 ms (live test's 500) |
| One context query at 500 words | 10.4 ms |

Startup is a one-off at launch and runs in the background, so the app is usable before it
finishes; suggestions fall back to letters, frequency and recency until it's ready. The spread
between the two 500-word figures is the document text: the live test's words carry longer tags.

`uv run pytest --live tests/test_moss_search.py` — both live tests pass, first time they have
ever run against real keys (they were silently skipping; see the PR). J-U gives Julian in a
tennis conversation and Jupyter in a data one, letter to suggestion 10.7 to 19.8 ms.

### Gloss to English with Claude

`uv run pytest --live tests/test_claude_translator.py -s` — 16 cases, all passing, the prompt
unchanged.

| | |
|---|---|
| Per sentence, p50 | 857 ms |
| Per sentence, range | 667 ms to 1,523 ms |
| Over 2 s (the test's limit) | none |
| Prompt size | 1,271 tokens, of which 1,250 come from cache after warm-up |

First sentence of a call, measured on a prompt prefix nothing had cached yet:

| | |
|---|---|
| No warm-up | 1,180 ms (writes 1,278 prompt tokens to cache) |
| After `warm()` | 754 ms (reads 1,283 from cache) |
| `warm()` itself | 767 to 902 ms, at startup, nothing waits for it |

So warm-up takes about 425 ms off the signer's first sentence, which is the one the judges
see. It costs one cache write per launch and no output tokens.

### Topic tags for autocomplete

`uv run pytest --live tests/test_tagger_live.py -s` — 3 tests, passing on 3 consecutive runs. Claude
Haiku returns 3 to 5 lowercase tags of 1 to 3 words, with the kind and the written form. No
tag copied a sentence or named anyone else in the conversation. Examples:

| Word | Context | Tags |
|---|---|---|
| Priyanka | "Hi, I'm Priyanka, I'm designing the new app..." | app design, mockups, product design |
| Figma | the same | ui design, mockups, design tools, prototyping |
| Julian | "Julian and I played doubles again on Saturday..." | tennis, doubles, weekend games, sports partners |
| API | "The API is returning a 500 on the signup endpoint..." | software engineering, backend development, web services |

Figma's kind comes back as `name` about a third of the time and `term` otherwise. The prompt
counts a product name as a name, so both are right by its own definition, and nothing depends
on it: ranking never reads the kind. Left alone rather than over-fitted.

### Tests on this machine

`uv run pytest -q`: 170 passed, 2 failed, 32 skipped. Both failures are Windows-only and
neither is in the language or autocomplete code:

- `tests/test_autocomplete.py::test_words_heard_in_captions_are_learned_with_tags` —
  `language/vocab_terms.py` reads macOS's `/usr/share/dict/words`, which doesn't exist here,
  so every ordinary word looks like jargon and the mock tagger picks the wrong tags. The
  heuristics are untouched; the Mac run is the one that counts.
- `tests/test_ui_server.py::test_engine_process_speaks_the_protocol` — the test starts the
  engine with `env={"HOME": ..., "PATH": "/usr/bin:/bin"}`. With no `SYSTEMROOT`, Python on
  Windows can't load `_overlapped` and asyncio won't import (`WinError 10106`), so the
  subprocess dies at startup. Person C's file; it passes on macOS.

Two contract tests also fail for missing hardware, as expected on a ThinkPad:
`test_captions_contract[cartesia]` (no BlackHole 16ch) and `test_recognizer_contract[camera]`
(no `cv2`, since `--extra camera` isn't installed here).
