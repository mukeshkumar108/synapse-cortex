import 'dotenv/config';
import { Honcho } from '@honcho-ai/sdk';
const client = new Honcho({
  baseURL: process.env.HONCHO_URL!.trim(),
  workspaceId: process.env.HONCHO_WORKSPACE_ID!.trim() || 'llm-test-agent',
  apiKey: process.env.HONCHO_API_KEY?.trim() || undefined,
  timeout: 30000, maxRetries: 1,
});
const peerId = 'user_5377a025-b876-4d1f-bd62-59352da44146';
const peer = client.workspace.peer(peerId);
const Q = [
  'What goals has this user expressed?',
  'What habits or routines are important to them?',
  'What things has the user asked Sophie to help them follow through on?',
  'What recurring commitments or expectations does this user have?',
  'What has Sophie promised or agreed to help with?',
  'What unresolved plans, goals, or outcomes are currently important?',
  'What patterns or repeated difficulties has the user described?',
];
async function main() {
  for (const q of Q) {
    try {
      const a = await peer.chat(q);
      console.log('Q:', q);
      console.log('A:', String(a).slice(0, 700));
      console.log('---');
    } catch (e) {
      console.log('Q:', q, 'ERROR:', String(e).slice(0, 150));
    }
  }
}
main();
