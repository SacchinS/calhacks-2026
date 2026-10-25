export const config = { projectKey: 'SB', releaseLabel: 'release', siteUrl: 'https://example.atlassian.net', signerAccountId: 'test-account' };
export const audit = {
  call_id: 'test-call',
  approved_by: 'Test signer', approved_via: 'signed YES', approved_at: '2026-10-25T12:00:00Z',
  model: 'claude-haiku-5-5', draft_version: 2, reasons: ['Unblocks the dashboard release.'],
  versions: [{ version: 1, changed: ['summary'], at: '2026-10-25T11:59:00Z' }, { version: 2, changed: ['due', 'blocks'], at: '2026-10-25T11:59:30Z' }],
};
export const input = {
  action: 'create', request_id: 'test-1',
  ticket: { summary: 'SignBridge test task', description: 'Check the filters. Confirm the release!',
    labels: ['signbridge-test'], due: '2026-10-30', blocks: 'SB-3', assign_to_signer: true }, audit,
};
export const reply = (status, value = {}) => ({ status, ok: status >= 200 && status < 300, json: async () => value });

export function memoryStore() {
  const records = new Map();
  return {
    records, get: async key => structuredClone(records.get(key)),
    set: async (key, value, options) => {
      if (options?.keyPolicy === 'FAIL_IF_EXISTS' && records.has(key)) throw new Error('key_exists');
      records.set(key, structuredClone(value));
    },
    delete: async key => { records.delete(key); },
  };
}

export function fakeJira() {
  const calls = [];
  const client = {};
  const methods = {
    create: () => reply(201, { key: 'SB-10' }),
    getIssue: () => reply(200, { fields: {
      project: { key: 'SB' }, status: { statusCategory: { key: 'new' } },
      issuelinks: [{ inwardIssue: { key: 'SB-10' }, type: { name: 'Blocks', inward: 'is blocked by' } }],
    } }),
    link: () => reply(201), audit: () => reply(204), comment: () => reply(201),
  };
  for (const [name, fn] of Object.entries(methods)) {
    client[name] = async (...args) => { calls.push([name, ...structuredClone(args)]); return fn(...args); };
  }
  return { client, calls };
}
