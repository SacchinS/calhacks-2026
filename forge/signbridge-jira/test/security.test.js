import test from 'node:test';
import assert from 'node:assert/strict';
import { createHmac } from 'node:crypto';
import { header, sign, verifySignature } from '../src/security.js';

const secret = 'unit-test-only-not-a-deployed-secret';
const now = 1792929600000;
function request(offset = 0) {
  const body = '{ "action": "context", "summary": "Dashboard" }';
  const timestamp = String(now / 1000 + offset);
  return { body, headers: { 'X-SignBridge-Timestamp': [timestamp], 'x-SIGNBRIDGE-signature': [sign(body, timestamp, secret)] } };
}
test('HMAC uses timestamp, dot, and the exact UTF-8 bytes', () => {
  assert.equal(sign('café', '123', secret), createHmac('sha256', secret).update('123.café').digest('hex'));
  assert.equal(verifySignature(request(), secret, now), true);
  assert.equal(header({ 'X-Test': ['first', 'second'] }, 'x-test'), 'first');
});
test('unsigned, missing-secret, malformed and tampered signatures fail closed', () => {
  assert.equal(verifySignature({ body: '{}', headers: {} }, secret, now), false);
  assert.equal(verifySignature(request(), '', now), false);
  for (const signature of ['', 'ab', 'z'.repeat(64), 'a'.repeat(65), null]) {
    const req = request(); req.headers['x-SIGNBRIDGE-signature'] = [signature];
    assert.equal(verifySignature(req, secret, now), false);
  }
  const req = request(); req.body += ' ';
  assert.equal(verifySignature(req, secret, now), false);
});
test('replay window accepts boundaries and rejects stale or future requests', () => {
  for (const offset of [-300, 300]) assert.equal(verifySignature(request(offset), secret, now), true);
  for (const offset of [-301, 301]) assert.equal(verifySignature(request(offset), secret, now), false);
});
test('headers must contain arrays and timestamp must be integer Unix seconds', () => {
  const req = request(); req.headers['X-SignBridge-Timestamp'] = String(now / 1000);
  assert.equal(verifySignature(req, secret, now), false);
  for (const timestamp of ['NaN', '1792929600.0', '1792929600000', '']) {
    const bad = request(); bad.headers['X-SignBridge-Timestamp'] = [timestamp];
    assert.equal(verifySignature(bad, secret, now), false);
  }
});
