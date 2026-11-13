# OpenSayo v1.15 — IT verification checklist

**Product:** OpenSayo v1.15 — app-wide polish and accessibility improvements for general users.
**Status:** Final candidate verification plan, NOT IT approval. Windows compiled runtime and all final package checks are required; prior hardware tests were user-reported for an earlier candidate.

## Review rules

Record PASS / FAIL / NOT TESTED for each item. Use harmless synthetic macros; never package imported personal form definitions or machine-specific capture data. A reported problem remains open until fixed and retested. Any release package must be audited again after its FINAL assembly, not just while editing source.

**Window checks:** repeated opens must raise the existing persistent window, not create clones. Modal file dialogs and confirmations may reopen for separate deliberate actions; test focus, cancel and repetition. See `WINDOW_AND_DIALOG_INVENTORY.md` for the complete inventory.

**Configuration:** fresh startup is a generic 25-field/3-column form; personal form field (`.osfld`), grid layout (`.oslay`) and dropdown (`.osdrp`) files are imported LOCALLY in that order. Private configuration is neither bundled nor named in this checklist. Older obsolete full-project formats are not a migration target; they should show a clear recoverable error.

## A. Audit and source cleanup

*Phase:* SOURCE REVIEW — no hardware yet

- [ ] **A01** — Search all source, test code, docs, images, metadata, file names and hidden resources for employer names, original business labels, locations, record identifiers, sample values and work-only phrases.  
  **Pass:** PASS = no inappropriate public references, with each candidate match disposition recorded.
- [ ] **A02** — Verify the old project-format naming is not exposed in public code, error messages or metadata.  
  **Pass:** PASS = public format and error text are generic; unsupported obsolete projects show a friendly warning instead of an exception. Full legacy project migration is not a v1.15 requirement.
- [ ] **A03** — Verify generic Date/calendar behavior no longer depends on an original field label.  
  **Pass:** PASS = user-defined date action compiles from configuration rather than hardcoded name.
- [ ] **A04** — Verify warnings, Help, About (including approved independent coworker-focused notice), program title, menus, status bar and dialogs match the approved wording and are consistent.  
  **Pass:** PASS = all visible text reviewed, including alerts and error paths.
- [ ] **A05** — Verify public banner/icon/docs contain no old application preview or recognizable workflow screenshot.  
  **Pass:** PASS = inspect image pixels, not only filenames.
- [ ] **A06** — Verify old test scripts, projects, autosaves, field/dropdown/layout backups, sample records and log files are absent from public deliverables.  
  **Pass:** PASS = zero private artifacts in tree and ZIP.
- [ ] **A07** — Verify hardcoded values and saved macros are not populated into the default project.  
  **Pass:** PASS = no private defaults in source or build resources.
- [ ] **A08** — Inspect original USB capture templates at packet level for unrelated device traffic, host metadata, timestamps, descriptors, packet comments, and sensitive payloads.  
  **Pass:** PASS = original exposures documented and all raw captures kept private; this review found unrelated USB traffic and capture metadata, so the full originals were removed from the working public tree. Final distribution remains pending.
- [ ] **A09** — Confirm sanitized capture replacement does not alter protocol correctness; keep original full captures PRIVATE outside release files.  
  **Pass:** PASS = exact byte-for-byte outgoing report equivalence offline, THEN independent Windows/device write-readback-persistence on final build. Offline part passed for 443 source reports and 15 synthetic scenarios; hardware part remains OPEN.
- [ ] **A10** — Review source build dependencies, third-party licenses, public contact info, version numbers, release notes and security statements for accuracy.  
  **Pass:** PASS = no misleading IT/security claims or unintended personal data.
- [ ] **A11** — Confirm publication does not include Git history, hidden .git directories, stale assets or private definitions.  
  **Pass:** PASS = fresh-history source package inventory reviewed.
- [ ] **A12** — Run byte/string searches on the final ZIP and built Windows distribution for known exact and variant terms (including UTF-16LE).  
  **Pass:** PASS = results inspected, not just script exit status.
- [ ] **A13** — Review all remaining recognizable workplace/workflow terminology as the explicitly requested FINALIZATION step.  
  **Pass:** PASS = user approves final terminology review after all code fixes.


- [ ] **A14** — Inspect the three sanitized PCAPNG containers: exactly 220 + 220 + 3 outgoing Sayo packets, no other USB endpoints/devices, no original timestamps, IRP IDs, Windows/CPU/Wireshark metadata, device descriptors or packet comments.  
  **Pass:** PASS = final packaged assets match audited minimal templates; preliminary parser and source scans PASSED.
- [ ] **A15** — Compare all extracted command payloads with the PRIVATE original captures without ever placing the originals in the public source tree.  
  **Pass:** PASS = 443/443 matching 64-byte reports including report checksums; offline comparison PASSED, audit hashes recorded privately.
