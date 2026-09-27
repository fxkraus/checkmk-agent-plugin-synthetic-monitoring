# Vendored: web-vitals

`web-vitals.iife.js` is the unmodified standalone IIFE build of Google's
[web-vitals](https://github.com/GoogleChrome/web-vitals) library (exposing `window.webVitals` with
`onLCP/onCLS/onINP/onFCP/onTTFB`). It is vendored because the executor runs air-gapped; to update it,
fetch it once on a networked machine, pin it, and drop it in:

    bun add web-vitals@4
    cp node_modules/web-vitals/dist/web-vitals.iife.js executor/src/synmon_executor/vendor/web-vitals.iife.js
    sha256sum executor/src/synmon_executor/vendor/web-vitals.iife.js   # record below

Pinned version: web-vitals v4.2.4  ·  SHA256: f759996a85b1ddf539ef3f16fdca3d39e48f670aef69e82c6200cc2b5f9f47bd

## License

web-vitals is Copyright 2020 Google LLC and licensed under the Apache License, Version 2.0 — see
[`LICENSE-web-vitals`](LICENSE-web-vitals). It is not covered by this project's MIT license.
