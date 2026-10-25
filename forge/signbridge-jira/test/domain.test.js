import test from 'node:test';
import assert from 'node:assert/strict';
import { validatePayload, buildQueries, searchTerms, jqlQuote, descriptionAdf, commentAdf, buildIssue, retryFields, validDate } from '../src/domain.js';
import { getConfig } from '../src/config.js';
import { input, config, audit } from './fixtures.js';

test('valid create and context payloads are normalized', () => {
  assert.deepEqual(validatePayload(input, 'SB'), input);
  assert.deepEqual(validatePayload({ action: 'context', summary: 'Dashboard' }, 'SB'), { action: 'context', summary: 'Dashboard', terms: [] });
});
test('summary accepts 255 Unicode characters and rejects 256 or whitespace', () => {
  assert.doesNotThrow(() => validatePayload({ ...input, ticket: { ...input.ticket, summary: '😀'.repeat(255) } }, 'SB'));
  for (const summary of ['x'.repeat(256), '', '   ', null, 3]) {
    assert.throws(() => validatePayload({ ...input, ticket: { ...input.ticket, summary } }, 'SB'), /invalid_fields/);
  }
});
test('field limits, date validity, project restriction, and booleans', () => {
  const bad = [
    { description: 'x'.repeat(2001) }, { labels: ['a', 'b', 'c', 'd'] }, { labels: ['UPPER'] },
    { labels: ['a'.repeat(41)] }, { labels: ['has space'] }, { labels: [2] }, { labels: null },
    { due: '2026-02-30' }, { due: '10/25/2026' }, { due: null },
    { blocks: 'OTHER-3' }, { blocks: 'SB-3 OR project=OTHER' }, { blocks: 'SB-0' },
    { assign_to_signer: 'true' }, { captions: 'never accepted' },
  ];
  for (const patch of bad) assert.throws(() => validatePayload({ ...input, ticket: { ...input.ticket, ...patch } }, 'SB'), /invalid_fields/);
  for (const patch of [{ request_id: '../oops' }, { request_id: 'x'.repeat(101) }, { captions: 'private' },
    { audit: { ...audit, transcript: 'private' } }]) {
    assert.throws(() => validatePayload({ ...input, ...patch }, 'SB'), /invalid_fields/);
  }
  assert.equal(validDate('2028-02-29'), true);
  assert.equal(validDate('2026-02-29'), false);
  assert.doesNotThrow(() => validatePayload({ ...input, ticket: { ...input.ticket, due: '', blocks: '', description: '' } }, 'SB'));
});
test('audit bounds and version shapes prevent arbitrary records', () => {
  for (const patch of [
    { draft_version: 0 }, { approved_at: 'yesterday' }, { approved_by: '' }, { model: '' },
    { reasons: ['x'.repeat(241)] }, { versions: [{ version: 3, changed: [], at: audit.approved_at }] },
    { versions: [{ version: 1, changed: ['caption'], at: audit.approved_at }] },
    { versions: [{ version: 2, changed: [], at: audit.approved_at }, { version: 1, changed: [], at: audit.approved_at }] },
    { call_id: '' }, { approved_via: 'unknown' },
  ]) assert.throws(() => validatePayload({ ...input, audit: { ...audit, ...patch } }, 'SB'), /invalid_fields/);
});
test('context terms are bounded before JQL generation', () => {
  for (const terms of [Array(13).fill('term'), ['x'.repeat(81)], 'term']) {
    assert.throws(() => validatePayload({ action: 'context', summary: 'Dashboard', terms }, 'SB'), /invalid_fields/);
  }
});
test('JQL escapes quotes and slashes, strips text operators, and caps terms', () => {
  assert.equal(jqlQuote('a"b\\c\n'), '"a\\"b\\\\c "');
  const words = searchTerms('The Dashboard " OR project = OTHER \\', ['filters + * ? ~', 'dashboard']);
  assert.deepEqual(words, ['dashboard', 'project', 'other', 'filters']);
  assert.equal(searchTerms('one two three four five six seven eight nine ten').length, 8);
  const queries = buildQueries({ summary: 'Dashboard filters', terms: ['release'] }, config);
  assert.match(queries.similar, /^project = "SB" AND statusCategory != Done AND \(/);
  assert.match(queries.release, /labels = "release"/);
  assert.equal(buildQueries({ summary: 'the and' }, config).similar, null);
});
test('description and comment use ADF text, one paragraph per sentence', () => {
  const doc = descriptionAdf('First sentence. Second sentence! Last?', audit);
  assert.equal(doc.type, 'doc'); assert.equal(doc.version, 1);
  assert.equal(doc.content.length, 4);
  assert.equal(doc.content[0].content[0].text, 'First sentence.');
  assert.match(doc.content[3].content[0].text, /approved in the meeting by Test signer \(signed YES\)/);
  assert.equal(descriptionAdf('', audit).content.length, 1);
  assert.match(commentAdf(audit).content[0].content[0].text, /Draft version 2\./);
  assert.equal(descriptionAdf('<script>text</script>', audit).content[0].content[0].type, 'text');
});
test('issue fields include conditional due and assignee with deduplicated app label', () => {
  assert.deepEqual(buildIssue(input, config).fields.assignee, { accountId: 'test-account' });
  const fields = buildIssue({ ...input, ticket: { ...input.ticket, due: '', assign_to_signer: false, labels: ['signbridge'] } }, config).fields;
  assert.equal('duedate' in fields, false); assert.equal('assignee' in fields, false);
  assert.deepEqual(fields.labels, ['signbridge']);
  assert.equal('assignee' in buildIssue(input, { ...config, signerAccountId: '' }).fields, false);
});
test('retry decision only drops named, eligible fields on a 400', () => {
  const fields = buildIssue(input, config).fields;
  assert.deepEqual(retryFields(400, { errors: { duedate: "Field 'duedate' cannot be set. It is not on the appropriate screen, or unknown." } }, fields), ['duedate']);
  assert.deepEqual(retryFields(400, { errors: { assignee: 'User cannot be assigned issues.' } }, fields), ['assignee']);
  assert.deepEqual(retryFields(400, { errors: { labels: 'Not on the screen' } }, fields), ['labels']);
  assert.deepEqual(retryFields(403, { errors: { assignee: 'cannot be assigned' } }, fields), []);
  assert.deepEqual(retryFields(400, { errors: { duedate: 'Invalid date format', summary: 'cannot be set' } }, fields), []);
  assert.deepEqual(retryFields(400, { errorMessages: ['summary includes assignee'] }, fields), []);
});
test('configuration rejects malformed projects and sites', () => {
  assert.equal(getConfig({ SITE_URL: config.siteUrl }).projectKey, 'SB');
  for (const patch of [{ SITE_URL: '' }, { SITE_URL: 'http://example.atlassian.net' },
    { SITE_URL: 'https://example.atlassian.net.evil.test' }, { JIRA_PROJECT_KEY: 'SB") OR project=OTHER' },
    { RELEASE_LABEL: 'release" OR true' }]) {
    assert.throws(() => getConfig({ SITE_URL: config.siteUrl, ...patch }), /configuration_required/);
  }
});
