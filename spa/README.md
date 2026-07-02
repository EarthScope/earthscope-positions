# spa/

This directory contains the web frontend for `es-pos webserver`.

This directory should only be touched by an earthscope developer.  It requires access to the private npm registry for the `@earthscope/spa-lib` package and comes pre-built in the `spaBuild/` directory.  

## Directory layout

| Directory | Purpose |
|-----------|---------|
| `spaGenerator/` | Quasar/Vue 3 TypeScript source — **edit code here** |
| `spaBuild/`     | Compiled static assets — **do not edit manually** |

## Building

```bash
cd spaGenerator
npm install        # first time, or after package.json changes
npm run build      # compiles to ../spaBuild/
```

During development you can run the dev server with hot reload:

```bash
npm run dev        # proxies /api → localhost:8000 (the FastAPI backend)
```

Then start the backend in another terminal:

```bash
es-pos webserver
```

## Notes

- `spaGenerator/node_modules/` is gitignored.
- `spaBuild/` is committed so the server works without a Node build step.
- The spa-lib package (`@earthscope/spa-lib`) lives in the EarthScope private
  npm registry.  Make sure your npm/npmrc is configured for that registry before
  running `npm install`.
