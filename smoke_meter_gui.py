import sys,tkinter as tk
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'py'))
from opensayo_v019_alpha22 import App
root=tk.Tk()
root.withdraw()
app=App(root)
app.layout_mode.set('8')
app._switch_device_layout()
root.deiconify()
root.update()
assert app.eight_meter_row.winfo_ismapped(), '8-key bar missing'
assert not app.capacity_row.winfo_ismapped(), '2-key meters erroneously shown'
assert not app.eight_capacity_label.winfo_ismapped(), 'redundant eight-key status line shown'
for n in range(8):
    app.eight_script_slot.set(str(n));root.update()
    assert app.eight_meter_title.get()==f'Script {n}',(n,app.eight_meter_title.get())
    assert app.eight_meter_label.get().endswith('/2028 bytes'),app.eight_meter_label.get()
print('PASS: one eight-key bar, all 8 slot titles track picker; two-key meters hidden',flush=True)
app.layout_mode.set('2');app._switch_device_layout();root.update()
assert app.capacity_row.winfo_ismapped(),'2-key bars not restored'
assert not app.eight_meter_row.winfo_ismapped(),'8-key bar visible in 2-key'
print('PASS: two-key meters restored after mode switch',flush=True)
root.destroy()
