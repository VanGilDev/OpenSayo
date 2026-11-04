"""Offline, source-grounded audit of OpenSayo Key 1 memory assumptions.
No USB imports, device enumeration, or write capabilities.
"""
import hashlib
import json
from pathlib import Path


def audit(source_path, snapshot_paths=()):
    src = Path(source_path).read_text(encoding='utf-8')
    required = ['def read_report(', 'def read_script(', 'def write_script(',
                'CMD_SCRIPT = 0xF0', 'MEMORY_SIZE = 512', 'MAX_DATA = 54']
    absent = [s for s in required if s not in src]
    if absent:
        raise ValueError('Unexpected source layout; missing: ' + ', '.join(absent))
    lines = [
        'OpenSayo Alpha 6 — OFFLINE MEMORY-LAYOUT AUDIT',
        'No device connection, no new capture, no USB requests, no writes.', '',
        'SOURCE-VERIFIED KEY 1 FACTS',
        'Device selection: VID 8089, PID 000C, interface 1, usage page FF00, usage 1, product O2L.',
        'Report: 64 bytes, ID 02, script command F0.',
        'Read request: F0 + 2-byte big-endian address; response requires report ID 02 and status 00.',
        'Read loop begins at address 0; app expects 512 bytes for a guarded Key 1 write.',
        'Writes use chunks of at most 54 script bytes, with 2 address bytes in each packet.',
        'Safety cutoff: 494 bytes including two FF exit markers.',
        'Existing writer requires two identical full live reads and a saved backup; verifies full readback.',
        '', 'KEY 1 ADDRESS BOUNDARIES (derived, not probed)',
    ]
    for addr in range(0, 512, 54):
        lines.append(f'  0x{addr:04X} ({addr:3d}) — nominal next chunk start')
    lines += [
        '  0x0200 (512) — first address outside the known 512-byte region.',
        '', 'LIMITATIONS / RISKS',
        'The F0 address is a byte offset in the known Key 1 script region; no key selector has been verified.',
        'Status 03 at address 512 (previous exploratory observation) does not identify Key 2 storage.',
        'The current read loop stops on short blocks and nonzero status; it does not scan other key banks.',
        'An unsuccessful read at 512 cannot distinguish end-of-region, invalid address, or another protocol.',
        'Website 21 12 reports and direct HID 02 F0 reports are distinct envelopes.',
        'There is NO verified Key 2 address, write command, acknowledgment, or readback.',
        'Therefore Key 2 writes and automatic overflow remain DISABLED.',
    ]
    snapshots = []
    for p in snapshot_paths:
        d = json.loads(Path(p).read_text(encoding='utf-8'))
        if d.get('format') != 'OpenSayo key2 exploratory snapshot v1':
            raise ValueError(f'{p}: unrecognized snapshot format')
        raw = bytes.fromhex(d['key1_512_hex'])
        if len(raw) != 512:
            raise ValueError(f'{p}: expected exactly 512 bytes')
        declared = d.get('key1_sha256')
        actual = hashlib.sha256(raw).hexdigest()
        if declared and declared != actual:
            raise ValueError(f'{p}: Key 1 SHA256 mismatch')
        snapshots.append((Path(p).name, d, raw, actual))
    lines += ['', 'OPTIONAL EXISTING SNAPSHOT REVIEW']
    if not snapshots:
        lines.append('No snapshots selected. Source-only audit is complete; prior 512/status03 observations noted above.')
    for name, d, raw, sha in snapshots:
        lines.append(f'{name}: Key 1 SHA256={sha}')
        for block in d.get('extended_read_blocks', []):
            lines.append(f"  address {block.get('address')}: status={block.get('status', 'n/a')}; "
                         f"bytes={len(bytes.fromhex(block['hex'])) if block.get('hex') else 0}; "
                         f"error={block.get('error', 'none')}")
    if len(snapshots) >= 2:
        base_name, _, base_raw, _ = snapshots[0]
        for name, _, raw, _ in snapshots[1:]:
            differences = [i for i, (a,b) in enumerate(zip(base_raw, raw)) if a != b]
            lines.append(f'Key 1 difference: {base_name} vs {name}: {len(differences)} bytes')
            if differences:
                lines.append('  offsets: ' + ', '.join(str(i) for i in differences[:50]))
            else:
                lines.append('  Same Key 1 memory; this does NOT prove the location of Key 2.')
    lines += ['', 'RECOMMENDATION',
              'Keep using the verified Key 1 writer only. Do not infer a Key 2 writer from address 512.',
              'Next engineering task: establish a separate, reproducible Key 2 readback method before any write.']
    return '\n'.join(lines) + '\n'
