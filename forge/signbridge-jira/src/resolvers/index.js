import Resolver from '@forge/resolver';
import { authorize } from '@forge/api';
import { jira, logStatus } from '../jira.js';
import { validateAudit } from '../domain.js';

const resolver = new Resolver();

resolver.define('getAudit', async ({ context }) => {
  // Only use the issue from Forge's resolver context, never a key supplied in
  // invoke payload. asApp reads require an explicit check of this user's access.
  const issue = context.extension?.issue;
  if (!issue?.id || !/^[A-Z][A-Z0-9_]*-[1-9][0-9]*$/.test(issue.key ?? '')) {
    throw new Error('issue_context_required');
  }
  try {
    // The issuePanel itself is available to users who can edit this issue.
    if (!await authorize().onJiraIssue(issue.id).canEdit()) throw new Error('forbidden');
    const response = await jira.readAudit(issue.key);
    if (response.status === 404) return { audit: null };
    if (!response.ok) throw new Error('audit_unavailable');
    const { value } = await response.json();
    const { call_id, approved_by, approved_via, approved_at, model, draft_version, reasons, versions } = value;
    return { audit: validateAudit({ call_id, approved_by, approved_via, approved_at, model, draft_version, reasons, versions }) };
  } catch {
    logStatus('getAudit', 503, issue.key);
    throw new Error('audit_unavailable');
  }
});

export const handler = resolver.getDefinitions();