- [ ] **A16** — Independently exercise protocol generation for representative 2-key bank 1/6/7/8 scripts and assignments using sanitized templates.  
  **Pass:** PASS = no outgoing report differences versus original sources; 12 bank-write examples + 3 mapping/commit examples PASSED offline. Real device still pending.
- [ ] **A17** — Inspect the final source tree AND Windows distribution to ensure only the three sanitized protocol assets were bundled; no original full USBPcap files, captured host data, or private backups copied in.  
  **Pass:** PASS = final manifest checked; Windows build verification PENDING.


## B. Package/build integrity

*Phase:* AFTER audit fixes, BEFORE running EXE

- [ ] **B01** — Preserve immutable backup of original known-working archive and private definition files outside the public build tree.  
  **Pass:** PASS = backups open and are not inside release folders.
- [ ] **B02** — Verify no unexpected executables, source maps, keys, passwords, tokens, credentials, local paths or internal hostnames are packaged.  
  **Pass:** PASS = source and distribution manifest reviewed.
- [ ] **B03** — Ensure version displays 1.15 consistently in application, release notes, package and executable metadata.  
  **Pass:** PASS = user-facing screens and current-release materials consistently show v1.15; no outdated release branding.
- [ ] **B04** — Build Windows EXE from reviewed source using documented BUILD_WINDOWS_EXE.bat, capture warnings and failures.  
  **Pass:** PASS = reproducible build; no unexpected dependencies or errors.
- [ ] **B05** — Launch produced OpenSayo.exe from its complete dist/OpenSayo folder (do not move EXE alone).  
  **Pass:** PASS = starts without developer source tree or browser service.
- [ ] **B06** — Inspect entire dist/OpenSayo tree including _internal, captured resources and embedded images after PyInstaller build.  
  **Pass:** PASS = no private files or unreviewed traces bundled.
- [ ] **B07** — Test a new Windows user profile / clean configuration with no existing autosave.  
  **Pass:** PASS = startup is generic and does not quietly load old saved user state.
- [ ] **B08** — Record exact final source ZIP and executable build hashes; verify file manifest and final ZIP entries.  
  **Pass:** PASS = audited package matches the one later distributed.
- [ ] **B09** — Confirm installation/launch instructions and RESTORE_PERSONAL_CONFIGURATION instructions match real UI menu labels.  
  **Pass:** PASS = beginner can perform steps without guessing.
- [ ] **B10** — Verify offline use; no unexpected telemetry, URL access, elevated permissions or automatic write to hardware.  
  **Pass:** PASS = app behaves as documented and does not program devices at launch.


## C. Fresh-start UI and generic defaults

*Phase:* WINDOWS APP

- [ ] **C01** — On clean launch confirm 25 fields, first 10 generic names, fields 11–25 numbered, all values empty.  
  **Pass:** PASS = precisely 25 and no private content.
- [ ] **C02** — Confirm default Form View is three columns and does not resemble original private layout.  
  **Pass:** PASS = generic/unorganized template.
- [ ] **C03** — Confirm dropdown library initially empty and fields default to Text unless configured.  
  **Pass:** PASS = no organization-specific choices or calendar shortcuts.
- [ ] **C04** — Confirm the optional Debug tab, definitions management, form editor, Freeform editor and device controls remain accessible.  
  **Pass:** PASS = none removed by public cleanup.
- [ ] **C05** — Check About displays the **exact approved personal Independent Project Notice** (not the older corporate wording), retains developer credit/contact, and the Help entry previously marked for removal is absent.  
  **Pass:** PASS = exact intended user-visible texts.
- [ ] **C06** — Check resizing, scrolling, keyboard focus, contrast, labels, menu actions and blank-state instructions.  
  **Pass:** PASS = no overlap/crash and usable at normal Windows scaling.
- [ ] **C07** — Test New, Open, Save, Save As, Reset Defaults, and exit/restart; warn before losing unsaved edits.  
  **Pass:** PASS = data loss protections work and reset restores public defaults.
- [ ] **C08** — Add fields past 25, past 69 and to at least 300; test saving/reopening, layout expansion, and definition/import round trips.  
  **Pass:** PASS = no 69- or 300-field hard limit, truncation, or index error.
- [ ] **C09** — Verify autosave cannot unexpectedly restore private data after reset or on another machine; check behavior after clean shutdown.  
  **Pass:** PASS = user understands when previous local state is reused.

- [ ] **C10** — Stress-test at 301 and 500+ fields on Windows, including scrolling, adding, editing, deleting, repositioning, save/load, and responsiveness.  
  **Pass:** PASS = no artificial 300-field cutoff, lost data, or unacceptable freezing; record tested maximum (do **not** advertise unlimited capacity until measured).
