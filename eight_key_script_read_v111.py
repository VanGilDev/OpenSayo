"""EXPERIMENTAL read-only SayoDevice 2x4V RGB slot reader, v1.11.

This is intentionally fail-closed. USBPcap captured website read exchanges
for scripts 61, 62, and 63, but live OpenSayo readback remains unverified. No flash Save and
no macro data writes are made here. UI must validate/decode before importing.

The read request is the observed short (4-byte offset) form of v2 command 0x1A;
a macro write uses a *different 56-byte* form. The module rejects any response
without an exact target index, offset, byte count, and valid v2 checksum.
"""
from __future__ import annotations
import struct
import time
from pathlib import Path
from datetime import datetime

_DIAG_PATH = Path.home() / "OpenSayo_Step74_Read_Diagnostic.txt"

def _diag(message):
    try:
        with _DIAG_PATH.open("a", encoding="utf-8") as out:
            out.write(datetime.now().isoformat(timespec="seconds") + " " + message + "\n")
    except OSError:
        pass

from eight_key_protocol_v111 import (
    select_unique, v2_packet, CONFIG_PAGE, CONFIG_USAGE,
    BLOCK_SIZE,
)


def _checksum_valid(reply):
    if len(reply) != 64:return False
    claimed=int.from_bytes(reply[2:4], 'little')
    check=bytearray(reply)
    check[2:4]=b'\0\0'
    calculated=sum(struct.unpack('<32H', check)) & 0xFFFF
    return claimed == calculated


def _read_response(dev, index, offset):
    # Exactly 4 parameter bytes: request only, no script data, no Save.
    pkt=v2_packet(0x1A,index,offset.to_bytes(4,'little'))
    if len(pkt)!=64 or pkt[4:8]!=bytes((8,0,0x1A,index)):
        raise RuntimeError('Invalid read request construction. No request sent.')
    _diag(f"REQUEST slot={index} offset={offset} header={pkt[:12].hex(' ')}")
    if dev.write(pkt)!=64:
        raise IOError(f'Hardware read request failed at offset {offset}.')
    # Unsolicited status packets may arrive between valid script blocks.
    # Bound the number of discarded packets; never weaken script-data checks.
    for attempt in range(12):
        reply=bytes(dev.read(64,timeout_ms=2000))
        _diag(f"REPLY slot={index} offset={offset} attempt={attempt+1} length={len(reply)} header={reply[:12].hex(' ')} checksum={_checksum_valid(reply)}")
        if not reply:raise TimeoutError(f'No Script {index} read reply at offset {offset}.')
        if len(reply)==64 and reply[:2]==b'\x21\x00' and reply[6]==0xFF:
            if not _checksum_valid(reply):
                raise ValueError('Unsolicited status report has invalid checksum; editor protected.')
            _diag(f'IGNORED unsolicited status at offset={offset}')
            continue
        if reply[:3]==b'\x21\x00\xF2':continue  # older status report
        if not _checksum_valid(reply):
            raise ValueError('Read response has an invalid checksum; editor must not be modified.')
        if reply[:2]!=b'\x21\x12' or reply[6:8]!=bytes((0x1A,index)):
            raise ValueError('Read response targets an unexpected command or script. See OpenSayo_Step74_Read_Diagnostic.txt in your user folder.')
        if offset==0xFFFFFFFF:
            if reply[4:6]!=b'\x08\x44':
                raise ValueError('Unexpected 8-key script-length response; editor protected.')
        else:
            expected_size = 0x1C if offset == 2028 else 0x3C
            if reply[4:6] != bytes((expected_size, 0)) or int.from_bytes(reply[8:12],'little')!=offset:
                raise ValueError('Read response size/offset disagrees with requested script.')
        return reply
    raise RuntimeError('No matching script response after 12 status messages; editor protected.')


def read_script_slot(hid, script_index):
    """Return the 2048-byte script image; raise on any uncertainty.

    Uses the observed 8-byte read request and never transmits macro data
    blocks or flash Save. The offset FFFFFFFF requests metadata only.
    """
    if type(script_index) is not int or not 0<=script_index<=63:
        raise ValueError('Script slot must be 0–63')
    info=select_unique(hid,CONFIG_PAGE,CONFIG_USAGE)
    dev=hid.device()
    try:
        _diag(f"START slot={script_index}; header-only diagnostic")
        dev.open_path(info['path'])
        header=_read_response(dev,script_index,0xFFFFFFFF)
        length=int.from_bytes(header[8:12],'little')
        # Website write behavior suggests 2048 boundary; do not accept other
        # undocumented capacities as if they were known-good.
        if length != 2048:
            raise ValueError(f'Unexpected script memory size {length}; editor protected.')
        buf=bytearray()
        for i in range(40):
            offset=i*BLOCK_SIZE
            reply=_read_response(dev,script_index,offset)
            buf.extend(reply[12:12 + (20 if offset == 2028 else BLOCK_SIZE)])
            time.sleep(0.01)
        if len(buf)!=2048:
            raise RuntimeError('Script read was incomplete; editor protected.')
        # A completely empty slot is never imported as a valid macro.
        if not any(buf):
            raise ValueError('Device script is blank; existing editor unchanged.')
        return bytes(buf)
    finally:
        dev.close()
