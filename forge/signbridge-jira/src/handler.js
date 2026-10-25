import { BridgeError, validatePayload } from './domain.js';
import { verifySignature } from './security.js';
import { getConfig } from './config.js';

export const response = (statusCode, value) => ({
  statusCode, headers: { 'Content-Type': ['application/json'] }, body: JSON.stringify(value),
});

// Dependency injection keeps authentication and routing testable without Forge.
export async function handle(request, { env = process.env, context, create, log = () => {} }) {
  if (request.method !== 'POST') return response(405, { error: 'method_not_allowed' });
  if (!verifySignature(request, env.SIGNBRIDGE_SECRET)) return response(401, { error: 'unauthorized' });
  if (Buffer.byteLength(request.body, 'utf8') > 24000) return response(400, { error: 'request_too_large' });
  let raw;
  try { raw = JSON.parse(request.body); } catch { return response(400, { error: 'invalid_json' }); }
  let action = 'request';
  try {
    const config = getConfig(env);
    const input = validatePayload(raw, config.projectKey);
    action = input.action;
    const result = await (action === 'context' ? context : create)(input, config);
    log(action, 200, result.key);
    return response(200, result);
  } catch (error) {
    const status = error instanceof BridgeError ? error.status : 503;
    log(action, status);
    return response(status, { error: error instanceof BridgeError ? error.code : 'service_unavailable' });
  }
}
