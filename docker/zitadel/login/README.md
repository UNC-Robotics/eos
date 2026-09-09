# EOS-branded ZITADEL Login V2

EOS customizes the self-hosted [ZITADEL Login V2](https://zitadel.com/docs/guides/integrate/login-ui)
app so the hosted login screen matches the EOS web UI. The EOS source changes
live in [`overlay/`](./overlay); upstream Zitadel is pinned and fetched at build
time by the [`Dockerfile`](./Dockerfile).

## Build

```bash
docker build -t eos-zitadel-login:v4.15.1-eos docker/zitadel/login
```

`docker-compose.yml` references this image via `ZITADEL_LOGIN_IMAGE`
(default `eos-zitadel-login:v4.15.1-eos`). The multi-stage build:

1. Sparse-clones Zitadel at `ZITADEL_REF` (default `v4.15.1`).
2. Copies `overlay/` over the checkout and drops non-English locale bundles.
3. Builds the standalone app from source (`buf generate` -> `@zitadel/client` -> `next build`).
4. Packages the result into a slim runtime image (mirrors upstream `apps/login/Dockerfile`).

Bump the version by changing `ZITADEL_REF` (and the image tag) and reapplying
the overlay against the new source.

## Customizations (`overlay/`)

| File | Change |
| --- | --- |
| `apps/login/src/components/dynamic-theme.tsx` | Single centered EOS card (white/`slate-900` on `gray-50`/`slate-950`), brand header, drops the side-by-side layout. Larger card (`max-w-[480px]`, `p-10`). |
| `apps/login/src/components/eos-brand.tsx` | EOS logo + "Experiment Orchestration System" subtitle (new), sized up. |
| `apps/login/src/components/input.tsx` | Larger fields (height, padding, `text-lg`) and label. Shared across all stages. |
| `apps/login/src/components/button.tsx` | Larger buttons (taller, `text-base`). Shared across all stages. |
| `apps/login/src/components/alert.tsx` | Error alerts use EOS red instead of yellow (which clashes with the dark primary). |
| `apps/login/src/components/checkbox.tsx` | Focus ring uses the EOS primary instead of indigo. |
| `apps/login/src/components/eos-logo.png` | EOS logo, copied from `docs/_static/img/eos-logo.png`. |
| `apps/login/src/app/(login)/layout.tsx` | Page background set to EOS `gray-50` / `slate-950`; theme controls centered under the card. |
| `apps/login/src/app/(login)/loginname/page.tsx` | Username stage: drops the step title/description (brand subtitle stands in). |
| `apps/login/src/components/username-form.tsx` | Username stage: removes the back button and the self-registration link. |
| `apps/login/src/styles/globals.scss` | EOS system font; larger `h1` page titles and descriptions. |
| `apps/login/locales/en.json` | "Username" field label. |
| `apps/login/src/i18n/request.ts` | Local locale files win over the hosted-login translations. |
| `apps/login/src/lib/i18n.ts` | English only. |
| `apps/login/src/components/language-switcher.tsx` | Hidden when only one language is available. |
| `pnpm-workspace.yaml` | Trimmed to the projects needed to build the login app. |

Colors (primary blue `#2563eb` light / yellow `#eab308` dark, etc.), watermark
removal, and `AUTO` theme mode are applied separately via the Zitadel branding
(label policy) API, not in this image.
