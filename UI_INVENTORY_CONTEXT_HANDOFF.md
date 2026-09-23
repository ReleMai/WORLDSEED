# Inventory and context UI handoff

The graphical inventory and container panels now use a warmer framed surface, clearer item slots and hover feedback. Storage shows mass and volume capacity gauges. The world right-click menu and item action menu use the same compact button panel, opening from the click point with a 145 ms ease-out. Button hit regions are registered at the final position, including when the menu is clamped against a window edge. The quantity label in the narrow inventory detail pane has been shortened to prevent overlap.

- Scope: `worldseed/ui/pygame_terminal.py`, `tests/test_dev37_floating_interaction_ui.py`.
- Simulation/save contracts: unchanged. Rendering and popup animation are observational; existing action tokens still dispatch through the menu widget.
- RNG and persistence: none.
- Verification: `SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy PYTHONPATH=repo python -m unittest discover -s repo/tests -p test_dev37_floating_interaction_ui.py -v` (9 passed); compileall of the changed files passed. Inventory and natural-container layouts were rendered and visually inspected at 1280 × 800.
- Performance: one 145 ms opening animation on a new menu, no continuous animation or additional simulation work. Repaints keep the menu open without replaying its opening animation.
- UI: floating panels retain drag, resize, filtering, item transfer, quantity controls, keyboard selection and Esc; the context menu preserves click actions and location labels.
- Known limit: the terminal backend keeps its existing text presentation. No new assets are required.
