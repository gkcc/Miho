import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

import {
  DEFAULT_BINARY_SPECS,
  DEFAULT_BINARY_RELATIVE_PATHS,
  PE_SUBSYSTEM_WINDOWS_CUI,
  PE_SUBSYSTEM_WINDOWS_GUI,
  VISUALIZER_ASSET_RELATIVE_PATHS,
  expectedPeSubsystemForBinaryPath,
  parseCliArguments,
  parsePeSubsystem,
  verifyBinaries,
  verifyEmbeddedVisualizerBytes,
  verifyPeSubsystem,
} from '../scripts/verify_embedded_visualizer_bytes_v1.mjs';

function syntheticAssets() {
  return VISUALIZER_ASSET_RELATIVE_PATHS.map((relativePath, index) => ({
    relativePath,
    bytes: Buffer.from(`visualizer-asset-${index}:<${relativePath}>`, 'utf8'),
  }));
}

function syntheticPe({
  subsystem = PE_SUBSYSTEM_WINDOWS_GUI,
  optionalMagic = 0x020b,
  peOffset = 0x80,
  optionalHeaderSize = optionalMagic === 0x010b ? 0xe0 : 0xf0,
} = {}) {
  const optionalHeaderOffset = peOffset + 4 + 20;
  const binary = Buffer.alloc(optionalHeaderOffset + optionalHeaderSize + 16, 0);
  binary.writeUInt16LE(0x5a4d, 0);
  binary.writeUInt32LE(peOffset, 0x3c);
  binary.writeUInt32LE(0x00004550, peOffset);
  binary.writeUInt16LE(optionalMagic === 0x010b ? 0x014c : 0x8664, peOffset + 4);
  binary.writeUInt16LE(1, peOffset + 6);
  binary.writeUInt16LE(optionalHeaderSize, peOffset + 4 + 16);
  binary.writeUInt16LE(optionalMagic, optionalHeaderOffset);
  binary.writeUInt16LE(subsystem, optionalHeaderOffset + 68);
  return binary;
}

function syntheticBinary(assets, peOptions) {
  const chunks = [syntheticPe(peOptions)];
  assets.forEach((asset, index) => {
    chunks.push(Buffer.from([0xff, index, 0x00]));
    chunks.push(asset.bytes);
    chunks.push(Buffer.from([0xfe, 0x00]));
  });
  return Buffer.concat(chunks);
}

test('accepts a synthetic binary containing all seven raw assets exactly once', () => {
  const assets = syntheticAssets();
  const binary = syntheticBinary(assets);
  const counts = verifyEmbeddedVisualizerBytes(binary, assets, 'synthetic.exe');

  assert.equal(assets.length, 7);
  assert.deepEqual([...counts.values()], Array(7).fill(1));
  assert.equal(
    verifyPeSubsystem(binary, PE_SUBSYSTEM_WINDOWS_GUI, 'synthetic.exe'),
    PE_SUBSYSTEM_WINDOWS_GUI,
  );
});

test('rejects a synthetic binary with a missing raw asset', () => {
  const assets = syntheticAssets();
  const binary = syntheticBinary(assets.slice(0, -1));

  assert.throws(
    () => verifyEmbeddedVisualizerBytes(binary, assets, 'missing.exe'),
    /solver\.js: expected exactly 1 raw-byte occurrence, found 0/,
  );
});

test('rejects a synthetic binary when one embedded asset byte changed', () => {
  const assets = syntheticAssets();
  const changedAssets = assets.map((asset, index) => {
    if (index !== 1) return asset;
    const changed = Buffer.from(asset.bytes);
    changed[Math.floor(changed.length / 2)] ^= 0x01;
    return { ...asset, bytes: changed };
  });

  assert.throws(
    () => verifyEmbeddedVisualizerBytes(syntheticBinary(changedAssets), assets, 'changed.exe'),
    /hsr\/app\.js: expected exactly 1 raw-byte occurrence, found 0/,
  );
});

test('rejects a synthetic binary containing a duplicate raw asset', () => {
  const assets = syntheticAssets();
  const binary = Buffer.concat([syntheticBinary(assets), assets[4].bytes]);

  assert.throws(
    () => verifyEmbeddedVisualizerBytes(binary, assets, 'duplicate.exe'),
    /zzz\/app\.js: expected exactly 1 raw-byte occurrence, found 2/,
  );
});

test('CLI defaults to all three release binaries and accepts repeated overrides', () => {
  assert.deepEqual(DEFAULT_BINARY_SPECS, [
    {
      relativePath: 'target/release/miho-desktop.exe',
      expectedSubsystem: PE_SUBSYSTEM_WINDOWS_GUI,
    },
    {
      relativePath: 'target/release/miho.exe',
      expectedSubsystem: PE_SUBSYSTEM_WINDOWS_CUI,
    },
    {
      relativePath: 'target/automation-no-window/release/miho.exe',
      expectedSubsystem: PE_SUBSYSTEM_WINDOWS_GUI,
    },
  ]);
  assert.deepEqual(parseCliArguments([]).binaryPaths, [...DEFAULT_BINARY_RELATIVE_PATHS]);
  assert.deepEqual(
    parseCliArguments(['--binary', 'first.exe', '--binary', 'second.exe']).binaryPaths,
    ['first.exe', 'second.exe'],
  );
  assert.throws(() => parseCliArguments(['--binary']), /Missing value for --binary/);
  assert.throws(() => parseCliArguments(['unexpected']), /Unknown argument: unexpected/);
});

