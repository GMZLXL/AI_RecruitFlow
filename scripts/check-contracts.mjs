import { readFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import openapiTS, { astToString } from 'openapi-typescript';

const contract = new URL('../contracts/openapi.yaml', import.meta.url);
const generated = new URL('../starter/frontend/src/types/api.generated.ts', import.meta.url);
const result = spawnSync(process.execPath, [fileURLToPath(new URL('./python.mjs', import.meta.url)), 'scripts/export_contract.py', '--check'], { stdio: 'inherit' });
if (result.status !== 0) process.exit(result.status ?? 1);
const types = astToString(await openapiTS(contract));
const current = readFileSync(generated, 'utf8');
// CLI prepends a standard generated-file banner; compare the actual declarations.
const declarations = (value) => value.slice(value.indexOf('export interface paths')).replaceAll('\r\n', '\n');
if (declarations(current) !== declarations(types)) {
  console.error('TypeScript contract drift. Run npm run contracts:generate.');
  process.exit(1);
}
console.log('OpenAPI and TypeScript contracts match the backend.');
