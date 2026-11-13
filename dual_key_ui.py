"""Read-only dual-key inspection and explicit two-part overflow preview."""
import tkinter as tk
from tkinter import ttk, messagebox
from dual_key_overflow import split_script
from device_readback import read_bank,decode
from sayo_macro_language import script_to_readable
from opensayo_v019_alpha22 import FIELD_NAMES

class DualKeyWindow(tk.Toplevel):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app=app
        self.title('OpenSayo — Dual-Key Form Viewer / Overflow')
        self.geometry('1050x700')
        self.k1=tk.StringVar(value=app.physical_key1.get())
        self.k2=tk.StringVar(value=app.physical_key2.get())
        self.source={}
        self.plan=None
        top=ttk.Frame(self,padding=10);top.pack(fill='x')
        for name,var in [('Key 1 script',self.k1),('Key 2 script',self.k2)]:
            ttk.Label(top,text=name).pack(side='left',padx=5)
            ttk.Combobox(top,textvariable=var,values=[str(i) for i in range(1,9)],width=5,state='readonly').pack(side='left')
        ttk.Button(top,text='Load Both from Device',command=self.load_both).pack(side='left',padx=12)
        ttk.Label(self,text='Viewer reads both banks independently. Loading does not edit either bank or the main editor.',padding=(12,0)).pack(anchor='w')
        book=ttk.Notebook(self);book.pack(fill='both',expand=True,padx=10,pady=8)
        self.views={}
        for label in ('Key 1','Key 2','Compare','Overflow preview'):
            frame=ttk.Frame(book);book.add(frame,text=label)
            widget=tk.Text(frame,wrap='none',font=('Consolas',10),undo=False)
            widget.pack(fill='both',expand=True)
            self.views[label]=widget
        self.book=book
        bottom=ttk.Frame(self,padding=10);bottom.pack(fill='x')
        ttk.Button(bottom,text='Plan overflow from main macro',command=self.plan_overflow).pack(side='left')
        ttk.Button(bottom,text='Copy Part 1 to main editor',command=lambda:self.copy_part(0)).pack(side='left',padx=8)
        ttk.Button(bottom,text='Copy Part 2 to main editor',command=lambda:self.copy_part(1)).pack(side='left')
        ttk.Label(self,text='Important: Key 2 does NOT start automatically. Press Key 2 manually after Key 1 finishes. No hardware writes in this viewer.',foreground='#8b4e10',padding=10).pack(anchor='w')
    def put(self,key,value):
        w=self.views[key];w.config(state='normal');w.delete('1.0','end');w.insert('1.0',value);w.config(state='disabled')
    @staticmethod
    def form_summary(decoded, unknown):
        if unknown:
            return 'Unrecognized instructions: no form fields inferred.'
        try:
            readable,_=script_to_readable(decoded)
            chunks=readable.split('{TAB}')
            # Provide an interpretation only when the script contains a
            # plausible tab-separated form sequence; never claim certainty.
            if len(chunks)<4 or not chunks[0].strip() or not chunks[1].strip():
                return 'No recognizable tab-separated form structure.'
            lines=['Form sequence candidate (partial sequences allowed):','']
            for i,value in enumerate(chunks[:len(FIELD_NAMES)]):
                lines.append(f'{i+1:02d} {FIELD_NAMES[i]}: {value or "(blank / navigation)"}')
            lines.append('\nInterpretation only; raw macro remains unchanged.')
            return '\n'.join(lines)
        except Exception as exc:
            return 'Form recognition unavailable: '+str(exc)

    def load_both(self):
        self.source={}
        try:
            for key,slot in [('Key 1',int(self.k1.get())),('Key 2',int(self.k2.get()))]:
                data=read_bank(slot)
                decoded,unknown,size=decode(data)
                self.source[key]={'slot':slot,'script':decoded,'size':size,'unknown':unknown}
                self.put(key,f'{key} → Script {slot} | {size} bytes'+(' | UNKNOWN OPCODES' if unknown else '')+'\n\n'+self.form_summary(decoded,unknown)+'\n\n=== ORIGINAL INSTRUCTIONS ===\n'+decoded)
            a,b=self.source['Key 1'],self.source['Key 2']
            self.put('Compare',f'KEY 1: Script {a["slot"]}, {a["size"]} bytes\nKEY 2: Script {b["slot"]}, {b["size"]} bytes\n\n=== KEY 1 FORM ===\n{self.form_summary(a["script"],a["unknown"])}\n\n=== KEY 2 FORM ===\n{self.form_summary(b["script"],b["unknown"])}')
            messagebox.showinfo('OpenSayo','Load successful',parent=self)
        except Exception as exc:messagebox.showerror('Dual-key read failed',str(exc),parent=self)
    def plan_overflow(self):
        try:
            source=self.app.macro_text.get('1.0','end-1c')
            a,b,na,nb=split_script(source)
            self.plan=(a,b)
            self.put('Overflow preview',f'PART 1 → Key 1: {na}/468 bytes\nPART 2 → Key 2: {nb}/468 bytes\n\nKey 2 requires a SECOND PHYSICAL PRESS.\nThis plan does not write or reassign hardware.\n\n=== PART 1 ===\n{a}\n=== PART 2 ===\n{b or "(no overflow)"}')
            self.book.select(3)
            messagebox.showinfo('Overflow plan ready',f'Part 1: {na} bytes\nPart 2: {nb} bytes\n\nPreview only. Device unchanged.',parent=self)
        except Exception as exc:messagebox.showerror('Overflow unavailable',str(exc),parent=self)
    def copy_part(self,index):
        if not self.plan:
            messagebox.showwarning('No plan','Click Plan overflow first.',parent=self);return
        text=self.plan[index]
        if not text:
            messagebox.showinfo('No overflow','There is no second part.',parent=self);return
        if not messagebox.askyesno('Replace editor text?',f'Copy Part {index+1} to the main editor?\nThis replaces the editor contents, not the device. Save your original first.',parent=self):return
        self.app._macro_sync_lock=True
        try:
            self.app.macro_text.delete('1.0','end');self.app.macro_text.insert('1.0',text)
        finally:self.app._macro_sync_lock=False
        self.app._macro_reverse()
