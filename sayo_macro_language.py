"""Website-compatible Sayo macro text generation (US keyboard layout).
Uses documented Sayo keyboard/modifier instructions and explicit sleep widths.
"""
import re

SPECIAL={"TAB":"Tab","ENTER":"Enter","DOWN":"ArrowDown","UP":"ArrowUp",
 "LEFT":"ArrowLeft","RIGHT":"ArrowRight","ESC":"Escape","ESCAPE":"Escape",
 "BACKSPACE":"Backspace","SPACE":"Space","DELETE":"Delete","END":"End","HOME":"Home","PAGEUP":"PageUp","PAGEDOWN":"PageDown","CAPSLOCK":"CapsLock"}
PUNCT={"-":("Minus",False),"_":("Minus",True),"/":("Slash",False),
 "?":("Slash",True),".":("Period",False),">":("Period",True),
 ",":("Comma",False),"<":("Comma",True),"=":("Equal",False),
 "+":("Equal",True),";":("Semicolon",False),":":("Semicolon",True),
 "'":("Quote",False),'"':("Quote",True),"[":("BracketLeft",False),
 "{":("BracketLeft",True),"]":("BracketRight",False),"}":("BracketRight",True),
 "\\":("Backslash",False),"|":("Backslash",True),"!":("1",True),
 "@":("2",True),"#":("3",True),"$":("4",True),"%":("5",True),
 "^":("6",True),"&":("7",True),"*":("8",True),"(":("9",True),
 ")":("0",True),"`":("Backquote",False),"~":("Backquote",True)}
# The documented standard HID names supported by the current bytecode encoder.
STANDARD_KEYS=set('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789') | {
    'Tab','Enter','ArrowDown','ArrowUp','ArrowLeft','ArrowRight','Escape',
    'Backspace','Space','Delete','End','Home','PageUp','PageDown','CapsLock',
    'Minus','Slash','Period','Comma','Equal','Semicolon','Quote',
    'BracketLeft','BracketRight','Backslash','Backquote','Insert','ShiftLeft',
} | {f'F{i}' for i in range(1,25)}
MODIFIER_KEYS={'L_Ctrl':1,'L_Shift':2,'L_Alt':4,'L_Meta':8,
               'R_Ctrl':16,'R_Shift':32,'R_Alt':64,'R_Meta':128}

def sleep_instruction(ms):
    if not 0<=ms<=65535:raise ValueError('Sleep must be between 0 and 65535 ms.')
    if ms==0:return ''
    return f'SLEEP {ms}' if ms<=255 else f'SLEEP_U16 {ms}'

TOKEN=re.compile(r"\{([A-Za-z0-9+_]+)(?::(\d+))?\}")

def compile_macro(source, key_ms=5, action_ms=10, repeat_ms=15, caps_mode=False):
    """Translate readable text with {TAB}, {ENTER}, {DOWN}, {WAIT:ms}.
    Literal newlines separate editor lines; use {ENTER} to send Enter.
    """
    if not (1<=key_ms<=60000 and 0<=action_ms<=60000 and 0<=repeat_ms<=60000):
        raise ValueError('Timing must be between 0 and 60000 ms (key delay at least 1).')
    result=[]; previous=None; shift_held=False
    def sleep(ms):
        if ms: result.append(sleep_instruction(ms))
    def release_shift():
        nonlocal shift_held
        if shift_held:
            result.append('RELEASE_SK hidkey_L_Shift')
            shift_held=False
    def key(name, shift=False, navigation=False):
        nonlocal previous,shift_held
        if shift and not shift_held:
            result.append('PRESS_SK hidkey_L_Shift');shift_held=True
        elif not shift:
            release_shift()
        if previous==name and not navigation:sleep(repeat_ms)
        result.append('PRESS_GK hidkey_'+name)
        sleep(key_ms)
        result.append('RELEASE_GK hidkey_'+name)
        # Sayo recommends a delay between consecutive key operations.
        if navigation:sleep(action_ms)
        else:sleep(action_ms)
        previous=name
    def char(ch):
        if ch=='\n' or ch=='\r':return
        if ch=='\t':key('Tab',navigation=True);return
        if ch==' ':key('Space');return
        if ch.isascii() and ch.isalpha():key(ch.upper(),ch.isupper() != caps_mode);return
        if ch.isascii() and ch.isdigit():key(ch);return
        if ch in PUNCT:
            name,shift=PUNCT[ch];key(name,shift);return
        raise ValueError(f'Unsupported character {ch!r}. Use ASCII text or a supported {{TOKEN}}.')
    if caps_mode:
        key('CapsLock',navigation=True)
    pos=0
    for m in TOKEN.finditer(source):
        for c in source[pos:m.start()]:char(c)
        command=m.group(1).upper(); number=m.group(2)
        if "+" in command or command in ("SHIFT","CTRL","ALT","L_SHIFT","R_SHIFT","L_CTRL","R_CTRL","L_ALT","R_ALT"):
            if number is not None:raise ValueError(f"{command} does not take a number")
            release_shift()
            parts=command.split("+")
            mods={"SHIFT":"L_Shift","CTRL":"L_Ctrl","ALT":"L_Alt","L_SHIFT":"L_Shift","R_SHIFT":"R_Shift","L_CTRL":"L_Ctrl","R_CTRL":"R_Ctrl","L_ALT":"L_Alt","R_ALT":"R_Alt"}
            active=[mods[x] for x in parts if x in mods]
            keys=[x for x in parts if x not in mods]
            if len(keys)>1 or len(set(active))!=len(active):raise ValueError(f"Invalid shortcut {{{command}}}")
            for mod in active:result.append("PRESS_SK hidkey_"+mod)
            if keys:
                name=keys[0]
                if name in SPECIAL:name=SPECIAL[name]
                elif len(name)==1 and name.isalpha():pass
                elif len(name)==1 and name.isdigit():pass
                elif name not in STANDARD_KEYS:raise ValueError(f"Unsupported shortcut key {name}")
                result.append("PRESS_GK hidkey_"+name)
                sleep(key_ms)
                result.append("RELEASE_GK hidkey_"+name)
            else:sleep(key_ms)
            for mod in reversed(active):result.append("RELEASE_SK hidkey_"+mod)
            sleep(action_ms)
            previous=None
        elif command=='WAIT':
            if number is None:raise ValueError('Use {WAIT:15}, for example.')
            ms=int(number)
            if ms>60000:raise ValueError('WAIT must be at most 60000 ms.')
            release_shift();sleep(ms);previous=None
        elif command in SPECIAL:
            if number is not None:raise ValueError(f'{command} does not take a number.')
            key(SPECIAL[command],navigation=True)
        else:raise ValueError('Unknown token {'+m.group(1)+'}.')
        pos=m.end()
    for c in source[pos:]:char(c)
    release_shift()
    if caps_mode:key('CapsLock',navigation=True)
    return optimize_adjacent_sleeps(('\n'.join(result)+'\n') if result else '')

