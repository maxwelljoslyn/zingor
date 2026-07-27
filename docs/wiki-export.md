# Exporting to a Wiki

Zingor can turn any character sheet into MediaWiki markup, ready to paste into a wiki page such as one on the [Adventure wiki](https://adventure.alexissmolensk.com). This is a one-time copy: it produces a snapshot of the character as it currently stands, with no ongoing link back to Zingor.

## Exporting a Character

Visit the character sheet of the character you want to export.

At the top-right of the character sheet, find the "Export to Wiki" button, and click it.

A "Wiki Export" window opens containing the character's full sheet rendered as MediaWiki markup: identity, ability scores, hit points, encumbrance, inventory, conditions, spells, sage knowledge, and notes.

Click "Copy to Clipboard" to copy the markup, then paste it into the edit box of your wiki page and save. Click "Close" when you're done.

:::{note}
The export is a snapshot taken at the moment you click the button. Editing the character in Zingor afterwards will not update any external wiki pages that you've already created. To update those pages, re-export your character as shown above.
:::

## A Starting Point for External Sync

The exported MediaWiki markup is more than plain text. Many parts of the exported data are wrapped in **Zingor microformats** (ZMF), the `zingor-*` HTML class names that you'll need for the [external synchronization](external-synchronization.md) feature. Ability scores, name, race, spells, sage studies / abilities, and other syncable fields are already marked up with ZMF for you.

Therefore, if you plan to keep your character's permanent record on a MediaWiki page, the best way to get started is to export your character, save the result to a wiki page, and point external sync at that page. Zingor will then periodically scrape the page to update your character data in Zingor. Afterwards, as long as you keep the ZMF markup intact, you can experiment with the layout of your wiki page as you see fit.

See [External Synchronization](external-synchronization.md) for instructions on making use of that feature, and the types of data it can parse to update Zingor.

:::{note}
Not everything in the export can be included in external sync. For example, your character's money and inventory items are included to make the resulting wiki page as complete as possible, but there's no ZMF markup for them: those gameplay elements are managed in Zingor itself. See [Marking Up Your External Webpage](external-synchronization.md#marking-up-your-external-webpage) for the full list of character data that can be synced.
:::
