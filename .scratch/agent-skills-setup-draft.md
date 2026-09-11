# Agent skills setup draft

Status: Approved and applied. The destination is `AGENTS.md`; the three configuration files below are installed. Local Markdown, the default triage labels, and the single-context layout are configured. The proposed-content blocks are retained as the review record.

## Proposed AGENTS.md

```markdown
## Agent skills

### Issue tracker

Issues and specs live in local Markdown under `.scratch/<feature>/`. Before reading or publishing them, read `docs/agents/issue-tracker.md`.

### Triage labels

Use the five default triage role strings. Before assigning a triage status, read `docs/agents/triage-labels.md`.

### Domain docs

This is a single-context project with root `CONTEXT.md` and `docs/adr/`. Before exploring or changing the codebase, read `docs/agents/domain.md`.
```

## Proposed docs/agents/issue-tracker.md

```markdown
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
```

## Proposed docs/agents/triage-labels.md

```markdown
# Triage Labels

Map the canonical triage roles to the following local tracker status strings.

| Canonical role | Tracker status | Meaning |
| --- | --- | --- |
| `needs-triage` | `needs-triage` | Maintainer needs to evaluate the issue |
| `needs-info` | `needs-info` | Waiting on reporter information |
| `ready-for-agent` | `ready-for-agent` | Fully specified and ready for agent implementation |
| `ready-for-human` | `ready-for-human` | Requires human implementation |
| `wontfix` | `wontfix` | Will not be actioned |

When a skill applies a triage label, write its mapped value in the spec or issue's `Status:` line. Edit the tracker-status column if the vocabulary changes later.
```

## Proposed docs/agents/domain.md

```markdown
# Domain Docs

This project uses a single-context layout: `CONTEXT.md` at the repository root and architecture decisions in `docs/adr/`.

## Before exploring the codebase

Read the root `CONTEXT.md` and any ADRs in `docs/adr/` relevant to the area being explored or changed.

If those documents are missing, proceed silently. The domain-modeling skill creates them lazily as terms and decisions become settled.

## Use the glossary's vocabulary

Use the terms defined in `CONTEXT.md` when naming domain concepts in issues, proposals, hypotheses, tests, and code. Respect the glossary's avoided synonyms.

If a needed concept is missing, reconsider whether it fits the project's language or note the gap for domain-modeling.

Keep `CONTEXT.md` a glossary. Record architectural decisions in ADRs and requirements in the feature spec.

## Surface ADR conflicts

If a proposed change contradicts an existing ADR, identify that ADR and explain why the decision should be revisited before overriding it.
```
