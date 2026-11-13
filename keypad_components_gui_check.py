"""Offline fake-HID regression for keypad component paths, no USB connected.

The fake device sources and macros are synthetic, not private definitions.
"""
from pathlib import Path
import sys, time, tkinter as tk
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'py'))
from opensayo_v019_alpha22 import App, messagebox
from sayo_macro_language import compile_macro, script_to_readable, validate_script
from alpha22_device_ops import encode_script
from eight_key_protocol_v111 import offline_selftest, script_packets

assert offline_selftest()
root=tk.Tk(); root.geometry('1200x800'); app=App(root); root.update()
prompts=[]
messagebox.askyesno=lambda *a,**k: True
messagebox.showinfo=lambda *a,**k: prompts.append(('info',a))
messagebox.showwarning=lambda *a,**k: prompts.append(('warn',a))
messagebox.showerror=lambda *a,**k: prompts.append(('error',a))

# 2-key readback uses a simulated source and fake read_bank, never HID.
import device_readback, hardware_protocol
readsrc=compile_macro('{BACKSPACE}{TAB}SMALL{TAB}A', 11,22,13)
readimage=encode_script(readsrc).ljust(512,b'\0')
orig_decode=device_readback.decode; orig_read=device_readback.read_bank
calls=[]
device_readback.read_bank=lambda bank: (calls.append(('read',bank)) or readimage)
device_readback.decode=lambda data: (readsrc,[],len(encode_script(readsrc)))
app.layout_mode.set('2');app._switch_device_layout();root.update()
app._a22_device_load();root.update()
assert calls and calls[0][0]=='read',calls
assert app.field_vars[0].get()=='{BACKSPACE}'
assert app.field_vars[1].get()=='SMALL'
assert app._compile_form_key(1)[0].strip()==readsrc.strip()
assert app.macro_text.get('1.0','end-1c').strip()==readsrc.strip()
assert not [x for x in calls if x[0]=='write'],'read must never write'
# Simulated 2-key save: verify packet assembly and readback, no real I/O.
orig_make=hardware_protocol.make_bank_reports
orig_send=hardware_protocol.send
hardware_protocol.make_bank_reports=lambda bank,code:(calls.append(('build2',bank,len(code))) or [b'packet-2'])
hardware_protocol.send=lambda data:calls.append(('write2-simulated',len(data)))
app._a22_device_save();root.update()
assert any(x[0]=='build2' for x in calls)
assert any(x[0]=='write2-simulated' for x in calls)
# Malformed/overlong device import must leave editors unchanged.
old_fields=[v.get() for v in app.field_vars]
old_script=app.macro_text.get('1.0','end-1c')
device_readback.decode=lambda data: (compile_macro('A'+('{TAB}B'*30)),[],100)
app._a22_device_load();root.update()
assert [v.get() for v in app.field_vars]==old_fields
assert app.macro_text.get('1.0','end-1c')==old_script
assert any(x[0]=='warn' for x in prompts)
# Restore fake modules immediately after simulated 2-key tests.
device_readback.decode=orig_decode;device_readback.read_bank=orig_read
hardware_protocol.make_bank_reports=orig_make;hardware_protocol.send=orig_send

# 8-key layout picker, slot index and per-key packet construction.
app.layout_mode.set('8');app._switch_device_layout();root.update()
for key in (0,1,2,3,4,5,6,7,8,32,63):
    app.eight_script_slot.set(str(key))
    assert app._eight_selected_slot()==key
    blocks,end,save=script_packets(key,encode_script(readsrc)+b'\xff')
    assert len(blocks)==39 and all(len(b)==64 for b in blocks)
app.eight_script_slot.set('0')
# Mock async 8-key READ: HID module is dummy; reader returns empty image which
# fake decoder converts into the synthetic source.
import eight_key_script_read_v111,eight_key_protocol_v111
orig_reader=eight_key_script_read_v111.read_script_slot
orig_decode=device_readback.decode
import types
sys.modules['hid']=types.SimpleNamespace()  # no device implementation by design
read_calls=[]
eight_key_script_read_v111.read_script_slot=lambda hid,slot:(read_calls.append(slot) or b'simulated')
device_readback.decode=lambda data:(readsrc,[],len(encode_script(readsrc)))
app._eight_load_focused()
for _ in range(45):
    root.update();time.sleep(.014)
    if 'read back and loaded' in app.session_status.get():break
assert read_calls==[0],read_calls
assert app.field_vars[0].get()=='{BACKSPACE}'
assert app._eight_source().strip()==readsrc.strip()
assert not any('Invalid/incomplete' in p for p in [app.eight_meter_label.get()]), app.eight_meter_label.get()
# Verify a Form edit changes same source used by meter, save and preview.
app.field_vars[1].set('REPLACED');root.update()
newsource=app._eight_source()
assert newsource.strip()!=readsrc.strip()
assert 'REPLACED' in script_to_readable(newsource)[0]
assert app.eight_meter_label.get().split('/')[0]==str(len(encode_script(newsource))+1)
# Simulate saved write safely; no hid.device exists.
orig_write=eight_key_protocol_v111.guarded_write_one
write_calls=[]
eight_key_protocol_v111.guarded_write_one=lambda hid,slot,code: (write_calls.append((slot,bytes(code))) or {'verified_persistent':False})
app._eight_save_focused()
for _ in range(45):
    root.update();time.sleep(.014)
    if write_calls:break
assert write_calls and write_calls[0][0]==0
assert write_calls[0][1]==encode_script(newsource)+b'\xff'
# Selecting another slot must not silently replace active field contents.
prior=app.field_vars[1].get()
app.eight_script_slot.set('7');app._eight_slot_changed();root.update()
assert app.field_vars[1].get()==prior
# Invalid synthetic slot read is refused with no partial form mutation.
old_fields=[v.get() for v in app.field_vars]
app._sync_form_to_editor();root.update()
old_source=app.macro_text.get('1.0','end-1c')
eight_key_script_read_v111.read_script_slot=lambda hid,slot:b'bad8'
device_readback.decode=lambda data:(compile_macro('A'+('{TAB}B'*30)),[],100)
app._eight_load_focused()
for _ in range(60):root.update();time.sleep(.012)
assert [v.get() for v in app.field_vars]==old_fields
assert app.macro_text.get('1.0','end-1c')==old_source, (app.macro_text.get('1.0','end-1c')[:100],old_source[:100],app.session_status.get())
# Freeform imports raw device macro independently of form formatting.
app._workspace_activate('freeform',script='',readable='')
app._eight_import_into_original_editor(readsrc,7);root.update()
assert app._freeform_source().strip()==readsrc.strip()
assert app.freeform_text.get('1.0','end-1c').startswith('{BACKSPACE}{TAB}SMALL')
# Cleanup patched protocol functions.
eight_key_script_read_v111.read_script_slot=orig_reader
device_readback.decode=orig_decode
eight_key_protocol_v111.guarded_write_one=orig_write
root.destroy()
print('PASS: simulated 2-key read/write/no-write-on-load/invalid rejection, 8-key slot/read/write/byte-meter/form-freeform parity, safe packet construction')
print('NO USB device was opened or programmed; write operations were replaced by local fakes.')
