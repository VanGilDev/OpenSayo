"""Experimental global 0xF0 stream writer; not an independent slot writer."""
from pathlib import Path
from datetime import datetime
import hashlib,time
from eight_key_writer import exchange,VID,PID,PAGE,USAGE,frame
SIZE=2048

def _step16_transact(dev, cmd, payload):
    """Exact Step 16 HID request/response behavior, independent of GUI exchange."""
    sent = dev.write(frame(cmd, payload))
    if sent != 64:
        raise RuntimeError(f'HID write length {sent} (expected 64)')
    reply = bytes(dev.read(64, timeout_ms=2500))
    if len(reply) != 64 or reply[0] != 2:
        raise RuntimeError(f'No valid 64-byte O2 reply: {reply[:8].hex()}')
    if reply[1] != 0:
        raise RuntimeError(f'Device returned status 0x{reply[1]:02X}; command=0x{cmd:02X}; request_payload={payload.hex()}; response={reply[:8].hex()}')
    if reply[2] > 60:
        raise RuntimeError(f'Bad response length {reply[2]}')
    return reply[3:3+reply[2]]

def read_region(dev):
    """Copy of the known-working Step 16 full 2048-byte reader."""
    result = bytearray()
    while len(result) < SIZE:
        address = len(result)
        chunk = _step16_transact(dev, 0xF0, address.to_bytes(2, 'big'))
        if not 1 <= len(chunk) <= 60 or len(result)+len(chunk) > SIZE:
            raise RuntimeError(f'Unexpected read chunk length at {address}: {len(chunk)}')
        result.extend(chunk)
    return bytes(result)

def write_global_macro(code):
    """Intentionally disabled: independent script boundaries remain unverified."""
    raise RuntimeError('OpenSayo blocks global macro writes: script-slot boundaries are not verified. Use Preview Protected Memory Changes (read-only) to inspect the proposed changes.')


def preview_global_memory_changes(code):
    """Read-only full-region backup and diff report; NEVER sends a write or SAVE."""
    if not 0 < len(code) <= 2028:
        raise ValueError('Compiled macro must be 1–2028 bytes')
    import hid, json
    matches=[d for d in hid.enumerate(VID,PID) if d.get('usage_page')==PAGE and d.get('usage')==USAGE]
    if len(matches)!=1:
        raise RuntimeError(f'Expected one 8-key device, found {len(matches)}')
    dev=hid.device()
    try:
        dev.open_path(matches[0]['path'])
        before=read_region(dev)
    finally:
        dev.close()
    directory=Path.home()/'Documents'/'OpenSayo'/'macro_backups'
    directory.mkdir(parents=True,exist_ok=True)
    stamp=datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    backup=directory/('memory_before_'+stamp+'.bin')
    backup.write_bytes(before)
    if backup.read_bytes()!=before:
        raise RuntimeError('Backup verification failed')
    # Compare against a read-only target; NEVER issue a device write.
    target=(code+b'\xff\xff').ljust(SIZE,b'\x00')
    differences=[i for i,(x,y) in enumerate(zip(before,target)) if x!=y]
    ranges=[]
    for offset in differences:
        if ranges and offset==ranges[-1][1]+1:ranges[-1][1]=offset
        else:ranges.append([offset,offset])
    # Preserve the unverified tail; this is NOT slot isolation.
    protected_start,protected_end=1998,2028
    protected_target=bytearray(target)
    protected_target[protected_start:protected_end]=before[protected_start:protected_end]
    protected_differences=[i for i,(x,y) in enumerate(zip(before,protected_target)) if x!=y]
    protected_ranges=[]
    for offset in protected_differences:
        if protected_ranges and offset==protected_ranges[-1][1]+1:protected_ranges[-1][1]=offset
        else:protected_ranges.append([offset,offset])
    report=directory/('memory_preview_'+stamp+'.json')
    data={'mode':'READ ONLY; NO WRITES OR SAVE','backup_path':str(backup),
          'sha256_before':hashlib.sha256(before).hexdigest(),
          'compiled_code_bytes':len(code),'global_region_bytes':SIZE,
          'changed_byte_count':len(differences),'changed_ranges_inclusive':ranges,
          'protected_offsets_inclusive':[protected_start,protected_end-1],
          'protected_changed_byte_count':len(protected_differences),
          'protected_changed_ranges_inclusive':protected_ranges,
          'blocked_tail_changes':sum(protected_start<=i<protected_end for i in differences),
          'protected_preview_sha256':hashlib.sha256(protected_target).hexdigest(),
          'first_changed_offset':differences[0] if differences else None,
          'last_changed_offset':differences[-1] if differences else None,
          'warning':'Global target is NOT slot isolated; do not apply as a write.'}
    report.write_text(json.dumps(data,indent=2),encoding='utf-8')
    return str(report),len(protected_differences),str(backup)
