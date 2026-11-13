"""Verify the sole enable/disable control is the Field View Use checkbox. No USB writes."""
from pathlib import Path
import tkinter as tk
from tkinter import ttk
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'py'))
from opensayo_v019_alpha22 import App

root=tk.Tk();root.geometry('1200x900');app=App(root);root.update()
assert len(app.enabled_vars)==25
app.field_vars[0].set('FIRST');app.field_vars[1].set('MIDDLE');app.field_vars[2].set('THIRD')
app.endpoint.set(2);root.update()
app.open_form_preview();root.update()
# Form View has no toggles, but does have input controls.
assert len(app._preview_inputs)>=3
assert not any(isinstance(w,ttk.Checkbutton) for w in app.form_preview_tab.winfo_children())
original=bool(app.enabled_vars[1].get())
assert original
# Change via Field View Use (exact same callback as clicking normal Checkbutton).
app._enabled_controls[1].invoke();root.update()
assert not app.enabled_vars[1].get(), 'Use did not disable field'
assert 1 not in app._preview_inputs, 'Disabled field still has a Form View textbox'
assert app.field_vars[1].get()=='MIDDLE', 'Stored data cleared'
assert app.field_definitions[1]['enabled'] is False
script,_=app._compile_form_key(1)
assert 'PRESS_GK hidkey_F' in script and 'PRESS_GK hidkey_D' in script and 'PRESS_GK hidkey_M' not in script,script
assert script.count('PRESS_GK hidkey_Tab')==2,script
app._enabled_controls[1].invoke();root.update()
assert app.enabled_vars[1].get() is True and 1 in app._preview_inputs
assert app.field_vars[1].get()=='MIDDLE'
app._close_form_preview();root.destroy()
print('PASS: Field View normal Use checkbox, Form View label-only display, preserved value and two Tabs')
