import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const SCRIPT_PATH = fileURLToPath(import.meta.url);
const DEFAULT_ROOT = path.resolve(path.dirname(SCRIPT_PATH), '..');

export const VISUALIZER_ASSET_RELATIVE_PATHS = Object.freeze([
  'crates/miho-core/assets/visualizer/hsr/index.html',
  'crates/miho-core/assets/visualizer/hsr/app.js',
  'crates/miho-core/assets/visualizer/hsr/styles.css',
  'crates/miho-core/assets/visualizer/zzz/index.html',
  'crates/miho-core/assets/visualizer/zzz/app.js',
  'crates/miho-core/assets/visualizer/zzz/styles.css',
  'crates/miho-core/assets/visualizer/solver.js',
]);

export const DEFAULT_BINARY_RELATIVE_PATHS = Object.freeze([
  'target/release/miho-desktop.exe',
  'target/release/miho.exe',
  'target/automation-no-window/release/miho.exe',
]);

const USAGE = `Usage:
  node scripts/verify_embedded_visualizer_bytes_v1.mjs [options]

Options:
  --root <path>     Workspace root containing the Visualizer sources.
                    Defaults to the parent directory of this script.
  --binary <path>   Binary to verify. Repeat to replace the three defaults.
                    Relative paths are resolved from --root.
  --help            Show this help.

The default binaries are:
${DEFAULT_BINARY_RELATIVE_PATHS.map((entry) => `  ${entry}`).join('\n')}`;

export function countBufferOccurrences(haystack, needle) {
  if (!Buffer.isBuffer(haystack) || !Buffer.isBuffer(needle)) {
    throw new TypeError('countBufferOccurrences expects Buffer arguments');
  }
  if (needle.length === 0) {
    throw new RangeError('cannot count occurrences of an empty Buffer');
  }

  let count = 0;
  let offset = 0;
  while (offset <= haystack.length - needle.length) {
    const foundAt = haystack.indexOf(needle, offset);
    if (foundAt === -1) break;
    count += 1;
    // Advance one byte so even overlapping duplicate occurrences are rejected.
    offset = foundAt + 1;
  }
  return count;
}

export function verifyEmbeddedVisualizerBytes(binaryBytes, assets, binaryLabel = '<binary>') {
  if (!Buffer.isBuffer(binaryBytes)) {
    throw new TypeError('binaryBytes must be a Buffer');
  }
  if (!Array.isArray(assets) || assets.length === 0) {
    throw new TypeError('assets must be a non-empty array');
  }

  const violations = [];
  const counts = new Map();
  for (const asset of assets) {
    if (typeof asset?.relativePath !== 'string' || !Buffer.isBuffer(asset?.bytes)) {
      throw new TypeError('each asset must contain relativePath and bytes');
    }
    if (asset.bytes.length === 0) {
      throw new Error(`Visualizer source is empty: ${asset.relativePath}`);
    }

    const count = countBufferOccurrences(binaryBytes, asset.bytes);
    counts.set(asset.relativePath, count);
    if (count !== 1) {
      violations.push(`${asset.relativePath}: expected exactly 1 raw-byte occurrence, found ${count}`);
    }
  }

  if (violations.length > 0) {
    throw new Error(
      `Embedded Visualizer byte verification failed for ${binaryLabel}:\n${violations
        .map((entry) => `  - ${entry}`)
        .join('\n')}`,
    );
  }

  return counts;
}

export function parseCliArguments(argv) {
  const result = {
    root: DEFAULT_ROOT,
    binaryPaths: [],
    help: false,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === '--help') {
      result.help = true;
      continue;
    }
    if (argument !== '--root' && argument !== '--binary') {
      throw new Error(`Unknown argument: ${argument}\n\n${USAGE}`);
    }
    const value = argv[index + 1];
    if (value === undefined || value.startsWith('--')) {
      throw new Error(`Missing value for ${argument}\n\n${USAGE}`);
    }
    index += 1;
    if (argument === '--root') {
      result.root = path.resolve(value);
    } else {
      result.binaryPaths.push(value);
    }
  }

  if (result.binaryPaths.length === 0) {
    result.binaryPaths = [...DEFAULT_BINARY_RELATIVE_PATHS];
  }
  return result;
}

export function verifyBinaries({ root, binaryPaths }) {
  const workspaceRoot = path.resolve(root);
  const assets = VISUALIZER_ASSET_RELATIVE_PATHS.map((relativePath) => {
    const sourcePath = path.resolve(workspaceRoot, relativePath);
    let bytes;
    try {
      bytes = fs.readFileSync(sourcePath);
    } catch (error) {
      throw new Error(`Cannot read Visualizer source ${sourcePath}: ${error.message}`, { cause: error });
    }
    return { relativePath, bytes };
  });

  const results = [];
  for (const binaryArgument of binaryPaths) {
    const binaryPath = path.isAbsolute(binaryArgument)
      ? path.normalize(binaryArgument)
      : path.resolve(workspaceRoot, binaryArgument);
    let binaryBytes;
    try {
      binaryBytes = fs.readFileSync(binaryPath);
    } catch (error) {
      throw new Error(`Cannot read release binary ${binaryPath}: ${error.message}`, { cause: error });
    }
    verifyEmbeddedVisualizerBytes(binaryBytes, assets, binaryPath);
    results.push(binaryPath);
  }
  return results;
}

function runCli() {
  const options = parseCliArguments(process.argv.slice(2));
  if (options.help) {
    process.stdout.write(`${USAGE}\n`);
    return;
  }

  const verified = verifyBinaries(options);
  for (const binaryPath of verified) {
    process.stdout.write(
      `Verified ${VISUALIZER_ASSET_RELATIVE_PATHS.length} Visualizer assets exactly once in ${binaryPath}\n`,
    );
  }
}

const invokedPath = process.argv[1] ? path.resolve(process.argv[1]) : null;
if (invokedPath === path.resolve(SCRIPT_PATH)) {
  try {
    runCli();
  } catch (error) {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 1;
  }
}