- [ ] **C11** — Open About at 100%, 125%, and 150% Windows display scaling, including smaller window/screen sizes; inspect all four personal-notice paragraphs, developer contact, Debug toggle and Close control.  
  **Pass:** PASS = entire notice is readable and controls remain reachable without clipping.

- [ ] **C12** — In Field View, uncheck Use for a text field and confirm its value control disappears; recheck and confirm it returns with its previous value and formatting.  
  **Pass:** PASS = label only when disabled, full input restored; no loss of field ID or order.
- [ ] **C13** — In Grid Mode, verify the enable/disable checkbox is absent. Test regular/half-height tiles and separate display-only labels after disabling a real field in Field View.  
  **Pass:** PASS = disabled field remains in exactly the same cell, visually marked label only; independent grid labels do not change.
- [ ] **C14** — In Field View, toggle Use, save and reopen; compare enabled state and all field settings before/after. Manage Fields must have no duplicate Use/Enabled control.  
  **Pass:** PASS = enabled flag persists; name, format, selected dropdown library, date action and stored values remain intact.
- [ ] **C15** — Stress-test 300 and 500-field forms with a mix of enabled and disabled fields, reopening the grid and saving/reloading.  
  **Pass:** PASS = checkbox controls, scrolling and form rendering remain responsive, without an artificial ceiling.


  **Pass:** PASS = Form View has no field enable/disable checkbox, no Alt-triggered UI, and disabled inputs remain label-only; use Field View to toggle.
- [ ] **C18** — Disable and re-enable fields from Field View, then inspect them in Form View, including off-screen rows; check focus and scroll positions during redraw.  
  **Pass:** PASS = disabled input disappears leaving label only (no checkbox); re-enable in Field View restores the input and existing value; view does not jump unexpectedly.


## D. Private configuration restore

*Phase:* LOCAL ONLY — NEVER INCLUDE PERSONAL FILES IN PUBLIC ZIP

- [ ] **D01** — Import your actual .osfld field definitions; verify all 69 fields, IDs, labels, formats and options.  
  **Pass:** PASS = no renamed/missing/reordered fields.
- [ ] **D02** — Import actual .oslay grid layout after fields; compare positions and column arrangement with your known-good screenshot.  
  **Pass:** PASS = each field returns to intended position.
- [ ] **D03** — Import actual .osdrp dropdown definitions; check all libraries and exact option spelling/case/order.  
  **Pass:** PASS = no blank, truncated, duplicated or remapped choices.
- [ ] **D04** — Verify field-to-dropdown binding (not just list import); choosing each dropdown inserts correct script text.  
  **Pass:** PASS = correct field and exact case-sensitive output.
- [ ] **D05** — Check Date field accepts private configured action and generates Down → Enter as intended; verify final End when required by macro.  
  **Pass:** PASS = intended keys in exact order, no accidental date typing.
- [ ] **D06** — Verify private scripts and macro navigation follow the original field sequence, including skip/blank/manual fields.  
  **Pass:** PASS = each keystroke reaches correct field; no extra/missing Tabs.
- [ ] **D07** — Save complete restored project .osayo; close and reopen; compare fields, layout, libraries, scripts, assignments and values.  
  **Pass:** PASS = round trip lossless.
- [ ] **D08** — Save/load form format .osfrm if used; verify included layout/options and separate definitions import/export.  
  **Pass:** PASS = all supported file types round trip.
- [ ] **D09** — Import and export shareable JSON definitions if used; verify restoration on new blank profile.  
  **Pass:** PASS = formatting, custom mappings and actions preserved.
- [ ] **D10** — Open a synthetic obsolete `.osayo` project with 69 generic fields, via File > Open Project. Do NOT require migration of obsolete full-project structures.  
  **Pass:** PASS = helpful "Unsupported Project Format" warning, no raw `IndexError`, no change to current unsaved data, and guidance to import `.osfld`, `.oslay`, `.osdrp` instead.
- [ ] **D11** — Re-test synthetic 25/69/300/500-field configs after any normalization changes; confirm no duplicate IDs or layout collisions.  
  **Pass:** PASS = no regression in structural compatibility.
- [ ] **D12** — Confirm temporary private config remains in user-controlled storage only, not output ZIP, logs, test fixtures or source commits.  
  **Pass:** PASS = private data never included in published files.


- [ ] **D13** — Load the three newly provided private files in order using the actual Windows UI: fields, layout, dropdowns. Compare all 69 stable IDs, grid cells, 24 display-only labels, 10 half-height field settings, five dropdown libraries and existing date formats.  
  **Pass:** PASS = exact restore; verify Windows rendering in addition to already-passed simulated desktop checks. Keep file contents private.
- [ ] **D14** — Disable a field, save a new `.osfld` field list, reopen it, and verify `enabled: false` persists. Re-import a pre-toggle `.osfld` lacking the flag.  
  **Pass:** PASS = new files preserve checkbox state; existing files default to enabled; importing never changes originals.
