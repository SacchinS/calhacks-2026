# SignBridge Jira bridge

Forge app for the **Atlassian Agentic Workforce Challenge, Track 1: Agents that do the work**: turn a Claude-drafted,
human-approved meeting action into a Jira Task, optionally blocking a release.
The native **SignBridge meeting** issue panel shows approval, model, reasons and
version history. Forge does not run Claude or ingest meeting captions.

See the [architecture review](ARCHITECTURE.md) for the existing Mac/Python app,
dependencies and implementation status. No Python files are changed here.

## Bridge contract

Team specification: [docs/person-b-spec.md](../../docs/person-b-spec.md), "The bridge contract". Create sends nested `ticket` and `audit` objects. Audit includes `call_id`; history uses `versions[].{version, changed, at}`. `linked` is the target key or null. The shared secret is `FORGE_SHARED_SECRET` on the Mac and `SIGNBRIDGE_SECRET` in Forge.

Send POST JSON to the installation's `signbridge` web trigger with:

- `X-SignBridge-Timestamp`: integer Unix time in **seconds**.
- `X-SignBridge-Signature`: HMAC-SHA256 **hex** of the exact UTF-8 bytes of
  `timestamp + "." + body`, keyed with `SIGNBRIDGE_SECRET`.
- `Content-Type: application/json`.

Headers are read case-insensitively. The timestamp must be within 300 seconds of
Forge's clock, including future skew. Do not parse/reformat JSON after signing.
Web triggers are public; HMAC is checked by the handler before parsing the body.
Never put Jira tokens on the Mac. The shared bridge secret is needed on the Mac.

Context request (`examples/context.json`):

```json
{"action":"context","summary":"Dashboard filters","terms":["filters","dashboard"]}
```

Returns `{similar: [{key, summary, status, url}], release: [...]}` with at most five
similar and three release issues. Both searches stay in `JIRA_PROJECT_KEY` and
exclude Done status categories. The combined summary/terms query is capped at
eight distinct words (40 characters each); stopwords and Lucene operators are
removed and JQL strings are escaped. Up to 12 input terms, 80 characters each.
Only summary/status fields are requested, using enhanced `/rest/api/3/search/jql`.

Create request (`examples/create.json`, synthetic test data only):

```json
{
  "action": "create",
  "request_id": "test-1",
  "ticket": {
  "summary": "SignBridge test: verify dashboard filters",
  "description": "Verify the dashboard filters. Confirm the release dependency.",
  "due": "",
  "labels": ["signbridge-test"],
  "blocks": "SB-3",
  "assign_to_signer": false
  },
  "audit": {
    "call_id": "test-call",
    "approved_by": "Test signer",
    "approved_via": "signed YES",
    "approved_at": "2026-10-25T12:00:00Z",
    "model": "claude-haiku-5-5",
    "draft_version": 2,
    "reasons": ["Unblocks the dashboard release."],
    "versions": [
      {"version": 1, "changed": ["summary", "description"], "at": "2026-10-25T11:59:00Z"},
      {"version": 2, "changed": ["blocks"], "at": "2026-10-25T11:59:30Z"}
    ]
  }
}
```

Summary: nonempty, at most 255 Unicode characters. Description: at most 2,000.
Labels: at most three, each `[a-z0-9-]{1,40}`. Forge adds `signbridge`. `due` is
empty or a valid calendar date in YYYY-MM-DD. `blocks` is empty or a key in the
configured project; its open/project state is checked against Jira before linking.
`request_id` is 1–100 letters, digits, dots, underscores or hyphens. Approval time
must be an ISO UTC timestamp, draft version 1–1000, up to eight reasons
of 240 characters, and up to 20 increasing versions listing only changed field
**names** (summary, description, due, labels, blocks, assign_to_signer, asked, people, ready, possible_duplicate, reasons) and an ISO `at` timestamp. `approved_via` is signed YES/button/key; `call_id` is required (up to 80 identifier characters). The Mac uses `{call_id}-v{draft_version}` for request IDs; `test-1` is the requested manual test ID.

Unknown request/audit fields are rejected. Never send captions, transcripts,
sentence history, or raw model responses. Reasons must be concise draft rationale,
not quotations from a call. The app cannot detect captions disguised as a summary
or reason: the Mac caller must enforce this boundary and obtain human approval.

