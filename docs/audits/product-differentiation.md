# Product differentiation and interoperability

Research checked 2026-10-05. Leis.org could not be opened directly from this environment (HTTP 403); no pages were scraped. Its public landing-page search result describes federal/state/municipal/institutional collections, but feature-by-feature benchmarking remains unverified. Use only public pages or obtain permission for deeper comparison. Legalize documentation and its public format specification were reviewed directly.

## Product position

LeiAberta's differentiator is an evidence-oriented Brazilian legislative trail: a public norm is linked to its official source, structured devices, verified amendments, and (where official identity links exist) legislative proceedings. Its model should keep text, relations, diffs, proposition metadata and votes distinct, and label unknown evidence. Current coverage is partial and should be visibly stated. It must not imply every Brazilian law is already indexed.

Legalize's current docs describe a REST API with structured/paginated laws, reform records, git-style historical commits, time travel, webhooks, SDKs and generated OpenAPI. Its public SPEC v0.4 describes Markdown law files, per-country manifests, source/legal dates and reproducible Git histories. That is useful interoperability guidance, not a dependency or a claim of conformance. The Legalize service itself states generated data should not be treated as official/verified text. LeiAberta should keep its official-source evidence/provenance contract as its authority and export compatible shapes where they fit.

Leis.org appears to position itself around multi-jurisdiction legislation, consolidated/versioned text and institutional libraries. Direct benchmark details could not be verified due access restriction; revisit by permission or public product demo. Do not collect or replicate its corpus.

## Provenance chain and evidence contract

Current chain is strongest for `Law → LawVersion/SourceSnapshot → LegalNode`, `LawChange → source amending law + source URL + evidence marker`, and Senate proceeding dossier stored separately against an enacted norm. The remaining product gap is a consistently typed chain from amendment `Law` to official bill/proposition, amendment text, author/rapporteur, committee/plenary decision, vote and official source. Cross-link only on verified official identifiers. Represent `verified`, `partial`, `not_found`, `not_applicable`, `source_unavailable` explicitly; never derive identity solely from a title/number coincidence.

Diff classification should support ADD, MODIFY, REPEAL, RESTORE, RENUMBER and MOVE, with before/after checksums, stable node identity and source law citation. Existing history relations without both texts stay relations and must not be rendered as textual diffs. Version-at-date needs clear semantics: enacted text, latest available compilation, and effective text are distinct.

## Priority roadmap by user value / effort

| Rank | Capability | Why | Effort |
| ---: | --- | --- | --- |
| 1 | Per-law evidence coverage and last checked timestamps | Makes gaps/freshness legible and prevents overclaiming | S |
| 2 | Search and law pages usable without JavaScript, with canonical metadata | Accessibility, discovery and link previews | M |
| 3 | Verified amendment-to-proposition provenance graph over current relational schema | Core “what changed, who and why” promise | L |
| 4 | Structural diff types and direct URLs to affected nodes | Lets users verify changes | M |
| 5 | History UI distinguishes official link, fetched text, validated diff and missing evidence | Avoids false certainty | S |
| 6 | Export a selected law/version/history as JSON and Markdown with provenance | Reuse, research and legal interoperability | M |
| 7 | Add JSON-LD/Schema.org legislation metadata and OpenAPI coverage contract | Search-engine and ecosystem integration | M |
| 8 | API version prefix + consistent cursor pagination / max page sizes | Stable integrations under catalog growth | M |
| 9 | Webhooks/change feed after source freshness and dedupe are reliable | Enables downstream alerts | L |
| 10 | Timeline/blame and version-at-date with explicit legal-date semantics | High-value historical research | L |

## Compatibility recommendation

Additive export only. Consider Legalize frontmatter keys where semantics match: jurisdiction, type, dates, status, source and text-state. Do not equate Railway retrieved-at time with legal source date, Git commit chronology with legal effect, or an imported current compilation with full point-in-time history. Keep LeiAberta's stable node IDs and evidence URLs in explicit extension metadata. Create a conformance fixture and disclose non-conformant fields before publishing an adapter.
