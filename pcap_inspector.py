"""Offline-only USBPcap analyzer. Never opens a HID device."""
import struct
from pathlib import Path
from collections import Counter


def reports(path, bus=1, device=None):
    data=Path(path).read_bytes()
    if len(data)>150_000_000:
        raise ValueError('Capture exceeds 150 MB inspection limit')
    offset=0; found=[]; addresses=Counter(); packets=0
    while offset+12<=len(data):
        typ,length=struct.unpack_from('<II',data,offset)
        if length<12 or offset+length>len(data):
            raise ValueError('Invalid or truncated pcapng block')
        if typ==6:
            cap=struct.unpack_from('<I',data,offset+20)[0]
            raw=data[offset+28:offset+28+cap]
            if len(raw)>=27:
                h,irp,status,fn,info,bus_id,dev,ep,transfer=struct.unpack_from('<HQIHBHHBB',raw)
                if bus_id==bus:
                    addresses[dev]+=1
                    if (device is None or dev==device) and ep==3 and transfer==1 and info==0 and 27<=h<=len(raw):
                        payload=raw[h:]
                        if len(payload)==64 and payload.startswith(b'\x21\x12'):
                            found.append((dev,payload))
            packets+=1
        offset+=length
    return found,addresses,packets


def aligned_pairs(a,b):
    """Match unique exact commands first, then near-identical reports; no positional assumptions."""
    used=set(); pairs=[]
    for i,x in enumerate(a):
        choices=[]
        for j,y in enumerate(b):
            if j in used or len(x)!=len(y):
                continue
            diff=sum(c!=d for c,d in zip(x,y))
            # Restrict fuzzy matches to same report family, to avoid arbitrary command alignment.
            same_family=(x[:3]==y[:3] and x[4:7]==y[4:7])
            if diff==0 or (same_family and diff<=4):
                choices.append((diff,j))
        if choices:
            diff,j=min(choices)
            used.add(j);pairs.append((i,j,diff))
    return pairs


def describe(paths):
    lines=['OpenSayo v0.19 Alpha 3 — OFFLINE USBPcap Inspector',
           'READ-ONLY: Existing captures only. No USB commands sent.',
           'Matching reports and changing bytes are observations, NOT a validated write protocol.','']
    all_reports=[]
    for path in paths:
        entries,addresses,total=reports(path)
        lines.append(f'FILE: {Path(path).name} | packets={total} | outgoing matching HID reports={len(entries)}')
        lines.append('USB bus 1 addresses: '+', '.join(f'{d}:{n}' for d,n in addresses.most_common(12)))
        for i,(dev,payload) in enumerate(entries,1):
            lines.append(f'  {i:02d} device={dev:02d} bytes={len(payload)} {payload[:40].hex(" ")} ...')
        all_reports.append([x[1] for x in entries]);lines.append('')
    if len(all_reports)==2:
        a,b=all_reports
        lines.append('COMMAND-ALIGNED COMPARISON (exact matches or <=4 differences in same command family):')
        lines.append(f'  report counts: {len(a)} vs {len(b)}')
        pairs=aligned_pairs(a,b)
        lines.append(f'  aligned report pairs: {len(pairs)}')
        for i,j,diff in pairs:
            if diff:
                lines.append(f'  file A report #{i+1} <-> file B report #{j+1}: {diff} changed bytes')
                for pos,(x,y) in enumerate(zip(a[i],b[j])):
                    if x!=y:lines.append(f'    byte offset {pos}: {x:02X} -> {y:02X}')
                lines.append('    A full report: '+a[i].hex(' '))
                lines.append('    B full report: '+b[j].hex(' '))
        lines.append(f'  unmatched reports: A={len(a)-len(pairs)}, B={len(b)-len(pairs)}')
        lines.append('  NOTE: An unmatched report is not necessarily a macro write; it may be setup/traffic.')
        lines.append('  NOTE: A checksum, macro address, and safe Key 2 write procedure remain unverified.')
    return '\n'.join(lines)
