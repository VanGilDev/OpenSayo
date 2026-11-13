"""Conservative inspection of a verified, stable 512-byte script readback."""
from collections import Counter

def inspect(data: bytes) -> str:
    if len(data)!=512:
        raise ValueError("Exactly 512 bytes required")
    lines=["", "512-BYTE REGION ANALYSIS (observations only)",
           "WARNING: This region is not proven to be shared by both keys.",
           "An FF byte is not automatically a script delimiter.", ""]
    counts=Counter(data)
    lines.append(f"Byte totals: 00={counts[0]}, FF={counts[255]}, other={512-counts[0]-counts[255]}")
    active=[i for i,b in enumerate(data) if b not in (0,255)]
    lines.append(f"First non-00/FF offset: {active[0] if active else 'none'}")
    lines.append(f"Last non-00/FF offset: {active[-1] if active else 'none'}")
    ff=[i for i,b in enumerate(data) if b==255]
    lines.append(f"FF offsets (first 80): {ff[:80]}")
    pairs=[i for i in range(511) if data[i:i+2]==b'\xff\xff']
    lines.append(f"FF FF candidate offsets (first 80): {pairs[:80]}")
    # Search for exact website/live assignment fragments; absence does not disprove references.
    fragments={'live key-index 1 config fragment':bytes.fromhex('09 00 14 24 10 22'),
               'website config fragment':bytes.fromhex('14 24 10 22'),
               'live key-index 0 fragment':bytes.fromhex('40 00 00 00')}
    lines.append('')
    lines.append('Assignment fragment exact matches (not proof of linkage):')
    for name,pattern in fragments.items():
        found=[];pos=0
        while True:
            pos=data.find(pattern,pos)
            if pos<0:break
            found.append(pos);pos+=1
        lines.append(f"  {name}: {found[:30]}" + (" (more omitted)" if len(found)>30 else ""))
    lines.extend(['', '16-byte rows, all 512 bytes (hex and ASCII):'])
    for i in range(0,512,16):
        chunk=data[i:i+16]
        ascii_text=''.join(chr(x) if 32<=x<127 else '.' for x in chunk)
        lines.append(f"  {i:04X}: {chunk.hex(' '):47s}  {ascii_text}")
    lines.extend(['', 'CONCLUSION:',
      'This identifies byte distributions, possible boundaries and literal fragments only.',
      'No verified Key 2 script pointer, partition, or capacity has been established.',
      'Do not enable Key 2 writes or auto-overflow based on this analysis.'])
    return '\n'.join(lines)
