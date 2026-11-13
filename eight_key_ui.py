"""Read-only 2x4V RGB physical-key assignment editor, OpenSayo v1.1.

No configuration-writing commands are implemented here. A guarded USB read is
performed only on explicit user request, against VID/PID 8089:000B FF00/0001.
"""
import time
import tkinter as tk
from tkinter import ttk, messagebox

VID, PID, PAGE, USAGE = 0x8089, 0x000B, 0xFF00, 0x0001


def read_eight():
    import hid
    matches = [d for d in hid.enumerate(VID, PID)
               if d.get('usage_page') == PAGE and d.get('usage') == USAGE]
    if len(matches) != 1:
        raise RuntimeError(f'Expected one 2x4V RGB vendor interface; found {len(matches)}. No reports sent.')
    dev = hid.device()
    result = []
    try:
        dev.open_path(matches[0]['path'])
        for index in range(8):
            request = bytearray(64)
            request[:5] = bytes((2, 0x16, 2, 0, index))
            request[5] = sum(request[:5]) & 255
            if dev.write(bytes(request)) != 64:
                raise RuntimeError(f'Key {index+1}: HID request failed; stopped.')
            raw = bytes(dev.read(64, timeout_ms=1500))
            if len(raw) != 64 or raw[:3] != b'\x02\x00\x2e':
                raise RuntimeError(f'Key {index+1}: unexpected response header or size; stopped.')
            payload = raw[3:49]
            if payload[:2] != bytes((0, index)) or payload[2] != 1:
                raise RuntimeError(f'Key {index+1}: unexpected record index or mode; stopped.')
            # This selector location was established through before/after readback.
            selector = raw[19]
            script = selector - 0x40 if 0x40 <= selector <= 0x7f else None
            result.append((index, script, raw))
            time.sleep(.12)
    finally:
        dev.close()
    return result


class EightKeyWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title('OpenSayo v1.1 — 2x4V RGB · 8 Physical Keys')
        self.geometry('760x500')
        self.minsize(660, 430)
        self.vars = [tk.StringVar(value='Not read') for _ in range(8)]
        self.actual = [None] * 8
        self.verified = False
        self.status = tk.StringVar(value='Device assignments have not been read.')
        ttk.Label(self, text='2x4V RGB · Physical Key Assignments',
                  font=('Segoe UI', 15, 'bold')).pack(anchor='w', padx=18, pady=(16, 4))
        ttk.Label(self, text='Eight independent keys · 64 script slots (0–63) · readback-enabled preview').pack(anchor='w', padx=18)
        board = ttk.Frame(self, padding=12)
        board.pack(fill='both', expand=True, padx=12, pady=10)
        for i in range(8):
            r, c = divmod(i, 4)
            box = ttk.LabelFrame(board, text=f'Physical Key {i+1}', padding=12)
            box.grid(row=r, column=c, padx=5, pady=7, sticky='nsew')
            ttk.Label(box, text=f'Device index {i}').pack(anchor='w')
            ttk.Combobox(box, textvariable=self.vars[i], state='readonly',
                         values=[f'Script {n}' for n in range(64)], width=13).pack(pady=(8, 2), fill='x')
        for c in range(4):board.columnconfigure(c, weight=1)
        for r in range(2):board.rowconfigure(r, weight=1)
        ttk.Label(self, textvariable=self.status, wraplength=700).pack(fill='x', padx=18, pady=(0, 8))
        buttons = ttk.Frame(self, padding=(16, 0, 16, 8))
        buttons.pack(fill='x')
        ttk.Button(buttons, text='Read All 8 From Device', command=self.read_device).pack(side='left', padx=4)
        ttk.Button(buttons, text='Compare Selections', command=self.compare).pack(side='left', padx=4)
        ttk.Button(buttons, text='Apply to Device (not yet verified)', state='disabled').pack(side='left', padx=4)
        ttk.Button(buttons, text='Close', command=self.destroy).pack(side='right', padx=4)
        ttk.Label(self, text='Safety: no script writes, assignment writes, saves, or firmware commands. '
                  'Selections are preview-only until the write protocol is verified.',
                  foreground='#a10016', wraplength=720).pack(fill='x', padx=18, pady=(0, 14))

    def read_device(self):
        if not messagebox.askyesno('Read 8-key assignments',
            'Send eight read-only O2 0x16 requests to 8089:000B?\n\n'
            'This will NOT save or change the device.', parent=self):
            return
        try:
            records = read_eight()
        except Exception as exc:
            self.verified = False
            self.status.set(f'READ FAILED — {exc}')
            messagebox.showerror('8-key readback failed', str(exc), parent=self)
            return
        self.actual = [slot for _, slot, _ in records]
        for i, slot in enumerate(self.actual):
            self.vars[i].set(f'Script {slot}' if slot is not None else 'Unknown assignment')
        self.verified = all(x is not None for x in self.actual)
        self.status.set('8/8 read. ' + ('All assignments decoded (device readback).' if self.verified else
                                      'Some assignments are not script mode; no verification claimed.'))

    def compare(self):
        if not self.verified:
            messagebox.showwarning('Not verified', 'Read all eight device assignments first.', parent=self)
            return
        matches = [self.vars[i].get() == f'Script {self.actual[i]}' for i in range(8)]
        self.status.set('8/8 selections match device readback.' if all(matches) else
                        f'{sum(matches)}/8 selections match device readback. No changes sent.')
