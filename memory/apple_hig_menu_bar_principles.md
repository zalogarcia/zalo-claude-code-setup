---
name: Apple HIG Menu Bar Design Principles
description: Comprehensive design principles extracted from Apple's Human Interface Guidelines for menu bars — covers anatomy, ordering, labeling, keyboard shortcuts, dynamic items, platform differences (macOS/iPadOS), and menu bar extras
type: reference
---

# Apple HIG: Menu Bar Design Principles

Source: https://developer.apple.com/design/human-interface-guidelines/the-menu-bar
Extracted: 2026-04-04

---

## 0. Cross-Platform Consistency & General Menus

- **Adopt the menu structure people expect from Mac** — this helps them immediately understand and use the menu bar on iPad as well.
- **iPadOS keyboard shortcuts use the same patterns as macOS.**
- **Menu bar menus share appearance and behavior with all menu types.** For general menu organization and labeling guidance, see the separate Apple HIG "Menus" page.
- **Not supported** on iOS, tvOS, visionOS, or watchOS.

---

## 1. Menu Bar Anatomy & Ordering

Menus must appear in this exact order when present:

1. **App Name** (bold, short version of app name)
2. **File**
3. **Edit**
4. **Format**
5. **View**
6. **App-specific menus** (custom menus go here)
7. **Window**
8. **Help**

Additionally on macOS: Apple menu on leading side, menu bar extras on trailing side.

---

## 2. Core Best Practices

- **Support default system-defined menus and their ordering.** People expect familiar order. The system implements many standard item behaviors automatically.
- **Always show the same set of menu items.** Never hide menu items based on context — **disable** unavailable items instead. This helps people learn what your app can do.
- **Use familiar icons for menu item actions.** Use the same system icons for Copy, Share, Delete, etc. wherever they appear.
- **Support standard keyboard shortcuts.** People expect Cmd+C, Cmd+X, Cmd+V, Cmd+S, Cmd+P etc. Define custom shortcuts only when necessary.
- **Prefer short, one-word menu titles.** They take less space and are easy to scan. If multi-word is needed, use title-style capitalization.

---

## 3. App Menu

- Lists items that apply to the app as a whole, not to a specific task/document/window.
- App name displayed in **bold** to identify the active app.
- **Display the About item first**, with a separator after it (its own group).
- Use a short app name (16 characters or fewer) for About. Don't include version numbers.
- "Settings..." opens app-level settings only. Document-specific settings go in File menu.
- Custom app-config items go **after** Settings, in the same group.
- Use the **same short app name** consistently in About, Hide, and Quit items.
- Option key changes "Quit AppName" to "Quit and Keep Windows".

**Standard order:** About > Settings > Custom items > Services > Hide App > Hide Others > Show All > Quit

---

## 4. File Menu

- Contains commands for managing files/documents.
- If app doesn't handle files, you can rename or eliminate this menu.
- **New Item:** Use a term that names what your app creates (e.g., "New Event", "New Calendar").
- **Open:** If it requires a file picker, add an ellipsis ("Open...").
- **Open Recent:** List document names (not file paths), ordered by most recently opened first. Include "Clear Menu".
- **Close:** Option key changes to "Close All". In tab-based windows, "Close Tab" replaces "Close". Option changes "Close Tab" to "Close Other Tabs".
- **Close Tab:** In tab-based windows, replaces Close. Option changes to "Close Other Tabs". Consider also adding a "Close Window" item so people can close the entire window in one action.
- **Close File:** Consider supporting if your app can open multiple views of the same file.
- **Save:** Auto-save periodically so people don't have to keep choosing Save. Prompt for name/location on first save. For multi-format saving, prefer a **pop-up menu** in the Save sheet for format selection.
- **Save All:** Saves all open documents.
- **Duplicate** preferred over "Save As", "Export", "Copy To", "Save To" — these don't clarify the relationship between original and new file. Option changes Duplicate to "Save As".
- **Rename.../Move To...:** Standard items for renaming and relocating documents.
- **Export As...** reserved for formats the app doesn't typically handle. Current document remains open; exported file doesn't open.
- **Revert To:** When autosaving is on, shows a submenu of recent versions and a version browser option. Chosen version replaces the current document.
- **Page Setup...** only for document-specific printing parameters. Global parameters (printer name) and frequently changed ones (copies) belong in Print panel.

---

## 5. Edit Menu

- For changes to content in current document/text container and Clipboard operations.
- Useful even in non-document apps.
- **Undo/Redo:** Clarify the target — append the action name (e.g., "Undo Paste and Match Style", "Undo Typing").
- **Delete** not "Erase" or "Clear" — naming must match the Delete key behavior.
- **Find items:** Consider whether they belong in Edit or File menu depending on what's being searched.

**Standard order:** Undo > Redo > Cut > Copy > Paste > Paste and Match Style > Delete > Select All > Find > Spelling and Grammar > Substitutions > Transformations > Speech > Start Dictation > Emoji & Symbols

---

## 6. Format Menu

- For text formatting attributes. Exclude if app doesn't support formatted text.
- Standard items: **Font** submenu (Show Fonts, Bold, Italic, Underline, Bigger, Smaller, Show Colors, Copy/Paste Style) and **Text** submenu (alignment, writing direction, ruler).

---

## 7. View Menu

