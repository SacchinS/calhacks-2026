import React, { useEffect, useState } from 'react';
import ForgeReconciler, { Text, Heading, Stack, Lozenge, DynamicTable, useProductContext } from '@forge/react';
import { invoke } from '@forge/bridge';

const App = () => {
  const context = useProductContext();
  const issueKey = context?.extension?.issue?.key;
  const [data, setData] = useState(undefined);
  const [error, setError] = useState(false);
  useEffect(() => {
    if (!issueKey) return;
    let active = true;
    setData(undefined);
    setError(false);
    invoke('getAudit').then(value => { if (active) setData(value); })
      .catch(() => { if (active) setError(true); });
    return () => { active = false; };
  }, [issueKey]);
  if (error) return <Text>Couldn't load the meeting audit. Reopen this panel to retry.</Text>;
  if (data === undefined) return <Text>Loading meeting audit...</Text>;
  if (!data.audit) return <Text>This issue wasn't created from a SignBridge meeting.</Text>;
  const audit = data.audit;
  const approvedAt = new Date(audit.approved_at).toLocaleString(context?.locale, {
    ...(context?.timezone ? { timeZone: context.timezone } : {}),
    dateStyle: 'medium', timeStyle: 'short',
  });
  return (
    <Stack space="space.100">
      <Heading as="h3">SignBridge meeting</Heading>
      <Lozenge appearance="success">Approved in meeting</Lozenge>
      <Text>{`Approved by ${audit.approved_by} with a ${audit.approved_via}`}</Text>
      <Text>{approvedAt}</Text>
      <Text>{`Drafted live by Claude (${audit.model}) during the call: version ${audit.draft_version}`}</Text>
      {audit.reasons.length > 0 && <Heading as="h4">Reasons</Heading>}
      {audit.reasons.map((reason, index) => <Text key={index}>{`• ${reason}`}</Text>)}
      {audit.versions.length > 0 && <DynamicTable
        caption="Draft versions"
        head={{ cells: [{ key: 'version', content: 'Version' }, { key: 'fields', content: 'Changed fields' }] }}
        rows={audit.versions.map(version => ({ key: String(version.version), cells: [
          { key: 'version', content: String(version.version) },
          { key: 'fields', content: version.changed.join(', ') || 'Initial draft' },
        ] }))}
        rowsPerPage={5}
      />}
      <Text>Meeting captions are never sent to Jira.</Text>
    </Stack>
  );
};

ForgeReconciler.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
