import { readFile } from 'node:fs/promises';
import { sign } from '../src/security.js';

// Usage: node scripts/send.mjs context|create payload.json [--unsigned]
// URLs and secrets are environment variables, never command arguments or logs.
const [action, file, flag] = process.argv.slice(2);
try {
  if (!['context', 'create'].includes(action) || !file || (flag && flag !== '--unsigned')) {
    throw new Error('usage');
  }
  const url = new URL(process.env.FORGE_TRIGGER_URL);
  if (url.protocol !== 'https:' || url.username || url.password) throw new Error('url');
  const payload = JSON.parse(await readFile(file, 'utf8'));
  if (payload.action !== action) throw new Error('action');
  // Manual checks in this repository are authorized only for labeled test issues.
  if (action === 'create' && !payload.ticket?.labels?.includes('signbridge-test')) throw new Error('test_label');
  const body = JSON.stringify(payload);
  const headers = { 'Content-Type': 'application/json' };
  if (flag !== '--unsigned') {
    if (!process.env.SIGNBRIDGE_SECRET) throw new Error('secret');
    const timestamp = String(Math.floor(Date.now() / 1000));
    headers['X-SignBridge-Timestamp'] = timestamp;
    headers['X-SignBridge-Signature'] = sign(body, timestamp, process.env.SIGNBRIDGE_SECRET);
  }
  const response = await fetch(url, { method: 'POST', headers, body, redirect: 'error' });
  const result = await response.json();
  // Context contains ticket text: report keys only. Never dump an HTTP body.
  const keys = [result.key, ...(result.similar ?? []).map(issue => issue.key),
    ...(result.release ?? []).map(issue => issue.key)]
    .filter(key => typeof key === 'string' && /^[A-Z][A-Z0-9_]*-[0-9]+$/.test(key));
  console.log(JSON.stringify({ action, status: response.status, keys }));
  if (!response.ok) process.exitCode = 1;
} catch {
  console.error(JSON.stringify({ action: ['context', 'create'].includes(action) ? action : 'request', status: 0 }));
  process.exitCode = 1;
}
