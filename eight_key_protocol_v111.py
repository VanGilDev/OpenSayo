"""OpenSayo v1.11 experimental SayoDevice 2x4V RGB protocol.

Derived from physically verified Step 67/68/70/71 test logic, not from the
legacy two-button code.  The physical Script 0..7 -> Button 1..8 map is
verified *on device* before any write.  An ACK or Save reply is NOT proof of
persistence: the user must physically test after unplugging/reconnecting.

IMPORTANT: An unknown Save reply does not mean the macro failed.  Step 67/70
persisted despite an unexpected reply.  No automatic retries or rollbacks.
"""
import struct
import time

VID = 0x8089
PID = 0x000B
CONFIG_PAGE, CONFIG_USAGE = 0xFF11, 2
LEGACY_PAGE, LEGACY_USAGE = 0xFF00, 1
BLOCK_SIZE, BLOCK_COUNT = 52, 39
OBSERVED_WRITE_EXTENT = BLOCK_SIZE * BLOCK_COUNT  # 2028 bytes in tested bulk writes
EXPECTED_MAP = list(range(8))
REFERENCE_FIRST_Q = bytes.fromhex('21 12 A6 4B 3C 00 1A 01 00 00 00 00 11 14 06 0F 19 14 FF').ljust(64,b'\0')
REFERENCE_END = bytes.fromhex('21 12 41 13 08 00 1A 01 FF FF FF FF').ljust(64,b'\0')
REFERENCE_SAVE = bytes.fromhex('21 12 CA 84 06 00 0D 00 96 72').ljust(64,b'\0')
REFERENCE_SAVE_REPLY = bytes.fromhex('21 12 32 12 04 00 0D 00').ljust(64,b'\0')


def v2_packet(command, index, params):
    if not 0 <= index <= 255 or len(params) > 56:
        raise ValueError('V2 packet parameters outside 64-byte report')
    pkt = bytearray(64)
    pkt[:2] = b'\x21\x12'
    pkt[4:6] = (len(params) + 4).to_bytes(2,'little')
    pkt[6:8] = bytes((command,index))
    pkt[8:8+len(params)] = params
    pkt[2:4] = (sum(struct.unpack('<32H', pkt)) & 0xFFFF).to_bytes(2,'little')
    return bytes(pkt)


def script_packets(index, code):
    if not 0 <= index <= 63:
        raise ValueError('Script index must be 0 through 63')
    if not code or len(code) > OBSERVED_WRITE_EXTENT or code[-1] != 0xFF:
        raise ValueError('Script must end in EXIT (0xFF), and fit within 2028 bytes')
    content = code.ljust(OBSERVED_WRITE_EXTENT,b'\0')
    blocks = [v2_packet(0x1A,index,(i*BLOCK_SIZE).to_bytes(4,'little')+
                        content[i*BLOCK_SIZE:(i+1)*BLOCK_SIZE]) for i in range(BLOCK_COUNT)]
    return blocks, v2_packet(0x1A,index,b'\xFF'*4),v2_packet(0x0D,0,b'\x96\x72')


def offline_selftest():
    first = v2_packet(0x1A,1,b'\0'*4+bytes.fromhex('11 14 06 0F 19 14 FF').ljust(52,b'\0'))
    assert first == REFERENCE_FIRST_Q
    assert v2_packet(0x1A,1,b'\xFF'*4) == REFERENCE_END
    assert v2_packet(0x0D,0,b'\x96\x72') == REFERENCE_SAVE
    for i in (0,1,2,3,4,5,6,7,8,32,63):
        data, marker, save = script_packets(i, bytes((0x11,0x04,0x06,0x0F,0x19,0x04,0xFF)))
        assert len(data)==39
        assert all(x[6:8]==bytes((0x1A,i)) and int.from_bytes(x[8:12],'little')==j*52
                   for j,x in enumerate(data))
        assert marker[6:8] == bytes((0x1A,i))
        assert save == REFERENCE_SAVE
    return True


def select_unique(hid, page, usage):
    matches = [d for d in hid.enumerate(VID,PID)
               if d.get('interface_number')==1 and
               d.get('usage_page')==page and d.get('usage')==usage]
    if len(matches)!=1:
        raise RuntimeError(f'Expected exactly one 2x4V RGB HID collection {page:04X}/{usage}; found {len(matches)}. No write.')
    if '2x4' not in str(matches[0].get('product_string') or '').lower():
        raise RuntimeError('Device identity is not a confirmed 2x4V RGB. No write.')
    return matches[0]