Returns `{key, url, linked, audit_saved, warnings}`, with `linked` equal to the target key or null. A completed request ID always returns the first stored result. In-progress requests return 409 `request_pending`. Status
401 is `{"error":"unauthorized"}`; 405 rejects other methods, 400 rejects invalid
JSON/fields, 502 reports definitive Jira failure, and 503 reports config/storage
or indeterminate creation failures. Bodies are JSON strings with array-valued
response headers, as required by Forge web trigger events.

The HMAC proves possession of the shared secret, not that a gesture happened.
Forge trusts approval metadata from the authenticated Mac; the Mac must keep
drafting separate from the explicit approval that permits creation.

## Idempotency and partial failures

KVS `req:<request_id>` is claimed with `keyPolicy: FAIL_IF_EXISTS`, before Jira is
called. It stores pending/created/complete state and the result. Concurrent
invocations cannot both create. Results contain no ticket description or audit.
Do not reuse IDs across separate actions/meetings; use UUIDs in the Mac caller.

One 400 retry omits only duedate/labels/assignee named in Jira's field-specific
screen/assignment error. All other fields are retained, with omission warnings.
**For `signbridge-test` requests, a labels-screen error aborts instead of creating
an unlabeled test issue**, respecting the team's live-check authorization.

Linking, audit and comment failures become warnings after creation. The release
issue is read back to verify that it shows **is blocked by** the new issue; an
unverified/reversed link is reported as a warning. No claim is made that this
site-specific check has run until the demo installation is tested.

A definitive create rejection clears the pending marker. A timeout, 5xx or lost
response retains it: Jira might have created the issue. **This intentionally
differs from clearing on every failure**, which would permit duplicates. A key
checkpoint is saved before optional work. A retry may return it with
`completion_incomplete` if completion/result persistence failed. If a pending
claim remains, inspect Jira and reconcile it before deleting KVS state; do not
use a fresh request ID to bypass an uncertain outcome. There is no automatic
expiration of idempotency state or guaranteed distributed exactly-once commit
across Jira and KVS.

The audit property is `signbridge.audit` with the accepted audit fields plus
`source: "SignBridge"`, `request_id`, and Forge's `created_at`. Issue properties
are visible to users/apps with Jira issue access and are editable; this is an
attribution display, not an immutable compliance log. Caption text is never put
in the property or the creation comment. App logs contain only action, status
and issue keys. Do not add raw exception/request/response logging.

## Install and deploy (development)

The downloaded UI Kit template uses **nodejs24.x**, 256 MB, ARM64. That Forge
runtime is retained as requested; local helpers/tests also run on Node 22.
Dependencies use ES modules and UI Kit (`render: native`). Scopes are the classic
`read:jira-work`, `write:jira-work`, and `storage:app`. The panel resolver checks
the current user's issue edit permission before its `asApp()` property read.

Run every Forge command below from this folder. This app is already registered
in the SignBridge Developer Space; `app.id` is public metadata, not a credential.

```powershell
Set-Location forge/signbridge-jira
npm ci
npm test
npm run lint
forge lint
forge deploy --environment development --non-interactive
forge install --environment development --product jira --site <demo-site>.atlassian.net --non-interactive
```

Set these variables in the **same environment**:

| Variable | Value |
| --- | --- |
| SIGNBRIDGE_SECRET | Shared random secret, encrypted; user enters it privately |
| JIRA_PROJECT_KEY | SB |
| SIGNER_ACCOUNT_ID | Sacchin's Jira account ID; optional unless assignment is requested |
| RELEASE_LABEL | release |
| SITE_URL | https://<demo-site>.atlassian.net (origin only) |

For the secret, run this interactively and enter the name and value when prompted;
do not paste it into chat, a tracked file, shell history or a logged command:

```powershell
forge variables set --encrypt --environment development
```

Then set the nonsensitive values and **redeploy** (variable changes take effect
only on the next deployment):

```powershell
forge variables set --environment development JIRA_PROJECT_KEY SB
forge variables set --environment development SIGNER_ACCOUNT_ID <account-id>
forge variables set --environment development RELEASE_LABEL release
forge variables set --environment development SITE_URL https://<demo-site>.atlassian.net
forge deploy --environment development --non-interactive
forge webtrigger create --environment development
```

Choose the demo installation and **signbridge** trigger. Put the resulting URL in
the **Mac's untracked `.env`** as `FORGE_TRIGGER_URL` and the same secret as
`FORGE_SHARED_SECRET`. The Python caller is not added in this prompt. Never deploy
production without asking the user first. Reinstall with `--upgrade` when scopes
change; ordinary code deployments do not need reinstallation.

