# Splitting Treasure

A hoard is a pile of things nobody can cut in half: one gem is worth 4,200 XP whether it goes to Alix or to Bront, and there is no dividing it. Zingor's treasure splitter takes the list of what the party found, the list of who is dividing it, and hands out the items so that everybody's XP comes out as close to even as indivisible loot allows.

The splitter lives at **Treasure** in the top bar. It is a DM tool: only staff accounts see the link or can open the page.

## Dividing a Hoard

The page has two halves and one button.

**The hoard.** Type or paste the items into the big box, one per line, as a name and an XP value:

```
# cavern of the frog king
gem of true seeing: 4,200
platinum crown: 3100
healing potion: 400 xp
healing potion: 400
```

The format is deliberately forgiving, so you can transcribe a hoard as fast as you can read it out:

- The colon is optional — `platinum crown 3100` works too.
- Commas in numbers are ignored, and so is a trailing `xp`.
- A line starting with `#` is a comment, and blank lines are skipped.
- **A name listed twice is two separate items.** The two healing potions above are two 400 XP potions, not one. They are shown as `healing potion (1 of 2)` and `healing potion (2 of 2)` in the results, so a potion sitting in somebody's take says on its own row how many there were.

JSON and Python dicts (`{"gem": 4200}`) are also accepted, so output from elsewhere can be pasted straight in. A name repeated there is two items as well — `{"potion": 400, "potion": 500}` is both potions, not just the second one, even though neither Python nor JSON can hold a key twice.

**Who draws.** Below the hoard is every active character in the campaign. Primary characters and henchmen — the party proper — start checked; followers, hirelings and pets are listed underneath, unchecked, because they draw a share only when the party says so. Check and uncheck to match who was actually there.

**Shares.** Each character's share count defaults to their current fighter equivalent level, which is how this party divides treasure: one share per FEL. The number is an ordinary editable box, because the FEL that matters is often not today's. If the party agreed to divide on everyone's level *before* the fight — before the XP from this very hoard moved anybody up — type those numbers in instead.

Click **Divide the hoard** and the division appears below.

## Reading the Result

A table of figures heads the division: the hoard's total XP, how many items it held, how many shares it was cut into, what one fair share would be worth if treasure were divisible, and the **spread** — the gap between the best-off and worst-off recipient, in XP per share. Per share, because shares are not always equal: a character drawing four of them takes home more raw XP than a henchman drawing one and may still be the worse off of the two, so the per-share figures are the only ones that compare.

That spread is the honest measure of how well the division went, and it is rarely zero. A single item worth more than a fair share puts a hard floor under it — if the hoard is one 10,000 XP crown and four characters, somebody gets the crown and three people get nothing, and no algorithm can do better. When the spread looks large, look for the lump causing it; that is usually the item the party will want to sell and divide as coin instead.

Below the figures each recipient gets a block: their name, how many shares they drew, their XP total, their XP per share, and how far that total sits above or below a perfectly fair share. Their items are listed underneath, most valuable first.

## Adjusting the Division by Hand

The algorithm divides by value alone. It does not know that Cwen has wanted a silver mirror since the party met her, or that the party voted to give Bront the crown for going back into the fire. So the division is a starting point you can rearrange: **drag any item onto somebody else's block to hand it to them.**

Every total reworks itself around the move — the recipients' XP, their XP per share, their over/under against a fair share, and the spread at the top all recompute from where the items actually sit now. Nothing else moves: handing over the crown does not set the algorithm loose to rebalance everything around it. Moves accumulate, so you can keep dragging until the division looks the way the party wants it.

Once you have moved anything, the page says so, because **dividing the hoard again starts over from the algorithm and discards your moves.** That is the way back if you rearrange yourself into a corner. The same is true of the share boxes: change one after dividing and you need to divide again for it to take effect, since the division on screen was made against the old numbers.

Dragging needs a pointer. There is no keyboard equivalent yet.

## What the Splitter Does Not Do

Nothing on this page is saved. A division is a calculation to read off the screen and apply by hand — the items are not added to anybody's inventory, and reloading the page gives you an empty form. The division you are looking at, moves and all, lives only in the page itself, so leaving the page loses it; the splitter is fast enough to re-run as many times as the party wants to argue about it.

Shares are also whole numbers here. A henchman on a traditional half share is written the way the party would work it out anyway: everyone else on 2, the henchman on 1.

## From the Command Line

The same division is available as a management command, which reads a hoard file in any of the formats above:

```
uv run python manage.py split_treasure hoard.txt --shares 4
```

Pass `--names` instead of `--shares` to name the recipients, appending `:shares` to anyone drawing an uneven share — `--names 'Alix,Bront:2,Cwen:1/2'`. Unlike the web page, the command accepts fractional shares and rescales them. Add `--json` for machine-readable output, or `-o` to write the result to a file.
