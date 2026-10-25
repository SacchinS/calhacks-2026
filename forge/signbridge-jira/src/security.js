import { createHmac, timingSafeEqual } from 'node:crypto';

// Forge serializes header values as arrays. Header names remain case-insensitive.
export function header(headers, name) {
  const entry = Object.entries(headers ?? {}).find(([key]) => key.toLowerCase() === name.toLowerCase());
  return Array.isArray(entry?.[1]) ? entry[1][0] : undefined;
}

export function sign(body, timestamp, secret) {
  return createHmac('sha256', secret).update(`${timestamp}.${body}`).digest('hex');
}

export function verifySignature(request, secret, now = Date.now()) {
  const timestamp = header(request.headers, 'x-signbridge-timestamp');
  const signature = header(request.headers, 'x-signbridge-signature');
  if (!secret || typeof request.body !== 'string' || typeof timestamp !== 'string'
      || !/^\d{10}$/.test(timestamp) || typeof signature !== 'string'
      || !/^[a-fA-F0-9]{64}$/.test(signature)) return false;
  if (Math.abs(now / 1000 - Number(timestamp)) > 300) return false;
  const expected = Buffer.from(sign(request.body, timestamp, secret), 'hex');
  const actual = Buffer.from(signature, 'hex');
  return actual.length === expected.length && timingSafeEqual(actual, expected);
}
