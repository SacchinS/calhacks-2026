import test from 'node:test';
import assert from 'node:assert/strict';
import { handle } from '../src/handler.js';
import { sign } from '../src/security.js';
import { BridgeError } from '../src/domain.js';

const env = { SIGNBRIDGE_SECRET: 'test-only', SITE_URL: 'https://example.atlassian.net' };
function request(body = JSON.stringify({ action: 'context', summary: 'Dashboard' })) {
  const timestamp = String(Math.floor(Date.now() / 1000));
  return { method: 'POST', body, headers: { 'X-SignBridge-Timestamp': [timestamp],
    'X-SignBridge-Signature': [sign(body, timestamp, env.SIGNBRIDGE_SECRET)] } };
}
test('unsigned POST gets exact 401 body and never reaches Jira', async () => {
  const result = await handle({ method: 'POST', body: '{}', headers: {} }, { env });
  assert.equal(result.statusCode, 401); assert.deepEqual(JSON.parse(result.body), { error: 'unauthorized' });
  assert.deepEqual(result.headers, { 'Content-Type': ['application/json'] });
});
test('non-POST gets 405; signed malformed JSON gets 400', async () => {
  assert.equal((await handle({ method: 'GET' }, { env })).statusCode, 405);
  assert.equal((await handle(request('{'), { env })).statusCode, 400);
});
test('authenticated context routes with normalized fields', async () => {
  const result = await handle(request(), { env, context: async input => {
    assert.deepEqual(input.terms, []); return { similar: [], release: [] };
  } });
  assert.equal(result.statusCode, 200);
});
test('validation rejects unexpected caption payloads before action', async () => {
  const result = await handle(request(JSON.stringify({ action: 'context', summary: 'Dashboard', captions: 'private' })), { env });
  assert.equal(result.statusCode, 400);
});
test('service errors never expose ticket text, bodies, or audit', async () => {
  const logs = [];
  const result = await handle(request(), { env, context: async () => { throw new Error('private ticket content'); },
    log: (...args) => logs.push(args) });
  assert.equal(result.statusCode, 503);
  assert.equal(JSON.stringify([result, logs]).includes('private'), false);
});
test('pending create status is preserved', async () => {
  const result = await handle(request(), { env, context: async () => { throw new BridgeError(409, 'request_pending'); } });
  assert.equal(result.statusCode, 409);
});