## Manual checks and debugging

Set `FORGE_TRIGGER_URL` and `SIGNBRIDGE_SECRET` privately in the sender process's
environment. `send.mjs` never prints either or dumps response bodies/ticket text.
It rejects creates without `signbridge-test`. For a new test run, choose a new
request ID; reuse the same file/ID to check idempotency.

```powershell
node scripts/send.mjs context examples/context.json --unsigned
node scripts/send.mjs context examples/context.json
node scripts/send.mjs create examples/create.json
node scripts/send.mjs create examples/create.json
```

Expect unsigned POST → 401; context → SB-3 among release keys; first create → a
new test key; duplicate create → the same key. Inspect the created issue for the
ADF description, short creation comment and `signbridge.audit` property; on SB-3
verify **is blocked by <test key>**. Open **Apps → SignBridge meeting** on the issue
to inspect approval time, Claude version, reasons and history. Existing issues
without audit show the empty state. Issue panels require opening via the app
button/menu and users need edit access; they do not automatically open on creation.

Record the actual test keys for deletion. None are implied by unit-test fixtures.

While debugging an installed development app:

```powershell
$env:FORGE_USER_VAR_SIGNBRIDGE_SECRET = $env:SIGNBRIDGE_SECRET
$env:FORGE_USER_VAR_JIRA_PROJECT_KEY = 'SB'
$env:FORGE_USER_VAR_RELEASE_LABEL = 'release'
$env:FORGE_USER_VAR_SITE_URL = 'https://<demo-site>.atlassian.net'
# Also set FORGE_USER_VAR_SIGNER_ACCOUNT_ID privately if testing assignment.
forge tunnel --environment development
```

Tunnel variables need the `FORGE_USER_VAR_` prefix; deployed encrypted variables
are not automatically available locally. Manifest changes require redeployment
and tunnel restart; source-only changes hot reload. Be careful with CLI verbose
output; do not print or share payloads/audit records.

## Current references and differences from the task

Read before implementation, October 25, 2026:

- [Web trigger manifest](https://developer.atlassian.com/platform/forge/manifest-reference/modules/web-trigger/)
  and [events](https://developer.atlassian.com/platform/forge/events-reference/web-trigger/):
  `urlFormat: v2`, dynamic responses, public endpoint, header values are arrays.
- [requestJira/asApp/route](https://developer.atlassian.com/platform/forge/apis-reference/fetch-api-product.requestjira/):
  all backend Jira paths use `route` and the app identity.
- [Issue panel](https://developer.atlassian.com/platform/forge/manifest-reference/modules/jira-issue-panel/),
  [product context](https://developer.atlassian.com/platform/forge/ui-kit/hooks/use-product-context/),
  [resolvers](https://developer.atlassian.com/platform/forge/runtime-reference/forge-resolver/),
  [invoke](https://developer.atlassian.com/platform/forge/apis-reference/ui-api-bridge/invoke/),
  [authorization](https://developer.atlassian.com/platform/forge/runtime-reference/authorize-api/).
- [Permissions](https://developer.atlassian.com/platform/forge/manifest-reference/permissions/),
  [Jira scopes](https://developer.atlassian.com/platform/forge/manifest-reference/scopes-product-jira/),
  [encrypted variables/redeploy](https://developer.atlassian.com/platform/forge/cli-reference/variables-set/),
  [KVS and atomic claims](https://developer.atlassian.com/platform/forge/storage-reference/kvs-api/).
  KVS defaults to last-write-wins; the conditional claim is required for concurrency.
- Jira REST v3: [enhanced search](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-search/),
  [issues](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/),
  [links](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-links/),
  [link direction](https://developer.atlassian.com/cloud/jira/platform/issue-linking-model/),
  [properties](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-properties/),
  [comments](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-comments/).
  The large issues page was also checked through its linked official OpenAPI schema.

The template name is `jira-issue-panel-ui-kit`, rather than `jira-issue-panel`.
Its current runtime is Node 24 rather than the local Node 22 mentioned in the
request. The project Developer Space requires a shared app rather than a personal
app. The requested classic scopes, v2 dynamic trigger, UI Kit wiring and enhanced
search endpoint agree with current docs. The pending-marker safety exception and
test-label safeguard above are implementation decisions, not claims of a different
Forge API requirement.
