# SPDD Analysis: Eliminate Player TUI Flicker When Terminal Is Unfocused/Backgrounded

## Original Business Requirement

> when the player is not in focus, especially when terminal window is in the background, it flickers. i want that resolved.

## Domain Concept Identification

### Existing Concepts (from codebase)

- **Player Session** (`cli/player/app.py::PlayerApp`): the long-lived interactive TUI session. Owns the `EventBus`, the main loop, and the lifecycle of all UI components. Runs at a fixed 0.25s `Tick` cadence with a 0.05s bus poll.
- **Renderer** (`cli/player/renderer.py::Renderer`): the sole owner of the primary `rich.live.Live` display. Subscribes to ~11 event types; every one of them calls `_refresh()` → `_build_panel()` → `Live.update()`. It is stateless with respect to what was last painted — it has no notion of "unchanged frame".
- **Live Display** (`rich.live.Live`): the terminal-painting mechanism. Currently constructed as `Live(refresh_per_second=4, transient=True)` with `auto_refresh` left at its default (`True`) and `screen` left at its default (`False`). This is the concept at the centre of the defect.
- **Terminal Viewport**: an implicit, un-modelled concept. The panel's geometry is derived by calling `shutil.get_terminal_size()` **three separate times** inside a single `_build_panel()` call (`renderer.py:248`, `:276`, `:333`) — for the progress-bar width, the queue-row count, and the horizontal rule width. Rich's own `Console` independently derives a fourth notion of width. There is no single authoritative viewport value.
- **Input Handler** (`cli/player/input.py::InputHandler`): background thread holding the tty in cbreak mode; `pause()`/`resume()` restore and re-enter cbreak for modal flows.
- **Modal Overlays** (`browser.py`, `editor.py`, `importer.py`): each stops the main `Live` via `Renderer.pause()` and opens its *own* `Live` at `refresh_per_second=10` on a *module-level* `Console()` instance — three distinct `Console` objects exist (`browser.py:73`, `editor.py:105`, `importer.py:19`) plus `cli/play.py:21`.
- **Event Bus** (`events/bus.py::EventBus`): a plain `queue.Queue` with no coalescing or deduplication. Every emitted event is dispatched individually; several event types map to a full repaint.

### New Concepts Required