def read_all_assignments(hid):
    """Read-only 0x16 query from the legacy FF00 collection for physical 1-8."""
    info = select_unique(hid,LEGACY_PAGE,LEGACY_USAGE)
    dev=hid.device()
    mapping=[]
    try:
        dev.open_path(info['path'])
        for key in range(8):
            req=bytearray(64)
            req[:5]=bytes((2,0x16,2,0,key))
            req[5]=sum(req[:5]) & 255
            if dev.write(bytes(req)) != 64:
                raise RuntimeError(f'Physical key {key+1}: short assignment query')
            reply=bytes(dev.read(64,timeout_ms=2000))
            if len(reply)!=64 or reply[:3]!=bytes((2,0,46)):
                raise RuntimeError(f'Physical key {key+1}: invalid assignment response; no write')
            record=reply[3:49]
            if record[:3]!=bytes((0,key,1)):
                raise RuntimeError(f'Physical key {key+1}: unexpected assignment record; no write')
            value=record[16]
            mapping.append(value-0x40 if 0x40<=value<=0x7F else None)
    finally:
        dev.close()
    return mapping


def _reply(dev, timeout_ms=1500):
    """Skip unsolicited 0xF2 status frames; only a matching full echo is an ACK."""
    for _ in range(5):
        raw=bytes(dev.read(64,timeout_ms=timeout_ms))
        if not raw:return b''
        if raw[:3]==b'\x21\x00\xF2':continue
        return raw
    return b''


def guarded_write_one(hid,index,code,progress=lambda msg:None):
    """ONE write for one slot. No retries, no backup/rollback, requires physical validation.

    Caller explicitly confirms overwrite and knows site backup is required.
    The function enforces exact 0..7 assignment mapping immediately before write.
    Hardware save may affect other configuration; not guaranteed safe.
    """
    offline_selftest()
    blocks,marker,save=script_packets(index,code)
    mapping=read_all_assignments(hid)
    progress('Read-only physical assignment map: '+repr(mapping))
    if index not in mapping:
        raise RuntimeError(f'STOP: Script {index} is not assigned to any physical button. No macro writes sent.')
    if mapping.count(index)!=1:
        raise RuntimeError(f'STOP: Script {index} has ambiguous physical assignments. No macro writes sent.')
    info=select_unique(hid,CONFIG_PAGE,CONFIG_USAGE)
    dev=hid.device()
    save_sent=False
    try:
        dev.open_path(info['path'])
        for j,packet in enumerate(blocks):
            if dev.write(packet)!=64:
                raise RuntimeError(f'STOP: short write at block {j+1}; state uncertain; do not retry')
            response=_reply(dev)
            if response!=packet:
                raise RuntimeError(f'STOP: block {j+1} response mismatch; state uncertain; do not retry; reply {response[:16].hex(" ")}')
            if j in (0,9,19,29,38):progress(f'Slot {index}: {j+1}/39 script blocks echoed')
        if dev.write(marker)!=64:raise RuntimeError('STOP: short end-marker write. No Save command sent.')
        marker_reply=_reply(dev)
        if not (len(marker_reply)>=12 and marker_reply[:2]==b'\x21\x12' and
                marker_reply[6:8]==bytes((0x1A,index)) and
                marker_reply[8:12]==bytes.fromhex('00 08 00 00')):
            raise RuntimeError('STOP: unrecognized end-marker response. No Save command sent.')
        time.sleep(0.65)
        if dev.write(save)!=64:
            raise RuntimeError('STOP: Save command short write; device state unknown; do not retry')
        save_sent=True
        reply=_reply(dev)
        samples=[reply[:16].hex(' ').upper() if reply else '(timeout)']
        status='EXPECTED_REPLY' if reply==REFERENCE_SAVE_REPLY else 'UNVERIFIED_REPLY'
        if status!='EXPECTED_REPLY':
            for _ in range(3):
                extra=bytes(dev.read(64,timeout_ms=450))
                if not extra:break
                samples.append(extra[:16].hex(' ').upper())
                if extra==REFERENCE_SAVE_REPLY:
                    status='EXPECTED_REPLY_AFTER_OTHER_MESSAGE'
                    break
        progress('Save command sent; response '+status+'. PHYSICAL TEST REQUIRED.')
        return {'script_index':index,'blocks_echoed':39,'save_sent':save_sent,
                'save_response':status,'reply_prefixes':samples,
                'verified_persistent':False}
    finally:
        dev.close()
