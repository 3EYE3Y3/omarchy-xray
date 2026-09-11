# Upstream compatibility

Inspected on 2026-09-11 in the live installation; local files and commands were treated as authoritative.

| Component | Inspected value |
|---|---|
| Omarchy | `4.0.2-1` |
| Plugin manifest API | schema version `1` |
| Quickshell | `0.3.1` (Arch build) |
| Hyprland | `0.56.2` |

## Plugin contract

X-Ray uses plugin id `io.github.3eye3y3.xray`, kind `overlay`, entry point `XRay.qml`, and `keepLoaded: true`. Schema 1 requires `id`, `name`, `version`, a non-empty `kinds` array, and `entryPoints`; overlay entry points must be safe relative files. Plugin folders may contain no symlinks (except Git internals are excluded by the validator). The supported kinds in this installation are `bar`, `bar-widget`, `menu`, `overlay`, `panel`, and `service`.

User plugins are Git checkouts at `~/.config/omarchy/plugins/<plugin-id>/`. `omarchy plugin add <git-url> --enable --yes` clones, validates, rescans, then enables. Saves below the user plugin directory hot-reload; `omarchy-shell shell rescanPlugins` forces discovery, while `omarchy restart shell` restarts the whole shell. Removal is supported by `omarchy plugin remove <id> --yes`. X-Ray never modifies `/usr/share/omarchy`.

## APIs used

- `PanelWindow`, `WlrLayershell`, `WlrKeyboardFocus.None/Exclusive`, `Variants`, `Process`, and `StdioCollector` from the installed Quickshell API.
- `Color.menu`, `Color.muted`, `Color.urgent`, and `Style` spacing/font/radius tokens from `qs.Commons`.
- `omarchy-shell shell summon io.github.3eye3y3.xray <json>` for lazy opening.
- `hyprctl activewindow -j`, `hyprctl clients -j`, and `hyprctl monitors -j` through the bounded probe runner.
- `/proc` and `/sys`, plus direct-argv calls to system inspection tools documented in the README.

Relevant inspected paths:

- `/usr/share/omarchy/bin/omarchy-plugin-{add,enable,remove,validate}`
- `/usr/share/omarchy/shell/services/PluginRegistry.qml`
- `/usr/share/omarchy/shell/plugins/README.md`
- `/usr/share/omarchy/shell/plugins/{emojis,reminders,panels/monitor}`
- `/usr/share/omarchy/shell/Commons/{Color,Style}.qml`
- `~/.config/omarchy/shell.json`
- `~/.config/hypr/bindings.lua`

## Assumptions and limitations

- Compatibility is asserted for Omarchy 4.0.x/schema 1. Future manifest schemas or renamed theme tokens require revalidation.
- The QML UI expects the plugin checkout to contain Python 3.11+ and calls its colocated `bin/xray`; no package install is needed.
- Vision follows mapped visible Hyprland clients on known monitors. Compositor geometry is authoritative, but unusual output transforms/fractional scaling may cause small overlay offsets.
- Plugin code is unsandboxed by Omarchy, as its installer warning states. X-Ray mitigates this with direct argv execution, bounded output, timeouts, and read-only behavior.
- `SUPER+X` was already assigned to Universal cut, so X-Ray does not claim it.
