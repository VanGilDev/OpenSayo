"""Offline earlier build GUI repeat-window regression; run under Xvfb or Windows.
No device communication. Uses a generic app session and no personal definitions.
"""
from pathlib import Path
import sys, tkinter as tk
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'py'))
from opensayo_v019_alpha22 import App, VERSION
assert VERSION=='1.15'
root=tk.Tk(); root.withdraw()
try:
    app=App(root)
    cases=[
        ('Help',lambda:app._show_help(),'help_window'),
        ('About',lambda:app._show_about(),'about_window'),
        ('Settings',lambda:app.settings(),'settings_window'),
        ('Form View',lambda:app.open_form_preview(),'form_preview_window'),
        ('Grid Mode',lambda:app._open_grid_mode(),'designer_grid_window'),
        ('Manage Fields',lambda:app._open_manage_fields(),'manage_fields_window'),
        ('Recorder',lambda:app._open_recorder(),'recorder_window'),
        ('Navigate Keys',lambda:app._edit_navigate_keys(0),'navigate_keys_window'),
        ('8-Key Device Management',lambda:app._eight_device_management(),'eight_device_management_window'),
    ]
    for name,fn,attr in cases:
        fn(); root.update_idletasks(); first=getattr(app,attr)
        assert first is not None and first.winfo_exists(),f'{name}: not opened'
        for _ in range(3):
            fn(); root.update_idletasks()
            assert getattr(app,attr) is first and first.winfo_exists(),f'{name}: duplicate created'
        first.destroy();root.update_idletasks()
        fn();root.update_idletasks()
        second=getattr(app,attr)
        assert second is not first and second.winfo_exists(),f'{name}: reopen failed'
        second.destroy()
    print(f'PASS: {len(cases)} modeless dialogs single-instance + close/reopen, no USB writes')
finally:
    root.destroy()
