# Architecture Decision Records

Short records of decisions that were *arguable* — where a reasonable developer
would have chosen differently, and where someone reading the code later would
otherwise have to re-derive the reasoning or, worse, "fix" it back.

Not every decision belongs here. A record earns its place when the losing option
was genuinely attractive, when the cost of the decision is visible in the code
(so the code looks worse than it is without the context), or when the decision
constrains work that hasn't happened yet.

These are developer documentation and deliberately sit outside `docs/`, which is
the user-facing site published to Read the Docs.

## Format

One file per decision, named `NNNN-kebab-case-title.md`, numbered in the order
they were accepted. Each carries a status (`accepted`, `superseded by NNNN`), the
context that forced a choice, the decision, and — most importantly — the
consequences, including the ones we don't like.

Records are immutable once accepted. A decision that changes gets a new record
that supersedes the old one; the old one stays, because the reasoning that led to
it was true at the time and explains code that may still be around.

## Index

- [0001 — Zingor microformats stay one level deep](0001-zmf-stays-flat.md)
