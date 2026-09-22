# WORLDSEED Unified Inventory Validation

Parallel UI Track 1 redesigns the pygame inventory without changing inventory ownership or simulation authority.

## Player-facing contract

- I opens one inventory surface.
- Carried items are visible as clickable icon cards.
- Selection updates the detail pane in place.
- Use, Drop, Split and Store are available directly beside the selected item when legal.
- Split only changes the selected action quantity; it does not create a second persistent stack representation.
- Executing an action keeps the inventory open.
- Terminal mode keeps the previous hierarchical fallback.

## Authority contract

The renderer only emits pointer/keyboard intent tokens. Item mutations remain in existing simulation commands:

- EatCommand
- EquipCommand
- ReadBookCommand
- DropCommand
- StoreCommand

No pygame callback mutates Inventory, world piles, equipment or time directly.

## Targeted regression coverage

- Structured feature-menu data still reaches the pygame renderer.
- UI_ACTION tokens pass through the shared menu widget to the inventory owner.
- Unified inventory item cards remain pointer-selectable at small and large window sizes.
- A real pygame flow selects a four-item Wood stack, chooses Split (2), drops that amount, stays inside the inventory flow, and leaves two Wood in the authoritative Inventory.
- Existing terminal navigation tests remain unchanged and continue to exercise the fallback inventory.

## Manual checks

1. Open inventory with I and confirm there is no Pack/Browse duplication.
2. Click several item icons and confirm the grid never disappears while details update.
3. For food, confirm Use is labeled as Eat and consumes one item.
4. For equippable gear, confirm Use equips the item through the existing equipment command.
5. With a stack larger than one, click Split and verify Drop/Store uses the displayed half-stack amount.
6. Adjust quantity with - / + / All and verify the selected amount never exceeds the carried count.
7. Stand near a storage container and verify Store becomes enabled; move away and verify it is disabled.
8. Resize to 800x520 and 1600x900 and confirm cards/actions remain inside the window and above the footer.
9. Verify Esc returns directly to gameplay from the graphical inventory.
