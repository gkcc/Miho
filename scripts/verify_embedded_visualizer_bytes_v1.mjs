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

export const PE_SUBSYSTEM_WINDOWS_GUI = 2;
export const PE_SUBSYSTEM_WINDOWS_CUI = 3;

export const DEFAULT_BINARY_SPECS = Object.freeze([
  Object.freeze({
    relativePath: 'target/release/miho-desktop.exe',
    expectedSubsystem: PE_SUBSYSTEM_WINDOWS_GUI,
  }),
  Object.freeze({
    relativePath: 'target/release/miho.exe',
    expectedSubsystem: PE_SUBSYSTEM_WINDOWS_CUI,
  }),
  Object.freeze({
    relativePath: 'target/automation-no-window/release/miho.exe',
    expectedSubsystem: PE_SUBSYSTEM_WINDOWS_GUI,
  }),
]);

export const DEFAULT_BINARY_RELATIVE_PATHS = Object.freeze(
  DEFAULT_BINARY_SPECS.map((spec) => spec.relativePath),
);

const USAGE = `Usage:
  node scripts/verify_embedded_visualizer_bytes_v1.mjs [options]

Options:
  --root <path>     Workspace root containing the Visualizer sources.
                    Defaults to the parent directory of this script.
  --binary <path>   Binary to verify. Repeat to replace the three defaults.
                    Relative paths are resolved from --root.
  --help            Show this help.

The default binaries are:
${DEFAULT_BINARY_SPECS.map(
    (spec) => `  ${spec.relativePath} (PE subsystem ${spec.expectedSubsystem}: ${peSubsystemName(spec.expectedSubsystem)})`,
  ).join('\n')}`;

function invalidPe(binaryLabel, detail) {
  return new Error(`Invalid PE image for ${binaryLabel}: ${detail}`);
}

export function peSubsystemName(subsystem) {
  if (subsystem === PE_SUBSYSTEM_WINDOWS_GUI) return 'WINDOWS_GUI';
  if (subsystem === PE_SUBSYSTEM_WINDOWS_CUI) return 'WINDOWS_CUI';
  return `UNKNOWN(${subsystem})`;
}

export function parsePeSubsystem(binaryBytes, binaryLabel = '<binary>') {
  if (!Buffer.isBuffer(binaryBytes)) {
    throw new TypeError('binaryBytes must be a Buffer');
  }
  // IMAGE_DOS_HEADER ends at byte 0x40 and stores e_lfanew at 0x3c.
  if (binaryBytes.length < 0x40) {
    throw invalidPe(binaryLabel, 'DOS header is truncated');
  }
  if (binaryBytes.readUInt16LE(0) !== 0x5a4d) {
    throw invalidPe(binaryLabel, 'DOS magic is not MZ');
  }

  const peOffset = binaryBytes.readUInt32LE(0x3c);
  if (peOffset < 0x40) {
    throw invalidPe(binaryLabel, `e_lfanew points inside the DOS header (${peOffset})`);
  }
  // The PE signature is followed by the fixed 20-byte COFF header.
  const optionalHeaderOffset = peOffset + 4 + 20;
  if (optionalHeaderOffset > binaryBytes.length) {
    throw invalidPe(binaryLabel, `e_lfanew points beyond the complete PE/COFF header (${peOffset})`);
  }
  if (binaryBytes.readUInt32LE(peOffset) !== 0x00004550) {
    throw invalidPe(binaryLabel, 'PE signature is not PE\\0\\0');
  }

  const optionalHeaderSize = binaryBytes.readUInt16LE(peOffset + 4 + 16);
  // Subsystem is a two-byte field at offset 68 in both PE32 and PE32+.
  const subsystemEnd = 68 + 2;
  if (optionalHeaderSize < subsystemEnd) {
    throw invalidPe(
      binaryLabel,
      `optional header is too small for Subsystem (${optionalHeaderSize} bytes)`,
    );
  }
  if (optionalHeaderOffset + optionalHeaderSize > binaryBytes.length) {
    throw invalidPe(binaryLabel, 'optional header is truncated');
  }

  const optionalMagic = binaryBytes.readUInt16LE(optionalHeaderOffset);
  if (optionalMagic !== 0x010b && optionalMagic !== 0x020b) {
    throw invalidPe(
      binaryLabel,
      `optional header magic is neither PE32 nor PE32+ (0x${optionalMagic.toString(16)})`,
    );
  }
  return binaryBytes.readUInt16LE(optionalHeaderOffset + 68);
}

export function verifyPeSubsystem(binaryBytes, expectedSubsystem, binaryLabel = '<binary>') {
  if (
    expectedSubsystem !== PE_SUBSYSTEM_WINDOWS_GUI
    && expectedSubsystem !== PE_SUBSYSTEM_WINDOWS_CUI
  ) {
    throw new RangeError(`unsupported expected PE subsystem: ${expectedSubsystem}`);
  }
  const actualSubsystem = parsePeSubsystem(binaryBytes, binaryLabel);
  if (actualSubsystem !== expectedSubsystem) {
    throw new Error(
      `PE subsystem verification failed for ${binaryLabel}: expected ${expectedSubsystem} `
      + `(${peSubsystemName(expectedSubsystem)}), found ${actualSubsystem} `
      + `(${peSubsystemName(actualSubsystem)})`,
    );
  }
  return actualSubsystem;
}

function normalizedPathIdentity(value) {
  const normalized = path.normalize(path.resolve(value));
  return process.platform === 'win32' ? normalized.toLowerCase() : normalized;
}

export function expectedPeSubsystemForBinaryPath(root, binaryPath) {
  const binaryIdentity = normalizedPathIdentity(binaryPath);
  const matched = DEFAULT_BINARY_SPECS.find(
    (spec) => normalizedPathIdentity(path.resolve(root, spec.relativePath)) === binaryIdentity,
  );
  return matched?.expectedSubsystem ?? null;
}

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
    const expectedSubsystem = expectedPeSubsystemForBinaryPath(workspaceRoot, binaryPath);
    if (expectedSubsystem === null) {
      // Custom --binary overrides still have to be well-formed PE images. The
      // exact GUI/CUI policy is defined only for the three default artifacts.
      parsePeSubsystem(binaryBytes, binaryPath);
    } else {
      verifyPeSubsystem(binaryBytes, expectedSubsystem, binaryPath);
    }
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
    const expectedSubsystem = expectedPeSubsystemForBinaryPath(options.root, binaryPath);
    const peSummary = expectedSubsystem === null
      ? 'a valid PE header'
      : `PE subsystem ${expectedSubsystem} (${peSubsystemName(expectedSubsystem)})`;
    process.stdout.write(
      `Verified ${VISUALIZER_ASSET_RELATIVE_PATHS.length} Visualizer assets exactly once and `
      + `${peSummary} in ${binaryPath}\n`,
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
