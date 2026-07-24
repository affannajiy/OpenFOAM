# Usability Heuristics — the OpenFOAM UI usability contract

**Read this first, then build.** Every UI change (landing page, Tab 1 background
mesh, Tab 2 snappy hex, popups, banners, log drawer) must satisfy the heuristics
below. When a design choice is unclear, this document decides. It adapts Nielsen's
10 usability heuristics to this application and folds in the higher-level goals
(satisfaction, usefulness, ease of use, ease of learning) they serve.

The audience is engineers who are **not** fluent in CFD jargon. That single fact
drives most rules here: plain language, safe defaults, and in-context help win
over power-user density.

---

## 0. Goals the heuristics serve

These are the outcomes we are optimising for. Each heuristic below feeds one or
more of them.

| Goal | We have succeeded when the user can say… |
| --- | --- |
| **Satisfaction** | "It is pleasant to use." / "I am satisfied with it." / "It works the way I want it to work." |
| **Usefulness** | "It is useful." / "It helps me be more effective." / "It helps me be more productive." |
| **Flexibility & efficiency** | "It is flexible." |
| **Ease of use** | "It is easy to use." / "It is simple to use." |
| **Ease of learning** | "It is easy to learn." / "I learned to use it quickly." / "I easily remember how to use it." |

---

## 1. Visibility of system status

> Communicate clearly what the system's state is. No action with consequences should be taken without informing the user. Give feedback as quickly as possible (ideally immediately). Build trust through open, continuous communication.

**In this app:**
- The **log drawer** streams raw OpenFOAM output live; `set_running` blinks while a
  worker runs, `set_step` shows "Step X/3" from snappy phase headers. A run must
  never look frozen.
- The **`MessageBanner`** reports every finish: success (green, with a next-step
  action) or error (red, with a plain-language fix from `scan_log_for_fix`).
- `status_changed` updates the status label the instant a run ends; ParaView
  state refreshes on the same signal so a finished mesh is usable immediately.
- Long checks (launcher pre-flight, WSL boot) show a splash and progress, never a
  blank window.
- **No destructive or long action starts silently** — writing `blockMeshDict`,
  running `snappyHexMesh -overwrite`, or removing time dirs is announced in the log.

## 2. Match between system and the real world

> Users must understand meaning without looking up definitions. Never assume your words match the user's. Use their familiar terminology and mental models.

**In this app:**
- Speak in **plain, non-CFD language**. "DX/DY/DZ is the cell **size**" — not
  "base grid spacing tensor." Tooltips are the canonical help and must stay
  jargon-free (see CLAUDE.md → Tooltips).
- Labels reflect the user's goal: "Continue to Snappy Hex Mesh →", "Suggest point",
  "Refresh file list" — verbs the user thinks in.
- Surface types are described by what they *do* (outer shell / solid body inside
  the domain), not by their dict keyword.
- Error text is translated: `OF_ERROR_MAP` turns stack traces into
  "Your DX/DY/DZ is too small… increase it (use a bigger number)."

## 3. User control and freedom

> Support Undo and Redo. Show a clear, labelled, discoverable way to exit the current interaction (e.g. a Cancel button).

**In this app:**
- Every popup (`_MessageCard` overlay) has a clear, labelled dismiss/Cancel; the
  file picker has explicit Up / New Folder / Cancel.
- Long runs are cancellable — the close-guard asks (default **No**) before stopping
  workers, so the user never loses a run by accident.
- Destructive edits are reversible where possible: `_refresh_file_list(_preserve=True)`
  keeps the user's per-row values across rebuilds; recent-delete confirms first.
- Users can always back out of a case and pick another without restarting.

## 4. Consistency and standards

> Improve learnability through internal consistency (within this product family) and external consistency (industry conventions).

**In this app:**
- **Internal:** one popup style only (`_MessageCard` — never stock Qt dialogs);
  one set of colour/style tokens in `ui_shared.py`; `ChevronComboBox` everywhere
  (never a bare `QComboBox`); two font tokens (`FONT_UI`, `FONT_MONO`) — never a
  hardcoded family. Fixed table column widths match header and rows.
