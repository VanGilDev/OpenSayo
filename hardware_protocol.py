"""OpenSayo Alpha .20 experimental O2L V2 capture-derived writer.
Requires pip install hidapi; runs on Windows. No write occurs without explicit user confirmation.
"""
import argparse, pathlib, struct, sys, time, zipfile
VID,PID,INTERFACE,USAGE_PAGE,USAGE=0x8089,0x000c,1,0xff11,2
ROOT=pathlib.Path(getattr(sys, "_MEIPASS", pathlib.Path(__file__).resolve().parent))

def packets(path):
    b=path.read_bytes();pos=0;out=[]
    while pos+12<=len(b):
        typ,length=struct.unpack_from('<II',b,pos)
        if length<12 or pos+length>len(b): raise ValueError('Malformed PCAPNG block')
        if typ==6:
            n=struct.unpack_from('<I',b,pos+20)[0];f=b[pos+28:pos+28+n]
            if len(f)>=91 and f[16]==0 and f[21]==3 and f[22]==1 and f[27]==0x21:
                out.append(bytes(f[27:91]))
        pos+=length
    return out

def checksum(p):
    p=bytearray(p);p[2:4]=b'\0\0'
    value=sum(int.from_bytes(p[i:i+2],'little') for i in range(0,64,2))&0xffff
    p[2:4]=value.to_bytes(2,'little')
    return bytes(p)

def validate(p):
    return len(p)==64 and p[0:2]==b'\x21\x12' and checksum(p)==p

def bank_packets(bank):
    filename='script7_40_baseline.pcapng' if bank==7 else 'script8_40_baseline.pcapng'
    raw=packets(ROOT/'captures'/filename)
    assert len(raw)==220 and all(validate(p) for p in raw)
    assert all(p[7]==bank-1 for p in raw)
    unique={}
    for p in raw:
        if p[6]==0x1a and p[8:12]!=b'\xff'*4:
            offset=int.from_bytes(p[8:12],'little')
            if offset in unique: assert unique[offset]==p
            unique[offset]=p
    assert sorted(unique)==list(range(0,4057,52))
    image=bytearray(4096)
    for offset,p in unique.items():
        count=min(52,4096-offset)
        image[offset:offset+count]=p[12:12+count]
    a_pair=bytes.fromhex('11 04 06 64 19 04 06 96')
    b_pair=bytes.fromhex('11 05 06 64 19 05 06 96')
    assert image[:321]==b_pair+a_pair*39+b'\xff', 'Baseline does not match verified 321-byte image'
    assert not any(image[321:]), 'Unexpected nonzero trailing baseline bytes'
    # 58 complete key cycles (B + 57 A) = 464 bytes.
    # Add a final 2-byte sleep at 0x1D0, ending at 0x1D2 (466).
    # The next byte at 0x1D2 is 00, and all later bytes are zero.
    target=b_pair+a_pair*57+bytes.fromhex('06 64')
    assert len(target)==466
    assert target[464:466]==bytes.fromhex('06 64')
    for k in range(0,464,8):
        q=target[k:k+8]
        assert q[0]==0x11 and q[4]==0x19 and q[1]==q[5]
        assert q[2:4]==b'\x06\x64' and q[6:8]==b'\x06\x96'
    image[:]=target+b'\x00'*(4096-len(target))
    changed=[]
    for p in raw:
        q=bytearray(p)
        if q[6]==0x1a and q[8:12]!=b'\xff'*4:
            offset=int.from_bytes(q[8:12],'little')
            count=min(52,4096-offset)
            q[12:12+count]=image[offset:offset+count]
        changed.append(checksum(q))
    assert all(validate(p) for p in changed)
    assert len(changed)==220
    # Reconstruct outgoing transfer, including duplicated blocks, to prove round-trip.
    reconstructed=bytearray(4096)
    for p in changed:
        if p[6]==0x1a and p[8:12]!=b'\xff'*4:
            offset=int.from_bytes(p[8:12],'little');count=min(52,4096-offset)
            reconstructed[offset:offset+count]=p[12:12+count]
    assert reconstructed==image
    return changed,len(target),target

def assignment_packets(key1,key2):
    p=packets(ROOT/'captures'/'key_swap_reference.pcapng')
    assert len(p)==3 and all(validate(x) for x in p)
    assert p[0][6:8]==b'\x10\x00' and p[0][24]==0x47
    assert p[1][6:8]==b'\x10\x01' and p[1][24]==0x46
    assert p[2][:10]==bytes.fromhex('21 12 ca 84 06 00 0d 00 96 72')
    out=[]
    for i,slot in enumerate((key1,key2)):
        q=bytearray(p[i]);q[24]=0x40+slot-1;out.append(checksum(q))
    return out,p[2]

