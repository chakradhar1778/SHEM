# React + TypeScript + Vite

This template provides a minimal setup to get React working in Vite with HMR and some Oxlint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the Oxlint configuration

If you are developing a production application, we recommend enabling type-aware lint rules by installing `oxlint-tsgolint` and editing `.oxlintrc.json`:

```json
{
  "$schema": "./node_modules/oxlint/configuration_schema.json",
  "plugins": ["react", "typescript", "oxc"],
  "options": {
    "typeAware": true
  },
  "rules": {
    "react/rules-of-hooks": "error",
    "react/only-export-components": ["warn", { "allowConstantExport": true }]
  }
}
```

See the [Oxlint rules documentation](https://oxc.rs/docs/guide/usage/linter/rules) for the full list of rules and categories.

## Install on your phone (PWA, same Wi-Fi)

From the repo root run **`python start.py`**. It builds the frontend when needed,
creates a local HTTPS certificate for this PC's LAN address, and serves the app,
API and live data on `https://<pc-ip>:8443`.

First time on a phone: open the printed `http://<pc-ip>:8080` set-up page. Tap
*Download certificate*, trust it as the page explains, then *Open SHEM* →
*Install app* / *Add to Home Screen*. HTTPS is what lets the app be installed and
use the microphone for voice.

The service worker is registered only in production builds (`npm run dev` skips it).