- **External:** OpenFOAM dict conventions are honoured in generated files; standard
  desktop idioms (tabs, drawers, Cancel/Continue, red = error) are used as users
  expect.

## 5. Error prevention

> Prevent high-cost errors first, then little frustrations. Avoid slips with constraints and good defaults. Prevent mistakes by removing memory burdens, supporting undo, and warning users.

**In this app:**
- **High-cost first:** the background-mesh guard (`_projected_cell_count` /
  `_MAX_BG_CELLS`) refuses a billion-cell grid *before* blockMesh crashes on int32
  overflow — the exact class of high-cost, cryptic failure to catch up front.
- **Good defaults / constraints:** smart per-row defaults (largest STL → Boundary;
  others → FaceZone + CellZone); Vol Dir locked to None on Boundary rows;
  Max ≥ Min enforced; spinboxes bounded 0–20.
- **Pre-flight check** (Sec 05) validates polyMesh present, ≥1 Boundary, FaceZone
  has a CellZone, and location ≠ (0,0,0) before letting the user run.
- "Suggest point" removes the memory/guess burden for locationInMesh.

## 6. Recognition rather than recall

> Let people recognise information in the interface rather than remember it. Offer help in context, not a tutorial to memorise. Reduce what users must remember.

**In this app:**
- The file table **shows** every geometry file and its settings — the user picks
  from what's visible, not from memory of filenames.
- `QFileSystemWatcher` auto-rescans `constant/`, so new STLs appear without the
  user recalling to refresh.
- Options are presented as labelled controls with visible current values, not
  free-text the user must recall the syntax for.
- Context help (tooltips, banner fixes) appears at the moment of need.

## 7. Flexibility and efficiency of use

> Provide accelerators (keyboard shortcuts, gestures). Provide personalization. Allow customization of how the product works.

**In this app:**
- Accelerators exist for power users while defaults carry novices: manual "Refresh
  file list" as a fallback to auto-rescan; the workflow flows Tab 1 → Tab 2 with a
  one-click "Continue".
- Per-row / per-patch customization (surface type, refinement levels, layers) lets
  experienced users tailor the mesh; beginners can accept the smart defaults.
- The layout is responsive (`resizeEvent` reflows below 900 px) so it adapts to the
  user's window, not the other way around.

## 8. Aesthetic and minimalist design

> Keep content and visual design focused on essentials. Don't let unnecessary elements distract. Prioritize content and features that support primary goals.

**In this app:**
- The five snappy cards each own one concern; nothing competes for attention.
- Advanced/rare controls are disabled or hidden until relevant (V.LVL disabled when
  Vol Dir is None; Vol Dir locked on Boundary rows).
- The log drawer is collapsible — detail on demand, out of the way otherwise.
- No decorative clutter; colour is used to mean something (status, error, success).

## 9. Help users recognise, diagnose, and recover from errors

> Use traditional error visuals (bold, red text). Say what went wrong in the user's language — no jargon. Offer a solution, e.g. a one-click fix.

**In this app:**
- Errors use the red `MessageBanner` (bold, red — the expected visual).
- `scan_log_for_fix` / `OF_ERROR_MAP` translate the failure into plain words **and**
  hand back the concrete fix ("increase DX/DY/DZ… then click Generate again").
- The message names the cause and the next action, never just an error code.

## 10. Help and documentation

> Make help easy to search. Present documentation in context at the moment it's needed. List concrete steps to carry out.

**In this app:**
- Primary help is **in context**: every interactive widget has a plain-words
  tooltip; banners carry the fix inline.
- Longer guidance lives in `documentation/` and the README, structured with
  concrete, numbered steps.
- The user should rarely need to leave the app to learn the next action — the next
  step is offered where they are (e.g. "Continue to Snappy Hex Mesh →").

---

## How to use this document

1. Before designing or changing any UI element, find the heuristic(s) it touches
   above and satisfy the "In this app" rules.
2. If a new pattern isn't covered here, add it — this file is the living contract.
3. When a heuristic conflicts with density or power, favour the heuristic: the
   primary user is a non-expert who must succeed on the first try.
