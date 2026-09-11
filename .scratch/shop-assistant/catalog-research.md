# Catalog seed research

Date: 2026-09-11. Scope: prototype goods across categories, a small useful seed, and approximately 100,000 products for load testing. No data downloaded or generated. These are recommendations, not accepted architectural decisions.

## Candidates

| Candidate | Data and scale | License evidence | Fit |
| --- | --- | --- | --- |
| DummyJSON products | Placeholder catalog with titles, descriptions, categories, price, stock, attributes and images. Documentation example reports 194 items across 24 categories; this is an example count, not a verified current API count. Real brand/product names appear, so it is not wholly fictional. All records can be exported using `limit=0`. [Product docs](https://dummyjson.com/docs/products) | Repository declares MIT; its license text covers software and associated documentation. Separate rights/provenance for third-party imagery were not established by this review. [Repository](https://github.com/Ovi/DummyJSON), [license](https://raw.githubusercontent.com/Ovi/DummyJSON/master/LICENSE) | Fast optional UI/retrieval seed; too small for the 100k target. Save a fixed text snapshot and use local placeholders for images. Do not call the hosted API at chat runtime. |
| Faker plus a project-owned category schema | Generator, not an existing dataset. Commerce methods produce names, departments, prices and descriptions. A category-aware factory must supply coherent attributes and stock. Arbitrary record counts are possible, but random text repetition and incoherent combinations need deliberate control. [Commerce API](https://fakerjs.dev/api/commerce) | Faker explicitly permits commercial and noncommercial use under MIT. [Official project](https://fakerjs.dev/) | Best base for fictional, locally generated load fixtures. A local LLM can later phrase descriptions using only supplied facts; Faker's generic description method is insufficient for realistic retrieval evaluation. |
| McAuley Lab Amazon Reviews 2023 metadata | Real historical products with titles, categories, descriptions, attributes and crawled prices. Metadata schema does not provide authoritative stock. All Beauty metadata alone lists 112,590 records. [Dataset card](https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023/raw/main/README.md), [field definitions and JSONL loading](https://amazon-reviews-2023.github.io/index.html) | No explicit dataset license was found in the first-party dataset README reviewed. This is an unresolved provenance question, not a claim that reuse is forbidden. [Dataset README](https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023/raw/main/README.md) | Adequate scale and richer language, but unnecessary complexity for fictional goods. Do not adopt by default; rights and normalization would need separate resolution. |

## Recommended direction

Use project-owned synthetic goods as the main fixture. DummyJSON is a viable existing small demonstration seed if real brand names are acceptable, but it does not satisfy a varied 100k fictional catalog. The Amazon dataset is not the simplest fit.

Proposed generation and ingestion contract:

1. Define a modest fixed taxonomy and category-specific attributes. Generate stable product IDs, fictional names, integer minor-unit prices, currency, stock and internally consistent facts using a fixed seed.
2. Start with roughly 200-500 reviewed products for retrieval and answer evaluation. Create a separate 100k fixture with varied attributes and descriptions for performance tests; measure retrieval quality separately from scale.
3. If local inference is available, generate descriptions from those facts in an offline job. Reject descriptions that invent specifications; preserve the approved outputs. Model choice, endpoint, license and generation cost remain unresolved.
4. Freeze the resulting JSONL plus a manifest containing schema version, generator version/seed, record count and checksum. If using Faker, pin the package version: its documentation warns that identical seeds can produce different values after upgrades. [Reproducibility guidance](https://fakerjs.dev/guide/usage#reproducible-results)
5. Feed the frozen artifact through the independent ingestion job. Restarted ingestion reuses stable IDs. V1 serves an immutable catalog; ingestion recovery and rebuilding remain supported even though catalog updates are out of scope.
6. Use local product-detail routes and placeholder artwork. No public dataset API, external image host or generation service should be required for serving the already-ingested fixture.

The generation approach, record counts, schema and artifact format above are engineering recommendations. They have not been implemented or benchmarked.
