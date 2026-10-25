import { BridgeError, buildIssue, commentAdf, issueUrl, retryFields } from './domain.js';

// Forge and Jira cannot share one database transaction. Claim atomically, then
// retain that claim whenever Jira may already have accepted a create request.
// In particular, a lost network response must never cause a second POST /issue.
export async function runCreate(input, config, { store, jira, log = () => {}, now = () => new Date() }) {
  const ticket = input.ticket;
  const storageKey = `req:${input.request_id}`;
  function existing(record) {
    if (record.result) return record.result;
    throw new BridgeError(409, 'request_pending');
  }
  const prior = await store.get(storageKey);
  if (prior) return existing(prior);
  try {
    await store.set(storageKey, { state: 'pending', created_at: now().toISOString() }, { keyPolicy: 'FAIL_IF_EXISTS' });
  } catch {
    // A concurrent invocation may have won the claim. A storage outage fails
    // closed: this invocation cannot establish ownership and must not create.
    const winner = await store.get(storageKey);
    if (winner) return existing(winner);
    throw new BridgeError(503, 'storage_unavailable');
  }

  const warnings = [];
  if (ticket.assign_to_signer && !config.signerAccountId) warnings.push('signer_not_configured');
  const issue = buildIssue(input, config);
  let response;
  try { response = await jira.create(issue); } catch { throw new BridgeError(503, 'creation_outcome_unknown'); }
  if (response.status === 400) {
    let errors;
    try { errors = await response.json(); } catch { errors = {}; }
    const omit = retryFields(response.status, errors, issue.fields);
    if (omit.includes('labels') && ticket.labels.includes('signbridge-test')) {
      await store.delete(storageKey);
      throw new BridgeError(422, 'test_label_unavailable');
    }
    if (omit.length) {
      for (const field of omit) {
        delete issue.fields[field];
        warnings.push(`${field}_omitted`);
      }
      try { response = await jira.create(issue); } catch { throw new BridgeError(503, 'creation_outcome_unknown'); }
    }
  }
  if (!response.ok) {
    // A definitive rejection is safe to retry. 5xx/timeouts can follow a Jira
    // commit; preserve the pending claim for manual reconciliation in that case.
    if (response.status >= 400 && response.status < 500 && response.status !== 408) {
      await store.delete(storageKey);
      throw new BridgeError(502, 'jira_create_rejected');
    }
    throw new BridgeError(503, 'creation_outcome_unknown');
  }
  let created;
  try { created = await response.json(); } catch { throw new BridgeError(503, 'creation_outcome_unknown'); }
  if (typeof created.key !== 'string' || !new RegExp(`^${config.projectKey}-[1-9][0-9]*$`).test(created.key)) {
    throw new BridgeError(503, 'creation_outcome_unknown');
  }
  const result = { key: created.key, url: issueUrl(config.siteUrl, created.key), linked: null, audit_saved: false, warnings };
  // Checkpoint the key before optional work, so a storage failure later still
  // gives retries the existing issue. This is a conservative incomplete result.
  try {
    await store.set(storageKey, { state: 'created',
      result: { ...result, warnings: [...warnings, 'completion_incomplete'] } });
  } catch { log('checkpoint', 503, created.key); }

  if (ticket.blocks) {
    try {
      const targetResponse = await jira.getIssue(ticket.blocks);
      if (!targetResponse.ok) throw new Error('target_unavailable');
      const target = await targetResponse.json();
      if (target.fields.project.key !== config.projectKey || target.fields.status.statusCategory.key === 'done') {
        throw new Error('target_not_open');
      }
      // With the standard Blocks type, the source (new issue) is inwardIssue.
      // Verify the target's actual displayed relation after writing the link.
      const linked = await jira.link({ type: { name: 'Blocks' }, inwardIssue: { key: created.key }, outwardIssue: { key: ticket.blocks } });
      if (!linked.ok) throw new Error('link_failed');
      const checkResponse = await jira.getIssue(ticket.blocks);
      if (!checkResponse.ok) throw new Error('link_unverified');
      const check = await checkResponse.json();
      const verified = (check.fields.issuelinks ?? []).some(link => link.inwardIssue?.key === created.key
        && link.type.name === 'Blocks' && link.type.inward.toLowerCase() === 'is blocked by');
      result.linked = verified ? ticket.blocks : null;
      if (!verified) warnings.push('link_direction_unverified');
    } catch { warnings.push('link_failed'); }
  }
  try {
    const saved = await jira.audit(created.key, { ...input.audit, source: 'SignBridge', request_id: input.request_id, created_at: now().toISOString() });
    result.audit_saved = saved.ok;
    if (!saved.ok) warnings.push('audit_not_saved');
  } catch { warnings.push('audit_not_saved'); }
  try {
    const commented = await jira.comment(created.key, commentAdf(input.audit));
    if (!commented.ok) warnings.push('comment_not_saved');
  } catch { warnings.push('comment_not_saved'); }
  try { await store.set(storageKey, { state: 'complete', result }); }
  catch { warnings.push('idempotency_result_not_saved'); log('complete', 503, created.key); }
  return result;
}
