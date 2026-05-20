#!/usr/bin/env node
/**
 * Post-tsc CJS build step: writes a package.json into dist/cjs/ that
 * declares the directory as CommonJS. Node's resolution algorithm
 * uses the nearest package.json `"type"` field to decide module
 * format; the top-level package.json sets the default for the package
 * as a whole, and a nested package.json overrides for a subtree.
 */
const fs = require('node:fs');
const path = require('node:path');

const target = path.join(__dirname, '..', 'dist', 'cjs', 'package.json');
fs.mkdirSync(path.dirname(target), { recursive: true });
fs.writeFileSync(target, JSON.stringify({ type: 'commonjs' }, null, 2) + '\n');
console.log(`wrote ${target}`);
