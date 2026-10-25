import test from 'node:test';
import assert from 'node:assert/strict';
import { runCreate } from '../src/workflow.js';
import { input, config, memoryStore, fakeJira, reply } from './fixtures.js';

function setup() {
  const { client: jira, calls } = fakeJira();
  const store = memoryStore();
  return { deps: { store, jira, now: () => new Date('2026-10-25T12:00:00Z') }, calls };
}
test('creates in order, verifies link direction, saves audit, comments, and returns stored result', async () => {
  const { deps, calls } = setup();
  const result = await runCreate(input, config, deps);
  assert.deepEqual(result, { key: 'SB-10', url: 'https://example.atlassian.net/browse/SB-10', linked: 'SB-3', audit_saved: true, warnings: [] });
  assert.deepEqual(calls.map(call => call[0]), ['create', 'getIssue', 'link', 'getIssue', 'audit', 'comment']);
  assert.deepEqual(calls.find(call => call[0] === 'link')[1], { type: { name: 'Blocks' }, inwardIssue: { key: 'SB-10' }, outwardIssue: { key: 'SB-3' } });
  const audit = calls.find(call => call[0] === 'audit')[2];
  assert.equal(audit.source, 'SignBridge'); assert.equal(audit.request_id, 'test-1');
  assert.equal(audit.created_at, '2026-10-25T12:00:00.000Z');
  assert.deepEqual(await runCreate(input, config, deps), result);
  assert.equal(calls.filter(call => call[0] === 'create').length, 1);
});
test('concurrent identical requests make exactly one Jira issue', async () => {
  const { deps, calls } = setup();
  const results = await Promise.allSettled([runCreate(input, config, deps), runCreate(input, config, deps)]);
  assert.equal(calls.filter(call => call[0] === 'create').length, 1);
  assert.equal(results.filter(result => result.status === 'fulfilled').length >= 1, true);
  for (const result of results) if (result.status === 'rejected') assert.equal(result.reason.code, 'request_pending');
});
test('the same completed request ID always returns its first result', async () => {
  const { deps } = setup();
  const first = await runCreate(input, config, deps);
  assert.deepEqual(await runCreate({ ...input, ticket: { ...input.ticket, summary: 'Changed' } }, config, deps), first);
});
test('pending marker is written before create and unknown outcomes remain claimed', async () => {
  const { deps } = setup();
  let creates = 0;
  deps.jira.create = async () => {
    creates++;
    assert.equal((await deps.store.get('req:test-1')).state, 'pending');
    throw new Error('lost response');
  };
  await assert.rejects(runCreate(input, config, deps), /creation_outcome_unknown/);
  await assert.rejects(runCreate(input, config, deps), /request_pending/);
  assert.equal(creates, 1);
});
test('a definitive create rejection clears the claim', async () => {
  const { deps } = setup(); deps.jira.create = async () => reply(400, { errors: { summary: 'invalid' } });
  await assert.rejects(runCreate(input, config, deps), /jira_create_rejected/);
  assert.equal(await deps.store.get('req:test-1'), undefined);
});
test('a 500 response keeps the pending claim', async () => {
  const { deps } = setup(); deps.jira.create = async () => reply(500);
  await assert.rejects(runCreate(input, config, deps), /creation_outcome_unknown/);
  assert.equal((await deps.store.get('req:test-1')).state, 'pending');
});
test('400 screen error retries once without that field and adds warning', async () => {
  const { deps } = setup(); const bodies = [];
  deps.jira.create = async body => {
    bodies.push(structuredClone(body));
    return bodies.length === 1 ? reply(400, { errors: { duedate: 'Field cannot be set' } }) : reply(201, { key: 'SB-10' });
  };
  const result = await runCreate(input, config, deps);
  assert.equal(bodies.length, 2); assert.equal('duedate' in bodies[0].fields, true);
  assert.equal('duedate' in bodies[1].fields, false); assert.deepEqual(result.warnings, ['duedate_omitted']);
});
test('does not make more than one screen-field retry', async () => {
  const { deps } = setup(); let creates = 0;
  deps.jira.create = async () => { creates++; return reply(400, { errors: { duedate: 'Field cannot be set' } }); };
  await assert.rejects(runCreate(input, config, deps), /jira_create_rejected/);
  assert.equal(creates, 2);
});
test('test creation never silently drops the required test label', async () => {
  const { deps } = setup(); let creates = 0;
  deps.jira.create = async () => { creates++; return reply(400, { errors: { labels: 'Field cannot be set' } }); };
  await assert.rejects(runCreate(input, config, deps), /test_label_unavailable/);
  assert.equal(creates, 1);
});
test('closed or foreign link targets are warnings, and do not prevent audit/comment', async () => {
  for (const fields of [{ project: { key: 'OTHER' }, status: { statusCategory: { key: 'new' } } },
    { project: { key: 'SB' }, status: { statusCategory: { key: 'done' } } }]) {
    const { deps, calls } = setup(); deps.jira.getIssue = async () => reply(200, { fields });
    const result = await runCreate(input, config, deps);
    assert.equal(result.linked, null); assert.deepEqual(result.warnings, ['link_failed']);
    assert.equal(calls.some(call => call[0] === 'link'), false); assert.equal(result.audit_saved, true);
  }
});
test('optional write failures are warnings and preserve idempotency', async () => {
  const { deps } = setup();
  deps.jira.link = async () => reply(403); deps.jira.audit = async () => reply(403);
  deps.jira.comment = async () => { throw new Error('network'); };
  const result = await runCreate(input, config, deps);
  assert.equal(result.audit_saved, false); assert.equal(result.linked, null);
  assert.deepEqual(result.warnings, ['link_failed', 'audit_not_saved', 'comment_not_saved']);
  assert.deepEqual(await runCreate(input, config, deps), result);
});
test('a reversed site link is not reported as verified', async () => {
  const { deps } = setup(); deps.jira.getIssue = async () => reply(200, { fields: {
    project: { key: 'SB' }, status: { statusCategory: { key: 'new' } },
    issuelinks: [{ outwardIssue: { key: 'SB-10' }, type: { name: 'Blocks', outward: 'blocks' } }],
  } });
  const result = await runCreate(input, config, deps);
  assert.equal(result.linked, null); assert.deepEqual(result.warnings, ['link_direction_unverified']);
});
test('storage outage before claim never creates', async () => {
  const { deps, calls } = setup(); deps.store.set = async () => { throw new Error('storage down'); };
  await assert.rejects(runCreate(input, config, deps), /storage_unavailable/);
  assert.equal(calls.length, 0);
});
test('failure saving final result leaves checkpoint with key, never creates again', async () => {
  const { deps, calls } = setup(); const set = deps.store.set;
  deps.store.set = async (key, value, options) => {
    if (value.state === 'complete') throw new Error('storage down');
    return set(key, value, options);
  };
  const result = await runCreate(input, config, deps);
  assert.ok(result.warnings.includes('idempotency_result_not_saved'));
  const retry = await runCreate(input, config, deps);
  assert.equal(retry.key, result.key); assert.ok(retry.warnings.includes('completion_incomplete'));
  assert.equal(calls.filter(call => call[0] === 'create').length, 1);
});
