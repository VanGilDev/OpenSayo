"""Ensure workspace switches don't force the Debug tab visible when user disabled it."""
from pathlib import Path
import sys, tkinter as tk
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'py'))
from opensayo_v019_alpha22 import App
root=tk.Tk();app=App(root);root.update()
def visible():return str(app.debug_tab) in app.book.tabs()
app.show_debug.set(False);app._toggle_debug();root.update();assert not visible()
for i in range(3):
    app._workspace_activate('freeform',script='PRESS_GK hidkey_a\nEXIT',readable='a')
    root.update();assert not visible(),f'Debug appeared switching into Freeform {i}'
    app._workspace_activate('form_project')
    root.update();assert not visible(),f'Debug appeared switching back to Form View {i}'
app.show_debug.set(True);app._toggle_debug();root.update();assert visible()
for i in range(3):
    app._workspace_activate('freeform',script='PRESS_GK hidkey_a\nEXIT',readable='a')
    root.update();assert visible(),f'Debug disappeared from enabled Freeform {i}'
    app._workspace_activate('form_project')
    root.update();assert visible(),f'Debug disappeared from enabled Form View {i}'
app.show_debug.set(False);app._toggle_debug();root.update();assert not visible()
root.destroy()
print('PASS: debug tab visibility remains synced to checkbox after repeated workspace switches')
