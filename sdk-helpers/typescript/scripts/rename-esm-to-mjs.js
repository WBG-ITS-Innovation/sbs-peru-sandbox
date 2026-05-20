#!/usr/bin/env node
/**
 * Post-tsc ESM build step: renames index.js to index.mjs and writes a
 * package.json into dist/esm/ that declares the directory as ESM.
 * The .mjs extension is the more conservative ESM marker; the
 * package.json `"type": "module"` is the modern marker. Both together
 * give the broadest Node.js compatibility.
 */
const fs = require('node:fs');
const path = require('node:path');

const esmDir = path.join(__dirname, '..', 'dist', 'esm');
fs.mkdirSync(esmDir, { recursive: true });

// Write the package.json marker.
fs.writeFileSync(
  path.join(esmDir, 'package.json'),
  JSON.stringify({ type: 'module' }, null, 2) + '\n',
);

// Rename .js → .mjs for every emitted file.
function renameJsToMjs(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      renameJsToMjs(full);
    } else if (entry.isFile() && entry.name.endsWith('.js')) {
      const renamed = full.replace(/\.js$/, '.mjs');
      fs.renameSync(full, renamed);
      console.log(`renamed ${full} → ${renamed}`);
    }
  }
}
renameJsToMjs(esmDir);
