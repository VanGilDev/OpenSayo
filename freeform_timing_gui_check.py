"""v1.15 shared Freeform timing toolbar and safe local Wait insertion."""
from pathlib import Path
import sys,tkinter as tk
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'py'))
from opensayo_v019_alpha22 import App
root=tk.Tk();app=App(root);root.update()
app._restore_timing_defaults();app.dropdown_open_ms.set('75');root.update()
app._workspace_activate('freeform',script='',readable='HELLO{TAB}WORLD')
root.update()
assert hasattr(app,'freeform_timing_status')
assert (app.macro_key_ms.get(),app.macro_nav_ms.get(),app.macro_repeat_ms.get(),app.dropdown_open_ms.get()) == ('15','20','15','75')
original=app._freeform_source()
app.macro_key_ms.set('35');app.macro_nav_ms.set('45');app.macro_repeat_ms.set('55');app.dropdown_open_ms.set('95')
app._apply_freeform_timing();root.update()
assert (app.text_delay.get(),app.action_delay.get(),app.repeat_gap.get())==('35','45','55')
assert 'device not programmed' in app.freeform_timing_status.get()
assert app._freeform_source()!=original,'Updated timing should change generated readable script'
assert '35' in app._freeform_source() and '45' in app._freeform_source()
# A WAIT token is emitted only from explicit user action and can be changed.
app.insert_wait_ms.set('120')
app.freeform_text.mark_set('insert','end-1c')
app._insert_freeform_wait();root.update()
assert '{WAIT:120}' in app.freeform_text.get('1.0','end-1c')
assert 'SLEEP 120' in app._freeform_source()
# Restoring defaults also updates Freeform toolbar because it shares variables.
app._restore_timing_defaults();app.dropdown_open_ms.set('75');root.update()
assert (app.macro_key_ms.get(),app.macro_nav_ms.get(),app.macro_repeat_ms.get())==('15','20','15')
root.destroy()
print('PASS: Freeform timing controls share 15/20/15 + 75 defaults; Apply is local, Wait inserted, no USB write')
