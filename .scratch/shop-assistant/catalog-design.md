# Synthetic catalog

Status: Accepted as part of the v1 design on 2026-09-11. No data generated yet.

## Hierarchy

Each product belongs to exactly one leaf category. Department filters include all child categories. Stable category IDs are independent of display names.

| Department | Leaf categories | Example category attributes |
| --- | --- | --- |
| Electronics | Headphones; Portable speakers | Connection type, battery life, water-resistance rating |
| Home | Electric kettles; Table lamps | Kettles: capacity and power; lamps: brightness and dimmability |
| Office | Keyboards; Desk organizers | Keyboards: layout and connection; organizers: material and compartments |
| Sports | Yoga mats; Dumbbells | Mats: material and thickness; dumbbells: fixed/adjustable and piece count |
| Outdoors | Backpacks; Camping lanterns | Backpacks: capacity; lanterns: brightness and runtime |

## Shared product fields

- Stable product ID, fictional name/brand, department and leaf-category IDs, description, and category-specific attributes.
- Price in integer USD cents and nonnegative stock quantity; availability is derived from stock rather than generated independently.
- Rating average on a 1-5 scale plus rating count. Unrated products have count zero and a null average. Ratings are synthetic aggregate facts, with no invented customer review text.
- Length, width, and height in centimeters, plus weight in kilograms. These refer to the product rather than its shipping package; record the measured configuration where relevant (for example, a rolled mat). Structured unit-aware values support numeric filtering.
- A local product-detail path derived from the product ID and local placeholder artwork. No external product page or image service is required.

## Generation and consistency

Generate structured facts with a fixed seed and category-specific ranges before asking the local LLM for descriptions. Descriptions must be supported by those facts; unknown attributes stay unknown. Freeze validated descriptions and facts in a versioned JSONL artifact with record count and checksum, so ingestion restarts do not regenerate content.

Use approximately 300 reviewed products spanning the ten leaf categories for quality tests. Build a separate 100,000-product fixture for load tests, with meaningful attribute variation rather than duplicate descriptions alone. Include unrated and out-of-stock products, near-identical products with different constraints, and overlapping names to test filtering and cache correctness.

## Serving rules

Apply price, stock, rating, dimensions, weight, and category constraints using structured fields. A semantically similar description cannot override a numeric constraint. Product facts are authoritative; descriptions are a searchable representation. Product comparison uses shared units and reports unavailable or inapplicable attributes explicitly.
