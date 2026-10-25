import api, { route } from '@forge/api';

// Never log the request, error response body, exception message, or audit record.
// Jira error messages can repeat ticket text and account details.
export function logStatus(action, status, key) {
  const issueKey = typeof key === 'string' && /^[A-Z][A-Z0-9_]*-[1-9][0-9]*$/.test(key) ? key : undefined;
  console.log(JSON.stringify({ action, status, ...(issueKey ? { key: issueKey } : {}) }));
}

const json = { Accept: 'application/json', 'Content-Type': 'application/json' };
async function call(action, path, method = 'GET', body, key) {
  try {
    const response = await api.asApp().requestJira(path, {
      method, headers: json, ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    logStatus(action, response.status, key);
    return response;
  } catch {
    logStatus(action, 502, key);
    throw new Error('jira_transport_error');
  }
}

export const jira = {
  search: (jql, maxResults) => call('context', route`/rest/api/3/search/jql`, 'POST', {
    jql, maxResults, fields: ['summary', 'status'],
  }),
  create: body => call('create', route`/rest/api/3/issue`, 'POST', body),
  getIssue: key => call('read', route`/rest/api/3/issue/${key}?fields=project,status,issuelinks`, 'GET', undefined, key),
  link: body => call('link', route`/rest/api/3/issueLink`, 'POST', body, body.inwardIssue.key),
  audit: (key, body) => call('audit', route`/rest/api/3/issue/${key}/properties/signbridge.audit`, 'PUT', body, key),
  readAudit: key => call('getAudit', route`/rest/api/3/issue/${key}/properties/signbridge.audit`, 'GET', undefined, key),
  comment: (key, body) => call('comment', route`/rest/api/3/issue/${key}/comment`, 'POST', { body }, key),
};
