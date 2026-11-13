"""Offline GUI smoke check for Help; run under a display/Xvfb. No USB writes."""
from pathlib import Path
import ast
import sys
import tkinter as tk
from tkinter import ttk
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'py'))
from opensayo_v019_alpha22 import App

source=Path(__file__).resolve().parents[1]/'py'/'opensayo_v019_alpha22.py'
tree=ast.parse(source.read_text(encoding='utf-8'))
f=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='_show_help')
a=next(x for x in f.body if isinstance(x,ast.Assign) and any(isinstance(y,ast.Name) and y.id=='sections' for y in x.targets))
sections=ast.literal_eval(a.value)
assert len(sections)>=20, f'Expected comprehensive help, found {len(sections)} topics'
assert len({heading for heading,_ in sections})==len(sections)
for heading,body in sections:
    assert len(body)>100, (heading, 'short description')
    assert not any(x in body.casefold() for x in ('private business terminology','obsolete workflow label','v0.28','v0.18')),(heading, 'obsolete or identifying text')
needed=('Field','Freeform','Dropdown','Date','8-Key','2-Key','Device','Capacity','Restore')
assert all(any(k.lower() in h.lower() for h,_ in sections) for k in needed)
root=tk.Tk();root.withdraw()
app=App(root)
app._show_help()
root.update_idletasks()
w=app.help_window
assert w and w.winfo_exists()
texts=[c for c in w.winfo_children()[0].winfo_children() if isinstance(c,tk.Text)]
assert len(texts)==1, len(texts)
body=texts[0]
content=body.get('1.0','end')
for idx,(heading,detail) in enumerate(sections):
    assert f'{idx+1}. {heading}' in content
    assert detail in content
    assert body.tag_ranges(f'section_{idx}')
    assert body.tag_ranges(f'toc_{idx}')
buttons=[c for c in w.winfo_children()[0].winfo_children()[0].winfo_children() if isinstance(c,ttk.Button)]
assert any(b.cget('text')=='Find Next' for b in buttons)
search_entry=next(c for c in w.winfo_children()[0].winfo_children()[0].winfo_children() if isinstance(c,ttk.Entry))
search_entry.insert(0,'2028')
next(b for b in buttons if b.cget('text')=='Find Next').invoke()
root.update()
assert body.tag_ranges('search_hit'), 'Find Next failed'
# Avoid leaking a user profile from a test run: test in a temporary HOME.
w.destroy(); root.destroy()
print(f'PASS: {len(sections)} full Help topics, linked contents, search, no private terms; no device writes')
