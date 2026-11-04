"""Offline, byte-for-byte comparison of captured 0x16 assignment records."""
def changes(a,b):
    x=bytes.fromhex(a);y=bytes.fromhex(b)
    if len(x)!=64 or len(y)!=64:raise ValueError("Expected two 64-byte records")
    return [(i,x[i],y[i]) for i in range(64) if x[i]!=y[i]]

def report(snaps):
    lines=["OpenSayo Alpha 14 — CONTROLLED SCRIPT ASSIGNMENT COMPARISON",
           "All data from read-only 0x16 responses. Website assignment changes are manual.",
           "Offset 4 was observed to differ between key indexes; script reference remains UNVERIFIED.",
           "Do not interpret changing bytes as script IDs until repeated controlled tests support it.",""]
    for i,s in enumerate(snaps):
        lines += [f"SNAPSHOT {i+1}: {s['label']}  Device: {s['device']}",
                  f"  Physical key index 0: {s['key0']}",f"  Physical key index 1: {s['key1']}"]
        diffs=changes(s['key0'],s['key1'])
        lines.append("  Within-snapshot key 0 vs key 1 differences: "+(', '.join(f"[{j}] {a:02X}->{b:02X}" for j,a,b in diffs) or 'NONE'))
        if i:
            prev=snaps[i-1]
            for k in ('key0','key1'):
                diffs=changes(prev[k],s[k])
                lines.append(f"  Previous snapshot -> this snapshot, {k}: "+(', '.join(f"[{j}] {a:02X}->{b:02X}" for j,a,b in diffs) or 'NO CHANGE'))
        lines.append("")
    if len(snaps)>1:
        lines += ["INTERPRETATION GUIDE:","- If key0 stays unchanged while key1 changes, the experiment isolated key1's assignment record.","- A byte varying with Script 1/2/3 is a candidate reference, not automatically a proven slot ID.","- If no bytes change, confirm website settings were applied and device reconnected if necessary."]
    return '\n'.join(lines)+'\n'
