# 0001 — Zingor microformats stay one level deep

**Status:** accepted (2026-08-16)

**Context:** issue #171, supporting sage study concentrations.

## Context

Zingor microformats (ZMF) let a player's wiki page carry structured data that
`characters/microformats.py` scrapes back. Until now the format had exactly two
shapes: scalars mapping to `Character` columns, and repeating records made of a
root element carrying `zingor-<record>` with descendants carrying
`zingor-<record>-<subfield>`. One level of nesting, no more.

Sage concentrations broke the assumption behind that. A concentration is a named
bucket *within* a study — `SageConcentration` has a foreign key to
`SageStudyPoints` — so the data genuinely is two levels deep. Representing it
raised a question the format had never had to answer: how does a child record say
which parent it belongs to?

Three options were on the table.

**Repeat the study as its own record, carrying an optional concentration
subfield.** The first attempt. It works, but every bucket row has to name its own
study, since ZMF roots are matched independently. On a wikitable that means
either a visibly repeated column or — as first built — hiding the study name in a
`display:none` span inside the bucket's cell. The hidden span was the tell that
something was wrong: a human editing the page would see "Ancient Asia" while the
parser read a study name they could not see, and deleting the wrong span detached
the row silently.

**Nest concentration records inside the study's markup.** Genuinely attractive.
The bucket inherits its study by containment, so the repeated name disappears
entirely, the markup mirrors the foreign key, orphans become impossible, and
there is no second place for a study's spelling to drift.

**Give concentrations their own record type,** a sibling of `zingor-sage-study`
that names its study explicitly.

## Decision

Concentrations get their own record type, `zingor-sage-concentration`, with
`-study`, `-name`, and `-points` subfields. ZMF stays one level deep.

The deciding constraint is that **`<tr>` cannot contain `<tr>`**. The sage section
is a wikitable, on Alexis's hand-written pages and in Zingor's own export.
Nesting would force a study to stop being a table row and become a `<div>` or a
list containing a sub-list, changing the page format for every concentrated
study, and turning "add a row" into "nest divs correctly in wikitext" for the
player writing it.

Nesting inside a single cell — a `<ul>` of buckets in the study row's last cell —
is legal and was considered. It keeps the table but crams the buckets into one
cell where their points cannot line up in a column, which reads worse for the
human the page exists for.

The costs of nesting fall almost entirely on the person hand-editing the page;
the benefits fall almost entirely on the parser. For a format whose whole premise
is riding along on a page a human wants to read and edit, that is the wrong way
round. Difficult for us leads to easy for them.

## Consequences

What we pay:

- A bucket repeats its study's name, which must be canonicalized and matched like
  any other study name.
- A bucket can name a study the page never lists. `wiki_sync._apply_studies`
  handles this by creating the study from what its buckets imply, and warning.
- A mistyped study name silently detaches a bucket from its study. Mitigated by a
  sync warning, but not prevented.
- The two-level data model is flattened on the way out and reassembled on the way
  in, so `wiki_sync` owns a resolution step that nesting would have made
  unnecessary.

What we keep:

- `_build_record` stays a flat descendant search. Had roots been able to contain
  roots, it would have needed scoping so a parent does not reach into its
  children — a change affecting how *every* record type parses, for the benefit
  of one.
- Every ZMF record remains one table row, which is what the wiki's pages already
  look like and what a player can write without learning anything new.
- A concentration can be added to a page by copying a row and editing two cells.

## Notes

This decision is about ZMF, the *external* format. It says nothing about the
internal model: `SageConcentration` keeps its foreign key to `SageStudyPoints`,
and the sheet renders buckets nested under their study. Only the wire format is
flat.

If a future record type needs real nesting badly enough — and can live outside a
table — this should be revisited rather than worked around with hidden elements.
Hiding data in `display:none` to satisfy a flat parser is the anti-pattern this
record exists to rule out.
