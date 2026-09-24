// Development-only Graphify entry point; never imported by the application.
import { createHash } from 'node:crypto';
import { execFileSync, spawnSync } from 'node:child_process';
import { readFileSync, writeFileSync, existsSync, rmSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';

process.chdir(fileURLToPath(new URL('../', import.meta.url)));
const python = resolve(process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python');
const graph = 'graphify-out/graph.json';
const stamp = 'graphify-out/cve-status.json';
const git = (...args) => execFileSync('git', args, { encoding: 'utf8' }).trim();
function snapshot() {
  // Include dirty and new source/config/docs, not only HEAD. Logs and local data
  // are excluded; hashing never exports file contents.
  const paths = git('ls-files', '-c', '-o', '--exclude-standard', '-z').split('\0')
    .filter(p => p && !/(^|\/)(app_log|report|test-results)\//.test(p)
      && !/(^|\/)\.env/.test(p) && !/\.(log|tsbuildinfo)$/.test(p));
  const hash = createHash('sha256');
  for (const p of [...new Set(paths)].sort()) {
    hash.update(p + '\0');
    hash.update(existsSync(p) ? readFileSync(p) : '<deleted>');
    hash.update('\0');
  }
  return { head: git('rev-parse', 'HEAD'), files: hash.digest('hex') };
}
function current() {
  try {
    const recorded = JSON.parse(readFileSync(stamp, 'utf8'));
    const now = snapshot();
    return recorded.head === now.head && recorded.files === now.files
      && recorded.graph === createHash('sha256').update(readFileSync(graph)).digest('hex');
  } catch { return false; }
}
function run(args) {
  if (!existsSync(python)) throw new Error('Graphify environment missing: see docs/REPOSITORY_INTELLIGENCE.md');
  const result = spawnSync(python, ['-m', 'graphify', ...args], {
    // Pre-setting the seed avoids Graphify's os.execvpe re-exec on Windows.
    stdio: 'inherit', env: { ...process.env, PYTHONUTF8: '1', PYTHONHASHSEED: '0' },
  });
  if (result.error) throw result.error;
  if (result.status !== 0) process.exit(result.status ?? 1);
}
const command = process.argv[2];
if (command === 'status') {
  const ok = current();
  console.log(ok ? 'GRAPH CURRENT' : 'GRAPH STALE — run npm run graph');
  process.exitCode = ok ? 0 : 1;
} else if (command === 'build') {
  const before = snapshot();
  rmSync(stamp, { force: true });
  // Force a complete local AST scan; never enable semantic extraction or upload.
  run(['extract', '.', '--code-only', '--force', '--max-workers', '2']);
  if (JSON.stringify(before) !== JSON.stringify(snapshot())) throw new Error('Repository changed during indexing; rerun.');
  const data = JSON.parse(readFileSync(graph, 'utf8'));
  if (!data.nodes?.length) throw new Error('Graphify produced an empty graph.');
  writeFileSync(stamp, JSON.stringify({ ...before,
    graph: createHash('sha256').update(readFileSync(graph)).digest('hex'),
    generatedAt: new Date().toISOString(),
  }, null, 2) + '\n');
  console.log('GRAPH CURRENT');
} else if (command === 'query') {
  if (!current()) { console.error('GRAPH STALE — run npm run graph before querying'); process.exit(1); }
  if (!process.argv[3]) throw new Error('Usage: npm run graph:query -- "question"');
  run(['query', process.argv.slice(3).join(' '), '--graph', graph]);
} else {
  throw new Error('Expected build, status, or query');
}
