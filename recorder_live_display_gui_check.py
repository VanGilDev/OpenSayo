"""Recorder test with local synthetic GUI key events only; no global keyboard hook."""
from pathlib import Path
import sys, tkinter as tk
from tkinter import ttk
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'py'))
from opensayo_v019_alpha22 import App
root=tk.Tk();root.geometry('1100x800')
app=App(root);root.update()
app._workspace_activate('freeform',script='',readable='');root.update()
app._open_recorder();root.update()
w=app.recorder_window
assert w.winfo_exists()
def descendants(node):
    for child in node.winfo_children():
        yield child
        yield from descendants(child)
cap=next(x for x in descendants(w) if isinstance(x,tk.Text))
buttons={x.cget('text'):x for x in descendants(w) if isinstance(x,ttk.Button)}
buttons['Start'].invoke();root.update()
# Generate synthetic keypresses in the recorder's capture box.
cap.focus_force();root.update()
for name in ('a','b','Tab','BackSpace','Return'):
    cap.event_generate('<KeyPress>',keysym=name)
    cap.event_generate('<KeyRelease>',keysym=name)
    root.update()
rendered=cap.get('1.0','end-1c')
assert 'a' in rendered and 'b' in rendered and '{TAB}' in rendered and '{BACKSPACE}' in rendered and '{ENTER}' in rendered,repr(rendered)
buttons['Stop'].invoke();root.update()
buttons['Apply Script'].invoke();root.update()
text=app.freeform_text.get('1.0','end-1c')
assert text=='ab{TAB}{BACKSPACE}{ENTER}',repr(text)
assert not w.winfo_exists()
root.destroy()
print('PASS: locally captured keys appear immediately in recorder text box; Apply Script imports same event sequence')
