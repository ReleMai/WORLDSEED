# WORLDSEED RC3 — terminal UI research notes

RC3's navigation redesign was based on patterns used by mature terminal UI systems rather than on another set of feature-specific key checks.

## Findings applied

### 1. Screen stacks are the right abstraction for Back
Textual models active views as a screen stack: pushing a screen makes it active, popping restores the previous screen, and the base/root screen is not casually discarded. WORLDSEED now mirrors that behavior with `NavigationStack` and `RouteState`.

### 2. Only the top/modal UI should own input
Textual modal screens and prompt_toolkit modal containers prevent parent bindings from firing while a child has focus. Urwid overlays similarly direct keyboard input to the top widget. WORLDSEED follows the same rule conceptually: the top route is the only route reading keys.

### 3. UI state must be explicit
Ratatui's application patterns recommend explicit current-screen/application-mode state and the Elm-style Model → Update → View separation. WORLDSEED retains route selection and pager scroll as explicit state rather than reconstructing menus after every child closes.

### 4. Back is navigation; Quit is application control
Inside a menu or detail view, ESC means Back. At a feature root, ESC dismisses that feature to gameplay. Only gameplay root interprets Q as save/quit. Q remains an optional Back alias inside modal menus for accessibility.

### 5. Breadcrumbs must reflect actual navigation state
Breadcrumbs are derived from the route stack, so `World Console > Records > World Ledger > People` corresponds to actual restorable parent states rather than decorative labels.

## WORLDSEED invariants

```text
ESC on child       -> pop exactly one route
ESC on feature root -> return to gameplay
push child         -> preserve parent selected row + scroll
close detail       -> restore exact parent
only top route     -> receives input
rendering          -> never mutates simulation
Q at gameplay root -> save and quit
```

## Relevant upstream documentation reviewed

- Textual — Screens / screen stack / modal screens
  https://textual.textualize.io/guide/screens/
- Textual — App `push_screen` / `pop_screen`
  https://textual.textualize.io/api/app/
- Ratatui — application screen state and modes
  https://www.ratatui.rs/tutorials/json-editor/app/
- Ratatui — The Elm Architecture
  https://www.ratatui.rs/concepts/application-patterns/the-elm-architecture/
- prompt_toolkit — modal containers and key-binding isolation
  https://python-prompt-toolkit.readthedocs.io/en/stable/pages/reference.html
- Urwid — overlays keep top widget focused for input
  https://urwid.org/manual/widgets.html


## RC4 finding — normalize keys before navigation

The RC3 stack logic was correct, but platform adapters were not producing a single key vocabulary. On Windows, WORLDSEED uses `msvcrt.getwch()`, which returns a single character from the console; the physical Escape key arrives as the literal escape character (`\x1b`). The Unix parser had already converted standalone Escape to `ESC`, so Windows and Unix were feeding different values into identical menu code. RC4 adds terminal-boundary normalization and widget-level defensive normalization.

The retained-screen design remains aligned with Textual's screen-stack model: only the top screen receives input and popping restores the previous screen. Prompt-toolkit similarly treats key parsing/bindings as a distinct layer from application actions; WORLDSEED now follows the same separation by canonicalizing backend input before menu semantics are applied.
