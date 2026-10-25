import { BridgeError } from './domain.js';

export function getConfig(env = process.env) {
  const projectKey = env.JIRA_PROJECT_KEY || 'SB';
  const releaseLabel = env.RELEASE_LABEL || 'release';
  let site;
  try { site = new URL(env.SITE_URL); } catch { throw new BridgeError(503, 'configuration_required'); }
  if (!/^[A-Z][A-Z0-9_]{1,19}$/.test(projectKey)
      || !/^[a-z0-9-]{1,40}$/.test(releaseLabel)
      || site.protocol !== 'https:' || !site.hostname.endsWith('.atlassian.net')
      || site.username || site.password || site.port || site.search || site.hash
      || site.pathname !== '/') throw new BridgeError(503, 'configuration_required');
  return { projectKey, releaseLabel, siteUrl: site.origin, signerAccountId: env.SIGNER_ACCOUNT_ID || '' };
}
