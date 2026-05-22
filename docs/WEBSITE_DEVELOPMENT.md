# Website Development

The public website is a static Vite/TypeScript project in `website/`.

## Local Setup

```bash
cd website
npm ci
npm run dev
```

Vite prints a local preview URL, usually `http://localhost:5173/open-mechanic/`.

## Production Build

```bash
cd website
npm ci
npm run build
```

The production output is written to `website/dist/`.

## GitHub Pages

The site is deployed at:

```text
https://speed785.github.io/open-mechanic/
```

`website/vite.config.ts` sets `base: "/open-mechanic/"`, so asset paths must work under that subpath. Prefer relative links for files in `website/public/`, such as `./favicon.svg`, unless Vite is importing the asset directly.

## Metadata Checklist

Before changing the first viewport or site copy, verify:

- Page title and meta description still describe the current implemented product.
- Open Graph and Twitter metadata match the visible hero copy.
- Claims about AI providers, cloud usage, APIs, Docker, or dashboard features are marked as current or planned accurately.
- `npm run build` succeeds.