- [ ] **D15** — For a text field, dropdown field and date-action field, fill harmless test values, disable/re-enable, and compare source data before/after.  
  **Pass:** PASS = original formats, values, dropdown references and date action are preserved, with no action emitted while disabled.
- [ ] **D16** — Reload the private `.oslay` after toggling active states; confirm the layout remains independent of the enabled flag and matches field IDs exactly.  
  **Pass:** PASS = all positions and visual labels remain in place, no silent remap, with private identifiers never put into public tests.
- [ ] **D17** — On Windows, use the supplied synthetic `Test_Fixtures/OpenSayo_Unsupported_Old_Project_Test.osayo` fixture with unsaved harmless text visible.  
  **Pass:** PASS = the friendly warning appears before a save/discard prompt; current unsaved data, workspace and file path stay unchanged. Synthetic fixture remains outside the public application/package.
- [ ] **D18** — Attempt to open a synthetically corrupted `.osayo` file, then a valid freshly saved current `.osayo` project and Freeform project.  
  **Pass:** PASS = corrupt file shows clear recoverable error; both valid modern formats still open without Tkinter exceptions; unsaved content is protected.
- [ ] **D19** — Test synthetic prior-format data that the generic compatibility path can interpret and unsupported future/unknown version numbers.  
  **Pass:** PASS = supported structure opens safely, unknown formats/versions rejected cleanly, with no partial workspace mutation.


- [ ] **D20** — After restoring the three PRIVATE files, toggle Use on a text field and on a dropdown/date field from Field View; inspect the results in Form View and Grid Mode, then re-import the grid layout.  
  **Pass:** PASS = all 69 field identities, five columns, 69 placements, 24 purely visual labels, 10 half-height settings and five dropdown libraries remain intact; no imported file is modified.
- [ ] **D21** — Save updated field defaults after toggles, close app, and reload; distinguish disabled *real fields* from the layout's independently created label-only tiles.  
  **Pass:** PASS = persisted `enabled` state remains correct; real disabled fields still take a Tab; purely visual labels have no Tab; re-enabling restores original configured action.


## E. Macro creation/editor compatibility

*Phase:* WINDOWS OFFLINE

- [ ] **E01** — Record keystrokes and verify REC indicator defaults off and flashes per action while recording.  
  **Pass:** PASS = actions are captured without stuck indicator.
- [ ] **E02** — Record multiple separated text runs; Edit Text modifies each run without deleting surrounding navigation/timing.  
  **Pass:** PASS = case-sensitive edits exactly preserved.
- [ ] **E03** — Verify full Freeform ↔ Form View synchronization for typed text, key presses, breaks and manual steps.  
  **Pass:** PASS = no loss when switching tabs.
- [ ] **E04** — Check manual-enter / stop-here steps and blank fields remain manual rather than auto-filled.  
  **Pass:** PASS = generated macro pauses/stops at intended point.
- [ ] **E05** — Check Tab, Down, Enter, End, modifiers, key press/release, delays, repeat-character delay, and final command.  
  **Pass:** PASS = exact script generation and preview order.
- [ ] **E06** — Test configurable millisecond delays (including ~15/60 ms where available) and a safe slower text entry option.  
  **Pass:** PASS = durations stored and honored.
- [ ] **E07** — Check Caps Lock warning/animation and case-preserving behavior; verify host Caps Lock is not left changed unexpectedly.  
  **Pass:** PASS = intended characters and state preservation.
- [ ] **E08** — Test copy/paste script import, save/load project, text macro import and script export.  
  **Pass:** PASS = script content intact before/after reload.
- [ ] **E09** — Validate invalid commands, malformed files, over-capacity scripts and unrecognized keys show clear errors without partial writes.  
  **Pass:** PASS = user can safely correct problems.
- [ ] **E10** — Verify macro preview/simulate does not type into live programs without an explicit run action.  
  **Pass:** PASS = no unintended keystrokes.
- [ ] **E11** — Check size/capacity meter matches compiled encoded bytes; warnings and flash-red state occur at and over limit.  
  **Pass:** PASS = correct boundary behavior.
- [ ] **E12** — Test action splitting at safe boundaries; never split held modifiers/keys or incomplete commands.  
  **Pass:** PASS = independent segments compile and retain action order.
- [ ] **E13** — Verify Form View displays loaded 8-key scripts when appropriate and Freeform shows same commands.  
  **Pass:** PASS = no script hidden by wrong editor tab.


- [ ] **E14** — Compile a three-field macro with the middle field unchecked, using distinct harmless typed test values.  
  **Pass:** PASS = middle value/action omitted, exactly the same number of Tabs emitted, next field receives its intended focus.