test('parses PE32 and PE32+ subsystem fields and enforces exact GUI/CUI values', () => {
  const pe32Gui = syntheticPe({ optionalMagic: 0x010b, subsystem: PE_SUBSYSTEM_WINDOWS_GUI });
  const pe32PlusCui = syntheticPe({
    optionalMagic: 0x020b,
    subsystem: PE_SUBSYSTEM_WINDOWS_CUI,
  });

  assert.equal(parsePeSubsystem(pe32Gui, 'pe32-gui.exe'), PE_SUBSYSTEM_WINDOWS_GUI);
  assert.equal(parsePeSubsystem(pe32PlusCui, 'pe32plus-cui.exe'), PE_SUBSYSTEM_WINDOWS_CUI);
  assert.throws(
    () => verifyPeSubsystem(pe32PlusCui, PE_SUBSYSTEM_WINDOWS_GUI, 'wrong.exe'),
    /expected 2 \(WINDOWS_GUI\), found 3 \(WINDOWS_CUI\)/,
  );
  assert.throws(
    () => verifyPeSubsystem(pe32Gui, 99, 'unsupported.exe'),
    /unsupported expected PE subsystem: 99/,
  );
});

test('rejects truncated and malformed DOS, PE, and optional headers', async (context) => {
  const cases = [
    {
      name: 'truncated DOS header',
      binary: Buffer.alloc(0x3f),
      pattern: /DOS header is truncated/,
    },
    {
      name: 'bad DOS magic',
      binary: (() => {
        const binary = syntheticPe();
        binary.writeUInt16LE(0, 0);
        return binary;
      })(),
      pattern: /DOS magic is not MZ/,
    },
    {
      name: 'e_lfanew inside DOS header',
      binary: syntheticPe({ peOffset: 0x20 }),
      pattern: /e_lfanew points inside the DOS header/,
    },
    {
      name: 'e_lfanew beyond file',
      binary: (() => {
        const binary = syntheticPe();
        binary.writeUInt32LE(binary.length, 0x3c);
        return binary;
      })(),
      pattern: /e_lfanew points beyond the complete PE\/COFF header/,
    },
    {
      name: 'bad PE signature',
      binary: (() => {
        const binary = syntheticPe();
        binary.writeUInt32LE(0, 0x80);
        return binary;
      })(),
      pattern: /PE signature is not PE\\0\\0/,
    },
    {
      name: 'undersized optional header',
      binary: syntheticPe({ optionalHeaderSize: 69 }),
      pattern: /optional header is too small for Subsystem/,
    },
    {
      name: 'truncated optional header',
      binary: syntheticPe().subarray(0, 0x80 + 4 + 20 + 100),
      pattern: /optional header is truncated/,
    },
    {
      name: 'bad optional header magic',
      binary: syntheticPe({ optionalMagic: 0x0107 }),
      pattern: /optional header magic is neither PE32 nor PE32\+/,
    },
  ];

  for (const malformed of cases) {
    await context.test(malformed.name, () => {
      assert.throws(
        () => parsePeSubsystem(malformed.binary, `${malformed.name}.exe`),
        malformed.pattern,
      );
    });
  }
});

test(
  'default three-binary verification applies desktop GUI, CLI CUI, and automation GUI policy',
  (context) => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'miho-pe-subsystem-gate-'));
    context.after(() => fs.rmSync(root, { recursive: true, force: true }));
    const assets = syntheticAssets();
    for (const asset of assets) {
      const sourcePath = path.join(root, asset.relativePath);
      fs.mkdirSync(path.dirname(sourcePath), { recursive: true });
      fs.writeFileSync(sourcePath, asset.bytes);
    }
    for (const spec of DEFAULT_BINARY_SPECS) {
      const binaryPath = path.join(root, spec.relativePath);
      fs.mkdirSync(path.dirname(binaryPath), { recursive: true });
      fs.writeFileSync(binaryPath, syntheticBinary(assets, { subsystem: spec.expectedSubsystem }));
      assert.equal(
        expectedPeSubsystemForBinaryPath(root, binaryPath),
        spec.expectedSubsystem,
      );
    }

    assert.deepEqual(
      verifyBinaries({ root, binaryPaths: [...DEFAULT_BINARY_RELATIVE_PATHS] }),
      DEFAULT_BINARY_RELATIVE_PATHS.map((relativePath) => path.resolve(root, relativePath)),
    );

    for (const spec of DEFAULT_BINARY_SPECS) {
      const wrongSubsystem = spec.expectedSubsystem === PE_SUBSYSTEM_WINDOWS_GUI
        ? PE_SUBSYSTEM_WINDOWS_CUI
        : PE_SUBSYSTEM_WINDOWS_GUI;
      const binaryPath = path.join(root, spec.relativePath);
      fs.writeFileSync(binaryPath, syntheticBinary(assets, { subsystem: wrongSubsystem }));
      assert.throws(
        () => verifyBinaries({ root, binaryPaths: [...DEFAULT_BINARY_RELATIVE_PATHS] }),
        (error) => error instanceof Error
          && error.message.includes(`expected ${spec.expectedSubsystem}`)
          && error.message.includes(`found ${wrongSubsystem}`),
      );
      fs.writeFileSync(
        binaryPath,
        syntheticBinary(assets, { subsystem: spec.expectedSubsystem }),
      );
    }
  },
);
