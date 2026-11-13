"""Simulated GUI check; no hardware access, no private definitions."""
import sys
import tkinter as tk
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'py'))
from opensayo_v019_alpha22 import App, DEFAULT_PROJECT
root=tk.Tk();root.withdraw()
app=App(root)
app.settings()
root.update_idletasks()
win=app.settings_window
assert win.winfo_exists()
buttons=[c for c in win.winfo_children()[0].winfo_children() if isinstance(c, __import__('tkinter').ttk.Button)]
button=next(x for x in buttons if x.cget('text')=='Restore timing defaults')
app.text_delay.set('77');app.action_delay.set('88');app.repeat_gap.set('99')
app.macro_key_ms.set('111');app.macro_nav_ms.set('222');app.macro_repeat_ms.set('333')
app.dropdown_open_ms.set('93')
button.invoke()
root.update_idletasks()
assert [x.get() for x in (app.text_delay,app.action_delay,app.repeat_gap)] == ['15','20','15']
assert [x.get() for x in (app.macro_key_ms,app.macro_nav_ms,app.macro_repeat_ms)] == ['15','20','15']
assert app.dropdown_open_ms.get()=='93', 'dropdown timing should not be implicitly altered'
p=app.current_project()
assert (p['text_delay_ms'],p['action_delay_ms'],p['repeat_gap_ms'],p['dropdown_open_ms'])==(15,20,15,93)
assert [DEFAULT_PROJECT[x] for x in ('text_delay_ms','action_delay_ms','repeat_gap_ms')]==[15,20,15]
assert app.help_window is None or not app.help_window.winfo_exists()
win.destroy();root.destroy()
print('PASS: File > Settings restore synchronizes 15/20/15 Settings and Viewer, retains independent dropdown 93, and persists project values; no USB writes')
