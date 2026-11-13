"""Experimental O2 2x4V RGB eight-key physical assignment writer.
Uses observed 0x16 full-record framing and 0x04 SAVE. No script-memory writes.
"""
import time
VID,PID,PAGE,USAGE=0x8089,0x000B,0xFF00,0x0001

def frame(cmd,payload):
    if len(payload)>60:raise ValueError('O2 payload too long')
    out=bytearray(64);out[:3]=bytes((2,cmd,len(payload)))
    out[3:3+len(payload)]=payload
    out[3+len(payload)]=sum(out[:3+len(payload)])&255
    return bytes(out)

def exchange(dev,cmd,payload):
    if dev.write(frame(cmd,payload))!=64:raise RuntimeError('HID write failed')
    raw=bytes(dev.read(64,timeout_ms=2500))
    if len(raw)!=64 or raw[0]!=2 or raw[1]!=0:raise RuntimeError(f'O2 command 0x{cmd:02X} failed: response={raw[:8].hex()} (status byte={raw[1] if len(raw)>1 else "missing"}). The device rejected this command; no write was attempted if this occurred during initial backup.')
    return raw

def read(dev,index):
    raw=exchange(dev,0x16,bytes((0,index)))
    if raw[2]!=46 or raw[3:5]!=bytes((0,index)) or raw[5]!=1:
        raise RuntimeError(f'Key {index+1} unexpected assignment record')
    return raw

def apply_assignments(slots):
    if len(slots)!=8 or any(type(s)!=int or not 0<=s<=63 for s in slots):
        raise ValueError('Exactly eight slots 0–63 required')
    import hid
    matches=[d for d in hid.enumerate(VID,PID) if d.get('usage_page')==PAGE and d.get('usage')==USAGE]
    if len(matches)!=1:raise RuntimeError(f'Expected one 8-key vendor interface; found {len(matches)}')
    dev=hid.device()
    try:
        dev.open_path(matches[0]['path'])
        before=[read(dev,i) for i in range(8)]
        for i,(raw,slot) in enumerate(zip(before,slots)):
            if raw[19]==0x40+slot:continue
            payload=bytearray(raw[3:49]);payload[0]=1;payload[16]=0x40+slot
            exchange(dev,0x16,bytes(payload));time.sleep(.15)
            after=read(dev,i)
            if after[19]!=0x40+slot:
                raise RuntimeError(f'Key {i+1} write mismatch. SAVE not sent; check device.')
        check=[read(dev,i) for i in range(8)]
        if any(raw[19]!=0x40+slots[i] for i,raw in enumerate(check)):
            raise RuntimeError('Pre-save eight-key verification failed; SAVE not sent')
        exchange(dev,0x04,b'\x72\x96');time.sleep(.2)
        final=[read(dev,i) for i in range(8)]
        if any(raw[19]!=0x40+slots[i] for i,raw in enumerate(final)):
            raise RuntimeError('Post-save verification failed')
        return [raw[19]-0x40 for raw in final]
    finally:dev.close()
