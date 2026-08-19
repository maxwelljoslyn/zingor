# Inventory, Containers, and Encumbrance

The Inventory section of your character sheet tracks everything your character owns: coins and treasures, weapons and armor, tools and containers, food and drink, and so on. It also tracks two key character statistics which are partially based on how much stuff you're carrying: **Encumbrance** and **Action Points**.

Only a character's owner can change that character's inventory. Other players see the same table, but without the editing controls described below.

## Adding an Item

At the bottom of the Inventory section, fill in the "Add Item" form:

- **Item name**: required.
- **Weight**: the weight of *one* of the item, written as a number and a unit, for example `5 lb` or `8 oz`.
  - If you leave this blank, or if Zingor can't interpret what you typed, the item will still be created with a weight of 0 oz. You can correct it afterwards by editing the row.
- **Quantity**: how many of the item you're adding, from 1 to 100.
  - Items with a quantity above 1 are a ***stack***, where one table row stands for several identical things.
- **Worn**: tick this if the character is wearing the item rather than just hauling it.

Click **Add Item**, and the row appears in the table.

## Editing an Item In Place

Every editable part of a row is edited on the row itself: click the value, a small form replaces it, and you click **Save** (or **Cancel** to back out). The clickable values are:

- the **item name**;
- the **×N** next to the name (e.g. if you have one of something, "×1" will be displayed.)
- the **weight**;
- the **capacity** of a container (see [Containers](#containers)).

The **Worn**, **Carried**, and **Container** checkboxes have no Save button: they take effect the moment you tick or untick them.

Worn and Carried are linked, because you cannot wear something you aren't carrying:

- ticking **Worn** ticks **Carried** as well;
- unticking **Carried** unticks **Worn**.

## Deleting an Item

The **X** button at the end of a row deletes that item, after a confirmation prompt.

:::{note}
Deleting a container **does not** delete everything inside it. Its contents are moved into your inventory as part of the deletion.
:::

## Quantities, Weights, and Units

Weights are always entered and stored **per single item**. The Weight column then shows you the whole stack's weight, with a reminder of the per-item figure underneath:

> **6 lb**<br>
> 2 lb each

So a stack of 3 flasks weighing 2 lb apiece reads as 6 lb, and the weight editor for that row is pre-filled with `2 lb`. Changing the weight changes each item in the stack weighs.

Weights are real physical quantities, not bare numbers: Zingor parses them with the [Pint](https://pint.readthedocs.io/) Python library, so a unit is always part of the value. The weight editor offers **lb**, **oz**, and **dwt**. Container capacities can additionally be given as volumes: **gal**, **qt**, **pt**, **fl oz**, or **cu ft**.

Because every weight carries its unit, mixed units compare correctly. Clicking the **Item** or **Weight** column heading sorts the table, and the weight sort is by true weight: a 12 oz item sorts below a 1 lb item.

## Containers

A container is an ordinary item with its **Container** box ticked. Any item can become one, from a backpack to a wagon.

### Putting Items In and Taking Them Out

To put an item in a container, click and drag the item onto the container's row in your inventory. The container row highlights as you drag over it; at this point, you can let go of the mouse button, and the item will move into the container.

To get an item back out, click the **↑ Take out** button on its row, which appears whenever an item is inside something. The item returns to the top level of the inventory.

A few moves are refused, because they'd produce an inventory that can't exist:

- An item can't be put inside itself, nor inside one of its own contents.
- A stack of more than 1 item can't become a container.
- A container's quantity can't be raised above 1: the things are inside *this* particular container item, so the inventory row can't stand for two identical boxes with different contents.
- Coins can't be containers (see [Money and Coins](#money-and-coins)).

:::{note}
Unticking **Container** on a container does not delete its contents; instead, they are moved back into your inventory.
:::

### How Nested Contents Are Shown

Contents are listed as their own rows, indented under the container that holds them, to as many levels as you care to nest. A container row with something inside it also gets a **▾ caret**; click it to fold that container's contents away, and click it again to unfold them. This is a per-viewer convenience remembered by your browser: it doesn't change the character's data, and other players see their own view.

A container's Weight column shows the container item's own weight, plus a note of the whole load (including the container's weight):

> **2 lb** (14 lb total)

If you give a container a **capacity** in weight, Zingor also shows how full it is, as a percentage of that capacity:

> [cap: 30 lb] 47% full

A capacity given as a *volume* is recorded and displayed, but no fill percentage is shown for it, since items have weights rather than volumes to measure against it. A container filled past its capacity is shown above 100% rather than being capped. This is a convenience feature so that you don't have to tediously drag items into a container in the correct order just to avoid hitting a hardcoded capacity limit.

## Splitting a Stack

Stack splitting is how you can divide a large number of identical items between multiple places. For example, you might want to carry 20 arrows in a quiver and 20 more wrapped in a piece of leather in your backpack.

A stack of more than one item has a **Split** button. Click it, type how many to split off, and click **Split**,  that many of the items in the stack will be moved to a second inventory row, keeping the same name, per-unit weight, container, and Worn/Carried flags. From there you can interact with the new row independently, such as by dragging it into a different container or marking it as not carried.

Nothing is created or destroyed in this process: the two rows still add up to the original quantity, and your character's encumbrance and wealth are unchanged. 

## Money and Coins

Money is added from the "Add Coins" form at the bottom of the Inventory section: enter a number of coins, choose **GP**, **SP**, or **CP**, and click **Add Coins**.

Adding coins tops up the character's loose carried stack of that currency if there is one, and starts a new stack if there isn't. The **Money** line in the Identity section is derived by summing up every coin stack your character has, wherever it happens to be: loose, stashed in a chest on your cart, or not carried at all.

:::{note}
Coins are ordinary inventory items in Zingor, not a separate money field. That means a coin stack behaves like any other row: you can split it, drag it into a container, edit its quantity to spend or gain coins, or delete it outright. It also means coins have weight and count toward encumbrance like everything else.
:::

Coin rows differ from other items in only two ways, both following from what coins are:

- **The weight isn't editable.** The weight of each type of coin is set by the game's rules, so Zingor fills it in and shows it. There is nothing to type.
- **There's no Container checkbox.** A pile of coins can't hold other items. (Put the coins in a purse, and make the *purse* a container.)

Money and inventory are also the parts of a character that [external synchronization](external-synchronization.md) deliberately leaves alone: they're managed here in Zingor rather than scraped from an external page.

## Encumbrance and Action Points

At the top of the Inventory section, above the table, you'll see a display like this:

> **Encumbrance:** 84.5 pound / 222 pound (38%)<br>
> **Action Points:** 4 / 5 (4 AP above 44.4; 3 AP above 88.8; 2 AP above 133.2; 1 AP above 177.6)

On the Encumbrance line, the first number is what your character is **currently carrying**; the second is his **maximum encumbrance**. The percentage is the first divided by the second

On the Action Points line, the first number is your **current AP**; the second number is your **maximum AP**. The parenthetical shows the encumbrance thresholds at which your character loses action points.

### What Counts as Carried

Current encumbrance is the total weight of everything in your inventory that has the **Carried** box ticked, including the contents of carried containers (however deeply nested). Untick **Carried** on an item to represent situations like leaving a chest of goods at an inn, or putting items on a wagon which is itself not carried.

Every edit you make to your inventory is immediately reflected in your Encumbrance. Adding, deleting, or splitting items; editing a weight or a quantity; and toggling the Worn and Carried boxes will all recalculate the Encumbrance line, and possibly the Action points line.

:::{note}
If a container is not carried, none of the items inside will be counted as carried.
:::

### How Maximum Encumbrance Is Calculated

Maximum encumbrance is calculated based on two factors: **Strength** and **bodyweight** (the Weight field in the Identity section). Strength gives a base carrying figure from the rules' encumbrance table. That figure is then scaled by the character's bodyweight relative to a 175 lb standard, and the result is rounded to the nearest pound. Therefore, all else being equal, a heavier character of a given Strength can carry proportionally more than a lighter one. Sage abilities and character-specific rules from the [Character Background Generator](https://wiki.alexissmolensk.com/index.php/Character_Background_Generator) may further alter your character's maximum encumbrance in some fashion.

:::{warning}
If either Strength or bodyweight is unset, Zingor shows no maximum encumbrance or encumbrance percentage.
:::

### How Action Points are Calculated

Action Points follow from maximum encumbrance. A typical character has 5 AP when unburdened or carrying a relatively light load. The range from nothing to their maximum is divided into five equal tiers, and each tier boundary crossed costs 1 AP. The thresholds are listed next to the AP figure so you can see what the next pound will cost you.

### Strength and Conditions That Change It

Because maximum encumbrance is derived from Strength, anything that changes Strength changes what the character can carry. Conditions can do exactly that: add a condition in the Conditions section with modifier type **Ability** and target **Strength**, and your encumbrance figures will be recomputed against the modified Strength. Removing or deactivating the condition puts them back.

At the top of the human range this is subtler than it looks, because of exceptional Strength: for a character with Strength 18, a +1 modifier raises the *percentile* by 10 rather than raising the score to 19, and the encumbrance table treats each percentile band as its own step. A negative modifier walks back down the same ladder.

A Strength condition can also be scoped, using the **Encumbrance only** option in the scope dropdown when adding a condition. The two settings differ in reach:

- **All (no scope)**: The condition changes your character's Strength in all cases. The Ability Scores section shows the modified score alongside the base one, and every Strength-derived stat (e.g. to-hit and damage modifiers) changes along with maximum encumbrance.
- **Encumbrance only**. The condition applies solely to the encumbrance calculation. Maximum encumbrance and Action Points change, but the character's displayed Strength score and their other Strength-derived stats do not.

Use the encumbrance-only form when a spell, item, or background detail's effect explicitly only affects carrying capacity. Use the unscoped form for anything that makes the character stronger or weaker in all respects.
