import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';
import { spawnSync } from 'node:child_process';

const backend = fileURLToPath(new URL('../starter/backend/', import.meta.url));
const local = resolve(backend, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
const result = spawnSync(existsSync(local) ? local : 'python', process.argv.slice(2), {
  cwd: backend, stdio: 'inherit',
});
if (result.error) console.error(result.error.message);
process.exit(result.status ?? 1);
