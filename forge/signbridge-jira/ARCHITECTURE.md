# SignBridge architecture and implementation review

Reviewed on `person-b`, October 25, 2026. This review describes checked-in code;
recorded live results are distinguished from checks performed for the Forge app.

## Existing application

The product is a native macOS menu-bar app for Deaf ASL signers in Google Meet.
`ui/macos` is a SwiftUI front end. `EngineClient.swift` launches `app.py` and
exchanges newline-delimited JSON with `ui/server.py` over stdin/stdout. Engine
logs go to stderr. The Preview and Demo windows share the engine state.

`app.py` is the composition root. Its implementation registry loads components
selected by YAML; `config.yaml` defaults to mocks and `config.demo.yaml` selects
real providers. Load/start failures use mock or console fallbacks with UI notices.
`shared/bus.py` provides in-process asyncio pub/sub with one queue per subscriber.
`shared/events.py` defines signs, letters, translations, captions, suggestions,
approval requests, speech/turn state, and mention events.

| Component | Role and connections |
| --- | --- |
| MediaPipe (`recognition/`) | Local webcam hand, face and pose landmarks; signing-space gating; custom/ASL Citizen/Kaggle sign classifiers; ONNX letter model; temporal segmenter. Emits signs and letters. Face grammar is implemented but disabled pending review. Video remains local. |
| Moss (`language/vocab_search.py`) | A temporary in-memory session index rebuilt from local SQLite word occurrences. Scores remembered words against recent conversational context. `autocomplete.py` combines that score with letter prefix, handshape substitutions, frequency and recency, falling back when search is slow. No persistent index push. |
| Claude (`language/claude.py`, `tagger.py`) | Translates buffered ASL gloss into spoken English. Separately tags vocabulary from a word and a short context window. Tags, words and use metadata go to SQLite; captions/sentences are not persisted there. Configured model is `claude-haiku-5-5`; warm-up and prompt caching are implemented. No Jira drafting agent is wired in this branch. |
| Cartesia (`outputs/`, `captions/`) | Sonic streams the approved English voice into BlackHole 2ch, selected as Meet's mic. Ink transcribes the other side via a distinct BlackHole 16ch input and emits captions and turn boundaries. Turn-taking delays speech until a pause. Caption names/jargon feed vocabulary learning and mention alerts; remembered keyterms are sent when Ink connects. |
| Review and UI | `utterance.py` buffers signs/letters and calls the translator. `router.py` optionally requires YES before speech. Autocomplete consumes YES/NO independently, with the consumed-event identity check preventing double approval. UI commands drive the same engine paths. |
| Forge (`forge/signbridge-jira/`) | Separate JavaScript service on Atlassian. Receives signed context/create requests, searches Jira, creates an approved Task and release dependency, saves an audit property and comment, and displays the audit in a UI Kit issue panel. KVS stores idempotency state/results. Jira credentials stay inside Forge. |

The intended extension is: meeting context and a Claude draft on the Mac → explicit
meeting approval → signed bridge request → Forge → Jira. The Mac caller/drafting UI
is **not implemented by this change**. Moss, MediaPipe and Cartesia are upstream of
that seam; Forge calls none of them and does not call Claude. It records the model
and approval supplied by the authenticated meeting app. A signed request proves
possession of the shared key, not that a physical gesture occurred; the Mac must
enforce review before sending create.

## Dependencies

Python requires 3.11–3.12. `pyproject.toml` lists Anthropic, Cartesia with WebSockets,
Moss, NumPy, python-dotenv, PyYAML and sounddevice. The camera extra adds MediaPipe,
OpenCV, LiteRT and ONNX Runtime. Dev tooling is pytest, pytest-asyncio and Ruff.
`uv.lock` locks Python dependencies. Model weights live in gitignored `models/`;
ASL Citizen setup temporarily requires PyTorch/ONNX. macOS also needs Swift/Xcode
and BlackHole for the real call. The Moss native core has no Intel macOS wheel;
the supported demo target is Apple Silicon, and the ThinkPad can run Moss.

The Forge app uses `@forge/api`, `@forge/kvs`, `@forge/resolver`, `@forge/bridge`,
`@forge/react` and React 18 hooks. Native UI components come only from UI Kit.
The downloaded template sets `nodejs24.x`, 256 MB, ARM64; that runtime is preserved.
Tests use built-in `node:test`. `package-lock.json` pins the dependency graph.

## Status and remaining validation

The Python engine, SwiftUI views, provider implementations, mocks, contracts and
unit tests exist. `docs/person-b-numbers.md` records successful live ThinkPad Moss
ranking/latency checks, 16 Claude translation cases (p50 857 ms), tagger checks,
and provisional autocomplete timings (P-R p50 31.5 ms (measured with the earlier Priyanka name; current demo uses Pranav); F-I p50 29.4 ms). These are
previously recorded measurements, not rerun for this Forge task. The README and
HANDOFF still contain older “needs keys”/“known edge” statements; source code and
the dated measurements show those portions have advanced.

Real camera thresholds, recordings, demo-laptop timings, two-laptop Meet behavior,
and Deaf review still require the appropriate people/hardware. Existing Windows
limitations are recorded in the numbers file (macOS word list, a subprocess test
with a Unix-only environment, and unavailable audio/camera hardware).

The branch was fast-forwarded to the updated Person B spec before finalizing the bridge. Its contract uses nested ticket/audit objects, call IDs, timestamped version changes and a linked issue key or null. The Mac ticket agent remains Prompt 4 follow-up work. Deployment/site verification, panel inspection and test issue keys must be recorded from actual live checks.
