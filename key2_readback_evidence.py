"""Read-only assessment of candidate Key 2 readback evidence from existing captures.
Does not import HID, send packets, or claim to discover firmware commands.
"""
from pathlib import Path
from pcap_inspector import reports


def assess(paths):
    lines = ["OpenSayo Alpha 8 — KEY 2 READBACK EVIDENCE", "OFFLINE ONLY — zero USB reads/writes; no packet replay.",
             "This checks whether saved outgoing traffic supports a Key 2 readback procedure.", ""]
    seen = []
    for path in paths:
        entries, addresses, total = reports(path)
        packets = [p for _, p in entries]
        setup = [p for p in packets if p[:2] == b"\x21\x12" and p[4] == 4]
        text = [(i, p) for i, p in enumerate(packets, 1) if p[:2] == b"\x21\x12" and p[4] == 0x3c]
        config = [(i, p) for i, p in enumerate(packets, 1) if p[:2] == b"\x21\x12" and p[4] == 0x24]
        lines.extend([f"FILE: {Path(path).name}", f"  Outgoing 64-byte records: {len(packets)}; setup-like: {len(setup)}; text-like: {len(text)}; configuration-like: {len(config)}"])
        for i,p in text:
            content = p[8:].split(b"\0",1)[0]
            label = content.decode('ascii', errors='replace')[:48]
            lines.append(f"  text #{i}: {label!r} | bytes2..3={p[2:4].hex(' ')}")
        for i,p in config:
            lines.append(f"  config #{i}: bytes2..3={p[2:4].hex(' ')}; byte31={p[31]:02x}")
        seen.append((Path(path).name,packets))
    lines.extend(['', 'CROSS-FAMILY IDENTICAL HEADER PAIRS (bytes 2..3)'])
    matches=0
    for name,packets in seen:
        text=[(i,p) for i,p in enumerate(packets,1) if p[4]==0x3c and p[:2]==b"\x21\x12"]
        configs=[(i,p) for i,p in enumerate(packets,1) if p[4]==0x24 and p[:2]==b"\x21\x12"]
        for ti,t in text:
            for ci,c in configs:
                if t[2:4]==c[2:4]:
                    matches+=1
                    lines.append(f"  {name}: text #{ti} and config #{ci} share header {t[2:4].hex(' ')} despite different payloads")
    if not matches: lines.append('  No cross-family header matches in the selected files.')
    lines.extend(['', 'READBACK REQUIREMENTS',
        '  [NOT VERIFIED] A Key 2-specific memory selection or address',
        '  [NOT VERIFIED] A Key 2 read request with device response',
        '  [NOT VERIFIED] Two matching reads of Key 2 data',
        '  [NOT VERIFIED] Independent proof that returned bytes belong to Key 2',
        '', 'IMPORTANT LIMITATIONS',
        '  These are OUTGOING records, not paired request/response transactions.',
        '  Header deltas or shared headers cannot establish a readback protocol.',
        '  The earlier F0 read at address 512 returned status 03; this is not a Key 2 bank.',
        '  Do not replay website packets or assume bytes 2..3 are checksums.',
        '', 'RESULT: No verified Key 2 readback. Key 2 writing and overflow remain DISABLED.',
        'Next step requires actual protocol evidence of a read RESPONSE, not further source-only audits.'])
    return '\n'.join(lines)+'\n'
