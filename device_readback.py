"""Experimental read-only O2L V2 script reader, inferred from 1->8->1 USBPcap."""
import time
import hardware_protocol as hw

SCRIPT_LENGTH=512

def request(bank, offset):
    if bank not in range(1,9):raise ValueError('Script 1-8 only')
    p=bytearray(64)
    p[0:2]=b'\x21\x12';p[4:6]=b'\x08\x00';p[6]=0x1a;p[7]=bank-1
    p[8:12]=offset.to_bytes(4,'little')
    return hw.checksum(p)

def response(dev,bank,offset,timeout_ms=1500):
    req=request(bank,offset)
    if dev.write(req)!=64:raise IOError('Read request HID write failed')
    deadline=time.monotonic()+timeout_ms/1000
    while time.monotonic()<deadline:
        received=bytes(dev.read(64,max(1,int((deadline-time.monotonic())*1000))))
        if len(received)==65 and received[0]==0:received=received[1:]
        if len(received)!=64:continue
        if received[:2]!=b'\x21\x12' or received[6]!=0x1a:continue
        if received[7]!=bank-1:continue
        if offset!=0xffffffff and received[8:12]!=req[8:12]:continue
        if hw.checksum(received)!=received:raise IOError('Response checksum mismatch')
        expected_size=0x08 if offset==0xffffffff else (0x34 if offset==468 else 0x3c)
        if received[4]!=expected_size:raise IOError(f'Unexpected response payload size {received[4]}')
        return received
    raise TimeoutError(f'No matching response for Script {bank} offset {offset:#x}')

def read_bank(bank):
    dev=hw.device()
    try:
        header=response(dev,bank,0xffffffff)
        length=int.from_bytes(header[8:12],'little')
        # Capture header payload starts 00 02 00 00 => 512 bytes.
        if length not in (512,4096):raise ValueError(f'Unexpected script size {length} bytes; refusing to guess')
        out=bytearray()
        for offset in range(0,length,52):
            p=response(dev,bank,offset)
            out.extend(p[12:12+min(52,length-offset)])
            time.sleep(.012)
        return bytes(out)
    finally:dev.close()

# Decode all keys that the encoder can write, including modifier opcodes.
# Import lazily to avoid a circular dependency with the GUI module.
def _key_names():
    from opensayo_v019_alpha22 import KEY_CODES
    from alpha22_device_ops import EXTRA_KEYS
    names={}
    for key,code in {**KEY_CODES,**EXTRA_KEYS}.items():
        names.setdefault(code,key)
    # Prefer the canonical spelling for directional keys.
    for key,code in EXTRA_KEYS.items():
        if key.startswith("Arrow"):names[code]=key
    # Canonical Sayo website names, not printable punctuation aliases from
    # the older GUI KEY_CODES table. These aliases share the same HID code.
    canonical={
        0x2D:"Minus",0x2E:"Equal",0x2F:"BracketLeft",0x30:"BracketRight",
        0x31:"Backslash",0x33:"Semicolon",0x34:"Quote",0x35:"Backquote",
        0x36:"Comma",0x37:"Period",0x38:"Slash",
        0x4F:"ArrowRight",0x50:"ArrowLeft",0x51:"ArrowDown",0x52:"ArrowUp",
        0x4B:"PageUp",0x4E:"PageDown",
    }
    names.update(canonical)
    return names

def decode(image):
    """Decode known bytecodes; preserve unknown suffix as RAW_HEX without editing it."""
    from sayo_macro_language import MODIFIER_KEYS
    names=_key_names()
    modifier_names={v:k for k,v in MODIFIER_KEYS.items()}
    lines=[];pos=0;unknown=False
    while pos<len(image):
        op=image[pos]
        if op in (0,255):
            if any(x not in (0,255) for x in image[pos:]):
                unknown=True;lines.append('RAW_HEX '+image[pos:].hex(' '))
            break
        if op in (0x11,0x19,0x10,0x18) and pos+1<len(image):
            code=image[pos+1]
            is_modifier=op in (0x10,0x18)
            name=(modifier_names if is_modifier else names).get(code)
            if name and name.strip():
                command=('PRESS_' if op in (0x11,0x10) else 'RELEASE_')+('SK' if is_modifier else 'GK')
                lines.append(command+' hidkey_'+name)
                pos+=2;continue
        if op==0x06 and pos+1<len(image):
            lines.append(f'SLEEP {image[pos+1]}');pos+=2;continue
        if op==0x0d and pos+2<len(image):
            lines.append(f'SLEEP_U16 {int.from_bytes(image[pos+1:pos+3],"little")}');pos+=3;continue
        unknown=True;lines.append('RAW_HEX '+image[pos:].hex(' '));break
    return '\n'.join(lines),unknown,pos
