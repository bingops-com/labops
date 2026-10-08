# Authentik

Authentik runs only on `labprod`, backed by
`authentik-labprod-postgresql`. Cloudflare Tunnel publishes
`https://auth.lab.bingo`.

The tracked blueprint owns four OIDC applications: confidential Argo CD at
`https://argocd.lab.bingo/auth/callback`, public-PKCE Grafana at
`https://grafana.lab.bingo/login/generic_oauth`, the public-PKCE LabOps Portal
at `https://lab.bingo/auth/callback`, and public-PKCE RomM at
`https://romm.lab.bingo/api/oauth/openid`. RomM receives Authentik group names
through a dedicated `groups` scope; `romm-admins` grants its administrator role.
Its dedicated `email` scope emits the verified-email claim required by RomM on
Authentik 2025.10 and later. Only the confidential Argo CD client secret and the
Authentik bootstrap password are stored in the Bitwarden `labprod` project and
mapped by tracked BitwardenSecret resources.

The same blueprint owns the `auth.lab.bingo` brand. Its inline custom CSS uses
neutral `LabOps SSO` branding shared by every relying application, while the
brand attributes keep the Authentik interface in light mode. The login flow
uses a full-viewport split layout: a blue welcome panel on the left ("Bienvenue
sur lab.bingo", the `LabOps SSO` lockup, a tagline and an animated cat sitting
in the bottom corner) and the native Authentik flow centered on the right. It
does not visually identify itself with any one client application. On narrow
screens the welcome panel becomes a compact header above the flow.

The CSS is written against the flow DOM of the pinned Authentik release
(2026.5, see `apps/gitops/clusters/labprod/authentik.yaml`) and relies on three
things that must be rechecked whenever that version changes:

- the flow executor structure: `ak-flow-executor.pf-c-login[data-layout]` as
  shadow host of `.pf-c-login__main`, `.pf-c-brand`, `.branding-logo` and the
  stage's `ak-flow-card`. Each executor rule is also written for releases that
  wrap these in an inner `div.pf-c-login` (2026.8 does), but only 2026.5 has
  been rendered and checked;
- the `RedHatDisplay` and `RedHatText` font families, which Authentik serves
  itself;
- the vendor name being hidden by CSS only: the flow title is visually replaced
  by "Connexion" (the flow's own title is unchanged and may still be announced
  by screen readers), the brand logo image is repainted as the cat, and the
  site footer is hidden. Footer links added to the brand later would therefore
  not be displayed until that rule is narrowed.

The CSS is intentionally embedded in `apps/platform/authentik/blueprint.yaml`,
including the mark and the cat as SVG data URIs: there is no uploaded media
file, external font, CDN asset or manual Admin UI setting to recover during a
rebuild. Change the blueprint rather than editing the brand in Authentik; the
mounted blueprint is the source of truth.

The blueprint makes `bingops` the sole member of `romm-admins`. RomM skips its
local setup wizard and creates that account automatically on the first OIDC
login; no RomM bootstrap password is required.

After reconciliation, verify the Authentik discovery endpoint and each login
through trusted HTTPS without printing tokens or Secret data. Also open an
incognito window on `https://auth.lab.bingo/if/flow/default-authentication-flow/`
and verify the welcome panel, the `LabOps SSO` lockup, the animated cat, the
"Connexion" title, the absence of the vendor name, keyboard focus and the
narrow-screen layout. This visual check is non-sensitive.
