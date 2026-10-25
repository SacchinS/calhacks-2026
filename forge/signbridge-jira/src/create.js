import { kvs } from '@forge/kvs';
import { jira, logStatus } from './jira.js';
import { runCreate } from './workflow.js';

export async function create(input, config) {
  return runCreate(input, config, { store: kvs, jira, log: logStatus });
}
