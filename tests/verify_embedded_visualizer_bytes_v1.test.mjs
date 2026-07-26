import assert from 'node:assert/strict';
import test from 'node:test';

import {
  DEFAULT_BINARY_RELATIVE_PATHS,
  VISUALIZER_ASSET_RELATIVE_PATHS,
  parseCliArguments,
  verifyEmbeddedVisualizerBytes,
} from '../scripts/verify_embedded_visualizer_bytes_v1.mjs';

function syntheticAssets() {
  return VISUALIZER_ASSET_RELATIVE_PATHS.map((relativePath, index) => ({
    relativePath,
    bytes: Buffer.from(`visualizer-asset-${index}:<${relativePath}>`, 'utf8'),
  }));
}

function syntheticBinary(assets) {
  const chunks = [Buffer.from([0x4d, 0x5a])];
  assets.forEach((asset, index) => {
    chunks.push(Buffer.from([0xff, index, 0x00]));
    chunks.push(asset.bytes);
    chunks.push(Buffer.from([0xfe, 0x00]));
  });
  return Buffer.concat(chunks);
}

test('accepts a synthetic binary containing all seven raw assets exactly once', () => {
  const assets = syntheticAssets();
  const counts = verifyEmbeddedVisualizerBytes(syntheticBinary(assets), assets, 'synthetic.exe');

  assert.equal(assets.length, 7);
  assert.deepEqual([...counts.values()], Array(7).fill(1));
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
  assert.deepEqual(parseCliArguments([]).binaryPaths, [...DEFAULT_BINARY_RELATIVE_PATHS]);
  assert.deepEqual(
    parseCliArguments(['--binary', 'first.exe', '--binary', 'second.exe']).binaryPaths,
    ['first.exe', 'second.exe'],
  );
  assert.throws(() => parseCliArguments(['--binary']), /Missing value for --binary/);
  assert.throws(() => parseCliArguments(['unexpected']), /Unknown argument: unexpected/);
});
