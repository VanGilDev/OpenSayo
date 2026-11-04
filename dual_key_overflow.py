"""Non-destructive two-key overflow planner. Never splits while a key is held."""
from alpha22_device_ops import encode_script
from sayo_macro_language import validate_script

CAP = 468

def split_script(source, cap=CAP):
    validate_script(source)
    lines = [s.strip() for s in source.splitlines() if s.strip() and s.strip() != 'EXIT']
    groups=[]; current=[]; held=set()
    for line in lines:
        current.append(line)
        if line.startswith('PRESS_GK hidkey_'):
            held.add(line.split('hidkey_',1)[1])
        elif line.startswith('RELEASE_GK hidkey_'):
            held.remove(line.split('hidkey_',1)[1])
        if not held:
            groups.append(current);current=[]
    if current: raise ValueError('Unbalanced trailing keypress')
    first=[]; second=[]; overflow=False
    for group in groups:
        candidate='\n'.join(first+group+['EXIT'])
        if not overflow and len(encode_script(candidate))<=cap:
            first.extend(group)
        else:
            overflow=True
            second.extend(group)
    if not second:
        return '\n'.join(first+['EXIT'])+'\n', '', len(encode_script('\n'.join(first+['EXIT']))) , 0
    a='\n'.join(first+['EXIT'])+'\n'
    b='\n'.join(second+['EXIT'])+'\n'
    na,nb=len(encode_script(a)),len(encode_script(b))
    if not first:raise ValueError('First atomic key action exceeds capacity')
    if nb>cap:raise ValueError(f'Overflow would need {nb} bytes on Key 2 (limit {cap}). No changes made.')
    return a,b,na,nb
