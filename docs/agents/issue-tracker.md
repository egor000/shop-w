# Issue tracker: Local Markdown

Issues and specs live as Markdown files under `.scratch/`.

## Conventions

- One feature per directory: `.scratch/<feature-slug>/`.
- The spec is `.scratch/<feature-slug>/spec.md`.
- Implementation tickets are separate files at `.scratch/<feature-slug>/issues/<NN>-<slug>.md`, numbered from `01`.
- Triage state is a `Status:` line near the top of each spec or issue. Use the role strings in `docs/agents/triage-labels.md`.
- Append comments and conversation history under a `## Comments` heading.
- Record ticket dependencies explicitly using feature-scoped ticket numbers or relative links. Read blockers before starting implementation.

## Publish or fetch

When a skill says "publish to the issue tracker", create or update the appropriate spec or ticket file using these conventions.

When a skill says "fetch the relevant ticket", read the referenced file. Resolve a bare ticket number within the identified feature; ask for the feature only if the number is ambiguous.

The shop assistant feature uses `.scratch/shop-assistant/`.

## Wayfinding operations

The wayfinder map is `.scratch/<effort>/map.md`, with Notes, Decisions-so-far, and Fog sections.

- Child tickets live at `.scratch/<effort>/issues/NN-<slug>.md`, numbered from `01`, with the question in the body.
- A `Type:` line records `research`, `prototype`, `grilling`, or `task`.
- Wayfinding has its own work lifecycle: a `Status:` line records `open`, `claimed`, or `resolved`.
- A `Blocked by: NN, NN` line lists prerequisites. A ticket is unblocked when all listed tickets are resolved.
- The frontier is the open, unblocked, unclaimed tickets, ordered by number.
- Claim by setting `Status: claimed` and saving before work.
- Resolve by appending an answer under `## Answer`, setting `Status: resolved`, and adding a gist plus link to the map's Decisions-so-far.