- [ ] **E15** — Disable a Date / Today's Date field and a Drop Down / Navigate field; re-enable both.  
  **Pass:** PASS = no unintended Down/Enter/dropdown navigation while disabled; original actions compile identically when re-enabled.
- [ ] **E16** — Split a form over Key 1 and Key 2 with disabled fields near their endpoint/boundary; compare generated readable and compiled scripts.  
  **Pass:** PASS = correct handoff count; no duplicated or missing Tab; disabled fields do not corrupt endpoint mapping.


- [ ] **E17** — Generate a macro containing A (filled), B (disabled, with a previously stored value), C (filled); compare Form Project readable script and compiled bytes on Windows.  
  **Pass:** PASS = disabled B emits no content or special action but produces its ordinary Tab navigation to C; exactly two Tabs in three steps when C is the endpoint, with no extra trailing Tab.
- [ ] **E18** — Repeat E17 with disabled Date/Todays Date, Drop Down/Navigate and field at a Key 1/Key 2 boundary.  
  **Pass:** PASS = no suppressed Down/Enter/navigation leaks; field count and inter-key handoff remain aligned; existing configured actions return unchanged when enabled.



- [ ] **E19** — In Freeform, verify Wait (ms), Key hold (ms), After navigation (ms), Repeated key gap (ms), Dropdown opening (ms), and Apply Timing to Key controls are visible and readable at common window sizes.
  **Pass:** PASS = Freeform and Macro Viewer show shared values (15/20/15 and 75 ms initially on a fresh profile); no second timing source appears.
- [ ] **E20** — Change timing in Freeform, apply, inspect generated script/byte meter, then switch to Macro Viewer and Settings and restore defaults.
  **Pass:** PASS = changes apply locally to the readable macro; shared controls sync; no USB access or unintended device writing; raw imported scripts remain preserved until edited.
- [ ] **E21** — Enter a harmless explicit wait in Freeform, click Insert Wait, inspect generated script, and try invalid/negative/out-of-range input.
  **Pass:** PASS = valid WAIT token inserts and preview refreshes; invalid input produces one friendly error, without changing the macro.

## F. Two-key Sayo validation

*Phase:* DEVICE CONNECTED — CONTROLLED TEST

- [ ] **F01** — Confirm device identification uses actual verified hardware IDs and correct connected/disconnected indicators.  
  **Pass:** PASS = no wrong-device writes.
- [ ] **F02** — Test clean connect/disconnect/reconnect across normal USB ports; watch for freezes or input stalls.  
  **Pass:** PASS = stable system; stop immediately if freezes recur.
- [ ] **F03** — Read Key 1 and Key 2 separately; confirm selected key content and byte meter.  
  **Pass:** PASS = no accidental cross-key overwrite.
- [ ] **F04** — Use distinct non-sensitive test macros on Key 1 and Key 2; preview first, then explicitly confirm write.  
  **Pass:** PASS = only chosen key programmed.
- [ ] **F05** — Read back after writes and physically press each key in a safe text editor.  
  **Pass:** PASS = actual output matches intended macro.
- [ ] **F06** — Unplug/reconnect, re-read and test again with app closed.  
  **Pass:** PASS = scripts persist and run independently.
- [ ] **F07** — Test abort/failure scenarios (disconnect while idle, missing device, no permission) without damaging stored scripts.  
  **Pass:** PASS = understandable error and no unintended write.


## G. Eight-key Sayo validation

*Phase:* DEVICE CONNECTED — CONTROLLED TEST

- [ ] **G01** — Verify physical buttons 1–8 map to script indexes 0–7 and assignment UI correctly.  
  **Pass:** PASS = each key matches the intended slot.
- [ ] **G02** — Use eight distinct non-sensitive test strings, each with a build-specific marker, and write only after preview.  
  **Pass:** PASS = no ambiguity with stale scripts.
- [ ] **G03** — Read each of eight scripts back and check output in safe text editor.  
  **Pass:** PASS = all eight correct; no cross-slot changes.
- [ ] **G04** — Unplug/reconnect and repeat test with app closed.  
  **Pass:** PASS = all eight persist.
- [ ] **G05** — Exercise high/low script slot read/import (including known higher index cases such as 61 and 63 when supported).  
  **Pass:** PASS = no editor or script-index truncation.
- [ ] **G06** — Test an empty script slot and script import; verify correct script/view handling.  
  **Pass:** PASS = no phantom content or crash.
- [ ] **G07** — Test script capacity meter and red flashing over-limit state with controlled oversized draft; prevent bad write.  
  **Pass:** PASS = correct guard.
- [ ] **G08** — Test device assignment/save persistence, read-after-write, 2-key/8-key switching and reconnect detection.  
  **Pass:** PASS = no wrong-device communication.
- [ ] **G09** — Verify generic date/navigation macro on physical hardware against a harmless text fixture, not any workplace system.  
  **Pass:** PASS = accurate action order without live-record risk.


