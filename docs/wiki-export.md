# Exporting to a Wiki

Zingor can turn any character sheet into MediaWiki markup, ready to paste into a wiki page such as one on the [Adventure wiki](https://adventure.alexissmolensk.com). This is a one-time copy: it produces a snapshot of the character as it currently stands, with no ongoing link back to Zingor.

## Exporting a Character

Visit the character sheet of the character you want to export.

At the top-right of the character sheet, find the "Export to Wiki" button, and click it.

A "Wiki Export" window opens containing the character's full sheet rendered as MediaWiki markup: identity, ability scores, hit points, encumbrance, inventory, conditions, spells, sage knowledge, and notes.

Click "Copy to Clipboard" to copy the markup, then paste it into the edit box of your wiki page and save. Click "Close" when you're done.

:::{note}
The export is a snapshot taken at the moment you click the button. Editing the character in Zingor afterwards does not update any wiki page you've already created; export again to refresh it.
:::

## A Starting Point for External Sync

The exported markup is more than plain text. Wherever Zingor knows how to read a value back in, it wraps that value in **Zingor microformats** (ZMF) — the same `zingor-` class names that power [external synchronization](external-synchronization.md). Ability scores, name, race, spells, sage studies, and the other syncable fields all come out already tagged.

That makes an exported page a convenient way to try external sync: export the character, save the markup to a wiki page, point external sync at that page, and it will scrape the character straight back into Zingor. From there you can keep editing the wiki page to drive further syncs. See [External Synchronization](external-synchronization.md) for how to associate a page and activate syncing.

:::{note}
Not everything in the export is synced back. Money and inventory, for example, are shown for readability but are managed in Zingor itself, so they carry no ZMF tags. See [External Synchronization](external-synchronization.md) for the full list of fields that participate in syncing.
:::
