import { jira } from './jira.js';
import { BridgeError, buildQueries, issueUrl } from './domain.js';

export async function context(input, config) {
  const queries = buildQueries(input, config);
  async function search(jql, limit) {
    if (!jql) return [];
    const response = await jira.search(jql, limit);
    if (!response.ok) throw new BridgeError(502, 'jira_search_failed');
    const data = await response.json();
    return (data.issues ?? []).slice(0, limit).map(issue => ({
      key: issue.key, summary: issue.fields.summary,
      status: issue.fields.status.name, url: issueUrl(config.siteUrl, issue.key),
    }));
  }
  const [similar, release] = await Promise.all([search(queries.similar, 5), search(queries.release, 3)]);
  return { similar, release };
}