- [ ] **G10** — Program a harmless multi-field 8-key test containing a disabled field on a selected script, then re-enable and compare compiled/written commands after guarded confirmation.  
  **Pass:** PASS = disabled action omitted, field position preserved, and read-back matches after persistence/reconnect.


- [ ] **G11** — Audit the legacy experimental `hardware_protocol.py bank_packets()` CLI path separately from the active `make_bank_reports()` UI path.  
  **Pass:** PASS = repair or explicitly retire the stale baseline-length assertion before declaring ALL bundled source utilities supported. The direct legacy CLI path currently fails against both ORIGINAL and sanitized baseline files; primary UI write path passes offline, physical tests PENDING.


## I. In-app Help completeness and usability

*Phase:* SOURCE REVIEW + SIMULATED GUI, THEN WINDOWS VISUAL TEST

- [ ] **I01** — Open Help > Quick Reference in Form and Freeform workspaces, including a second open attempt.  
  **Pass:** one working, readable Help window, no duplicate or crash.
- [ ] **I02** — Verify 23 distinct Help topics and their clickable Contents links/Return to Top anchors.  
  **Pass:** all links jump to the correct section (Xvfb preliminary PASS; Windows pending).
- [ ] **I03** — Test Find Next, Enter, Ctrl+F and no-match text with keyboard and mouse.  
  **Pass:** matches highlighted, wraparound correct, no UI lockup (Xvfb preliminary PASS for Find Next).
- [ ] **I04** — Compare every Help menu/tab/button name against the *current* v1.15 UI, including hidden Debug and Freeform controls.  
  **Pass:** no dead links, outdated menus, mock features presented as finished, or leftover version wording.
- [ ] **I05** — Follow the documented private configuration restore order `.osfld` → `.oslay` → `.osdrp` without consulting source.  
  **Pass:** exact field IDs/positions, labels and dropdowns restored without altering USB devices.
- [ ] **I06** — Compare Help field-toggle instructions with Use/Enabled controls and disabled/label-only Grid Mode rendering.  
  **Pass:** metadata preserved, disabled action suppressed, Tab position intact.
- [ ] **I07** — Verify Help descriptions for Text, Skip, Dropdown Navigate and generic Date actions against actual generated scripts.  
  **Pass:** every documented action matches observed preview and safe keyboard test.
- [ ] **I08** — Confirm 2-key and 8-key Help reflects separate 468/2028-byte safeguards, destination slots and physical assignments.  
  **Pass:** no implication that layout switching, import or export programs hardware.
- [ ] **I09** — Change settings timing away from default, click **File > Settings > Restore timing defaults**, then inspect Settings, Macro Viewer, Help, script preview and saved session.  
  **Pass:** Settings and Macro Viewer both show 15 ms hold/typing, 20 ms navigation, 15 ms repeat gap; dropdown opening remains 75 ms (or the currently selected value); regenerated scripts reflect the new timing after reset, existing device memory is untouched. Reopen app to check autosaved values. **Working-source offline and simulated GUI checks passed; Windows confirmation pending.**
- [ ] **I10** — Verify local recorder and Freeform instruction accuracy, including editing text, unknown instructions and readback caveats.  
  **Pass:** real controls work as documented; no claim of global keyboard capture.
- [ ] **I11** — Confirm Help contains no private field names, file contents, record identifiers, original business terms, or unnecessary personal information.  
  **Pass:** private definitions remain exclusively local; final byte/string scan clean.
- [ ] **I12** — Visual accessibility on Windows at 100%, 125%, 150% display scaling; scroll, TOC, search and readable font sizes.  
  **Pass:** nothing clipped or inaccessible; keyboard navigation works, including with small windows.

- [ ] **I13** — Follow Help's Field View-only Use checkbox instructions; verify neither Form View, Grid Mode nor Manage Fields exposes duplicate enable/disable controls.  
  **Pass:** PASS = Help accurately explains the single Use checkbox, label-only visuals, and preserved macro Tab transitions; no Alt instructions.

---

## H. Final release gates and sign-off

*Phase:* NO GITHUB ACTION UNTIL ALL REQUIRED GATES PASS

- [ ] **H01** — Review every failure; classify blocker versus accepted known limitation; document fix and rerun affected tests.  
  **Pass:** PASS = no open release blockers.
- [ ] **H02** — Collect evidence: screenshots of generic startup, restored private layout (PRIVATE ONLY), test outputs, device readback, hashes and audit report.  
  **Pass:** PASS = reproducible test record.
- [ ] **H03** — Complete final terminology/workplace disclosure review *after* the last patch and verify source and EXE independently.  
  **Pass:** PASS = user explicitly signs off.
- [ ] **H04** — Verify public release archive is freshly built from the reviewed files and contains none of the PRIVATE test artifacts.  
  **Pass:** PASS = final package checksum recorded.
