"""Split compiled binary into balanced-key chunks without changing bytes."""
def split_bytecode(data, cap=468):
    groups=[]; held=set(); start=0; i=0
    while i<len(data):
        op=data[i]
        if op in (0x11,0x19,0x06):
            if i+2>len(data):raise ValueError('Incomplete 2-byte instruction')
            arg=data[i+1]
            if op==0x11:
                if arg in held:raise ValueError('Repeated press without release')
                held.add(arg)
            elif op==0x19:
                if arg not in held:raise ValueError('Release without press')
                held.remove(arg)
            i+=2
        elif op==0x0d:
            if i+3>len(data):raise ValueError('Incomplete long sleep')
            i+=3
        else:raise ValueError(f'Unknown opcode 0x{op:02x} at {i}')
        if not held:
            groups.append(data[start:i]);start=i
    if held:raise ValueError('Macro ends with a held key')
    a=bytearray();b=bytearray();overflow=False
    for group in groups:
        if not overflow and len(a)+len(group)<=cap:a.extend(group)
        else:overflow=True;b.extend(group)
    if len(a)>cap or len(b)>cap:raise ValueError(f'Key 2 needs {len(b)} bytes; maximum {cap}')
    return bytes(a),bytes(b)
