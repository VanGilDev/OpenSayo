# OpenSayo v1.15

![OpenSayo banner](OpenSayo/assets/OpenSayo_Banner.jpg)

## Application preview

![OpenSayo application, Form View, and About window](OpenSayo/assets/OpenSayo_Layered_Preview.png)

*Fictional equipment service request demonstration. Variable details remain label-only.*


**OpenSayo v1.15** is an app-wide polish release intended to make OpenSayo more approachable and useful for general users. It is a Windows tool for creating, editing, previewing, and programming macros for supported Sayo keypads.

## What's included

- `OpenSayo/`: complete application source, Windows launch/build scripts, license, support files, sanitised Sayo USB protocol templates, and offline tests.
- `IT_Review/`: software overview, build and security review, test status, complete window/dialog inventory, staged verification checklist, and source SHA-256 hashes.

**Source package:** This repository does not contain a prebuilt Windows `.exe`. On Windows, `OpenSayo/BUILD_WINDOWS_EXE.bat` produces the complete `dist\OpenSayo\` runtime folder; `PACKAGE_IT_REVIEW_WINDOWS.bat` can then produce a ZIP including the compiled runtime and IT materials. Review hardware access and privacy requirements before workplace deployment.

## Run on Windows

1. Extract the entire ZIP; never run the `.bat` files directly from inside the archive.
2. If Python 3.12 is already available, open `OpenSayo/` and double-click `RUN_OPENSAYO.bat`.
3. To create a standalone executable, double-click `OpenSayo/BUILD_WINDOWS_EXE.bat`. Keep **all files in** `OpenSayo/dist/OpenSayo/` together; launch `OpenSayo.exe` from that folder.
4. To stage an executable-and-source IT review release archive after building, double-click `PACKAGE_IT_REVIEW_WINDOWS.bat` in the ZIP root.
5. Review tests are delivered in small interactive chat checklists; the complete IT plan is in `IT_Review/MASTER_VERIFICATION_CHECKLIST.md`. Do not connect or program a device until the later hardware test phase.

## Configuration

A fresh startup has 25 blank generic fields and a three-column grid. Field count grows with imported definitions. Personal field (`.osfld`), grid (`.oslay`) and dropdown (`.osdrp`) files are loaded **locally** in that order. None of those private files are included in this package. Only **Field View** has a field enable/disable control: uncheck a field's **Use** checkbox to make it label-only. Disabled fields appear as labels in Form View and retain their Tab navigation position. Grid Mode arranges the visual layout.

## Device script readback

On either supported keypad layout, choose the intended key or script slot before loading. A successful read should populate both the editable Field View and the raw Macro Viewer, including supported navigation actions. Original readback timing stays intact until you edit the form; recheck the regenerated macro and byte meter before programming. Unsupported scripts must leave your current editor intact. Recording keys shows the captured keystrokes in the recorder's text area while recording, but only while its own capture box is focused. All physical device writes must be separately confirmed and verified on Windows.

## Public demonstration

`OpenSayo/assets/OpenSayo_Generic_Form_Demo.png` is a **synthetic test configuration** shown in the actual application; it is not a screenshot of any external business system or real user information. Varying item details (reference, part/serial number, quantity) are intentionally label-only.

## Safety and support

Use only harmless test records when reviewing macros. IT should approve HID access, dependencies, and any device writes before deployment. The build script currently installs Python packages from PyPI; local IT may need to review and pin those packages. The binary build and physical device validation must be completed on Windows before a production release is considered verified.

**GitHub:** https://github.com/VanGilDev/OpenSayo

### v1.15 final Windows reviewer checkpoint

Verify Field View Use toggles correctly and restores the field's saved value.
Disabled fields appear as labels in Form View and retain their macro Tab
positions. Check that Field View Use controls the field state, and that layout
editing and physical device behavior still work normally.
