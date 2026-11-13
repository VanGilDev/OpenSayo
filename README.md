<p align="center">
  <img src="OpenSayo_Banner.jpg" alt="OpenSayo — Offline Programmable Keypad Macro Editor" width="100%">
</p>

<h1 align="center">OpenSayo — Offline Programmable Keypad Macro Editor</h1>

<p align="center">
  Free • Open Source • Offline • Windows
</p>

## Application Preview

<p align="center">
  <img src="OpenSayo_Layered_Preview.png" alt="OpenSayo macro editor, form preview, and About window" width="100%">
</p>

---

## About OpenSayo

**OpenSayo** is a free, open-source Windows application designed to create, edit, organize, preview, and program keyboard macros for compatible Sayo programmable keypads.

Developed as an alternative to browser-based programming tools, OpenSayo provides a dedicated desktop environment for configuring programmable keypads without requiring an active internet connection.

The goal is simple: **make programmable keypad macros easier to create, understand, modify, and deploy while keeping the software transparent, portable, and accessible.**

## What OpenSayo Does

OpenSayo allows users to configure programmable keypad buttons to execute predefined sequences of keyboard actions.

These sequences can include typed text, keyboard shortcuts, navigation commands, and timed delays. Instead of manually repeating the same keyboard operations, users can program their keypad to perform those actions with a single button press.

Once a compatible keypad has been successfully programmed, its stored macros can operate independently of OpenSayo. This allows users to configure their hardware on one computer and use it on another without installing OpenSayo on the destination system.

## Main Features

### Visual, Form-Based Macro Editing

OpenSayo includes a form-linked macro editor that organizes keyboard actions into individual fields.

Rather than requiring users to work exclusively with raw keyboard commands, the application presents editable values and configurable actions in a structured interface.

Users can configure:

- **Flexible Field Input & Configuration** — Customize text entries, dropdown definitions, date fields, and other field-specific actions.
- **Skippable Fields** — Use the **Use** checkbox in Field View to make a field label-only while preserving its saved value, settings, and Tab navigation.
- **Keyboard Navigation** — Configure navigation commands and movement between fields.
- **Macro Endpoints & Execution Order** — Control where each macro ends and how its actions execute.
- **Customizable Form View & Grid Mode** — Organize and preview fields for different workflows, with layouts that can be saved and loaded.
- **Reusable Definitions** — Load your own field, dropdown, and view-layout definitions without including personal configurations in the public installation.

This approach is particularly useful for repetitive data-entry workflows involving multiple fields, allowing users to build macros while maintaining a clear visual representation of their workflow.

### Macro Viewer and Editing

OpenSayo also provides a macro viewer for examining the underlying keyboard instructions.

This allows users to inspect and adjust macro sequences, including typed text, navigation keys, and timing operations. Freeform editing and recording tools provide additional flexibility when a workflow does not fit a structured form.

The combination of structured field editing and direct macro inspection gives users greater control over their programmed actions.

### Programmable Keypad Management

OpenSayo supports macro configuration for compatible two-key and eight-key Sayo keypads.

Users can:

- Configure separate macros for supported physical buttons.
- Select the script assigned to each physical button.
- Read supported script data from a connected device.
- Write edited scripts to the device.
- Review and apply physical key assignments.

Device configuration tools are integrated into the application. Hardware compatibility depends on the specific model and its supported protocol.

### Macro Size Monitoring

Programmable keypads have limited onboard storage.

OpenSayo provides macro-size information to help users identify scripts that exceed the capacity of their selected supported device before writing them to hardware.

### Form Preview

OpenSayo includes a separate Form View that visually represents the fields associated with a macro.

Users can organize fields and load saved layouts to suit different workflows. Grid Mode offers another way to review and work with fields.

This provides a visual reference for understanding how the programmed keyboard sequence corresponds to a larger data-entry form.

### Save, Load, and Reuse Projects

Users can save their macro configurations as OpenSayo project files (`.osayo`) and reload them for future editing.

The application supports local field definitions, dropdown definitions, and view layouts, so users can restore their own configurations after installing a clean public release.

This makes it possible to maintain multiple macro configurations without rebuilding them from scratch.

### Offline Operation

OpenSayo is designed to run locally on Windows.

An internet connection is not required for normal macro editing or supported device programming.

The application does not depend on a manufacturer's website to perform its supported programming operations.

### Open Source and IT Review

OpenSayo is distributed under the MIT License.

Source code and supporting build documentation are available for inspection, modification, and independent compilation.

This is particularly useful in environments where software must be reviewed before installation or use.

OpenSayo is an independently developed community project and is not officially affiliated with or endorsed by the creators or manufacturers of compatible devices or other systems.

---

## Supported Hardware

OpenSayo has been developed and tested with supported two-key and eight-key Sayo programmable USB keypads.

Compatibility is model-specific. Other devices may require additional protocol testing before they can be supported reliably.

If you would like support for another device, feel free to submit a feature request through GitHub Issues. Hardware contributions and sponsorships may help fund future device testing, but compatibility with any particular device cannot be guaranteed.

---

## Typical Uses

OpenSayo may be useful for:

- Repetitive data-entry tasks.
- Multi-field form completion.
- Frequently used text sequences.
- Keyboard navigation automation.
- Application-specific keyboard shortcuts.
- Workflows requiring consistent, repeatable keystroke sequences.

Users should review generated macros and confirm their behavior before relying on them in important workflows.

## Downloads and Installation

Download the latest packaged Windows release from:

**[OpenSayo Releases](https://github.com/VanGilDev/OpenSayo/releases)**

The release packages include:

- **Windows x64 Package** — Packaged application for Windows users.
- **Source & IT Package** — Source code and supporting materials for inspection and independent compilation.

Extract the Windows package and launch `OpenSayo.exe` from its extracted application folder.

For source compilation, review the included build instructions and supporting documentation. To restore your own setup, load your personal field, dropdown, and view-layout definitions after installation.

## Source Code, Bug Reports, and Suggestions

**GitHub Repository:**  
https://github.com/VanGilDev/OpenSayo

**Releases:**  
https://github.com/VanGilDev/OpenSayo/releases

**Bug Reports and Feature Requests:**  
https://github.com/VanGilDev/OpenSayo/issues

**Community Discussions:**  
https://github.com/VanGilDev/OpenSayo/discussions

Feedback, suggestions, bug reports, and contributions are welcome.

When reporting an issue, please include the OpenSayo version, Windows version, keypad model, and steps needed to reproduce the problem.

Do not include passwords, confidential information, or sensitive macro contents in public reports.

## License

OpenSayo is released under the **MIT License**.

See the [LICENSE](LICENSE) file for details.

---

<p align="center">
  <strong>OpenSayo — Program your keypad, not your patience.</strong> 🐾
</p>

*OpenSayo is an independent project and is not affiliated with or endorsed by the manufacturers of compatible devices.*
