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
