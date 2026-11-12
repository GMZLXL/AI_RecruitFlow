import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../..', import.meta.url));
const docker = spawnSync('docker', ['compose', 'version'], { cwd: root, stdio: 'ignore', windowsHide: true });
const local = fileURLToPath(new URL(`../../.tools/bin/docker-compose${process.platform === 'win32' ? '.exe' : ''}`, import.meta.url));
const binary = docker.status === 0 ? 'docker' : existsSync(local) ? local : 'docker-compose';
const args = [...(binary === 'docker' ? ['compose'] : []), ...process.argv.slice(2)];
const result = spawnSync(binary, args.length ? args : ['config', '--quiet'], { cwd: root, stdio: 'inherit', windowsHide: true });
if (result.error) { process.stderr.write('Docker Compose is unavailable. Install the official Docker Compose CLI.\n'); process.exit(2); }
process.exit(result.status ?? 1);
