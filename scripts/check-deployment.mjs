import { readFileSync } from 'node:fs';
const config = JSON.parse(readFileSync('wrangler.json', 'utf8'));
const id = config.d1_databases?.find(d => d.binding === 'DB')?.database_id;
if (!id || id === '00000000-0000-4000-8000-000000000000') {
  throw new Error('Create your Cloudflare D1 database and replace database_id in wrangler.json before deployment.');
}
console.log('Production database configuration is present.');
