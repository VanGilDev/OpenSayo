"""Synthetic OpenSayo project-file recovery regression. Runs offline under Windows GUI or Xvfb.

No real project/definitions, USB data, user-specific form labels or device access.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import sys
import tkinter as tk

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'py'))
from opensayo_v019_alpha22 import (
    App, UnsupportedProjectFormat, prepare_workspace_project,
    read_workspace_project, approved_default_project,
    UNSUPPORTED_PROJECT_NOTICE, UNREADABLE_PROJECT_NOTICE,
)

with TemporaryDirectory() as td:
    directory=Path(td)
    bad=directory/'Synthetic_Unsupported_Old_Project.osayo'
    # Simulate an older project with 69 generic fields, not a private config.
    bad.write_text(json.dumps({
        'format':'OpenSayo-OldProject','version':0,'dynamic_form':False,
        'fields':[{'name':f'Sample Field {n:02d}','value':'','format_type':'Text'}
                  for n in range(1,70)]
    }),encoding='utf-8')
    try:read_workspace_project(bad)
    except UnsupportedProjectFormat:pass
    else:raise AssertionError('Unsupported old file was unexpectedly accepted')

    current=directory/'Synthetic_Current_Project.osayo'
    current.write_text(json.dumps({
        'format':'opensayo-v023','version':1,'kind':'form_project',
        'form':approved_default_project(), 'scripts':{'1':'EXIT','2':'EXIT'}
    }),encoding='utf-8')
    kind,form_data,script,readable=read_workspace_project(current)
    assert kind=='form_project' and len(form_data['form']['fields'])==25
    free=directory/'Synthetic_Current_Freeform.osayo'
    free.write_text(json.dumps({
        'format':'opensayo-v023','version':1,'kind':'freeform',
        'script':'EXIT','readable':'Example'
    }),encoding='utf-8')
    kind,form_data,script,readable=read_workspace_project(free)
    assert kind=='freeform' and script=='EXIT' and readable=='Example'

    compatible=approved_default_project()
    compatible['format']='OpenSayo-PreviousForm'
    compatible['version']=2
    compatible['fields']=[dict(compatible['fields'][0],name=f'Sample {i+1}',field_id=f'id_{i:02d}') for i in range(69)]
    kind,form_data,_,_=prepare_workspace_project(compatible)
    assert kind=='form_project' and len(form_data['form']['fields'])==69

    damaged=directory/'Synthetic_Damaged.osayo'
    damaged.write_text('not valid json {{',encoding='utf-8')
    try:read_workspace_project(damaged)
    except ValueError:pass
    else:raise AssertionError('Damaged file was unexpectedly accepted')

    root=tk.Tk();root.withdraw()
    app=App(root)
    root.update_idletasks()
    # This is a volatile fake value: check that a failed open never deletes it.
    app.field_vars[0].set('UNSAVED EXAMPLE')
    before=app._workspace_snapshot()
    previous_path=app.workspace_path
    calls=[]
    def never_ask_to_leave():
        raise AssertionError('Unexpected save/discard prompt for rejected file')
    with (patch('tkinter.filedialog.askopenfilename',return_value=str(bad)),
          patch('tkinter.messagebox.showwarning',side_effect=lambda *args:calls.append(args)),
          patch('tkinter.messagebox.showerror',side_effect=lambda *args:calls.append(args)),
          patch.object(app,'_workspace_confirm_leave',side_effect=never_ask_to_leave)):
        app._workspace_open()
    assert len(calls)==1 and calls[0][0]=='Unsupported Project Format'
    assert calls[0][1]==UNSUPPORTED_PROJECT_NOTICE
    assert app._workspace_snapshot()==before and app.workspace_path==previous_path

    calls=[]
    with (patch('tkinter.filedialog.askopenfilename',return_value=str(damaged)),
          patch('tkinter.messagebox.showwarning',side_effect=lambda *args:calls.append(args)),
          patch('tkinter.messagebox.showerror',side_effect=lambda *args:calls.append(args)),
          patch.object(app,'_workspace_confirm_leave',side_effect=never_ask_to_leave)):
        app._workspace_open()
    assert len(calls)==1 and calls[0][0]=='Cannot Open Project'
    assert calls[0][1]==UNREADABLE_PROJECT_NOTICE
    assert app._workspace_snapshot()==before and app.workspace_path==previous_path

    # A saved modern file must still open normally and replace the working view.
    with (patch('tkinter.filedialog.askopenfilename',return_value=str(current)),
          patch.object(app,'_workspace_confirm_leave',return_value=True),
          patch('tkinter.messagebox.showerror',side_effect=AssertionError('Unexpected modern project load error'))):
        app._workspace_open()
    assert app.workspace_path==str(current)
    assert app.workspace_kind=='form_project'
    assert app.field_vars[0].get()!='UNSAVED EXAMPLE'
    root.destroy()

print('PASS: unsupported 69-field old project warns; corrupt file errors; active unsaved workspace remains unchanged; current project, freeform, and structural prior form load')
print('NO devices contacted, no USB writes, no private files loaded')
