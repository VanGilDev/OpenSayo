"""Offline-only security/compatibility checks for minimal USB protocol assets.

No hidapi import and no device commands. Public synthetic test data only.
"""
import struct, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT/'py'))
from hardware_protocol import packets, validate, make_bank_reports, assignment_packets
from pcap_inspector import reports as inspector_reports

expected = {'script7_40_baseline.pcapng':220,
            'script8_40_baseline.pcapng':220,
            'key_swap_reference.pcapng':3}
for filename, count in expected.items():
    path=ROOT/'py'/'captures'/filename
    b=path.read_bytes()
    # Minimal SHB, IDB and only the expected number of packet blocks.
    pos=0; blocktypes=[]
    while pos < len(b):
        assert pos+12<=len(b)
        typ,n=struct.unpack_from('<II',b,pos)
        assert n >= 12 and pos+n<=len(b)
        assert struct.unpack_from('<I',b,pos+n-4)[0] == n
        blocktypes.append(typ)
        if typ == 6:
            iface,t1,t2,caplen,origlen=struct.unpack_from('<IIIII',b,pos+8)
            raw=b[pos+28:pos+28+caplen]
            assert iface==0 and t1==0 and t2==0 and origlen==caplen==91
            assert len(raw)==91
            hlen,irp,status,fn,info,bus,dev,ep,transfer,datalen=struct.unpack_from('<HQIHBHHBBI',raw)
            assert (hlen,irp,status,info,bus,dev,ep,transfer,datalen)==(27,0,0,0,1,1,3,1,64)
        pos+=n
    assert blocktypes==[0x0A0D0D0A,1]+[6]*count
    assert b'Windows' not in b and b'Intel(' not in b and b'USBPcap1' not in b
    payloads=packets(path)
    assert len(payloads)==count and all(validate(p) for p in payloads)
    # Validate that an independent consumer recognizes all outgoing reports.
    parsed, addrs, total = inspector_reports(path)
    assert len(parsed)==count and total==count
    assert set(addrs)=={1} and addrs[1]==count

# These are DRY-RUN packet constructors: do not send any USB commands.
for bank in (1,6,7,8):
    for target in (b'\x11\x04\x06\x64\x19\x04\x06\x96', b'\xff'*80):
        outbound=make_bank_reports(bank,target)
        assert len(outbound)==221 and all(validate(q) for q in outbound)
for one,two in ((1,2),(7,8),(8,7)):
    seq,commit=assignment_packets(one,two)
    assert len(seq)==2 and all(validate(x) for x in seq+[commit])
print('PASS: 443 minimal Sayo-only reports, metadata stripped, 8 write samples and 3 mapping samples validated offline.')
print('NO HID DEVICE ACCESSED OR PROGRAMMED.')