def optimize_adjacent_sleeps(script):
    """Combine consecutive timing commands without moving key press/release actions."""
    result=[]; accumulated=0
    def flush():
        nonlocal accumulated
        while accumulated:
            chunk=min(accumulated,65535)
            result.append(sleep_instruction(chunk))
            accumulated-=chunk
    for raw in script.splitlines():
        line=raw.strip()
        match=re.fullmatch(r'SLEEP(?:_U16)? ([0-9]+)',line)
        if match:
            accumulated+=int(match.group(1))
        else:
            flush()
            if line:result.append(line)
    flush()
    return ('\n'.join(result)+'\n') if result else ''

def validate_script(source):
    """Validate documented subset, timing widths, and press/release balance."""
    pressed=set(); count=0; exited=False
    lines=source.splitlines()
    for lineno,raw in enumerate(lines,1):
        line=raw.strip()
        if not line:continue
        if exited:raise ValueError(f'Line {lineno}: instructions after EXIT')
        m=re.fullmatch(r'(PRESS_GK|RELEASE_GK|PRESS_SK|RELEASE_SK) hidkey_([A-Za-z0-9_]+)',line)
        if m:
            op,key=m.groups();kind=op[-2:]
            allowed=STANDARD_KEYS if kind=='GK' else MODIFIER_KEYS
            if key not in allowed:raise ValueError(f'Line {lineno}: unsupported {kind} key {key}')
            token=(kind,key)
            if op.startswith('PRESS'):
                if token in pressed:raise ValueError(f'Line {lineno}: {key} pressed twice without release')
                pressed.add(token)
            else:
                if token not in pressed:raise ValueError(f'Line {lineno}: {key} released without press')
                pressed.remove(token)
        else:
            m=re.fullmatch(r'(SLEEP|SLEEP_U16) ([0-9]+)',line)
            if m:
                opcode,raw_ms=m.groups();ms=int(raw_ms)
                if not 1<=ms<=(255 if opcode=='SLEEP' else 65535):
                    raise ValueError(f'Line {lineno}: {opcode} timing out of range')
            elif line=='EXIT':
                if pressed:raise ValueError(f'Line {lineno}: EXIT with held keys: {sorted(pressed)}')
                exited=True
            else:raise ValueError(f'Line {lineno}: unrecognized command: {line}')
        count+=1
    if pressed:raise ValueError(f'Keys not released: {sorted(pressed)}')
    return count

# Reverse translation is a readable approximation; the original script stays untouched.
INVERSE_PUNCT={(name,shift):ch for ch,(name,shift) in PUNCT.items()}
INVERSE_SPECIAL={v:k for k,v in SPECIAL.items() if k not in ("ESCAPE",)}
def script_to_readable(script):
    """Decode observed Sayo keystroke commands; preserve original source separately."""
    validate_script(script)
    output=[]; held=set(); keys=0
    for raw in script.splitlines():
        line=raw.strip()
        if line.startswith("PRESS_GK hidkey_"):
            name=line[len("PRESS_GK hidkey_"):]
            shifted="L_Shift" in held or "R_Shift" in held or "ShiftLeft" in held
            if name=="ShiftLeft":
                # Legacy macros sometimes encode left Shift as a generic HID key.
                # Treat it as a held modifier for the readable approximation.
                held.add("ShiftLeft")
                continue
            if name in INVERSE_SPECIAL:output.append("{"+INVERSE_SPECIAL[name]+"}")
            elif name=="Space":output.append(" ")
            elif len(name)==1 and name.isalpha():output.append(name if shifted else name.lower())
            elif len(name)==1 and name.isdigit():
                output.append(INVERSE_PUNCT.get((name,True),name) if shifted else name)
            elif (name,shifted) in INVERSE_PUNCT:output.append(INVERSE_PUNCT[(name,shifted)])
            else:raise ValueError(f"Cannot represent key {name} in readable editor")
            keys+=1
        elif line=="RELEASE_GK hidkey_ShiftLeft":
            held.discard("ShiftLeft")
        elif line.startswith("PRESS_SK hidkey_"):
            held.add(line[len("PRESS_SK hidkey_"):])
        elif line.startswith("RELEASE_SK hidkey_"):
            held.discard(line[len("RELEASE_SK hidkey_"):])
        elif line.startswith("SLEEP_U16 ") or line.startswith("SLEEP "):
            # Raw timings are preserved in the original script, not in readable text.
            pass
    return "".join(output), keys
