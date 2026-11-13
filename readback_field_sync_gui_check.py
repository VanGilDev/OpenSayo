"""Offline device readback regression: 8-key, 2-key, form text/actions, exact timing.

Only fabricated test macros. No HID access or device writes.
"""
from pathlib import Path
import sys, tkinter as tk, copy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'py'))
from opensayo_v019_alpha22 import App, device_readback_form_rows
from sayo_macro_language import compile_macro, script_to_readable
from alpha22_device_ops import encode_script

raw=compile_macro('{BACKSPACE}{DOWN}{ENTER}{TAB}HELLO{TAB}{TAB}BETA{TAB}{DOWN}{ENTER}', 19,32,7)
raw=raw.strip()
readable,_=script_to_readable(raw)
rows,end=device_readback_form_rows(readable,25)
assert end==4 and rows[0][2]=='{BACKSPACE}{DOWN}{ENTER}' and rows[1][2]=='HELLO', (rows,end,readable)
root=tk.Tk();root.geometry('1100x800');app=App(root);root.update()
app.layout_mode.set('8');app._switch_device_layout();root.update()
assert app.workspace_kind=='form_project'
assert app._eight_import_into_original_editor(raw,0)
root.update()
assert app.field_vars[0].get()=='{BACKSPACE}{DOWN}{ENTER}',app.field_vars[0].get()
assert app.field_vars[1].get()=='HELLO',app.field_vars[1].get()
assert app.field_vars[2].get()==''
assert app.field_vars[3].get()=='BETA'
assert app.endpoint.get()==4
assert app._eight_source().strip()==raw, 'Read must not regenerate original timing'
assert app.macro_text.get('1.0','end-1c').strip()==raw
assert app.eight_meter_label.get().split('/')[0]==str(len(encode_script(raw))+1),app.eight_meter_label.get()
# Form edit triggers new macro, but preserves unrelated navigation-only fields.
app.field_vars[1].set('CHANGED')
root.update()
assert app._eight_source().strip()!=raw
edited,_=script_to_readable(app._eight_source())
assert edited.startswith('{BACKSPACE}{DOWN}{ENTER}{TAB}CHANGED{TAB}{TAB}BETA{TAB}{DOWN}{ENTER}'),edited
app._sync_form_to_editor();root.update()
assert app.macro_text.get('1.0','end-1c').strip()==app._eight_source().strip(), 'view disagreement after edit'
assert 'Invalid/incomplete' not in app.eight_meter_label.get(),app.eight_meter_label.get()
# Re-load, save, normalize and restore the exact raw timing.
app._eight_import_into_original_editor(raw,0);root.update()
project=app.current_project()
from opensayo_v019_alpha22 import normalize_project
app.apply(normalize_project(project));root.update()
assert app._compile_form_key(1)[0].strip()==raw, 'roundtrip lost original readback'
# Two-key form readback from the same fabricated script; check no partial overwrite.
app.layout_mode.set('2');app._switch_device_layout();root.update()
assert app._sync_raw_to_form(raw)
root.update()
assert app.field_vars[0].get()=='{BACKSPACE}{DOWN}{ENTER}'
assert app._compile_form_key(1)[0].strip()==raw
before=app.current_project()
raw_before=app.macro_text.get('1.0','end-1c')
bad=compile_macro('HELLO{TAB}BETA',15,20,15)
# Too many field segments: should reject without altering the form.
try:
    device_readback_form_rows('A'+('{TAB}B'*100),25)
except ValueError:pass
else:raise AssertionError('oversize form accepted')
assert before==app.current_project()
assert raw_before==app.macro_text.get('1.0','end-1c')
root.destroy()
print('PASS: lossless 2/8-key device script load, form action mapping, byte meter, edit sync, project roundtrip, reject invalid mapping')
