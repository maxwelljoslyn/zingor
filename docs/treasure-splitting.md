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
- **A name listed twice is two separate items.** The two healing potions above are two 400 XP potions, not one. The second is shown as `healing potion (2)` in the results.

JSON and Python dicts (`{"gem": 4200}`) are also accepted, so output from elsewhere can be pasted straight in.

**Who draws.** Below the hoard is every active character in the campaign. Primary characters and henchmen — the party proper — start checked; followers, hirelings and pets are listed underneath, unchecked, because they draw a share only when the party says so. Check and uncheck to match who was actually there.

**Shares.** Each character's share count defaults to their current fighter equivalent level, which is how this party divides treasure: one share per FEL. The number is an ordinary editable box, because the FEL that matters is often not today's. If the party agreed to divide on everyone's level *before* the fight — before the XP from this very hoard moved anybody up — type those numbers in instead.

Click **Divide the hoard** and the division appears below.

## Reading the Result

The summary line gives the hoard's total XP, how many shares it was cut into, and what one fair share would be worth if treasure were divisible. It ends with the **spread**: the XP-per-share gap between the best-off and worst-off recipient.

That spread is the honest measure of how well the division went, and it is rarely zero. A single item worth more than a fair share puts a hard floor under it — if the hoard is one 10,000 XP crown and four characters, somebody gets the crown and three people get nothing, and no algorithm can do better. When the spread looks large, look for the lump causing it; that is usually the item the party will want to sell and divide as coin instead.

Below the summary each recipient gets a block: their name, how many shares they drew, their XP total, their XP per share, and how far that total sits above or below a perfectly fair share. Their items are listed underneath, most valuable first.

## What the Splitter Does Not Do

Nothing on this page is saved. A division is a calculation to read off the screen and apply by hand — the items are not added to anybody's inventory, and reloading the page gives you an empty form. To change a division, edit the shares or the hoard and divide again; the splitter is fast enough to re-run as many times as the party wants to argue about it.

Shares are also whole numbers here. A henchman on a traditional half share is written the way the party would work it out anyway: everyone else on 2, the henchman on 1.

## From the Command Line

The same division is available as a management command, which reads a hoard file in any of the formats above:

```
uv run python manage.py split_treasure hoard.txt --shares 4
```

Pass `--names` instead of `--shares` to name the recipients, appending `:shares` to anyone drawing an uneven share — `--names 'Alix,Bront:2,Cwen:1/2'`. Unlike the web page, the command accepts fractional shares and rescales them. Add `--json` for machine-readable output, or `-o` to write the result to a file.
