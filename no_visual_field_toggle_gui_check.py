"""Verify Form View and Grid Mode have no field-enable checkbox or Alt bindings."""
from pathlib import Path
import tkinter as tk
from tkinter import ttk
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'py'))
from opensayo_v019_alpha22 import App

def walk(w):
    yield w
    for c in w.winfo_children():yield from walk(c)

root=tk.Tk();root.geometry('1200x900');app=App(root);root.update()
app.open_form_preview();root.update()
assert not any(isinstance(c,ttk.Checkbutton) for c in walk(app.form_preview_tab)), 'Form View checkbox still present'
assert len(app._preview_inputs)>0
before=[v.get() for v in app.enabled_vars]
app.form_preview_window.event_generate('<KeyPress-Alt_L>')
app.form_preview_window.event_generate('<KeyRelease-Alt_L>')
root.update()
assert [v.get() for v in app.enabled_vars]==before
app._open_grid_mode();root.update()
assert not any(isinstance(c,ttk.Checkbutton) for c in walk(app.designer_grid_window)), 'Grid Mode checkbox still present'
assert not any('Enabled' in c.cget('text') for c in walk(app.designer_grid_window) if isinstance(c,ttk.Button)), 'Grid Mode Enabled button unexpectedly present'
app.designer_selected=0;app._designer_render();root.update()
app.designer_grid_window.event_generate('<KeyPress-Alt_L>')
app.designer_grid_window.event_generate('<KeyRelease-Alt_L>')
root.update()
assert [v.get() for v in app.enabled_vars]==before
assert all(not hasattr(app,name) for name in ('_quick_field_alt','designer_enable_check','designer_enabled'))
app._open_manage_fields();root.update()
assert not any(isinstance(c,ttk.Checkbutton) and ('Enabled' in c.cget('text') or 'Use' in c.cget('text')) for c in walk(app.manage_fields_window)), 'Manage Fields duplicate Enabled checkbox'
# Structural edits in Manage Fields must not implicitly re-enable a disabled field.
app._enabled_controls[0].invoke();root.update()
assert app.enabled_vars[0].get() is False
app.designer_selected=0;app._manage_refresh();root.update()
app.manage_name.set('Sample Field');app._manage_apply();root.update()
assert app.enabled_vars[0].get() is False, 'Manage Fields reset Use state'
assert app.field_definitions[0]['name']=='Sample Field'
app._close_grid_mode();app._close_form_preview();root.destroy()
print('PASS: no visual quick toggles or Alt actions; Manage Fields does not overwrite Use state')
