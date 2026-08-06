# Inventory, Containers, and Encumbrance

The Inventory section of a character sheet holds everything the character owns: gear, coins, and the containers that gear lives in. It also shows the two numbers that inventory drives, **Encumbrance** and **Action Points**.

Only a character's owner can change that character's inventory. Other players see the same table, but without the editing controls described below.

## Adding an Item

At the bottom of the Inventory section, fill in the "Add Item" form:

- **Item name** — required.
- **Weight** — the weight of *one* of the item, written as a number and a unit, for example `5 lb` or `8 oz`. Leave it blank for a weightless item. If Zingor can't make sense of what you typed, the item is created weighing 0 oz, and you can correct it afterwards by editing the row.
- **Quantity** — how many of the item you're adding, from 1 to 100. Items with a quantity above 1 are a *stack*: one row standing for several identical things.
- **Worn** — tick this if the character is wearing the item rather than just hauling it.

Click **Add Item**, and the row appears in the table.

## Editing an Item In Place

Every editable part of a row is edited on the row itself: click the value, a small form replaces it, and you click **Save** (or **Cancel** to back out). The clickable values are:

- the **item name**;
- the **× quantity** next to the name (a stack of one shows `×1`, so you can click it to stack up);
- the **weight**;
- the **capacity** of a container (see [Containers](#containers)).

The **Worn**, **Carried**, and **Container** checkboxes have no Save button: they take effect the moment you tick or untick them.

Worn and Carried are linked, because you cannot wear something you aren't carrying:

- ticking **Worn** ticks **Carried** as well;
- unticking **Carried** unticks **Worn**.

## Deleting an Item

The **x** button at the end of a row deletes that item, after a confirmation prompt.

:::{warning}
Deleting a container deletes everything inside it, at every level of nesting. If you want to keep the contents, take them out of the container first (see [Containers](#containers)).
:::

## Quantities, Weights, and Units

Weights are always entered and stored **per unit**, never per stack. The Weight column then shows you the whole stack's weight, with a reminder of the per-unit figure underneath:

> **6 lb**
> 2 lb each

So a stack of 3 flasks weighing 2 lb apiece reads as 6 lb, and the weight editor for that row is pre-filled with `2 lb`. Changing the quantity changes the stack weight; changing the weight changes what one of them weighs.

Weights are real physical quantities, not bare numbers: Zingor parses them with [pint](https://pint.readthedocs.io/), so a unit is always part of the value. The weight editor offers **lb** and **oz**. Container capacities can additionally be given as volumes: **gal**, **qt**, **pt**, **fl oz**, or **cu ft**.

Because every weight carries its unit, mixed units compare correctly. Clicking the **Item** or **Weight** column heading sorts the table, and the weight sort is by true weight — a 12 oz item sorts below a 1 lb item, not above it on the strength of the bigger number.

## Containers

A container is an ordinary item with its **Container** box ticked. Any item can become one: a backpack, a chest, a saddlebag, a wagon.

### Putting Items In and Taking Them Out

**Drag a row onto a container's row** to put that item inside. The container row highlights as you drag over it; drop, and the item moves in.

To get an item back out, click the **↑ Take out** button on its row, which appears whenever an item is inside something. The item returns to the top level of the inventory.

A few moves are refused, because they'd produce an inventory that can't exist:

- an item can't be put inside itself, nor inside one of its own contents (no loops);
- a stack of more than one can't become a container, and a container's quantity can't be raised above 1 — the things inside point at *this* container row, so one row can't stand for two boxes with different contents;
- coins can't hold anything (see [Money and Coins](#money-and-coins)).

Unticking **Container** on a full container doesn't delete anything: its contents are simply moved back out to the top level.

### How Nested Contents Are Shown

Contents are listed as their own rows, indented under the container that holds them, to as many levels as you care to nest. A container row with something inside it also gets a **▾ caret**; click it to fold that container's contents away, and click it again to unfold them. This is a per-viewer convenience remembered by your browser — it doesn't change the character's data, and other players see their own view.

A container's Weight column shows the container's own weight plus a note of the whole load:

> **2 lb** (14 lb total)

If you give a container a **capacity** in weight, Zingor also shows how full it is, as a percentage of that capacity:

> [cap: 30 lb] 47% full

A capacity given as a *volume* is recorded and displayed, but no fill percentage is shown for it, since items have weights rather than volumes to measure against it. A container filled past its capacity is shown above 100% rather than being capped: an overloaded pack is worth seeing.

## Splitting a Stack

A stack of more than one has a **Split** button. Click it, type how many to split off (at least 1, and fewer than the whole stack), and click **Split**.

The units you split off become a second row alongside the first, keeping the original's name, per-unit weight, container, and Worn/Carried flags. Nothing is created or destroyed — the two rows still add up to the original quantity — so the character's encumbrance and wealth are unchanged. From there you can drag the new row into a different container, hand-edit it, or mark it as not carried.

This is the way to divide a stack between two places: split 20 arrows off a stack of 40, then drag the new row into a quiver.

## Money and Coins

Money is added from the "Add Coins" form at the bottom of the Inventory section: enter a number of coins, choose **gp**, **sp**, or **cp**, and click **Add Coins**.

Adding coins tops up the character's loose carried stack of that currency if there is one, and starts a new stack if there isn't. The **Money** line in the Identity section is derived: it sums every coin stack the character has, wherever it happens to be — loose, stashed in a chest, or not carried at all.

:::{note}
Coins are ordinary inventory items in Zingor, not a separate money field. That means a coin stack behaves like any other row: you can split it, drag it into a container, edit its quantity to spend or gain coins, or delete it outright. It also means coins have weight and count toward encumbrance like everything else.
:::

Coin rows differ from other items in only two ways, both following from what coins are:

- **The weight isn't editable.** What a coin of each metal weighs is set by the game's rules, so Zingor fills it in and shows it, and there is nothing to type.
- **There's no Container checkbox.** A pile of coins can't hold other items. (Put the coins in a purse, and make the *purse* a container.)

Money and inventory are also the parts of a character that [external synchronization](external-synchronization.md) deliberately leaves alone: they're managed here in Zingor rather than scraped from an external page.

## Encumbrance

At the top of the Inventory section, above the table:

> **Encumbrance:** 84.5 pound / 222 pound (38%)
>
> **Action Points:** 4 / 5 (4 AP above 44.4; 3 AP above 88.8; 2 AP above 133.2; 1 AP above 177.6)

The first number is what the character is **currently carrying**; the second is their **maximum encumbrance**; the percentage is the first as a share of the second.

### What Counts as Carried

Current encumbrance is the total weight of everything with **Carried** ticked, including the contents of carried containers, however deeply nested. Untick **Carried** on an item — a chest left at an inn, a wagon-load of supplies — and it stops counting, and so does everything inside it.

Every weight-affecting change is reflected immediately: adding, deleting, or splitting items, editing a weight or a quantity, and toggling Carried all re-figure the encumbrance line as soon as you make them.

### How Maximum Encumbrance Is Derived

Maximum encumbrance comes from two things: the character's **Strength** and their **body weight** (the Weight field in the Identity section). Strength gives a base carrying figure from the rules' encumbrance table; that figure is then scaled by the character's body weight relative to a 175 lb standard, and the result is rounded to the nearest pound. A heavier character of a given Strength carries proportionally more than a lighter one.

If either Strength or body weight is unset, Zingor shows no maximum (and no percentage): it won't guess at a number it hasn't been given.

**Action Points** follow from maximum encumbrance. A character has 5 AP unburdened; the range from nothing to their maximum is divided into five equal tiers, and each tier boundary the load crosses costs 1 AP. The thresholds are listed next to the AP figure so you can see what the next pound will cost you.

### Strength, and Conditions That Change It

Because maximum encumbrance is derived from Strength, anything that changes Strength changes what the character can carry. Conditions do exactly that: add a condition in the Conditions section with modifier type **Ability** and target **Strength**, and the encumbrance figures are recomputed against the modified Strength. Removing or deactivating the condition puts them back.

At the top of the human range this is subtler than it looks, because of exceptional Strength: for a character with Strength 18, a +1 modifier raises the *percentile* by 10 rather than raising the score to 19, and the encumbrance table treats each percentile band as its own step. A negative modifier walks back down the same ladder.

A Strength condition can also be scoped, using the **Encumbrance only** option in the scope dropdown when adding a condition. The two settings differ in reach:

- **All (no scope)** — the condition changes the character's Strength everywhere. The Ability Scores section shows the modified score alongside the base one, and every Strength-derived stat (to-hit and damage modifiers, and so on) changes along with maximum encumbrance.
- **Encumbrance only** — the condition applies solely to the encumbrance calculation. Maximum encumbrance and Action Points change; the character's displayed Strength score and their other Strength-derived stats do not.

Use the scoped form for something that only affects hauling capacity — a pack harness, a beast of burden's load-bearing gear — and the unscoped form for anything that genuinely makes the character stronger or weaker.
