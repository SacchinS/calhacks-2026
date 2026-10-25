import { handle } from './handler.js';
import { context } from './context.js';
import { create } from './create.js';
import { logStatus } from './jira.js';

export async function bridge(request) {
  return handle(request, { context, create, log: logStatus });
}