- [ ] **H05** — Confirm complete Windows/device test is finished BEFORE authorizing any GitHub replacement action.  
  **Pass:** PASS = user approves release.
- [ ] **H06** — Only when user explicitly prompts after v1.15 passes: retrieve the saved private staging/new-history GitHub replacement plan.  
  **Pass:** PASS = GitHub is the NEXT STEP, never mixed with current audit.

- [ ] **H07** — Verify the three uploaded private field/layout/dropdown files, their identifying field IDs, names, library values, private regression data, and any generated project copy are absent from the entire public source tree, final ZIP and Windows distribution.  
  **Pass:** PASS = release manifest has zero private artifacts; test fixtures in shipped tests are generic only.

- [ ] **H08** — For the final v1.15 public preview, create and personally review a generic, coherent OpenSayo macro-form demonstration for the public README/banner. Show credible reusable automation actions and a logical flow; do not make it look like an arbitrary pre-filled business record. Present inherently item-specific fields—**Quantity, Serial Number, Part Number / Reference ID and similar change-per-item values—only as LABEL-ONLY/manual-entry locations**: no typed fake values, input-box presets, fixed macros or implied auto-fill for them.  
  **Pass:** PASS = screenshot accurately reflects the v1.15 app, clearly illustrates form-filling macro assistance, is visually polished, and contains no company-specific labels/data/private definition content. A generic example was captured in the application; final user approval and Windows visual confirmation remain pending.

- [ ] **H09** — In the public preview screenshot, demonstrate a generic **Reference ID** field as a disabled real macro field: its label remains visible, its input textbox is absent, and its place in Tab order is retained.  
  **Pass:** PASS = the screenshot is taken from the actual reviewed application (not an invented screen), shows a sensible reusable macro workflow with variable item-specific labels left manual, and contains no private company data or definitions.


- [ ] **H10 — IT documentation remediation:** Before preparing each review package, update every distributable IT document (overview, start-here guide, build/deployment instructions, security notes, release notes, testing checklist, window/dialog inventory, regression results and test fixtures). Remove unnecessary historical development identifiers, original workflow-specific examples, names and internal test labels. Preserve accurate operational instructions and current public-facing v1.15 wording. Do not expose private restoration files or real records.  
  **Pass:** all affected documentation is corrected in the next candidate, with substantive instructions intact. **Current source ZIP: documentation remediated and scanned. Review the compiled Windows distribution separately before final approval.**
- [ ] **H11 — Mandatory pre-send documentation audit:** **After** H10 edits and **before sending each candidate**, re-review the entire assembled source-and-build kit and IT review materials, including filenames, path names, generated scripts, screenshots/assets, ZIP member names and the ZIP contents. Scan for old terminology, internal development references, hardcoded example data and unintended private artifacts; manually inspect contextual matches to distinguish legitimate hardware terms. Verify all displayed versions are public `v1.15` and that review-candidate labels appear only on the outer download ZIP filename. Re-run the audit **after the final packaging changes**, not only on source.  
  **Pass:** recorded, reviewed manifest and clean pre-send checks; any finding is fixed and the check repeated before delivery. **Current source ZIP: audited after assembly. Repeat for each future package and the Windows-compiled distribution.**

---

## Validation record / defect log template

| Test ID | Status (PASS / FAIL / NOT RUN / N/A) | Build/hash | Evidence or notes | Retest date |
|---|---|---|---|---|
| e.g., D03 | NOT RUN | — | Compare exact dropdown items | — |

**Release decision:** ☐ All required tests completed ☐ All blockers resolved ☐ Final terminology review approved ☐ Private data excluded ☐ Windows/device verification complete ☐ User authorizes GitHub next step

**Important:** This checklist is a test plan, not a statement that every box has been executed. It can be expanded as the remaining v1.15 issues are reviewed. The preserved GitHub instructions will be recalled only after v1.15 passes all release gates and the user explicitly asks for the next step.


## J. v1.15 windows / repeated-popup regression inventory

*Phase:* staged window-review batches, with all remaining entry points required before sign-off.

**Release purpose:** v1.15 is **an app-wide polish and opening-up-to-the-general-user release**. Repeat this exact purpose at the future GitHub step.

**Critical finalization reminder:** The user personally encountered an action that could be repeatedly clicked to spam multiple windows. Its exact entry point has not yet been isolated. Every secondary window, chooser and confirmation must be reviewed before release. The complete **202-secondary-call-site** list is in `WINDOW_AND_DIALOG_INVENTORY.md`; no untested item is automatically approved.

