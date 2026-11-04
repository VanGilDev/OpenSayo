"""Alpha 12: read-only evidence comparison. No HID calls, no writes."""
from key_mapping_read import decode_mapping_response

SAMPLE_0=bytes.fromhex('02 00 1c 00 00 01 00 dc 05 66 08 00 00 08 07 08 07 64 00 40 00 00 00 00 00 00 00 00 1d 00 00 18 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00').ljust(64,bytes([0]))
SAMPLE_1=bytes.fromhex('02 00 1c 00 01 01 00 ac 0d 66 08 00 00 08 07 08 07 64 00 09 00 14 24 10 22 00 00 00 1b 00 00 18 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00').ljust(64,bytes([0]))

def analyze(raw0=SAMPLE_0,raw1=SAMPLE_1):
    a,b=bytes(raw0),bytes(raw1)
    lines=["OpenSayo Alpha 12 — KEY ASSIGNMENT CROSS-CHECK", "OFFLINE: no USB commands, writes, or new captures.", "Built-in examples come from the user's Alpha 11 report, not a new device read.", ""]
    for k,r in enumerate((a,b)):
        d=decode_mapping_response(r,k)
        lines += [f"Key index {k}: {len(r)} bytes; report_id={d.get('report_id')} status={d['status']} declared_length={d['length']}",
                  f"  Existing parser: checksum at offset {d.get('checksum_offset')}, actual byte={d.get('checksum_received')} (decimal), calculated={d.get('checksum_calculated')}",
                  f"  Field at offset 31: 0x{r[31]:02X} (same on both records; may be a trailer, not proven checksum)" if len(r)>31 else "  Truncated response",
                  f"  Indexed key field at offset 4: {r[4] if len(r)>4 else 'missing'}", ""]
    if len(a)==64 and len(b)==64:
        changes=[i for i in range(64) if a[i]!=b[i]]
        lines += ["Differences between indexed assignments:","  "+", ".join(f"{i}: {a[i]:02X}->{b[i]:02X}" for i in changes), ""]
        lines += ["Website config alignment (from existing Q7M5 capture):", "  website bytes[12:20]: AC 0D 66 08 08 07 08 07", "  live key1 bytes[7:17]: "+b[7:17].hex(' ').upper(),
                  "  website config bytes[24:32]: 09 00 00 00 14 24 10 22", "  live key1 bytes[19:25]: "+b[19:25].hex(' ').upper(),
                  "  Confirmed shared subsequences: AC 0D 66 08 and 14 24 10 22" if b'\xac\x0d\x66\x08' in b and b'\x14\x24\x10\x22' in b else "  Shared subsequences not found", ""]
    lines += ["INTERPRETATION:", "  0x16 returns two stable indexed assignment records on the tested O2L V2.",
              "  The 0x18 at offset 31 is identical for both responses; do not label it a checksum without proof.",
              "  The current checksum calculation fails for both records, so decoded layer fields remain tentative.",
              "  Shared configuration bytes support an association with website key settings, not a verified Key 2 script bank.",
              "  NO Key 2 writes, script overflow, or unverified read commands are enabled."]
    return "\n".join(lines)