- **Frame / Render Budget**: an explicit notion of "when is a repaint warranted". Currently repainting is unconditional and time-driven; it needs to become change-driven. Relates to Renderer and Event Bus (multiple queued repaint-triggering events between two frames should collapse into one paint).
- **Viewport Snapshot**: a single terminal-geometry value resolved once per frame from one authoritative source (Rich's `Console.size`), replacing the three independent `shutil` calls. Relates to Renderer and Live Display.
- **Render State Fingerprint**: a cheap comparable representation of everything the panel displays (track identity, play/pause state, whole-second position, browse/move index, queue ordering, import status, viewport dims). Enables skip-if-unchanged. Relates to Frame Budget.
- **Display Mode / Alternate Screen policy**: an explicit decision about whether the player owns the alternate screen buffer for its lifetime, rather than inheriting Rich's inline scrollback-repaint default. Relates to Live Display and Modal Overlays.

### Key Business Rules

- **The visible frame must be a whole frame**: the user must never observe a partially-erased or partially-redrawn panel. Governs Renderer, Live Display.
- **A repaint must only occur when the rendered content actually differs from what is on screen**: governs Renderer, Frame Budget, Event Bus.
- **Exactly one component may write to the terminal at a time**: governs Renderer and Modal Overlays — the main `Live` and any modal `Live` must be strictly mutually exclusive, and the tty must not be shared between the input thread's mode switching and an active paint.
- **All terminal geometry within a single frame must come from one consistent measurement**: governs Viewport Snapshot. A frame whose progress bar assumes 200 columns while its queue rows assume 80 is internally inconsistent.
- **Panel line count must be stable across consecutive frames unless the terminal was genuinely resized**: this is the invariant whose violation produces the reported flicker in non-alternate-screen mode. Governs Renderer.
- **Terminal state must be restored on every exit path**, including crash and `SIGINT` — already partially honoured via `atexit` in `InputHandler`, and any alternate-screen decision must preserve this. Governs Player Session.
- **Playback must be unaffected by rendering decisions**: skipping or throttling frames must never delay `TrackEnded` detection, the polling fallback in `_check_track_finished`, or key handling. Governs Player Session.

## Strategic Approach

### Solution Direction

Move the player's rendering from **unconditional, time-driven, inline repainting** to **conditional, change-driven painting on a stable, exclusively-owned viewport**.

Three reinforcing changes, in order of expected impact:

1. **Own the screen.** Have the player's `Live` take the alternate screen buffer for the session's lifetime instead of repainting inline in the scrollback. Inline mode repaints by moving the cursor up N lines and erasing them; if N differs between frames — which it does here, see below — the terminal shows a collapse-and-regrow, which reads exactly as "flicker". On the alternate screen the repaint is a bounded, in-place overwrite of a fixed region.

2. **Single source of geometry, resolved once per frame.** Replace the three independent `shutil.get_terminal_size()` calls with one viewport value taken from the same `Console` that Rich paints with. The strong suspicion for the *unfocused/backgrounded* specificity of the report is here: geometry queries against a backgrounded or non-foreground tty can fall back to defaults (80×24) or return stale values, and because the three call sites are independent they can disagree *within one frame* and *between adjacent frames*. Since `max_queue_rows = max(3, lines - 14)` directly controls the panel's line count, an oscillating `lines` value directly violates the stable-line-count invariant — this is the most plausible mechanism behind the exact symptom described.

3. **Paint only on change, and paint from one clock.** Currently there are two uncoordinated paint sources at the same nominal rate: Rich's own auto-refresh thread (`refresh_per_second=4`) and the main loop's `Tick` handler calling `Live.update()` (also 4 Hz, plus every other subscribed event). Their phases drift, so the panel is repainted roughly twice per cycle at arbitrary offsets. Collapsing to a single driver — and gating that driver on a render-state fingerprint so a paused, idle player paints ~zero frames per second — removes both the double-paint and the pointless repaints that a background-throttled terminal renders as tearing.

Data flow direction: *event → renderer state mutation → mark dirty* (no paint), then *single main-loop frame boundary → resolve viewport → build fingerprint → if changed, build panel and paint once*.

### Key Design Decisions

- **Alternate screen (`screen=True`) vs. staying inline**: trade-off is that the alternate screen removes the player's output from scrollback and requires disciplined teardown on every exit path (crash, `SIGINT`, `SIGTSTP`), while inline mode keeps history but is structurally prone to erase-and-redraw flicker whenever panel height varies. → **Recommend alternate screen.** The player is a full-screen, transient TUI (`transient=True` already signals the intent to leave no trace); scrollback of a now-playing panel has no value, and the current `transient` behaviour already discards it. Note this interacts with the modal overlays, which currently print into scrollback — see Risks.

- **Where to place refresh authority — Rich's auto-refresh thread vs. the main loop**: trade-off is that auto-refresh guarantees liveness even if the main loop stalls, while main-loop-driven painting gives a single deterministic frame boundary and makes dirty-checking meaningful (with auto-refresh on, Rich will repaint stale content regardless of what the renderer decides). → **Recommend disabling auto-refresh and painting explicitly from the main loop.** The main loop already ticks reliably at 0.25s and is the only place that can know a frame is complete.

- **Dirty-check granularity — fingerprint comparison vs. rendered-output comparison vs. per-field dirty flags**: rendered-output comparison is the most correct but requires building the panel anyway (saves the terminal write, not the CPU); per-field flags are cheapest but scatter invalidation logic across every handler and will rot; a fingerprint is built cheaply from already-available state. → **Recommend the fingerprint**, computed at the frame boundary. It must include the viewport dimensions so genuine resizes still repaint.

- **Progress-bar update granularity**: the bar currently changes on sub-second position deltas, so almost every frame is "dirty" by strict comparison. → **Recommend quantising the position into the fingerprint at the granularity the UI can actually show** (whole seconds for the timestamps; the filled-cell count for the bar). A paused player then produces a genuinely stable fingerprint and paints nothing.

- **Frame rate**: 4 Hz is already modest; the problem is double-painting and unconditional painting, not the nominal rate. → **Recommend keeping 4 Hz as the *maximum*** rather than raising or lowering it, and letting dirty-checking drive the actual rate down. Deliberately *lowering* the rate to hide flicker would be treating the symptom.

- **Console instance ownership**: four module-level `Console()` objects exist across the player and `cli/play.py`, each with independent size caching and state. → **Recommend a single Console owned by the player session and injected into the renderer and the modal flows.** This is a prerequisite for decision 2 being meaningful, and it is the CLI-layer analogue of the project's constructor-injection convention (`bootstrap.py` builds the graph; components receive dependencies).

- **Scope: renderer-only vs. renderer + modals**: the report names "the player" specifically. → **Recommend fixing the main renderer as the primary scope, with the modal `Live` instances brought onto the shared Console and the shared display-mode policy**, since a modal that paints inline while the main display owns the alternate screen would introduce a *new* class of visual artefact.

### Alternatives Considered

- **Lower `refresh_per_second` to 1–2**: rejected. It reduces how often the artefact is visible without removing it, and it degrades progress-bar and key-response feel. The double-paint and the unstable line count remain.
- **Switch the whole player to a full TUI framework (Textual / curses)**: rejected for this requirement. It would resolve the class of problem structurally, but it is a rewrite of `renderer.py`, `browser.py`, `editor.py`, and `importer.py` — far beyond a defect fix, and Rich is an existing, already-pinned dependency (`rich>=13.0`) whose `Live` supports every mechanism needed here.
- **Detect terminal focus (via focus-reporting escape sequences, `\x1b[?1004h`) and suspend rendering when unfocused**: rejected as the primary fix. It is poorly supported across terminals, adds another escape-sequence consumer competing with the input thread's parser (which currently discards unknown sequences at `input.py:99`), and it papers over the underlying instability rather than removing it. It could be a *later* optimisation once the render path is correct.
- **Diff-and-patch only the changed lines instead of the whole panel**: rejected. It duplicates what Rich's `Live` already does internally and would require hand-managing cursor positioning, which is precisely where the current artefact originates.

## Risk & Gap Analysis

### Requirement Ambiguities

- **"Flickers" is not characterised**: the requirement does not distinguish between (a) the whole panel blanking and reappearing, (b) the panel visibly collapsing/regrowing in height, (c) horizontal tearing mid-frame, (d) the cursor visibly jumping. Each points at a different mechanism. The strategic direction above addresses (a)–(c); if the actual complaint is (d), cursor-visibility handling is the fix. **Needs clarification, ideally with a screen recording.**
- **"Not in focus" vs. "in the background" are stated as related but distinct conditions** ("especially when"). Does flicker also occur in the foreground focused case, at lower intensity? If yes, the double-paint is likely the dominant cause; if it *only* occurs unfocused, geometry-query fallback is likely dominant. This determines which of the three changes carries the fix.
- **Terminal emulator and multiplexer are unstated.** iTerm2 throttles rendering of unfocused windows by default; tmux/screen introduce their own repaint semantics and their own size reporting. Reproduction depends on knowing this.
- **No acceptance criteria were supplied.** There is no stated definition of "resolved" and no stated observation window. Proposed in the AC table below and flagged for confirmation.
- **Whether losing the player panel from scrollback is acceptable** is not addressed by the requirement but is a user-visible consequence of the recommended alternate-screen decision. (Mitigated by the fact that `transient=True` already discards it today.)

### Edge Cases

- **Terminal resized while the window is backgrounded**: the geometry change is only observable on the next query. Without a stable viewport concept the panel can jump on refocus; with a fingerprint that includes dimensions it repaints exactly once. Matters because it is the legitimate case that must *not* be suppressed by dirty-checking.
- **Terminal narrower than the panel's minimum**: `bar_width = max(10, term_width - 23)` and the raw `Text("─" * (columns - 4))` at `renderer.py:333` — the latter has no floor and produces a negative multiplier below 4 columns. Content wrapping at narrow widths changes the panel's line count, re-triggering the exact instability being fixed.
- **Terminal shorter than 17 lines**: `max_queue_rows = max(3, lines - 14)` floors at 3, but the total panel content can then exceed the viewport, engaging Rich's overflow cropping — whose behaviour differs between alternate-screen and inline modes.
- **Backgrounded via `SIGTSTP` (Ctrl-Z) and resumed with `fg`**: terminal mode and, under alternate-screen, the screen buffer must be re-established. There is currently no `SIGTSTP`/`SIGCONT` handling anywhere in the player; `InputHandler` restores via `atexit` only.
- **stdout is not a tty** (piped, or running under the headless service path): `Live` degrades differently and geometry queries return fallbacks unconditionally. The player is interactive-only, but the failure mode should be explicit rather than incidental.
- **Modal overlay open while the terminal is backgrounded**: the main `Live` is stopped and a second `Live` at 10 Hz is running on a different `Console` — the same defect class, at 2.5× the rate, with no dirty-checking at all.
- **Import running in the background while the panel is up**: `ImportTrackDownloaded` events arrive at network-driven rates and each triggers a full repaint via `_on_import_track`. Bursts produce paint storms independent of the 4 Hz tick — a concrete case where event coalescing at the frame boundary matters.
- **The `_import_done` auto-dismiss at 10 seconds** (`renderer.py:349`) mutates renderer state *inside* `_build_panel()`. A dirty-check that decides not to build the panel would also never expire the banner. Time-based state expiry must move out of the build path.
- **Queue empty, or `current_track()` returning `None`**: the panel collapses to a one-line `Panel` (`renderer.py:209`) — a dramatic line-count change, and the fingerprint must handle it without a null-dereference.
- **Zero-length or unknown-duration track**: `progress_pct` guards `dur > 0`, but the fingerprint's position quantisation must not divide by zero.

### Technical Risks

- **Alternate-screen teardown on abnormal exit**: if the process dies without restoring the primary buffer, the user's terminal is left in a broken state — a strictly worse outcome than flicker. Mitigation: teardown registered on the same `atexit` path already used for termios restoration, plus explicit handling in `PlayerApp.run`'s `finally` block (which currently calls `renderer.stop()` before `input.stop()`).
- **Two threads touching the tty**: `InputHandler` runs `tcsetattr` on a background thread while the main thread paints. Today this is tolerated; under alternate-screen and explicit painting the ordering of mode switches versus screen switches becomes load-bearing. Mitigation: make `Renderer.pause()`/`resume()` and `InputHandler.pause()`/`resume()` a single ordered sequence rather than two independent calls made at three different call sites (`browser.py:133`, `editor.py:151`, `importer.py:84`).
- **`Renderer.resume()` is currently a latent bug** (`renderer.py:149`): it calls `Live.start()` on the same `Live` object that `pause()` stopped. Restarting a stopped `Live` in place is not a supported lifecycle in Rich and its behaviour has varied across versions — a plausible contributor to artefacts observed *after* a modal closes, which the user may be attributing to the general flicker. Needs verification against the installed Rich version.
- **Dirty-checking can mask real updates** if the fingerprint omits a field that affects the render. Any state that reaches `_build_panel()` — including the cached playlist membership at `renderer.py:315–324` and the import banner fields — must be represented. Mitigation: derive the fingerprint from the same state the panel builder reads, and cover with tests; `test_renderer.py` already exists (211 lines) as the anchor point.
- **Rich version behaviour**: `rich>=13.0` is an open lower bound, and `Live`'s refresh/screen internals are not a stability-guaranteed API surface. A fix validated on one version may behave differently on another. Mitigation: prefer the documented constructor options (`screen`, `auto_refresh`, `refresh_per_second`, `console`) over any internal attribute; note that `_refresh()` already reaches into `Live.is_started`.
- **Reproducibility**: the defect is environment-dependent (emulator, focus state, multiplexer) and may not reproduce on the developer's setup. Verification is inherently manual/visual, which is a real risk for a repo whose convention is TDD with automated tests. Mitigation: unit-test the *invariants* that are automatable — one paint per frame, no paint when state is unchanged, exactly one geometry resolution per frame, stable line count for fixed state and dimensions — and treat visual confirmation as a separate manual acceptance step.
- **Performance is not the concern; correctness of paint is.** Building the panel is cheap. Care is needed not to over-optimise the build path at the cost of the invariants above.
- **The player layer has no port abstraction** — `Renderer` depends directly on `rich.live.Live` and `shutil` in the CLI layer. This is consistent with the project's stated convention that the CLI handles all Rich output inline and that there is no shared presentation layer, so introducing a rendering port would be an architecture change, not a defect fix. Keep the fix inside `cli/player/`.

### Acceptance Criteria Coverage

No acceptance criteria were supplied with the requirement. The following are **proposed** and require confirmation before REASONS Canvas.

| AC# | Description | Addressable? | Gaps/Notes |
|-----|-------------|--------------|------------|
| 1 | Player panel shows no visible flicker while the terminal window is backgrounded/unfocused, observed over ≥60s of continuous playback | Partial | Addressable by the approach, but verification is manual/visual and environment-dependent; the emulator and multiplexer must be pinned down first |
| 2 | Player panel shows no visible flicker while the terminal is focused and in the foreground | Yes | Falls out of the same fix; also serves as the baseline comparison that disambiguates the two causes |
| 3 | No repaint occurs when nothing visible has changed (e.g. paused player, no key input, no import) | Yes | Directly unit-testable via the render-state fingerprint |
| 4 | Exactly one paint occurs per frame boundary regardless of how many repaint-triggering events were queued in that interval | Yes | Unit-testable; requires the single-driver decision (auto-refresh disabled) |
| 5 | Terminal geometry is resolved once per frame from a single source, and all panel sections agree on it | Yes | Unit-testable; replaces the three independent `shutil.get_terminal_size()` call sites |
| 6 | Panel line count is stable across consecutive frames for unchanged state and unchanged dimensions | Yes | Unit-testable; this is the core invariant behind the reported symptom |
| 7 | Genuine terminal resize still repaints promptly and correctly, including while backgrounded then refocused | Yes | Requires viewport dimensions in the fingerprint; partly manual to verify |
| 8 | Terminal state (mode, screen buffer, cursor) is fully restored on normal quit, `Ctrl-C`, and unhandled exception | Yes | Extends the existing `atexit` restoration; the alternate-screen decision makes this mandatory rather than merely desirable |
| 9 | Opening and closing a modal (browser / editor / import prompt) leaves the main panel visually intact with no residual artefacts | Partial | Depends on resolving the `Renderer.resume()` restart-a-stopped-`Live` issue and unifying Console ownership; scope confirmation needed |
| 10 | Playback behaviour is unchanged — track-end detection, key latency, and import progress reporting are unaffected | Yes | Covered by the existing suites in `test_app.py`, `test_controls.py`, `test_renderer.py` |

**Coverage gap**: ACs 1, 7, and 9 cannot be fully closed by automated tests. A manual verification protocol — named terminal emulator, backgrounded window, fixed observation window — should be agreed as part of the definition of done.

**Open questions to resolve before REASONS Canvas**:
1. Which terminal emulator, and is tmux/screen involved?
2. Does the flicker also occur when focused, at lower intensity?
3. What exactly flickers — the whole panel, its height, or a region?
4. Is losing the player panel from scrollback acceptable (alternate-screen decision)?
5. Is the fix scoped to the main renderer only, or does it include the three modal overlays?
