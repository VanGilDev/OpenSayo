"""Offline, evidence-labeled protocol inspection. No HID imports or writes."""
from pathlib import Path
from collections import Counter
from pcap_inspector import reports, aligned_pairs

CAPTURE_NAMES = ('q7.pcapng','q7m4.pcapng','q7m5.pcapng')

def family(p):
    if len(p)!=64 or p[:2]!=b'\x21\x12':return 'other'
    if p[2]==0x09 and p[4]==0x24:return 'configuration-like (09/24)'
    if p[2]==0xca and p[4]==0x06:return 'closing/status-like (CA/06)'
    if p[4]==0x04:return 'connection/setup-like (04)'
    if p[4]==0x3c:return 'text-containing family (3C)'
    return f'unknown family (byte4={p[4]:02X})'

def dump(path):
    entries,addresses,total=reports(path)
    arr=[p for _,p in entries]
    lines=[f'{Path(path).name}: {len(arr)} outgoing 64-byte reports; {total} captured packets',
           'CAUTION: USB bus and endpoint filtering does not by itself prove device identity.','']
    for i,p in enumerate(arr,1):
        ascii_text=''.join(chr(c) if 32<=c<127 else '.' for c in p[8:])
        lines += [f'#{i:02} {family(p)}',f'    bytes 0-7: {p[:8].hex(" ")}',f'    data 8-63: {p[8:].hex(" ")}',f'    printable data: {ascii_text}']
    return arr,lines

def decode(paths):
    lines=['OpenSayo v0.19 Alpha 4 — OFFLINE KEY 2 PROTOCOL DECODER',
           'READ-ONLY: never connects to a USB device; never sends commands.',
           'Labels are tentative observations, NOT confirmed firmware commands.','']
    arrays=[]
    for path in paths:
        arr,part=dump(path);arrays.append(arr);lines.extend(part);lines.append('')
    if len(arrays)>=2:
        a,b=arrays[0],arrays[1]
        lines += ['MATCHED COMMANDS — first two selected files:']
        for i,j,d in aligned_pairs(a,b):
            lines.append(f'  A#{i+1} ↔ B#{j+1} ({family(a[i])}): {d} changed byte(s)')
            if d:
                for k,(x,y) in enumerate(zip(a[i],b[j])):
                    if x!=y:lines.append(f'      offset {k}: {x:02X} -> {y:02X}')
        lines.append('')
    configs=[]
    for path,arr in zip(paths,arrays):
        for i,p in enumerate(arr,1):
            if p[2]==9 and p[4]==0x24:
                configs.append((Path(path).name,i,p))
    if configs:
        lines.append('CONFIGURATION-LIKE REPORTS:')
        for name,i,p in configs:
            lines.append(f'  {name} #{i}: offset3={p[3]:02X}; offset31={p[31]:02X}; sum(bytes4..63) mod256={sum(p[4:])%256:02X}')
        if len(configs)>1:
            baseline=configs[0][2]
            for name,i,p in configs[1:]:
                changed=[k for k,(x,y) in enumerate(zip(baseline,p)) if x!=y]
                lines.append(f'  Compared to first config, {name} #{i}: changed offsets={changed}')
        lines.append('  WARNING: Correlation between offsets 3 and 31 is not proof of checksum, script data, or key selector.')
    lines += ['', 'KNOWN KEY 1 WRITER (from existing OpenSayo source):',
              '  HID report ID 02; command F0; script address (big endian) plus <=54 data bytes.',
              '  Reads 512-byte Key 1 script region and verifies full readback after guarded writes.',
              '  The website capture reports start 21 12: different envelope; cannot replay as Key 1 F0 packets.',
              '  No confirmed Key 2 memory address, encoding, write acknowledgment, or readback method.',
              '', 'DECISION: Key 2 hardware writing stays DISABLED.']
    return '\n'.join(lines)
