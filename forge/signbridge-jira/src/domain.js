// These helpers have no Forge imports so they can run under node:test.
export class BridgeError extends Error {
  constructor(status, code) {
    super(code);
    this.status = status;
    this.code = code;
  }
}

const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const text = (value, max, required = false) => typeof value === 'string'
  && Array.from(value).length <= max && (!required || value.trim().length > 0);
const invalid = () => { throw new BridgeError(400, 'invalid_fields'); };
const fields = ['summary', 'description', 'due', 'labels', 'blocks', 'assign_to_signer'];
const changedFields = [...fields, 'asked', 'people', 'ready', 'possible_duplicate', 'reasons'];
const approvalFields = ['call_id', 'approved_by', 'approved_via', 'approved_at', 'model', 'draft_version', 'reasons', 'versions'];
const known = (value, keys) => Object.keys(value).every(key => keys.includes(key));

export function validDate(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const date = new Date(`${value}T00:00:00.000Z`);
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value;
}

export function validateAudit(audit) {
  if (!object(audit) || !known(audit, approvalFields)
      || !text(audit.call_id, 80, true) || !/^[a-zA-Z0-9._-]+$/.test(audit.call_id)
      || !text(audit.approved_by, 200, true) || !text(audit.approved_via, 80, true)
      || !['signed YES', 'button', 'key'].includes(audit.approved_via)
      || !text(audit.model, 100, true) || !Number.isInteger(audit.draft_version)
      || audit.draft_version < 1 || audit.draft_version > 1000
      || !text(audit.approved_at, 40, true)
      || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)$/.test(audit.approved_at)
      || !validDate(audit.approved_at.slice(0, 10))
      || !Number.isFinite(Date.parse(audit.approved_at))
      || !Array.isArray(audit.reasons) || audit.reasons.length > 8
      || !audit.reasons.every(reason => text(reason, 240, true))
      || !Array.isArray(audit.versions) || audit.versions.length > 20) invalid();
  let previous = 0;
  for (const version of audit.versions) {
    if (!object(version) || !known(version, ['version', 'changed', 'at'])
        || !Number.isInteger(version.version) || version.version <= previous
        || version.version > audit.draft_version || !Array.isArray(version.changed)
        || version.changed.length > changedFields.length
        || !version.changed.every(field => changedFields.includes(field))
        || !text(version.at, 40, true) || !Number.isFinite(Date.parse(version.at))) invalid();
    previous = version.version;
  }
  // Reconstruct the record deliberately: never persist arbitrary nested caller data.
  return Object.fromEntries(approvalFields.map(key => [key, audit[key]]));
}

export function validatePayload(input, projectKey) {
  if (!object(input) || !['context', 'create'].includes(input.action)) invalid();
  if (input.action === 'context') {
    if (!text(input.summary, 255, true) || !known(input, ['action', 'summary', 'terms']) || (input.terms !== undefined
        && (!Array.isArray(input.terms) || input.terms.length > 12
        || !input.terms.every(term => text(term, 80, true))))) invalid();
    return { action: 'context', summary: input.summary, terms: input.terms ?? [] };
  }
  const ticket = input.ticket;
  if (!known(input, ['action', 'request_id', 'ticket', 'audit'])
      || !object(ticket) || !known(ticket, fields) || !text(ticket.summary, 255, true)
      || !text(input.request_id, 100, true) || !/^[a-zA-Z0-9._-]+$/.test(input.request_id)
      || (ticket.description !== undefined && !text(ticket.description, 2000))
      || !Array.isArray(ticket.labels) || ticket.labels.length > 3
      || !ticket.labels.every(label => typeof label === 'string' && /^[a-z0-9-]{1,40}$/.test(label))
      || (ticket.due !== undefined && !text(ticket.due, 10)) || (ticket.due && !validDate(ticket.due))
      || (ticket.blocks !== undefined && !text(ticket.blocks, 40))
      || (ticket.blocks && !new RegExp(`^${projectKey}-[1-9][0-9]*$`).test(ticket.blocks))
      || (ticket.assign_to_signer !== undefined && typeof ticket.assign_to_signer !== 'boolean')) invalid();
  return {
    action: 'create', request_id: input.request_id,
    ticket: { summary: ticket.summary, description: ticket.description ?? '', labels: [...new Set(ticket.labels)],
      due: ticket.due ?? '', blocks: ticket.blocks ?? '', assign_to_signer: ticket.assign_to_signer ?? false },
    audit: validateAudit(input.audit),
  };
}

// Quotes protect JQL grammar; text terms are separately reduced to literal words
// to avoid interpreting Lucene operators inside Jira's text-search expression.
export const jqlQuote = value => `"${String(value).replace(/[\r\n\t]/g, ' ').replace(/\\/g, '\\\\').replace(/"/g, '\\"')}"`;
const stopwords = new Set('a an and are as at be by for from in is it of on or that the this to with we our please'.split(' '));
export function searchTerms(summary, terms = []) {
  return [...new Set([summary, ...terms].flatMap(value => value.toLowerCase().match(/[\p{L}\p{N}]+/gu) ?? [])
    .filter(word => word.length > 1 && !stopwords.has(word)).map(word => word.slice(0, 40)))].slice(0, 8);
}

export function buildQueries(input, config) {
  const base = `project = ${jqlQuote(config.projectKey)} AND statusCategory != Done`;
  const terms = searchTerms(input.summary, input.terms);
  return {
    similar: terms.length ? `${base} AND (${terms.map(term => `text ~ ${jqlQuote(term)}`).join(' OR ')}) ORDER BY updated DESC` : null,
    release: `${base} AND labels = ${jqlQuote(config.releaseLabel)} ORDER BY updated DESC`,
  };
}

export function adf(paragraphs) {
  return { type: 'doc', version: 1, content: paragraphs.filter(Boolean).map(value => ({
    type: 'paragraph', content: [{ type: 'text', text: value }],
  })) };
}

export function descriptionAdf(description, audit) {
  const sentences = description.trim().match(/[^.!?]+(?:[.!?]+(?=\s|$)|$)/g) ?? [];
  return adf([...sentences.map(sentence => sentence.trim()),
    `Drafted by Claude during a SignBridge call and approved in the meeting by ${audit.approved_by} (${audit.approved_via}).`]);
}

export function commentAdf(audit) {
  return adf([`Created from a SignBridge meeting. Approved by ${audit.approved_by} with a ${audit.approved_via} during the call. Draft version ${audit.draft_version}.`]);
}

export function buildIssue(input, config) {
  const ticket = input.ticket;
  return { fields: {
    project: { key: config.projectKey }, summary: ticket.summary, issuetype: { name: 'Task' },
    description: descriptionAdf(ticket.description, input.audit),
    labels: [...new Set([...ticket.labels, 'signbridge'])],
    ...(ticket.due ? { duedate: ticket.due } : {}),
    ...(ticket.assign_to_signer && config.signerAccountId ? { assignee: { accountId: config.signerAccountId } } : {}),
  } };
}

export function retryFields(status, error, issueFields) {
  if (status !== 400 || !object(error?.errors)) return [];
  return ['duedate', 'labels', 'assignee'].filter(field => Object.hasOwn(issueFields, field)
    && typeof error.errors[field] === 'string'
    && /cannot be set|not on (?:the |an? )?(?:appropriate )?screen|not (?:available|allowed)|cannot be assigned|can.?t be assigned|not assignable/i.test(error.errors[field]));
}

export const issueUrl = (siteUrl, key) => `${siteUrl}/browse/${encodeURIComponent(key)}`;
