"""Offline Key 2 evidence analysis. Never accesses USB hardware."""
from pathlib import Path
from pcap_inspector import reports

def analyze(paths):
    captures=[]
    for path in paths:
        entries, _, _ = reports(path)
        captures.append((Path(path).name, [(i,p) for i,(_,p) in enumerate(entries,1)]))
    lines=['OpenSayo v0.19 Alpha 5 — KEY 2 EVIDENCE ANALYSIS',
           'READ-ONLY. No device connection. Hypotheses are NOT a validated writer.','']
    text_records=[]
    configs=[]
    for name,entries in captures:
        lines.append(f'CAPTURE: {name} — {len(entries)} outgoing 64-byte reports')
        for idx,p in entries:
            if len(p)!=64 or p[:2]!=b'\x21\x12': continue
            if p[4]==0x3c:
                payload=p[8:]
                printable=''.join(chr(c) if 32<=c<=126 else '.' for c in payload).rstrip('.')
                text_records.append((name,idx,p,printable))
                lines.append(f'  text-like #{idx}: {printable!r} | header={p[:8].hex(" ")} | payload[8:16]={p[8:16].hex(" ")}')
            if p[4]==0x24:
                configs.append((name,idx,p))
        lines.append('')
    lines.append('TEXT-LIKE REPORT TRANSITIONS (same capture and bytes 4..7):')
    count=0
    for a in range(len(text_records)):
        for b in range(a+1,len(text_records)):
            n,i,p,txt=text_records[a];m,j,q,txt2=text_records[b]
            if n!=m or p[4:8]!=q[4:8]:continue
            diffs=[k for k in range(64) if p[k]!=q[k]]
            payload_delta=(sum(q[4:])-sum(p[4:]))%256
            header_delta=(q[3]-p[3])%256
            lines.append(f'  {n} #{i} {txt!r} -> #{j} {txt2!r}: offsets={diffs}; '
                         f'payload sum delta={payload_delta:02X}; header byte3 delta={header_delta:02X}; '
                         f'delta match={payload_delta==header_delta}')
            count+=1
    if not count:lines.append('  No comparable text-like report pairs in selected captures.')
    lines.extend(['','CONFIGURATION-LIKE REPORTS (byte4=24):'])
    for name,i,p in configs:
        lines.append(f'  {name} #{i}: byte2={p[2]:02X}, byte3={p[3]:02X}, byte31={p[31]:02X}; payload sum={sum(p[4:])%256:02X}')
    for a in range(len(configs)):
        for b in range(a+1,len(configs)):
            n,i,p=configs[a];m,j,q=configs[b]
            if p[4:8]!=q[4:8]:continue
            diff=[k for k in range(64) if p[k]!=q[k]]
            if len(diff)>12:continue
            pd=(sum(q[4:])-sum(p[4:]))%256;hd=(q[3]-p[3])%256
            lines.append(f'  {n} #{i} -> {m} #{j}: changed offsets={diff}; '
                         f'payload sum delta={pd:02X}; header byte3 delta={hd:02X}; delta match={pd==hd}')
    lines.extend(['','INTERPRETATION:',
                  '  A matching delta is consistent with additive integrity data, but does not prove a checksum algorithm.',
                  '  A full header calculation, Key 2 address, macro bytecode, acknowledgments and readback are still unknown.',
                  '  Some captured reports may be web-app traffic rather than firmware programming.',
                  '  NEVER replay these captured packets as USB commands.',
                  '  Key 1 guarded writer is unchanged. Key 2 hardware writing stays DISABLED.'])
    return '\n'.join(lines)
