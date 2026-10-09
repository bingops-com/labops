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
uses a full-viewport split layout: a blue welcome panel on the left ("Welcome to
lab.bingo", the `LabOps SSO` lockup, a tagline and an animated cat with a
pirate eye patch sitting in the bottom corner) and the native Authentik flow
centered on the right. It does not visually identify itself with any one client
application. On narrow screens the welcome panel becomes a compact header above
the flow.

The page is available in English and French. Authentik translates its own
strings from the visitor's locale (browser language or the language selector)
and exposes that locale on `<html lang>`; the copy added by the brand CSS is
declared once as `--labops-t-*` custom properties, in English on `:root` and in
French on `:root:lang(fr)`. The French block also rewrites the identification
label, which Authentik's French catalogue renders as "Email ou Username"; that
rewrite assumes the email + username fields of the default identification
stage. With it, every visible string of the login page is translated.

The language selector only offers English and French: the CSS hides the other
`<option>` elements of `ak-locale-select`, as Authentik has no setting to
restrict its locales. This has three known limits:

- pickers that ignore option styling (iOS, Android) still list every locale;
- a browser set to another language still gets Authentik's own strings in that
  language, next to the English copy of the brand. Add a `:root:lang(xx)` block
  and widen the option rule to support one more language;
- when the selector is used, Authentik 2026.5 only redraws the current step in
  the new language on the next page load or step, while the brand copy follows
  at once. The page is briefly bilingual until then.

Authentik does not enforce the uniqueness of a brand domain in its database.
labprod once held two `auth.lab.bingo` brands, which made every later change to
the brand fail validation ("domain must be unique") and silently kept the
previous login page. The blueprint therefore starts with a `state: absent`
entry that removes an `auth.lab.bingo` brand still carrying Authentik's stock
favicon, before the entry that owns the brand. It does nothing on a healthy or
empty instance. If the login page stops following the blueprint, check in the
Admin interface under Customization > Blueprints that `labops-branding` is
`successful`, and under System > Brands that the domain appears once.

The browser tab shows the LabOps mark and the title `lab.bingo - LabOps SSO`:

- the icon is `labops-favicon.svg` in the `authentik-branding-assets` ConfigMap
  (`apps/platform/authentik/branding-assets.yaml`). The Authentik server mounts
  it at `/data/media/public/labops-favicon.svg` through the `server.volumes`
  values of `apps/gitops/clusters/labprod/authentik.yaml`, and the brand's
  `branding_favicon` names it. Authentik only accepts a media file, a `/static`
  path or an http(s) URL there, hence the mount instead of an inline data URI.
  Media storage is otherwise unused and not persisted;
- the title comes from the blueprint setting the `title` of Authentik's own
  `default-authentication-flow`. That flow must exist before the blueprint
  applies, as for the OIDC providers, and an Authentik upgrade that re-applies
  its default flow blueprint resets the title until this blueprint is applied
  again.

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
- the vendor name being hidden: the on-page flow title is visually replaced by
  the localised "Log in" / "Connexion" (screen readers may still announce the
  flow's own title, `lab.bingo`), the brand logo image is repainted as the cat,
  and the site footer is hidden. Footer links added to the brand later would therefore
  not be displayed until that rule is narrowed.

The CSS is intentionally embedded in `apps/platform/authentik/blueprint.yaml`,
including the mark and the cat as SVG data URIs, and the favicon is a tracked
ConfigMap: there is no uploaded media file, external font, CDN asset or manual
Admin UI setting to recover during a rebuild. Change the blueprint rather than editing the brand in Authentik; the
mounted blueprint is the source of truth.

The blueprint owns the Authentik identity `bingops` with email
`therealbingops@gmail.com`. It makes that identity the sole member of every
relying-application privileged group: `argocd-admins`, `grafana-admins`,
`portal-editors` and `romm-admins`. The bootstrap `akadmin` account is not a
member of those groups and therefore does not receive administrator access to
the relying applications. New SSO applications must follow the same model: a
dedicated group with `bingops` as its only member, mapped to the application's
administrator role.

The `bingops` password is a sensitive external prerequisite owned by the lab
operator and stored in the operator's password manager; Git owns only the user,
email and group assignments. After an empty-database rebuild, use the
Bitwarden-delivered Authentik bootstrap account to set or reset the `bingops`
password, save the replacement in the password manager, then leave the
bootstrap account outside every relying-application privileged group. Repeating
the reset after a partial failure is safe. Rotate the password in Authentik and
the password manager together. Its only consumer is the operator signing in to
Authentik; recovery uses the bootstrap account. Verify by signing in as
`bingops` and checking the displayed email and group membership without
printing either credential.

RomM skips its local setup wizard and creates the account automatically on the
first OIDC login; no RomM bootstrap password is required. RomM is kept in the
independent `romm.yaml` blueprint entry so a failure in the shared brand cannot
block its OIDC provider, scopes, group or application.

After reconciliation, verify the Authentik discovery endpoint and each login
through trusted HTTPS without printing tokens or Secret data. Also open an
incognito window on `https://auth.lab.bingo/if/flow/default-authentication-flow/`
and verify the welcome panel, the `LabOps SSO` lockup, the animated cat, the
absence of the vendor name, keyboard focus and the narrow-screen layout. Check
both languages with the language selector, which must list only English and
French ("Log in" / "Connexion" and their matching copy, after a reload), and
the browser tab: LabOps icon and `lab.bingo - LabOps SSO`.
This visual check is non-sensitive.

For each relying application, log in as `bingops`, confirm the administrator
role, then log in with one non-privileged test identity and confirm it does not
receive that role. In Authentik, inspect the four privileged groups and confirm
that their only member is `bingops` with email `therealbingops@gmail.com`.
