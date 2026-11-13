"""Encode validated Sayo text into raw instruction bytes (without textual EXIT)."""
import re
from sayo_macro_language import validate_script, STANDARD_KEYS, MODIFIER_KEYS
from opensayo_v019_alpha22 import KEY_CODES
EXTRA_KEYS={"ShiftLeft":0xE1,"Minus":0x2D,"Equal":0x2E,"BracketLeft":0x2F,"BracketRight":0x30,
"Backslash":0x31,"Semicolon":0x33,"Quote":0x34,"Backquote":0x35,"Comma":0x36,
"Period":0x37,"Slash":0x38,"ArrowDown":0x51,"ArrowUp":0x52,"ArrowLeft":0x50,
"ArrowRight":0x4F,"PageUp":0x4B,"PageDown":0x4E}
EXTRA_KEYS.update({f"F{i}":0x3A+i-1 for i in range(1,13)})
EXTRA_KEYS.update({f"F{i}":0x68+i-13 for i in range(13,25)})

def encode_script(source):
    validate_script(source)
    out=bytearray()
    for line in source.splitlines():
        line=line.strip()
        if not line or line=='EXIT':continue
        m=re.fullmatch(r'(PRESS_GK|RELEASE_GK|PRESS_SK|RELEASE_SK) hidkey_([A-Za-z0-9_]+)',line)
        if m:
            op,key=m.groups()
            if op.endswith('_SK'):
                out.extend((0x10 if op=='PRESS_SK' else 0x18,MODIFIER_KEYS[key]))
            else:
                if key not in KEY_CODES and key not in EXTRA_KEYS:raise ValueError('Unsupported key '+key)
                out.extend((0x11 if op=='PRESS_GK' else 0x19,(KEY_CODES[key] if key in KEY_CODES else EXTRA_KEYS[key])))
            continue
        m=re.fullmatch(r'(SLEEP|SLEEP_U16) (\d+)',line)
        if m:
            kind,ms=m.group(1),int(m.group(2))
            if kind=='SLEEP':out.extend((0x06,ms))
            else:out.extend((0x0d,ms&255,ms>>8))
            continue
        raise ValueError('Unsupported instruction '+line)
    return bytes(out)
