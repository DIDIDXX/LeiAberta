# Security audit

Snapshot: 2026-10-05. Scope: FastAPI app, frontend, adapters/fetchers, Docker image, Railway deployment topology and repository controls. This is a code/config review plus read-only HTTP smoke, not a penetration test.

## Findings

| ID | Severity | Evidence / risk | Action |
| --- | --- | --- | --- |
| S-01 | P1 | No explicit request rate limiter on search/detail/history/proceedings. Detail reads can enqueue work for many distinct public catalog entries. Per-law dedupe and background batch caps limit duplicate/flood impact but not unique work. | Add edge rate limits or a trusted Redis-based limiter after confirming client IP forwarding and false-positive impact. Until then watch queue depth/oldest age and throttle batch caps. |
| S-02 | P1 | Planalto fetcher read the whole response without a byte ceiling and does not validate the final redirect host. Source URL is stored in DB and currently curated; no public route lets users submit it. | The fetcher now caps reads at 25 MB and rejects oversized bodies (unit-tested). Requested/final URL host and HTTPS allowlisting remains open; preserve documented official mirrors when implementing it. |
| S-03 | P1 | API did not set explicit common baseline headers. | Fixed in this branch with `nosniff`, `DENY`, strict-origin referrer, restricted permissions and HTTPS-only HSTS; covered by API tests. |
| S-04 | P2 | No CSP was configured. | Enforced same-origin scripts/API, disallowed objects and framing, restricted base/form targets, and allowed inline styles required by the existing UI. The existing Google Fonts stylesheet/font hosts are explicitly allowlisted. API tests assert core directives; no `unsafe-eval` or inline script exception. |
| S-05 | P2 | Docker runtime currently runs as root. | Non-root user added in this branch; verify worker and backup images separately (backup image already specifies postgres user). |
| S-06 | P2 | No license, SECURITY disclosure process, or automated dependency alert config was present in `origin/main`. | Add MIT license (permissive project default), SECURITY.md and Dependabot config; confirm copyright ownership before publishing future contributions. |
| S-07 | P2 | External source fetchers need redirect/host/size audit per adapter. Several families already have explicit host/identity checks and size caps (ALESP, SINJ-DF, SAPL, DOU); Planalto is weaker and Senate fetchers need uniform caps. | Complete shared fetch contract with explicit limits and fixtures; current stored-source trust boundary reduces but does not remove SSRF/DoS risk. |
| S-08 | P2 | Forwarded host/proto values can influence sitemap canonical URLs if `PUBLIC_BASE_URL` is unset. XML escaping prevents markup injection but does not establish a trusted canonical host. | Set `PUBLIC_BASE_URL` in production or validate host against configured domain; do not use arbitrary forwarded host for canonical links. |
| S-09 | P2 | No CORS middleware is configured, which is safe by default for cross-origin browser reads; avoid adding `*` if an API client request arises. | No change. Document as an intentional closed browser-origin policy until needed. |
| S-10 | P2 | Logs include user search query text in `app/main.py`. Query strings can contain personal/legal research details. | Change to structured counters/length and request correlation without raw query; set retention and access controls in Railway. |
| S-11 | P3 | No authentication is expected for the open-data read API; this makes abuse control, queue caps and payload limits the effective boundary. | Keep anonymous read access, add cost-aware throttling and response size bounds. |

## Reviewed controls

- No user-supplied URL fetch endpoint was found. Source URLs are catalog metadata and adapter-specific validators often verify domain and remote identity.
- SQLAlchemy statements use bound parameters; no direct SQL string interpolation involving API input was found in reviewed search/endpoints.
- Public job creation is deduplicated by law and job type and persisted before Redis dispatch.
- Law pages now include canonical/Open Graph metadata and bounded no-JavaScript text/source content; the DOM-rendered content is escaped and external source links require HTTPS.
- `.dockerignore` excludes `.env`, `.git`, local databases, `.venv`, and `node_modules`.
- No credential values were read into reports. Production smoke included only public endpoints.
- No CORS allow-all or third-party script integration was found in backend configuration during the reviewed subset.

## Release gate and verification

Security headers now include CSP; the web container runs as UID 10001 and law pages serve safe metadata/text. Planalto response bytes are capped at 25 MB, and `/ready` checks Alembic heads. Public client rate limiting and final redirect-host validation remain open because Railway proxy client identity and redirect behavior have not been validated. These hardening changes passed 138 Python tests and 5 E2E tests locally; CI and production deployment remain pending. No secrets are included in this report.