- Customizes appearance of **all** app windows, regardless of type.
- **Does NOT include** navigation between or managing specific windows (that's Window menu).
- **Provide a View menu even for a subset of view functions.** Even if only full-screen mode is supported.
- **Show/Hide toggle titles must reflect current state.** "Show Toolbar" when hidden, "Hide Toolbar" when visible.

**Standard items:** Show/Hide Tab Bar > Show All Tabs/Exit Tab Overview > Show/Hide Toolbar > Customize Toolbar > Show/Hide Sidebar > Enter/Exit Full Screen

---

## 8. App-Specific Menus

- Appear **between View and Window** menus.
- **Always put custom commands in the menu bar** — even infrequent or advanced ones. This makes them discoverable, keyboard-shortcuttable, and accessible via Full Keyboard Access.
- **Reflect app hierarchy** in menu ordering (e.g., Mail: Mailbox > Message > Format mirrors containment).
- **Order from most general/commonly-used to least.** People expect leading menus to be more specialized.

---

## 9. Window Menu

- For navigating, organizing, and managing windows.
- Does **NOT** customize window appearance (View menu) or close windows (File menu).
- **Always provide a Window menu, even for single-window apps.** Include Minimize and Zoom for Full Keyboard Access.
- **Consider adding show/hide items for panels** (but not font/color panels — those are in Format menu).
- **Avoid using Zoom for full-screen** — Enter/Exit Full Screen belongs in View menu.
- **List open windows alphabetically** for easy scanning. Don't list panels or modal views.
- Option key variants: Minimize → Minimize All, Zoom → Zoom All, Bring All to Front → Arrange in Front.
- Include Enter/Exit Full Screen in Window menu **only if there's no View menu**.

---

## 10. Help Menu

- Always the **trailing-most** menu in the menu bar.
- **macOS auto-includes a search field** at the top of the Help menu when using the Help Book format.
- **Standard items:** "Send YourAppName Feedback to Apple" (opens Feedback Assistant) and "YourAppName Help" (opens Help Viewer when using Help Book format).
- Keep the number of additional items **small** to avoid overwhelming people when they need help.
- Use a **separator** between primary help docs and additional items (registration info, release notes).
- Consider linking additional items from within help documentation instead of adding menu items.

---

## 11. Dynamic Menu Items

- Menu items that change behavior when a modifier key is pressed (e.g., Minimize → Minimize All with Option).
- **Never make a dynamic item the only way to accomplish a task.** They're hidden by default — use as shortcuts to advanced actions.
- **Use primarily in menu bar menus only** — not in contextual or Dock menus.
- **Require only a single modifier key.** Multiple keys + menu navigation is physically awkward and reduces discoverability.
- macOS auto-sets menu width to hold the widest item, including dynamic items.

---

## 12. iPadOS-Specific Principles

- Menu bar is **hidden until revealed** (pointer to top edge or swipe down). On macOS it's always visible.
- **When visible, the menu bar occupies the same vertical space as the status bar** at the top edge of the screen.
- Menus are **horizontally centered** (vs. leading-aligned on macOS).
- No menu bar extras, no Apple menu.
- App menu excludes About, Services, and app visibility items.
- Window controls appear in menu bar when full screen.
- **Ensure all functions are accessible through the app's UI** — menu bar is often hidden full-screen.
- **Always offer alternative ways to accomplish dynamic menu item tasks** (only available with hardware keyboard).
- **Don't use menu bar as catch-all** for functionality that doesn't fit elsewhere.
- Settings menu item should open the app's page in **iPadOS Settings**. Internal preferences use a separate menu item beneath Settings.
- **For tab-style navigation, add each tab as a View menu item** with key bindings.
- **Group items into submenus more aggressively than Mac** — iPad menu rows are taller (touch targets), and screens can be smaller.

---

## 13. macOS-Specific Principles

- Apple menu is always first (leading side), system-defined, unmodifiable.
- Menu bar extras appear on trailing end, space permitting.
- When space is constrained, system decreases spacing between titles, truncating if necessary.
- Full-screen mode hides menu bar until pointer moves to top of screen.

### Menu Bar Extras

- A menu bar extra **appears even when the app is not the frontmost app** — it persists while the app is running.
- Use a **symbol** (SF Symbol or custom icon) — black and clear colors for shape. System recolors for dark/light modes and selection state. Menu bar height is **24pt**.
- **Display a menu, not a popover**, when clicked — unless functionality is too complex for a menu.
- **Let users decide** whether to show the menu bar extra (typically via app settings). Consider offering the option during setup.
- **Don't rely on menu bar extras being visible** — system hides/shows them regularly. The system **prioritizes app menus over extras** and may hide extras to avoid crowding. If there are too many extras, the system may hide some.
- **Expose functionality through other channels too** (e.g., Dock menu via Control-click). A Dock menu is always available when the app is running.

---

## 14. Labeling & Naming Conventions

- Use **title-style capitalization** for multi-word menu titles.
- Use **ellipsis (...)** after items that require additional input before executing.
- Name the item after what it does, not how (e.g., "Delete" not "Remove from list").
- Keep menu item names concise and scannable.

---

## 15. Accessibility & Discoverability

- All commands should be in the menu bar — this makes them accessible to Full Keyboard Access users.
- Excluding commands from the menu bar (even rare ones) risks making them hard for everyone to find.
- Standard keyboard shortcuts are critical for accessibility.
- Show/Hide toggles help users understand current state.
- Disabled (not hidden) items teach users what's possible.