def device():
    import hid
    matches=[d for d in hid.enumerate(VID,PID) if d.get('interface_number')==INTERFACE and d.get('usage_page')==USAGE_PAGE and d.get('usage')==USAGE]
    if len(matches)!=1: raise RuntimeError(f'Expected exactly one matching O2L V2 interface, found {len(matches)}')
    dev=hid.device();dev.open_path(matches[0]['path']);print('OPENED: FF11/0002 vendor collection (report ID 0x21)');return dev

def send(seq):
    dev=device()
    try:
        for n,p in enumerate(seq,1):
            sent=dev.write(p)
            if sent!=64:raise IOError(f'Packet {n}/{len(seq)} wrote {sent} bytes instead of 64')
            time.sleep(.025)
        print(f'Sent {len(seq)} reports; DEVICE EXECUTION/PERSISTENCE NOT YET VERIFIED.')
    finally:dev.close()

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('stage',choices=['bank8','assign-7-8'])
    ap.add_argument('--write',action='store_true',help='Enable live USB writes after confirmation')
    a=ap.parse_args()
    if a.stage=='bank8':
        b8,n,target=bank_packets(8)
        assert n==466 and len(target)==466 and target[464:466]==bytes.fromhex('06 64')
        _,commit=assignment_packets(8,7)
        seq=b8+[commit]
        print('WRITE: Script 8 ONLY, 466 instruction bytes, B + 57 A, final SLEEP 100; 00 at 0x1D2.')
        print('Script 7 and physical key assignments unchanged.')
    else:
        updates,commit=assignment_packets(7,8)
        seq=updates+[commit]
        assert seq[0][24]==0x46 and seq[1][24]==0x47
        print('WRITE: Physical Key 1 -> Script 7; Physical Key 2 -> Script 8; then commit.')
        print('Script 7 and Script 8 contents are NOT rewritten.')
    assert all(validate(p) for p in seq)
    report=ROOT/f'preview_{a.stage}.txt'
    report.write_text('\n'.join(f'{i:03d} {p.hex(" ")}' for i,p in enumerate(seq))+'\n')
    print(f'Validated {len(seq)} outgoing reports. Packet preview: {report}')
    if not a.write:
        print('PREVIEW ONLY. No hardware writes occurred. Add --write when ready.');return
    print('EXPERIMENTAL HARDWARE WRITE: risk of device malfunction, lost assignments or stuck key.')
    print('Do not write assignments until BOTH banks are populated and verified.')
    print('Close the official website before writing; back up scripts first.')
    print('USB write success does NOT prove stored contents or persistence.')
    confirm=input(f'Type WRITE {a.stage} to proceed: ')
    if confirm!=f'WRITE {a.stage}':print('Cancelled.');return
    send(seq)

if __name__=='__main__':main()


def make_bank_reports(bank, target):
    """Experimental bank 1–6 writes use the validated bank 7 packet shape.

    Change only bank selector, payload and additive checksum.  This is a
    hypothesis requiring device readback; it is NOT a verified write protocol.
    """
    if bank not in range(1,9):
        raise ValueError("Bank must be 1–8")
    if len(target)>468:
        raise ValueError("468-byte per-bank cap exceeded")
    template=ROOT/'captures'/('script7_40_baseline.pcapng' if bank<=7 else 'script8_40_baseline.pcapng')
    raw=packets(template)
    if len(raw)!=220 or not all(validate(x) for x in raw):
        raise ValueError("Invalid captured write template")
    if not all(x[6]==0x1a and x[7]==(6 if bank<=7 else 7) for x in raw):
        raise ValueError("Unexpected bank template")
    image=target+b'\x00'*(4096-len(target))
    out=[]
    for p in raw:
        q=bytearray(p)
        q[7]=bank-1
        if q[8:12]!=b'\xff'*4:
            offset=int.from_bytes(q[8:12],'little')
            if offset>=4096:raise ValueError("Invalid captured offset")
            count=min(52,4096-offset)
            q[12:12+count]=image[offset:offset+count]
        out.append(checksum(q))
    _,commit=assignment_packets(7,8)
    reports=out+[commit]
    assert all(validate(x) for x in reports)
    return reports