- [ ] **J01** — Help: repeatedly open, verify ONE modeless window, raise/focus existing, close and reopen.
- [ ] **J02** — About: repeatedly open, one instance, full personal notice visible and not clipped.
- [ ] **J03** — Settings: repeatedly open, one instance, 15/20/15 restore defaults, no stale second settings editor.
- [ ] **J04** — Form View: repeated opens, one window, preserve values and scroll positions when toggling fields.
- [ ] **J06** — Manage Fields: repeated opens, one window; edits preserved on focus changes.
- [ ] **J07** — Local Macro Recorder: repeated opens, one window; safe local key capture and cancel/reopen.
- [ ] **J08** — Navigate Keys per-field editor: repeated opens, one at a time, safe focus; cancel/reopen and avoid stale field edits.
- [ ] **J09** — 8-Key Device Management: repeated opens, one window, no write from merely opening; postpone actual writes to hardware batch.
- [ ] **J10** — Dropdown import REVIEW popup: one modal review, Merge/Replace/Cancel respect scope; no stacked review panes.
- [ ] **J11** — Transient tooltip: appears/disappears cleanly, does not accumulate or trap focus.
- [ ] **J12** — Exercise all 41 file/name picker call sites recorded in popup inventory; cancel is harmless; long paths and permission errors handled.
- [ ] **J13** — Exercise all 150 confirmation/notice/error call sites, as applicable, with readable copy and correct parent/focus; device-related confirms only during safe hardware stage.
- [ ] **J14** — Windows keyboard Alt+Tab and Escape handling across modeless/dialog windows; no stuck modal grabs, duplicate popups, or invisible blockers.
- [ ] **J15** — **FINAL REMINDER:** confirm with the tester that no user-observed repeated-window defect remains; reopen every persistent window repeatedly before sign-off.
- [ ] **J16** — Display title/About/Docs all identify `v1.15`, and release materials repeat v1.15 purpose at GitHub step. No accidental v1.15 release labels on UI.
- [ ] **J17** — Verify review package excludes user's three private definition files, test imported projects, unfiltered original captures, pycache, build leftovers and old Git history.
- [ ] **J18** — Test opening app from the application run-from-source batch and built Windows exe; verify both use private current version session directory, not prior installs.

**Staged test batches:** presented interactively in chat in groups of manageable size. This master plan is for IT and final release sign-off; do not treat incomplete items as passed.

  **Pass:** No quick-checkbox, visual halos or Alt-driven field changes; enabling/disabling remains available from Field View Use only.
- [ ] **J20** — With **Show Debug tab** unchecked in About, switch Form Project → Freeform → Form Project repeatedly and save/open a project. Also test with the preference checked.  
  **Pass:** Unchecked stays hidden throughout; checked stays visible as expected; editor workspaces and scripts survive transitions without stale or duplicate tabs.
- [ ] **J21** — Review all package IT notes and their exact labels against the shipped source, including Help, screenshot requirements, public release naming and repeat-popup inventory.  
  **Pass:** No private definitions, outdated terminology, stage identifiers or obsolete screenshot claims are shipped.


  **Pass:** No checkbox exists in either visual window; Alt does not affect field enabled state. The prior Alt-release bug is resolved by removing this interaction, pending Windows confirmation.
- [ ] **J23 — Grid selected-field property removal:** Select a field, scroll and redraw Grid Mode. Verify the selected-field Enabled property and tile quick-check controls do not exist.
  **Pass:** Grid Mode never changes enabled state; any Field View Use change remains effective in label rendering, and the disabled field retains its Tab step.

## Current final review — Windows and IT sign-off

- [ ] Confirm Form View and Grid Mode display and layout controls behave normally.
- [ ] Confirm the Field View **Use** checkbox toggles label-only status, preserves values, and leaves Tab order intact.
- [ ] Open Help, search **Enable or Disable a Field**, and check concise current guidance, readability and search.
- [ ] Verify import order using local `.osfld`, `.oslay` and `.osdrp` files; do not include them in the public kit.
- [ ] Recheck the exact bundled app after Windows build: key preview, byte meter, 2-key and 8-key read/write/persistence.
- [ ] Audit ALL 11 secondary-window call sites and 41 picker sites in `WINDOW_AND_DIALOG_INVENTORY.md`, plus all 150 message/confirmation call sites for accidental repeat openings.
- [ ] Review generic application demo screenshot for sensible reusable macro values and label-only manual fields.
- [ ] Inspect every asset in the final ZIP and built Windows executable folder (including `_internal`).
- [ ] Verify SHA-256 manifest against the distributed source, confirm no personal definition files or unrelated captures.
- [ ] Complete the explicitly requested final recognizable-terminology review.
- [ ] Obtain user final acceptance and separate IT approval as applicable.

**Windows reviewer record:** Batch 01 8/8, Batch 02 8/8, Batch 03 5/6, Batch 04 4/6, Batch 05 7/8, Batch 06 7/8, Batch 07 8/8, Batch 08 8/8, Batch 10 7/8. Historical issues were addressed by later changes, except the Batch 10 Help wording fix still requires a Windows retest.
