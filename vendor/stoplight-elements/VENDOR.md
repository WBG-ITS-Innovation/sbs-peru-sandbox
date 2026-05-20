# Vendored Stoplight Elements

This directory holds the Stoplight Elements assets that the developer
portal renders. The assets are vendored locally (committed to the
repository) per [ADR 0037](../../docs/adr/0037-developer-portal-serving-mechanism.md):
no CDN dependency at portal-render time.

Re-vendoring procedure lives in [docs/CONTRIBUTING.md](../../docs/CONTRIBUTING.md);
do not modify these files in-place without updating that procedure and
the `VENDOR_ASSET_ALLOWLIST` constant in
[api/sbs_api/routes/portal.py](../../api/sbs_api/routes/portal.py).

## Provenance

| Field | Value |
| --- | --- |
| Upstream package | `@stoplight/elements` |
| Upstream version | `9.0.19` |
| Fetched from | `https://unpkg.com/@stoplight/elements@9.0.19/<file>` |
| Date fetched | 2026-05-20 |
| Fetched by | Prompt 9 workstream A |
| License | Apache-2.0 (see `LICENSE`) |

## Files and checksums

SHA-256 (verifies the bytes on disk match what was fetched):

| File | Size (bytes) | SHA-256 |
| --- | --- | --- |
| `web-components.min.js` | 2,077,254 | `5a4ed0326dd6df8bcc3821838d3c12be7e3e6e0ad7efb135c4b0cbff76d20b1e` |
| `styles.min.css` | 297,600 | `a52002228108fb567b75caff209c4d8aa256ae591de3dea7d3b1a384b1a27b06` |
| `LICENSE` | 10,760 | `d45c17f7ecc80e0deab3372ff352c7d00b7d573755c3c672088c21a376673698` |

SHA-384 (verifies bytes match the SRI hashes the previous CDN-loaded
dev portal pinned):

| File | SHA-384 (base64) |
| --- | --- |
| `web-components.min.js` | `L0FYPm8XLe2HHJT/qfQUJGqRqqq1rHxC8O1YooLjs+6CJ3O2TjlQEhbal3KJ8DBX` |
| `styles.min.css` | `iVQBHadsD+eV0M5+ubRCEVXrXEBj+BqcuwjUwPoVJc0Pb1fmrhYSAhL+BFProHdV` |

## Re-vendoring procedure

When Stoplight upstreams a new version (typically a security fix):

```bash
cd vendor/stoplight-elements

# Pull the new files. Replace 9.0.19 with the target version.
curl -fsS -o web-components.min.js \
  "https://unpkg.com/@stoplight/elements@<NEW_VERSION>/web-components.min.js"
curl -fsS -o styles.min.css \
  "https://unpkg.com/@stoplight/elements@<NEW_VERSION>/styles.min.css"
curl -fsS -o LICENSE \
  "https://unpkg.com/@stoplight/elements@<NEW_VERSION>/LICENSE"

# Record the new checksums.
shasum -a 256 web-components.min.js styles.min.css LICENSE
openssl dgst -sha384 -binary web-components.min.js | base64
openssl dgst -sha384 -binary styles.min.css | base64
```

Then update this `VENDOR.md` (the table above) with the new
checksums, sizes, and upstream version, and update
[api/sbs_api/routes/portal.py](../../api/sbs_api/routes/portal.py)
if filenames change. The `VENDOR_ASSET_ALLOWLIST` and the
`VENDOR_ASSET_MEDIA_TYPES` map both need updates when filenames or
content types change.

If filenames remain the same (the common case), only `VENDOR.md` and
the asset files change.
