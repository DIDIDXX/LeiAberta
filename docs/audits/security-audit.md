# Security audit

Snapshot: 2026-10-05. Scope: FastAPI app, frontend, adapters/fetchers, Docker image, Railway deployment topology and repository controls. This is a code/config review plus read-only HTTP smoke, not a penetration test.

## Findings

| ID | Severity | Evidence / risk | Action |
| --- | --- | --- | --- |
| S-01 | P1 | No public request budgets existed for search, detail or job-preparation routes. | Added Redis-backed global budgets (600 search, 240 detail/nodes, 60 prepare requests per minute) and 429/Retry-After. This does not trust client-provided IP headers; if Redis is unavailable it fails open and existing queue dedupe/backpressure remain. Per-client fairness is still open pending verified proxy identity. |
| S-02 | P1 | Planalto fetcher accepted arbitrary stored URLs/redirects and previously fell back to HTTP. Source URLs are curated and no public route accepts arbitrary fetch URLs. | PR #66 allows only HTTPS `*.planalto.gov.br` on port 443, validates each redirect before following, caps bodies at 25 MB and uses bounded retry only for transient failures. Unit tests cover host, downgrade, size, HTTPS upgrade and retry cases. |
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

Security headers include CSP; the web container runs as UID 10001. `/ready` verifies DB/schema; `/worker-health` checks a 30-second Redis heartbeat with 90-second TTL. Planalto fetches require HTTPS under `*.planalto.gov.br`, validate redirects before following, cap at 25 MB and retry only transient errors. Redis global budgets cover search/detail/job preparation; they deliberately do not claim per-client fairness. Python (146), E2E (5) and image jobs passed CI; production health/readiness/worker-health and browser checks passed. Other adapters still need a shared fetch contract. No secrets are included in this report.
