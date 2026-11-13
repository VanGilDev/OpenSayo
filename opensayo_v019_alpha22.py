#!/usr/bin/env python3
"""OpenSayo v1.15 — configurable form system and guarded SayoDevice writer.

Windows desktop app. Requires Python 3.10+; device programming requires hidapi.
Writes only the script memory. The official SayoDevice website's Save operation
may still be required to activate/persist the script on this firmware.
"""
from __future__ import annotations
import json, hashlib, time, sys, webbrowser, os, ctypes, re, copy, uuid, threading
from datetime import date
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from pcap_inspector import describe
from protocol_decoder import decode
from key2_evidence import analyze as analyze_key2
from key2_memory_audit import audit as audit_memory
from key2_readback_evidence import assess as assess_readback
from assignment_comparator import report as assignment_report
from sayo_macro_language import compile_macro as compile_sayo_text, validate_script, script_to_readable

VERSION = "1.15"
VID, PID = 0x8089, 0x000C
INTERFACE = 1
USAGE_PAGE = 0xFF00
USAGE = 1
DEVICE_MATCH = "O2L"
REPORT_ID = 0x02
CMD_SCRIPT = 0xF0
MAX_DATA = 54
MEMORY_SIZE = 512
SAFE_CUTOFF = 468  # two-key cap
EIGHT_SCRIPT_CAP = 2028  # user-confirmed initial eight-key script limit

# HID keyboard usage IDs confirmed by the Sayo script format/source data.
KEY_CODES = {chr(ord("A")+i): 0x04+i for i in range(26)}
KEY_CODES.update({str(i): code for i, code in zip(range(1,10), range(0x1E,0x27))})
KEY_CODES["0"] = 0x27
KEY_CODES.update({
    "Enter":0x28, "Escape":0x29, "Backspace":0x2A, "Tab":0x2B,
    "Space":0x2C, "-":0x2D, "=":0x2E, "[":0x2F, "]":0x30,
    "\\":0x31, ";":0x33, "'":0x34, "`":0x35, ",":0x36, ".":0x37,
    "/":0x38, "CapsLock":0x39, "Down":0x51, "Up":0x52,
    "Right":0x4F, "Left":0x50, "Home":0x4A, "Page Up":0x4B,
    "Page Down":0x4E, "End":0x4D, "Delete":0x4C, "Insert":0x49
})
# Script bytecode from the known TEST script:
# 0x11 + HID key = press; 0x19 + HID key = release;
# 0x06 + 8-bit ms delay; 0x0D + uint16 little-endian ms delay.
OP_PRESS, OP_RELEASE, OP_SLEEP8, OP_SLEEP16, OP_EXIT = 0x11, 0x19, 0x06, 0x0D, 0xFF

# A fresh installation has ten generic example labels and 15 numbered fields.
# User imports overwrite these labels, formats, positions and the field count.
INDEPENDENT_PROJECT_NOTICE = "I originally created OpenSayo because I wanted to make everyday tasks a little easier for myself and my coworkers. What started as a small personal project grew into something I thought other people might find useful too.\n\nOpenSayo is an independently developed application that allows users to create, edit, record, and program macros for supported programmable keypads.\n\nThis project is something I've put together independently, simply because I enjoy finding ways to make everyday tasks easier. While OpenSayo may work alongside devices and systems that might slightly resemble this, it is not officially affiliated with or endorsed by their respective creators or manufacturers.\n\nI hope this little tool makes someone's day a bit easier!"

STARTER_LABELS = ['First Name', 'Last Name', 'Date', 'Email Address', 'Phone Number', 'Street Address', 'City', 'State/Province', 'ZIP/Postal Code', 'Notes']
FIELD_NAMES = [STARTER_LABELS[i] if i < len(STARTER_LABELS) else str(i+1)
               for i in range(25)]
NO_ENTRY_STEPS = set()
MANUAL_FIELDS = set()
NAV_ONLY = set()

DEFAULT_FIELDS = [dict(step=i, field_id=f"field_{i:03d}", name=FIELD_NAMES[i-1],
                       value="", kind="text", format_type="Text", format_option="",
                       after="Tab", enabled=True) for i in range(1, 26)]
DEFAULT_PROJECT = {"format":"OpenSayo-Form", "version":2,
                   "text_delay_ms":15, "action_delay_ms":20, "repeat_gap_ms":15, "dropdown_open_ms":75,
                   "endpoint":0, "key2_endpoint":0, "fields":DEFAULT_FIELDS, "dropdowns":{}}
# Each version has its own session directory to avoid importing or
# overwriting another installation's personal session automatically.
LEGACY_SESSION_PATH = Path.home() / "Documents" / "OpenSayo" / "last_session.json"
SESSION_PATH = Path.home() / "Documents" / "OpenSayo" / "v1.15" / "last_session.json"
UI_PREFS_PATH = SESSION_PATH.with_name("ui_preferences.json")
KEY_PREFS_PATH = SESSION_PATH.with_name("key_assignment_preferences.json")

def field_is_enabled(field):
    """Old .osfld/.osfrm/.osayo files predate the toggle: default to enabled."""
    return bool(field.get("enabled", True))


def generic_field_display_label(i, field):
    name=str(field.get("name", ""))
    return str(i+1) if name==str(i+1) else f"{i+1:02d}. {name}"

def default_layout(count=25):
    """Create a simple three-column numbered grid; grow vertically as needed."""
    count=max(1,int(count))
    per_column=max(1,(count+2)//3)
    return {"columns":3,"rows":max(25,per_column),
            "positions":{str(i):[i//per_column,i%per_column] for i in range(count)},
            "allow_unplaced":True,"half_fields":[],"half_slots":{},"labels":[]}

def blank_project():
    project=json.loads(json.dumps(DEFAULT_PROJECT))
    for i,f in enumerate(project["fields"]):f["field_id"]=f"field_{i+1:03d}"
    project["dynamic_form"]=True
    project["layout"]=default_layout(len(project["fields"]))
    return project

def normalized_layout(raw,count):
    raw=raw if isinstance(raw,dict) else {}
    cols=max(3,min(8,int(raw.get("columns",3))))
    # Field counts are not capped at 69 or 240. The scrollable grid grows
    # vertically when more space is needed; available memory is the practical limit.
    rows=max(25,int(raw.get("rows",25)),(count+cols-1)//cols)
    result={"columns":cols,"rows":rows,"positions":{},"allow_unplaced":bool(raw.get("allow_unplaced")),"half_fields":[],"half_slots":{},"labels":[]}
    half={int(i) for i in raw.get("half_fields",[]) if str(i).isdigit() and 0<=int(i)<count} if isinstance(raw.get("half_fields",[]),list) else set()
    slots=raw.get("half_slots",{}) if isinstance(raw.get("half_slots",{}),dict) else {}
    result["half_fields"]=sorted(half)
    result["half_slots"]={}
    occupied={}  # (column,row) -> set of occupied vertical half slots
    explicit_unplaced=bool(raw.get("allow_unplaced"))
    positions=raw.get("positions",{}) if isinstance(raw.get("positions",{}),dict) else {}
    for i in range(count):
        if explicit_unplaced and str(i) not in positions:continue
        candidate=positions.get(str(i))
        try:c,r=int(candidate[0]),int(candidate[1])
        except (ValueError,TypeError,IndexError):c,r=-1,-1
        slot=int(slots.get(str(i),0)) if str(slots.get(str(i),0)) in ("0","1") else 0
        wanted={slot} if i in half else {0,1}
        def available(x,y):return not (occupied.get((x,y),set()) & wanted)
        if not (0<=c<cols and 0<=r<rows and available(c,r)):
            c,r=next(((x,y) for x in range(cols) for y in range(rows) if available(x,y)),(-1,-1))
        if c>=0:
            occupied.setdefault((c,r),set()).update(wanted)
            result["positions"][str(i)]=[c,r]
            if i in half:result["half_slots"][str(i)]=slot
    labels=raw.get("labels",[])
    if isinstance(labels,list):
        for item in labels[:150]:
            if not isinstance(item,dict):continue
            name=str(item.get("name","")).strip()[:100]
            pos=item.get("position")
            if not name or not isinstance(pos,list) or len(pos)!=2:continue
            try:c,r=int(pos[0]),int(pos[1]);side=int(item.get("side",0))
            except (ValueError,TypeError):continue
            if 0<=c<cols and 0<=r<rows:
                result["labels"].append({"id":str(item.get("id") or uuid.uuid4().hex),"name":name,"position":[c,r],"side":int(bool(side))})
    return result

def normalize_project(raw):
    # Accept current projects and structurally compatible older OpenSayo form
    # projects. Older saved format identifiers are never shipped in this source.
    if not isinstance(raw, dict):
        raise ValueError("Not a recognized OpenSayo form project")
    project_format=raw.get("format")
    prior_format=(isinstance(project_format,str) and
                  project_format.startswith("OpenSayo-") and
                  project_format!=DEFAULT_PROJECT["format"] and
                  raw.get("version") in (1,2) and
                  isinstance(raw.get("fields"),list))
    if project_format!=DEFAULT_PROJECT["format"] and not prior_format:
        raise ValueError("Not a recognized OpenSayo form project")
    result = blank_project()
    old = raw.get("fields", [])
    if not isinstance(old, list):
        raise ValueError("Invalid fields")
    if raw.get("dynamic_form"):
        if len(old)<1:raise ValueError("Form requires at least one field")
        clean=[];ids=set()
        for i,item in enumerate(old):
            if not isinstance(item,dict):raise ValueError("Invalid field")
            f=copy.deepcopy(item)
            f["name"]=str(f.get("name","")).strip()[:100]
            if not f["name"]:raise ValueError(f"Field {i+1} has no name")
            fid=str(f.get("field_id") or f"imported_{i:03d}")[:100]
            if fid in ids:raise ValueError("Duplicate field ID")
            ids.add(fid);f["field_id"]=fid;f["step"]=i+1
            f["value"]=str(f.get("value",""))[:500]
            f["after"]=str(f.get("after","Tab"))[:200]
            f["enabled"]=field_is_enabled(f)
            if f.get("format_type","Text") not in ("Text","Skip","Date","Drop Down"):
                raise ValueError("Invalid field format")
            clean.append(f)
        result["fields"]=migrate_date_fields(migrate_legacy_calendar_fields(clean,prior_format))
        result["layout"]=normalized_layout(raw.get("layout"),len(clean))
        result["dynamic_form"]=True
        result["use_caps_lock"]=bool(raw.get("use_caps_lock",False))
        for key,default in (("text_delay_ms",15),("action_delay_ms",20),("repeat_gap_ms",15),("dropdown_open_ms",75)):
            value=raw.get(key,default)
            result[key]=int(value) if str(value).isdigit() else default
        result["endpoint"]=max(0,min(len(clean)-1,int(raw.get("endpoint",0))))
        result["key2_endpoint"]=max(result["endpoint"],min(len(clean)-1,int(raw.get("key2_endpoint",result["endpoint"]))))
        libs=raw.get("dropdowns",{})
        if isinstance(libs,dict):result["dropdowns"]={str(k)[:80]:[str(v)[:200] for v in vals[:200]] for k,vals in libs.items() if isinstance(vals,list)}
        if isinstance(raw.get("form_raw_readbacks"),dict):
            result["form_raw_readbacks"]=raw["form_raw_readbacks"]
        return result
    # Older forms may not carry dynamic_form, so extend the template before
    # copying properties. Never truncate user fields at the 25-field default.
    count=max(len(DEFAULT_FIELDS),len(old))
    clean=[]
    for i in range(count):
        if i<len(DEFAULT_FIELDS):
            item=copy.deepcopy(DEFAULT_FIELDS[i])
        else:
            item=copy.deepcopy(DEFAULT_FIELDS[0])
            item.update(step=i+1,field_id=f"field_{i+1:03d}",name=str(i+1),value="")
        if i<len(old) and isinstance(old[i],dict):
            item.update(copy.deepcopy(old[i]))
        item["step"]=i+1
        item["name"]=str(item.get("name") or str(i+1))[:100]
        item["field_id"]=str(item.get("field_id") or f"field_{i+1:03d}")[:100]
        item["value"]=str(item.get("value", ""))[:500]
        item["after"]=str(item.get("after", "Tab"))[:200]
        item["enabled"]=field_is_enabled(item)
        if item.get("format_type") not in ("Text","Skip","Date","Drop Down"):
            item["format_type"]="Text"
        clean.append(item)
    result["fields"]=migrate_date_fields(migrate_legacy_calendar_fields(clean,prior_format))
    result["dynamic_form"]=True
    result["use_caps_lock"]=bool(raw.get("use_caps_lock",False))
    libraries=raw.get("dropdowns",{})
    if isinstance(libraries,dict):
        result["dropdowns"]={str(k)[:80]:[str(v)[:200] for v in vals[:200]] for k,vals in libraries.items() if isinstance(vals,list)}
    for key, default in (("text_delay_ms",15),("action_delay_ms",20),("repeat_gap_ms",15),("dropdown_open_ms",75)):
        value=raw.get(key,default)
        result[key]=int(value) if str(value).isdigit() else default
    result["endpoint"]=max(0,min(count-1,int(raw.get("endpoint",0))))
    result["key2_endpoint"]=max(result["endpoint"],min(count-1,int(raw.get("key2_endpoint",result["endpoint"]))))
    result["layout"]=normalized_layout(raw.get("layout") if isinstance(raw.get("layout"),dict) else default_layout(count),count)
    return result

# Project loading is checked before switching the active workspace so a bad
# or obsolete file cannot partially replace an editor or its current values.
class UnsupportedProjectFormat(ValueError):
    pass


UNSUPPORTED_PROJECT_NOTICE = (
    "This project file is from an older or unsupported format.\n\n"
    "Your current project has not been changed.\n\n"
    "To restore your configuration, import your current field (.osfld), "
    "grid (.oslay), and dropdown (.osdrp) definition files."
)
UNREADABLE_PROJECT_NOTICE = (
    "This project file could not be loaded. It may be damaged or contain "
    "invalid data.\n\nYour current project has not been changed.\n\n"
    "Please use a valid .osayo project, or import your field (.osfld), "
    "grid (.oslay), and dropdown (.osdrp) definition files."
)


def prepare_workspace_project(data):
    """Validate a saved project entirely before GUI workspace mutation.

    Returns (kind, form_data, script, readable), suitable for _workspace_activate.
    A supported historic form shape may still be accepted, but obsolete or
    unrecognized formats are cleanly rejected rather than guessed at.
    """
    if not isinstance(data, dict):
        raise ValueError("Project root is not a JSON object")
    fmt=data.get("format")
    if fmt=="opensayo-v023":
        if data.get("version")!=1:
            raise UnsupportedProjectFormat("Unrecognized project version")
        kind=data.get("kind")
        if kind=="form_project":
            form=data.get("form")
            if not isinstance(form, dict):
                raise ValueError("Form contents are missing or invalid")
            normalized=normalize_project(form)
            scripts=data.get("scripts", {})
            if not isinstance(scripts,dict) or any(not isinstance(v,str) for v in scripts.values()):
                raise ValueError("Saved script data is invalid")
            return kind, {**data, "form":normalized}, None, None
        if kind=="freeform":
            script=data.get("script")
            readable=data.get("readable")
            if not isinstance(script,str) or (readable is not None and not isinstance(readable,str)):
                raise ValueError("Freeform script data is invalid")
            return kind, None, script, readable
        raise ValueError("Missing or invalid workspace type")
    if (isinstance(fmt,str) and fmt.startswith("OpenSayo-") and
            data.get("version") in (1,2) and isinstance(data.get("fields"),list)):
        normalized=normalize_project(data)
        return "form_project", {"form":normalized,"scripts":{"1":"EXIT","2":"EXIT"}}, None, None
    raise UnsupportedProjectFormat("Old or unrecognized project format")


def read_workspace_project(path):
    try:
        data=json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Unable to read project JSON") from exc
    try:
        return prepare_workspace_project(data)
    except UnsupportedProjectFormat:
        raise
    except (ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
        raise ValueError("Invalid project data") from exc


def device_readback_form_rows(readable, field_count):
    """Map decoded device actions to editable form rows without silently dropping keys.

    Text fields can contain supported {TAB}/{DOWN}/{ENTER}/{BACKSPACE}
    macros. Any unsupported braces or a field beyond the configured count
    rejects the WHOLE mapping before a live form is modified.
    """
    if not isinstance(readable, str):
        raise ValueError("Device macro did not decode to readable instructions")
    parts=readable.replace("\r", "").replace("\n", "").split("{TAB}")
    if len(parts)>field_count:
        raise ValueError(f"Device macro reaches {len(parts)} fields; current form has {field_count}. Load a larger Field List first.")
    from sayo_macro_language import TOKEN
    rows=[]
    for i,part in enumerate(parts):
        if len(part)>500:
            raise ValueError(f"Device field {i+1} exceeds the 500-character form field limit; raw device script preserved")
        # Unknown or unbalanced tokens must never become literal keystrokes.
        remainder=TOKEN.sub("", part)
        if "{" in remainder or "}" in remainder:
            raise ValueError(f"Unsupported navigation token in field {i+1}; raw device script retained")
        if part:
            compile_sayo_text(part,15,20,15)
        if part=="{DOWN}{ENTER}":
            rows.append(("Date", "Today's Date", ""))
        else:
            rows.append(("Text", "", part))
    return rows, len(parts)-1


def legacy_script_fields(source):
    """Decode a legacy Sayo script or readable {TAB} sequence to form rows.

    Reject unsupported actions instead of silently discarding user keystrokes.
    Returns (list of (mode, option, value), zero-based endpoint).
    """
    source=source.strip()
    if not source:raise ValueError("Empty legacy script")
    if re.search(r"(?m)^\s*(?:PRESS_GK|RELEASE_GK|SLEEP|EXIT)\b",source):
        readable,_=script_to_readable(source.replace("hidkey_Down","hidkey_ArrowDown").replace("hidkey_Up","hidkey_ArrowUp").replace("hidkey_Left","hidkey_ArrowLeft").replace("hidkey_Right","hidkey_ArrowRight"))
    else:
        readable=source.replace("\r", "").replace("\n", "")
        if readable.endswith("{EXIT}"):readable=readable[:-6]
    parts=readable.split("{TAB}")
    # A legacy script may describe more fields than the fresh-install template.
    # Importing into the form still checks its currently configured field count.
    rows=[]
    for i,part in enumerate(parts):
        if part in ("{DOWN}{ENTER}","{DOWN}{ENTER}{END}"):
            rows.append(("Date","Today's Date",""))
        elif "{" in part or "}" in part:
            raise ValueError(f"Unsupported actions in legacy field {i+1}: {part!r}; original file was not modified")
        else:
            rows.append(("Text","",part))
    return rows,len(parts)-1

def normalize_date(value):
    """Accept MM/DD/YY and legacy MM/DD/YYYY; emit canonical MM/DD/YY."""
    from datetime import datetime
    value=str(value).strip()
    if not re.fullmatch(r"\d{2}/\d{2}/(?:\d{2}|\d{4})",value):
        raise ValueError("Date must be MM/DD/YY")
    parsed=datetime.strptime(value,"%m/%d/%Y" if len(value)==10 else "%m/%d/%y")
    return parsed.strftime("%m/%d/%y")

def valid_date(value):
    try:
        normalize_date(value)
        return True
    except (ValueError,TypeError):return False

def migrate_legacy_calendar_fields(fields,old_format=False):
    """Import previously implicit calendar actions as explicit Date settings.

    A date-labelled field containing navigation instructions is an explicit
    action. A blank older calendar field can also be migrated;
    ordinary blank Date fields in new installations remain plain text.
    """
    for field in fields:
        if field.get("format_type")!="Text":continue
        tokens=set(re.findall(r"[a-z]+",str(field.get("name","")).lower()))
        value=str(field.get("value","")).strip().lower().replace(" ","")
        has_action=("date" in tokens and value in ("down,enter","down,enter,end"))
        has_legacy_default=(old_format and {"arrival","date"}.issubset(tokens) and not value)
        explicitly_configured=(field.get("special_action")=="today_calendar")
        if has_action or has_legacy_default or explicitly_configured:
            field["format_type"]="Date"
            field["format_option"]="Today's Date"
            field["special_action"]="today_calendar"
            field["value"]=""
    return fields

def migrate_date_fields(fields):
    for field in fields:
        if field.get("format_type")!="Date":continue
        for key in ("format_option","date_option_memory"):
            if field.get(key)=="MM/DD/YYYY":field[key]="MM/DD/YY"
        if valid_date(field.get("value","")):
            field["value"]=normalize_date(field["value"])
        values=field.get("format_values")
        if isinstance(values,dict):
            for k,v in list(values.items()):
                if valid_date(v):values[k]=normalize_date(v)
    return fields

def parse_actions(text):
    for token in [t.strip() for t in text.split(",") if t.strip()]:
        m = re.fullmatch(r"(.+?)\s*[x×*]\s*(\d+)", token, re.I)
        key, count = (m.group(1).strip(), int(m.group(2))) if m else (token, 1)
        if key not in KEY_CODES or not 1 <= count <= 100:
            raise ValueError(f"Unsupported navigation action: {token!r}. Use Tab, Down, Enter, etc. or Tab x3.")
        for _ in range(count): yield key

def navigation_tokens(source):
    """Validate and translate comma/newline-separated key names to macro tokens."""
    aliases={"PAGE DOWN":"PAGEDOWN","PAGE UP":"PAGEUP","ARROWDOWN":"DOWN","ARROWUP":"UP","ESC":"ESCAPE"}
    supported={"BACKSPACE","DOWN","UP","PAGEDOWN","PAGEUP","ENTER","TAB","ESCAPE","LEFT","RIGHT","DELETE","HOME","END","SPACE"}
    result=[]
    for raw in re.split(r"[,\n]+",source):
        raw=raw.strip()
        if not raw:continue
        match=re.fullmatch(r"(.+?)\s*(?:x|×|\*)\s*(\d+)",raw,re.I)
        name=(match.group(1) if match else raw).strip().upper()
        name=aliases.get(name,name)
        count=int(match.group(2)) if match else 1
        if name not in supported or not 1<=count<=100:
            raise ValueError(f"Unsupported Navigate Keys entry: {raw!r}")
        result.extend(["{"+name+"}"]*count)
    if not result:raise ValueError("Navigate Keys sequence is empty")
    return result

def compile_v018(fields, endpoint, text_delay=5, action_delay=10, repeat_gap=15, enforce_limit=True):
    if not 0 <= endpoint < len(fields): raise ValueError("Invalid endpoint")
    for val in (text_delay, action_delay, repeat_gap):
        if not 0 <= val <= 60000: raise ValueError("Timing must be between 0 and 60000 ms")
    out=bytearray()
    for index, field in enumerate(fields[:endpoint+1]):
        # Disabled fields remain in the Tab map but produce no field action.
        if not field_is_enabled(field):
            if index < endpoint:
                out.extend(key_bytes("Tab",text_delay,action_delay))
                out.extend(delay_bytes(action_delay))
            continue
        mode=field.get("format_type", "Text")
        option=field.get("format_option", "MM/DD/YY")
        value="" if mode=="Skip" else field["value"]
        if mode=="Date":
            if option=="Blank":value=""
            elif option=="Today's Date":value="Down, Enter"
        if mode=="Drop Down" and not field.get("format_option"):
            raise ValueError(f"{field['name']}: choose a dropdown library before compiling")
        # Date action: type a date or invoke the configured calendar, not both.
        if mode=="Date" and option=="Today's Date":
            if not value.strip() or value.strip().lower().replace(" ", "") in ("down,enter", "down,enter,end"):
                value = ""  # This is a navigation instruction, not literal text.
                for key in parse_actions("Down, Enter"):
                    out.extend(key_bytes(key,text_delay,action_delay))
                    out.extend(delay_bytes(action_delay))
            if index < endpoint:
                out.extend(key_bytes("Tab",text_delay,action_delay))
                out.extend(delay_bytes(action_delay))
        if value and mode=="Date" and option=="MM/DD/YY" and not valid_date(value):
            raise ValueError(f"{field['name']} requires MM/DD/YY or the configured calendar action")
        if value:
            if mode=="Date" and option=="MM/DD/YY":value=normalize_date(value)
            previous=None
            for char in value:
                # Treat repeated HID key usage as requiring an explicit gap.
                current=char.upper()
                if previous == current: out.extend(delay_bytes(repeat_gap))
                out.extend(character_sequence(char,text_delay))
                previous=current
        # The endpoint does not tab past itself; Date actions remain explicit.
        if index < endpoint and not (mode=="Date" and option=="Today's Date"):
            out.extend(key_bytes("Tab",text_delay,action_delay))
            out.extend(delay_bytes(action_delay))
    if enforce_limit and len(out)+2 > SAFE_CUTOFF:
        raise ValueError(f"Macro needs {len(out)+2} bytes; safe Key 1 limit is {SAFE_CUTOFF}. Key 2 overflow is not enabled in v0.18.")
    return bytes(out)

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def delay_bytes(ms: int) -> bytes:
    if not 0 <= ms <= 60000:
        raise ValueError("Delay must be between 0 and 60000 ms.")
    if ms == 0:
        return b""
    if ms <= 255:
        return bytes((OP_SLEEP8, ms))
    return bytes((OP_SLEEP16, ms & 0xFF, (ms >> 8) & 0xFF))

def key_bytes(key: str, text_delay: int, action_delay: int, shifted: bool=False) -> bytes:
    if key not in KEY_CODES:
        raise ValueError(f"Unsupported key: {key!r}")
    code = KEY_CODES[key]
    out=bytearray()
    # Standard HID left Shift usage is 0xE1. Script key down/up instructions
    # are the same ones confirmed by the working S -> A test.
    if shifted:
        out.extend((OP_PRESS, 0xE1))
    out.extend((OP_PRESS, code))
    out.extend(delay_bytes(text_delay))
    out.extend((OP_RELEASE, code))
    if shifted:
        out.extend((OP_RELEASE, 0xE1))
    # action_delay is applied after navigation / field boundaries, not after
    # every character; this keeps longer macros within script capacity.
    return bytes(out)

def character_sequence(char: str, text_delay: int) -> bytes:
    if char == " ":
        return key_bytes("Space", text_delay, 0)
    if char.isalpha():
        return key_bytes(char.upper(), text_delay, 0, shifted=char.isupper())
    if char == "#":
        return key_bytes("3", text_delay, 0, shifted=True)
    if char in KEY_CODES:
        return key_bytes(char, text_delay, 0)
    raise ValueError(f"Unsupported character: {char!r}")

def compile_macro(fields, text_delay=55, action_delay=100, enforce_limit=True) -> bytes:
    """Compile the 11-step sequence; returns code without the device terminator."""
    out = bytearray()
    for f in fields:
        name, kind, value = f["name"], f["kind"], f["value"]
        if kind == "text":
            if not value:
                raise ValueError(f"{name}: text cannot be empty.")
            previous_key = None
            for char in value:
                current_key = char.upper()
                # A released key needs a distinct gap before another press of
                # the same HID usage. The 40ms gap is placed AFTER release.
                if current_key == previous_key:
                    out.extend(delay_bytes(40))
                out.extend(character_sequence(char, text_delay))
                previous_key = current_key
        elif kind not in ("manual", "navigation"):
            raise ValueError(f"Unknown field type for {name}: {kind}")
        nav = f.get("after", "None")
        if nav and nav != "None":
            for token in [x.strip() for x in nav.split(",") if x.strip()]:
                if token not in KEY_CODES:
                    raise ValueError(f"{name}: unsupported navigation action {token!r}.")
                out.extend(key_bytes(token, text_delay, action_delay))
                out.extend(delay_bytes(action_delay))
    if enforce_limit and len(out) + 2 > SAFE_CUTOFF:
        raise ValueError(
            f"Script requires {len(out)+2} bytes including EXIT markers, "
            f"above the {SAFE_CUTOFF}-byte safety cutoff. "
            f"Device capacity is {MEMORY_SIZE} bytes. Shorten the macro; "
            "automatic Key 2 overflow is not implemented yet."
        )
    return bytes(out)

def make_packet(command, payload):
    if len(payload) > 60:
        raise ValueError("Packet payload exceeds 60 bytes.")
    report = bytearray(64)
    report[0:3] = bytes((REPORT_ID, command, len(payload)))
    report[3:3+len(payload)] = payload
    report[3+len(payload)] = sum(report[:3+len(payload)]) & 0xFF
    return bytes(report)

def identify_supported_devices(hid):
    """Enumerate USB identities only. Never opens a device or sends reports."""
    models = ((0x000C, "O2L V2", "O2L"), (0x000B, "2x4V RGB", "2x4V"))
    found = []
    for pid, label, name_fragment in models:
        for d in hid.enumerate(VID, pid):
            product = str(d.get("product_string") or "")
            if (d.get("interface_number") == 1
                    and d.get("usage_page") == 0xFF11
                    and d.get("usage") == 2
                    and name_fragment.lower() in product.lower()):
                found.append((label, d))
    return found

def select_device(hid):
    candidates=[]
    for d in hid.enumerate(VID, PID):
        if d.get("interface_number") == INTERFACE and d.get("usage_page") == USAGE_PAGE and d.get("usage") == USAGE:
            product = str(d.get("product_string") or "")
            if DEVICE_MATCH.lower() in product.lower():
                candidates.append(d)
    if len(candidates) != 1:
        raise RuntimeError(f"Expected exactly one SayoDevice O2L configuration interface; found {len(candidates)}. No write sent.")
    return candidates[0]

def read_report(dev, address):
    req = make_packet(CMD_SCRIPT, bytes((address >> 8, address & 0xFF)))
    sent = dev.write(req)
    if sent != 64:
        raise IOError(f"Read request at {address} sent {sent}/64 bytes.")
    raw = bytes(dev.read(64, timeout_ms=1500))
    if len(raw) != 64 or raw[0] != REPORT_ID:
        raise IOError(f"Invalid/timeout response at address {address}: {raw[:8].hex(' ')}")
    if raw[1] != 0:
        return None, raw[1]
    n = raw[2]
    if n > 60:
        raise IOError(f"Invalid response payload length {n} at {address}.")
    return raw[3:3+n], 0

def read_script(dev, max_size=MEMORY_SIZE):
    data=bytearray()
    while len(data) < max_size:
        block, status = read_report(dev, len(data))
        if status:
            break
        if not block:
            break
        data.extend(block)
        if len(block) < MAX_DATA:
            break
    return bytes(data)

def write_script(dev, script: bytes, expected_live: bytes):
    """Compare two live reads against an explicitly chosen 512-byte baseline.
    Back up before writing; verify the full region afterward. Stop on any error."""
    if len(expected_live) != MEMORY_SIZE:
        raise RuntimeError("Selected baseline must be exactly 512 bytes.")
    if len(script) + 2 > MEMORY_SIZE:
        raise RuntimeError("Script plus EXIT markers exceeds device memory.")
    live = read_script(dev)
    second = read_script(dev)
    if len(live) != MEMORY_SIZE or live != second:
        raise RuntimeError("STOP: live memory reads are incomplete or disagree. No write sent.")
    backup_dir = Path.home() / "Downloads"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    backup = None
    for i in range(100):
        candidate = backup_dir / f"opensayo_prewrite_{stamp}_{i:02d}.bin"
        try:
            with candidate.open("xb") as f:
                f.write(live)
            backup = candidate
            break
        except FileExistsError:
            continue
    if backup is None or backup.read_bytes() != live:
        raise RuntimeError("STOP: unable to verify fresh backup. No write sent.")
    if live != expected_live:
        raise RuntimeError("STOP: current script differs from selected baseline. No write sent. Backup: " + str(backup))
    # Preserve untouched memory, including bytes after the new script.
    # v0.15 erroneously used b"\\\\xff\\\\xff" (ASCII backslash-x...)
    # instead of the two binary EXIT bytes 0xFF, 0xFF.
    target = bytearray(live)
    target[:len(script)] = script
    target[len(script):len(script)+2] = bytes((OP_EXIT, OP_EXIT))
    total = len(script) + 2
    writes_started = False
    try:
        for addr in range(0, total, MAX_DATA):
            chunk = bytes(target[addr:min(addr+MAX_DATA, total)])
            payload = bytes((addr >> 8, addr & 0xFF)) + chunk
            writes_started = True
            sent = dev.write(make_packet(CMD_SCRIPT, payload))
            if sent != 64:
                raise IOError(f"Write at {addr} sent {sent}/64 bytes.")
            raw = bytes(dev.read(64, timeout_ms=2000))
            if len(raw) != 64 or raw[0] != REPORT_ID or raw[1] != 0:
                raise IOError(f"Write acknowledgment failed at {addr}: {raw[:8].hex(' ')}")
            time.sleep(0.005)
        after = read_script(dev)
        if len(after) != MEMORY_SIZE:
            raise IOError(f"Readback length {len(after)} != {MEMORY_SIZE}.")
        if after != bytes(target):
            mismatch = [i for i, (got, want) in enumerate(zip(after, target)) if got != want]
            details = ", ".join(
                f"{i}: got {after[i]:02X}, expected {target[i]:02X}"
                for i in mismatch[:20]
            )
            raise IOError(f"Readback mismatch at {len(mismatch)} byte(s): {details}")
    except Exception as exc:
        raise RuntimeError(f"Write/readback failed (writes started: {writes_started}). "
                           f"DO NOT RETRY. Saved prewrite backup: {backup}. Details: {exc}") from exc
    return backup, after

def approved_default_project():
    """Return a generic, unconfigured 25-field startup form."""
    return blank_project()

class App:
    def __init__(self, root):
        self.root=root
        root.title(f"OpenSayo v{VERSION}")
        root.geometry("1040x850"); root.minsize(850,720)
        self.project=approved_default_project()
        self.field_definitions=copy.deepcopy(self.project["fields"])
        self.form_layout=copy.deepcopy(self.project["layout"])
        self._field_rows_ready=False
        self.form_preview_window=None
        self.form_designer_window=None
        try:self._form_preview_geometry=json.loads(UI_PREFS_PATH.read_text(encoding="utf-8")).get("preview_geometry","1240x820")
        except (OSError,ValueError,TypeError):self._form_preview_geometry="1240x820"
        self.workspace_kind="form_project"
        self.workspace_path=None
        self.freeform_standalone=""
        self.freeform_destination=1
        self._form_workspace_cache=None
        self._workspace_saved_snapshot=None
        self.baseline_path=None
        self._save_job=None; self._meter_job=None; self._loading=True; self.settings_window=None; self.about_window=None; self.help_window=None
        self.session_status=tk.StringVar(value="Session: loading")
        self.device_status=tk.StringVar(value="Key 1: not checked | Key 2: protocol pending")
        self.memory_status=tk.StringVar(value="Calculating memory…")
        self.key2_memory_status=tk.StringVar(value="Key 2: 0 / 468 bytes")
        self._freeform_sync=False
        self._editor_owner="form"
        self._editor_dirty=False
        self.endpoint=tk.IntVar(value=0)
        self.key2_endpoint=tk.IntVar(value=0)
        self._endpoint_guard=False
        self._accepted_key1_endpoint=0
        self.text_delay=tk.StringVar(value="15")
        self.action_delay=tk.StringVar(value="20")
        self.repeat_gap=tk.StringVar(value="15")
        self.fields=[]; self.field_vars=[]; self.nav_vars=[]
        self.format_vars=[];self.option_vars=[];self._format_widgets={};self._option_widgets={}
        self._typed_values={};self._date_values={};self._dropdown_values={};self._dropdown_controls={};self._format_previous={};self._format_sync=False
        self.dropdown_libraries={};self._dropdown_refreshing=False
        self.show_debug=tk.BooleanVar(value=False)
        try: _layout_prefs=json.loads(UI_PREFS_PATH.read_text(encoding="utf-8"))
        except (OSError,ValueError,TypeError): _layout_prefs={}
        self.layout_mode=tk.StringVar(value="2" if _layout_prefs.get("device_layout")=="2" else "8")
        self.scream_mode=tk.BooleanVar(value=bool(_layout_prefs.get("scream_mode",False)))
        self.device_bank=tk.StringVar(value="1")
        self.key2_bank=tk.StringVar(value="2")
        self.focused_key=tk.IntVar(value=1)
        self.eight_focused_key=tk.IntVar(value=1)
        self._capacity_warning_shown=False
        self._key2_flash_on=True
        self._key2_flash_job=None
        self._eight_flash_on=True
        self._eight_flash_job=None
        self._key_scripts={1:"",2:""}
        self._previous_key=1
        self._editor_swap=False
        self._last_valid_scripts={1:"",2:""}
        self._form_last_valid=None
        self._form_field_owners={}
        self._form_previous_values={}
        self._form_reverting=False
        self._form_edit_pending=False
        self.physical_key1=tk.StringVar(value="1")
        self.physical_key2=tk.StringVar(value="2")
        self._key_pref_loading=True
        self._load_key_preferences()
        self._build()
        # v1.11: original Step 41 Form/Macro Viewer/Freeform are the ONLY editors.
        # No separate eight-key editing tab: top script picker chooses destination.
        self._eight_workspace = None
        self._eight_busy = False
        self._eight_transfer_queue = __import__('queue').Queue()
        self._eight_transfer_token = None
        self.root.after(125, self._poll_eight_transfer)
        self.load_session()
        self._key_pref_loading=False
        self._loading=False
        # Generate directly from the authoritative Field View model. The legacy
        # readable-editor round trip loses Drop Down / Navigate / Skip metadata.
        self._sync_form_to_editor()
        self._last_valid_scripts[1]=self._key_scripts.get(1,"EXIT")
        self._render_key_previews()
        for v in self.field_vars+self.nav_vars+[self.text_delay,self.action_delay,self.repeat_gap,self.endpoint]:
            v.trace_add("write", self._changed)
        self._form_last_valid=self._form_snapshot()
        self._accepted_key1_endpoint=self.endpoint.get()
        self._form_previous_values={i:v.get() for i,v in enumerate(self.field_vars)}
        for i,v in enumerate(self.field_vars):
            v.trace_add("write",lambda *_,index=i:self._note_form_owner(index))
        for v in self.field_vars+self.format_vars+self.option_vars+[self.endpoint,self.key2_endpoint]:
            v.trace_add("write", self._form_changed)
        self.endpoint.trace_add("write",self._validate_endpoint_move)
        self.key2_endpoint.trace_add("write",self._validate_key2_endpoint_move)
        self._toggle_debug()
        self._update_form_fade()
        self._update_key_switch()
        self._refresh()
        self._workspace_saved_snapshot=self._workspace_snapshot()
        for v in (self.device_bank,self.key2_bank,self.physical_key1,self.physical_key2,self.focused_key):
            v.trace_add("write",self._key_preference_changed)
        self._field_rows_ready=True
        self._poll_assignment_status()
        self._poll_caps()
        self.root.protocol("WM_DELETE_WINDOW",self.close)

    def _load_key_preferences(self):
        """Independent of the form autosave: remember editor and device selections."""
        self._preferred_focused_key=1
        self._assignment_verified=False
        try:
            data=json.loads(KEY_PREFS_PATH.read_text(encoding="utf-8"))
            for name,var,allowed in (("device_bank",self.device_bank,{str(i) for i in range(1,9)}),
                    ("key2_bank",self.key2_bank,{str(i) for i in range(1,9)}|{"Off / Not loaded"}),
                    ("physical_key1",self.physical_key1,{str(i) for i in range(1,9)}),
                    ("physical_key2",self.physical_key2,{str(i) for i in range(1,9)})):
                value=str(data.get(name,var.get()))
                if value in allowed:var.set(value)
            self._preferred_focused_key=2 if data.get("focused_key")==2 else 1
            self.freeform_destination=2 if data.get("freeform_destination")==2 else 1
        except (OSError,ValueError,TypeError,json.JSONDecodeError):pass
        self.focused_key.set(self._preferred_focused_key if self.key2_bank.get().isdigit() else 1)
        self._previous_key=self.focused_key.get()

    def _save_key_preferences(self):
        if getattr(self,"_key_pref_loading",False):return
        data={"device_bank":self.device_bank.get(),"key2_bank":self.key2_bank.get(),
              "physical_key1":self.physical_key1.get(),"physical_key2":self.physical_key2.get(),
              "focused_key":self.focused_key.get(),"freeform_destination":self.freeform_destination}
        try:
            KEY_PREFS_PATH.parent.mkdir(parents=True,exist_ok=True)
            tmp=KEY_PREFS_PATH.with_suffix(".tmp")
            tmp.write_text(json.dumps(data,indent=2),encoding="utf-8")
            os.replace(tmp,KEY_PREFS_PATH)
        except OSError:pass

    def _key_preference_changed(self,*_):
        if self._loading or getattr(self,"_key_pref_loading",False):return
        self._assignment_verified=False
        self._save_key_preferences()
        self._update_assignment_warning()

    def _update_assignment_warning(self):
        if not hasattr(self,"assignment_warning"):return
        if getattr(self,"_assignment_verified",False):
            self.assignment_warning.pack_forget()
        else:
            if not self.assignment_warning.winfo_manager():
                self.assignment_warning.pack(fill="x",padx=8,pady=(1,3))
            self.assignment_warning.configure(text="Please verify key script assignments")

    def _poll_assignment_status(self):
        """Refresh USB presence without blocking Tk's event loop.

        HID enumeration may pause inside the Windows driver stack. Never perform
        it on the UI thread, and never call Tk from the background worker.
        """
        if not getattr(self, "_assignment_scan_busy", False):
            self._assignment_scan_busy = True
            self._assignment_scan_result = None

            def scan():
                try:
                    import hid
                    info = select_device(hid)
                    result = (bool(info), info.get("serial_number") if info else None)
                except Exception:
                    result = (False, None)
                self._assignment_scan_result = result

            threading.Thread(target=scan, daemon=True, name="OpenSayo-HID-presence").start()
        result = getattr(self, "_assignment_scan_result", None)
        if result is not None:
            self._assignment_scan_result = None
            self._assignment_scan_busy = False
            connected, serial = result
            if not connected:
                self._assignment_verified = False
            elif getattr(self, "_assignment_verified", False) and serial != getattr(self, "_verified_serial", None):
                self._assignment_verified = False
            self._update_assignment_warning()
        self.root.after(250, self._poll_assignment_status)

    def _build(self):
        style=ttk.Style()
        if "vista" in style.theme_names(): style.theme_use("vista")
        menubar=tk.Menu(self.root)
        filemenu=tk.Menu(menubar,tearoff=0)
        filemenu.add_command(label="New Form Project",command=lambda:self._workspace_new("form_project"))
        filemenu.add_command(label="New Freeform Macro",command=lambda:self._workspace_new("freeform"))
        filemenu.add_command(label="Open Project…",command=self._workspace_open)
        filemenu.add_separator()
        filemenu.add_command(label="Save Project",command=self._workspace_save)
        filemenu.add_command(label="Save Project As…",command=lambda:self._workspace_save(as_new=True))
        filemenu.add_separator()
        filemenu.add_command(label="Save Form Format…",command=self._export_form_format)
        filemenu.add_command(label="Load Form Format…",command=self._import_form_format)
        filemenu.add_separator()
        filemenu.add_command(label="Save Form Layout…",command=self._save_form_layout)
        filemenu.add_command(label="Load Form Layout…",command=self._load_form_layout)
        filemenu.add_command(label="Save Field List…",command=self._save_field_list)
        filemenu.add_command(label="Load Field List…",command=self._load_field_list)
        filemenu.add_separator()
        filemenu.add_command(label="Import Key 1 Script…",command=lambda:self._workspace_import_script(1))
        filemenu.add_command(label="Export Key 1 Script…",command=lambda:self._workspace_export_script(1))
        filemenu.add_separator()
        filemenu.add_command(label="Import Key 2 Script…",command=lambda:self._workspace_import_script(2))
        filemenu.add_command(label="Export Key 2 Script…",command=lambda:self._workspace_export_script(2))
        filemenu.add_separator()
        filemenu.add_command(label="Export Selected Script…",command=lambda:self._workspace_export_script(self.focused_key.get()))
        filemenu.add_separator()
        filemenu.add_command(label="Settings…",command=self.settings)
        filemenu.add_command(label="Exit",command=self.close)
        menubar.add_cascade(label="File",menu=filemenu)
        helpmenu=tk.Menu(menubar,tearoff=0)
        helpmenu.add_command(label="Quick Reference",command=self._show_help)
        helpmenu.add_separator()
        helpmenu.add_command(label="About OpenSayo…",command=self._show_about)
        menubar.add_cascade(label="Help",menu=helpmenu)
        self.root.config(menu=menubar)
        header=ttk.Frame(self.root,padding=(10,6));header.pack(fill="x")
        ttk.Label(header,text=f"OpenSayo v{VERSION}",font=("Segoe UI",18,"bold")).pack(side="left")
        ttk.Label(header,text="Form-linked Macro Viewer",foreground="#23784b").pack(side="left",padx=12)
        self.caps=tk.Label(self.root,text="CHECKING CAPS LOCK…",font=("Segoe UI",12,"bold"),padx=14,pady=9)
        self.caps.pack(fill="x",padx=12,pady=(0,8))
        # Device layout selection is presentation only; it never changes the USB target.
        mode_row=ttk.Frame(self.root,padding=(12,2,12,5));mode_row.pack(fill="x")
        ttk.Label(mode_row,text="Device layout:",font=("Segoe UI",10,"bold")).pack(side="left",padx=(0,8))
        ttk.Radiobutton(mode_row,text="2-Key",variable=self.layout_mode,value="2",command=self._switch_device_layout).pack(side="left",padx=5)
        ttk.Radiobutton(mode_row,text="8-Key",variable=self.layout_mode,value="8",command=self._switch_device_layout).pack(side="left",padx=5)
        ttk.Checkbutton(mode_row,text="I LIKE TO SCREAM",variable=self.scream_mode,command=self._on_scream_changed).pack(side="right",padx=8)
        self.workspace_label=ttk.Label(self.root,text="Form Project • complete application workspace",foreground="#666")
        self.workspace_label.pack(anchor="w",padx=12)
        # Preview18: explicit physical-key slots, with an optional second bank.
        toolbar=ttk.Frame(self.root,padding=(10,2));toolbar.pack(fill="x",padx=2,pady=2)
        self.two_key_toolbar=toolbar
        bankbar=ttk.LabelFrame(toolbar,text="Device Scripts",padding=5)
        bankbar.pack(side="left",fill="x",expand=True,padx=(0,5))
        assignments=ttk.LabelFrame(toolbar,text="Physical Key Assignments",padding=5)
        assignments.pack(side="left",fill="x",expand=True)
        slots=[str(i) for i in range(1,9)]
        bar=ttk.Frame(bankbar);bar.pack(anchor="center",pady=2)
        ttk.Label(bar,text="Key 1 Script:").pack(side="left")
        ttk.Combobox(bar,textvariable=self.device_bank,values=slots,state="readonly",width=3).pack(side="left",padx=3)
        ttk.Label(bar,text="Key 2 Script:").pack(side="left")
        ttk.Combobox(bar,textvariable=self.key2_bank,values=["Off / Not loaded"]+slots,state="readonly",width=7).pack(side="left",padx=3)
        self.key1_switch_label=tk.Label(bar,text="Key 1",font=("Segoe UI",9,"bold"),padx=5,cursor="hand2")
        self.key1_switch_label.pack(side="left")
        self.key1_switch_label.bind("<Button-1>",lambda e:self._select_key_button(1))
        self.key2_switch_label=tk.Label(bar,text="Key 2",font=("Segoe UI",9),padx=5,cursor="hand2")
        self.key2_switch_label.pack(side="left")
        self.key2_switch_label.bind("<Button-1>",lambda e:self._select_key_button(2))
        self.key2_bank.trace_add("write",lambda *_:self._refresh())
        actions=ttk.Frame(bankbar);actions.pack(anchor="center",pady=2)
        ttk.Button(actions,text="Import",command=lambda:self._workspace_import_script(self.focused_key.get())).pack(side="left",padx=2)
        ttk.Button(actions,text="Load Focused Key from Device",command=self._a22_device_load).pack(side="left",padx=2)
        ttk.Button(actions,text="Save Focused Key to Device",command=self._a22_device_save).pack(side="left",padx=2)
        self.assignment_warning=tk.Label(assignments,text="Please verify key script assignments",
                                         fg="#a10016",font=("Segoe UI",10,"bold"),anchor="center")
        self.assignment_warning.pack(fill="x",pady=(1,3))
        physical=ttk.Frame(assignments);physical.pack(anchor="center",pady=2)
        ttk.Label(physical,text="Physical Key 1:").pack(side="left")
        ttk.Combobox(physical,textvariable=self.physical_key1,values=slots,state="readonly",width=3).pack(side="left",padx=3)
        ttk.Label(physical,text="Physical Key 2:").pack(side="left")
        ttk.Combobox(physical,textvariable=self.physical_key2,values=slots,state="readonly",width=3).pack(side="left",padx=3)
        physical_actions=ttk.Frame(assignments);physical_actions.pack(anchor="center",pady=2)
        ttk.Button(physical_actions,text="Apply Key Assignments",command=self._a22_assign).pack(side="left",padx=3)
        ttk.Button(physical_actions,text="Detect Config",command=self.detect_device_configuration).pack(side="left",padx=3)
        # Eight-key script-slot selection is independent of two-key focus.
        self.eight_script_slot=tk.StringVar(value="0")
        self.eight_key_vars=[tk.StringVar(value="Not read") for _ in range(8)]
        self.eight_key_actual=[None]*8
        self.eight_slot_drafts={} 
        self.eight_key_status=tk.StringVar(value="Not read. Switching layout does not program hardware.")
        self.eight_focused_label=tk.StringVar(value="Script 0 selected (not loaded)")
        # Device Scripts strip, with the actual v1.11 selected-slot
        # editor and guarded writer underneath.  Do NOT use the old global F0
        # region as a substitute for an unverified independent slot read.
        self.eight_key_toolbar=ttk.LabelFrame(self.root,text="Device Scripts · 8-Key (2x4V RGB)",padding=7)
        eight_bar=ttk.Frame(self.eight_key_toolbar);eight_bar.pack(fill="x",pady=(1,5))
        picker_center=ttk.Frame(eight_bar);picker_center.pack(anchor="center")
        ttk.Label(picker_center,text="Key Script:").pack(side="left",padx=(0,7))
        self.eight_script_picker=ttk.Combobox(picker_center,textvariable=self.eight_script_slot,
                     values=[str(n) for n in range(64)],state="readonly",width=4)
        self.eight_script_picker.pack(side="left")
        eight_actions=ttk.Frame(self.eight_key_toolbar);eight_actions.pack(fill="x",pady=(0,2))
        self._eight_import_button=ttk.Button(eight_actions,text="Import Script",command=self._eight_import_focused)
        self._eight_import_button.pack(side="left",padx=3)
        self._eight_load_button=ttk.Button(eight_actions,text="Load Focused Key from Device",command=self._eight_load_focused)
        self._eight_load_button.pack(side="left",padx=3)
        self._eight_save_button=ttk.Button(eight_actions,text="Save Focused Key to Device",command=self._eight_save_focused)
        self._eight_save_button.pack(side="left",padx=3)
        ttk.Button(eight_actions,text="Device Management…",command=self._eight_device_management).pack(side="right",padx=3)
        ttk.Label(self.eight_key_toolbar,
                  text="Script 0–63 is the destination. Edit in the original Field View, Macro Viewer, or Freeform. "
                  "Load is a protected, read-only device test: invalid data cannot replace your editor.",
                  foreground="#555",wraplength=970).pack(anchor="w",pady=(2,0))
        self.eight_script_slot.trace_add("write",lambda *_:self._eight_slot_changed())
        if self.layout_mode.get()=="8":self._switch_device_layout()
        # Pack the fixed-height footer before expandable content: it must retain
        # its allotted height even when the window becomes short.
        footer=ttk.Frame(self.root,padding=(12,4,12,8))
        footer.pack(side="bottom",fill="x")
        self._capacity_footer=footer
        # Eight-key layout shows exactly ONE meter. It follows the selected
        # destination Script 0-7 and measures the CURRENT editing workspace,
        # i.e. the bytes Save Focused Key would actually transmit.
        self.eight_capacity_status=tk.StringVar(value="")
        self.eight_capacity_label=ttk.Label(footer,textvariable=self.eight_capacity_status)
        self.eight_meter_row=ttk.Frame(footer)
        self.eight_meter_title=tk.StringVar(value="Script 0")
        ttk.Label(self.eight_meter_row,textvariable=self.eight_meter_title,width=13).pack(side="left")
        self.eight_meter=tk.Canvas(self.eight_meter_row,width=170,height=13,bg="#272a30",highlightthickness=0)
        self.eight_meter.pack(side="left",padx=(4,9))
        self.eight_meter_label=tk.StringVar(value="0/2028 bytes")
        ttk.Label(self.eight_meter_row,textvariable=self.eight_meter_label).pack(side="left")
        self.eight_meter.bind("<Configure>",lambda e:self._update_eight_meter())
        self.eight_script_slot.trace_add("write",lambda *_:self._update_eight_meter())
        book=ttk.Notebook(self.root);book.pack(fill="both",expand=True,padx=8,pady=4)
        fields_tab=ttk.Frame(book)
        self.fields_tab=fields_tab
        book.add(fields_tab,text="Field View")
        self.book=book
        # Alpha18: offline text scratchpad for manual copy/paste into the official Sayo editor.
        # No assumption is made about the site's scripting language; no USB commands are sent.
        # The editor has its own scrollable body; capacity footer is outside the notebook.
        macro_outer=ttk.Frame(book)
        macro_outer.rowconfigure(0,weight=1); macro_outer.columnconfigure(0,weight=1)
        macro_canvas=tk.Canvas(macro_outer,highlightthickness=0)
        macro_scroll=ttk.Scrollbar(macro_outer,orient="vertical",command=macro_canvas.yview)
        macro_canvas.configure(yscrollcommand=macro_scroll.set)
        macro_canvas.grid(row=0,column=0,sticky="nsew")
        macro_scroll.grid(row=0,column=1,sticky="ns")
        self.macro_tab=ttk.Frame(macro_canvas,padding=12)
        macro_window=macro_canvas.create_window((0,0),window=self.macro_tab,anchor="nw")
        self.macro_tab.bind("<Configure>",lambda e:macro_canvas.configure(scrollregion=macro_canvas.bbox("all")))
        macro_canvas.bind("<Configure>",lambda e:macro_canvas.itemconfigure(macro_window,width=e.width))
        # Route wheel events from descendants to the containing page, except text widgets.
        macro_canvas.bind("<MouseWheel>",lambda e:(macro_canvas.yview_scroll(-int(e.delta/120),"units"),"break")[1])
        self.macro_outer=macro_outer
        book.add(macro_outer,text="Macro Viewer")
        self._build_macro_tab()
        def _macro_wheel(event):
            if self.book.select()==str(self.macro_outer):
                macro_canvas.yview_scroll(-int(event.delta/120),"units")
                return "break"
        def _bind_macro_wheel(widget):
            if isinstance(widget,(ttk.Combobox,tk.Text)):
                return
            widget.bind("<MouseWheel>",_macro_wheel,add="+")
            for child in widget.winfo_children():_bind_macro_wheel(child)
        _bind_macro_wheel(self.macro_tab)
        self._macro_canvas=macro_canvas

        # Freeform follows Finished Form Preview.
        self.freeform_tab=ttk.Frame(book,padding=10)
        ttk.Label(self.freeform_tab,text="Readable macro editor • type text or insert {TAB}, {ENTER}, and other actions",foreground="#555").pack(anchor="w",pady=(0,6))
        self.freeform_key_title=ttk.Label(self.freeform_tab,text="KEY 1 — ACTIVE",font=("Segoe UI",10,"bold"))
        self.freeform_key_title.pack(anchor="w")
        # Share the EXACT same timing variables as Macro Viewer: no conflicting
        # Freeform defaults or silently different script timings.
        waitbar=ttk.Frame(self.freeform_tab);waitbar.pack(fill="x",pady=(4,2))
        ttk.Label(waitbar,text="Wait (ms):").pack(side="left",padx=(4,3))
        ttk.Entry(waitbar,textvariable=self.insert_wait_ms,width=6).pack(side="left")
        ttk.Button(waitbar,text="Insert Wait",command=self._insert_freeform_wait).pack(side="left",padx=7)
        timings=ttk.Frame(self.freeform_tab);timings.pack(fill="x",pady=(0,4))
        for label,var in (("Key hold (ms)",self.macro_key_ms),
                          ("After navigation (ms)",self.macro_nav_ms),
                          ("Repeated key gap (ms)",self.macro_repeat_ms),
                          ("Dropdown opening (ms)",self.dropdown_open_ms)):
            ttk.Label(timings,text=label).pack(side="left",padx=(4,2))
            ttk.Entry(timings,textvariable=var,width=5).pack(side="left",padx=(0,7))
        ttk.Button(timings,text="Apply Timing to Key",command=self._apply_freeform_timing).pack(side="left",padx=5)
        self.freeform_timing_status=tk.StringVar(value="Timings are shared with Macro Viewer; applying never writes to a device.")
        ttk.Label(self.freeform_tab,textvariable=self.freeform_timing_status,foreground="#555").pack(anchor="w",pady=(0,4))
        self.freeform_text=tk.Text(self.freeform_tab,wrap="word",undo=True,font=("Consolas",10),height=6)
        self.freeform_text.pack(fill="both",expand=True,pady=(0,5))
        insertbar=ttk.Frame(self.freeform_tab)
        insertbar.pack(fill="x",pady=(0,5))
        ttk.Label(insertbar,text="Insert key:").pack(side="left")
        self._insert_key_choice=tk.StringVar(value="Tab")
        self._insert_keys=["Tab","Enter","ArrowDown","ArrowUp","ArrowLeft","ArrowRight","End","Home","Backspace","Delete","Escape","Space","PageDown","PageUp","CapsLock","L_Shift","R_Shift","L_Ctrl","R_Ctrl","L_Alt","R_Alt"]+[chr(i) for i in range(65,91)]+[str(i) for i in range(10)]
        ttk.Combobox(insertbar,textvariable=self._insert_key_choice,values=self._insert_keys,state="readonly",width=15).pack(side="left",padx=5)
        ttk.Button(insertbar,text="Insert Key",command=self._insert_freeform_key).pack(side="left",padx=5)
        ttk.Button(insertbar,text="Insert Tab",command=lambda:self._insert_freeform_key("Tab")).pack(side="left",padx=3)
        ttk.Button(insertbar,text="Insert Enter",command=lambda:self._insert_freeform_key("Enter")).pack(side="left",padx=3)
        ttk.Button(insertbar,text="Record Keys…",command=self._open_recorder).pack(side="right")
        ttk.Label(self.freeform_tab,text="Sayo macro — active key (read-only, selectable and copyable)").pack(anchor="w")
        self.freeform_other=tk.Text(self.freeform_tab,height=6,wrap="none",font=("Consolas",10),background="#f1f1f1")
        self.freeform_other.pack(fill="both",expand=True,pady=(0,6))
        self.freeform_other.configure(state="disabled")
        freeform_tools=ttk.Frame(self.freeform_tab);freeform_tools.pack(fill="x",pady=4,before=self.freeform_text)
        tools_top=ttk.Frame(freeform_tools);tools_top.pack(fill="x",anchor="w")
        tools_bottom=ttk.Frame(freeform_tools);tools_bottom.pack(fill="x",anchor="w",pady=(3,0))
        ttk.Button(tools_top,text="Apply Script",command=self._freeform_generate).pack(side="left",padx=3)
        ttk.Button(tools_top,text="Copy Sayo Macro",command=self._freeform_copy_sayo).pack(side="left",padx=3)
        ttk.Button(tools_top,text="Paste Sayo Macro",command=self._freeform_paste_sayo).pack(side="left",padx=3)
        ttk.Button(tools_bottom,text="Decode to Human-Readable",command=self._freeform_decode).pack(side="left",padx=3)
        freeform_site=tk.Label(tools_bottom,text="Open Sayo Website Compiler",fg="#1269bd",cursor="hand2",font=("Segoe UI",10,"underline"))
        freeform_site.pack(side="left",padx=4)
        freeform_site.bind("<Button-1>",lambda event:webbrowser.open("https://app.sayodevice.com/"))
        self.freeform_other.bind("<Control-v>",lambda e:(self._freeform_paste_sayo(),"break")[1])
        self.freeform_other.bind("<Control-V>",lambda e:(self._freeform_paste_sayo(),"break")[1])
        self._freeform_imported_raw=None
        self.freeform_readable=self.freeform_text
        
        self.freeform_text.bind("<Tab>",lambda e:(self._insert_freeform_key("Tab"),"break")[1])
        self.freeform_text.bind("<Control-Return>",lambda e:(self._insert_freeform_key("Enter"),"break")[1])
        self.freeform_text.bind("<<Modified>>",self._freeform_modified,add="+")
        self.macro_text.bind("<<Modified>>",lambda e:self.root.after_idle(self._freeform_from_macro),add="+")
        self.root.after_idle(self._freeform_from_macro)
        self.form_preview_tab=ttk.Frame(book,padding=10)
        book.add(self.freeform_tab,text="Freeform")
        # The standalone Freeform workspace is not a Form Project tab.
        book.hide(self.freeform_tab)
        self.debug_tab=ttk.Frame(book,padding=6)
        self.debug_book=ttk.Notebook(self.debug_tab)
        self.debug_book.pack(fill="both",expand=True)
        # Debug panels must be children of their actual containing notebook.
        self.testing_tab=ttk.Frame(self.debug_book,padding=6)
        self.testing_book=ttk.Notebook(self.testing_tab)
        self.testing_book.pack(fill="both",expand=True)
        preview_tab=ttk.Frame(self.testing_book,padding=10)
        test_tab=ttk.Frame(self.testing_book,padding=10)
        self.testing_book.add(preview_tab,text="Compiled Macro")
        self.testing_book.add(test_tab,text="Keyboard Test")
        self.debug_book.add(self.testing_tab,text="Testing Tools")
        self.form_designer_tab=ttk.Frame(self.debug_book,padding=8)
        self.debug_book.add(self.form_designer_tab,text="Form Designer")
        self.diagnostics_tab=ttk.Frame(book,padding=12)
        self.diag_tab=ttk.Frame(self.diagnostics_tab,padding=12)
        # Consolidated into Diagnostics selector below
        ttk.Label(self.diag_tab,text="READ-ONLY DIAGNOSTIC • Experimental address scan • Does not program either key",font=("Segoe UI",10,"bold")).pack(anchor="w",pady=6)
        ttk.Label(self.diag_tab,text="Compare existing diagnostic JSON snapshots. No new captures or device reads are needed.",wraplength=750,justify="left").pack(anchor="w",pady=8)
        ttk.Label(self.diag_tab,text="New exploratory device scans are disabled in Alpha 7. Review previously saved snapshots only.",foreground="#995500",wraplength=750).pack(anchor="w",pady=7)
        ttk.Button(self.diag_tab,text="Compare two diagnostic snapshots…",command=self.compare_key2_snapshots).pack(anchor="w",pady=7)
        self.diag_log=tk.Text(self.diag_tab,height=20,wrap="word",font=("Consolas",10))
        self.diag_log.pack(fill="both",expand=True,pady=8)
        self.diag_log.insert("end","No device commands are sent until you press Capture.\\n")
        self.offline_tab=ttk.Frame(self.diagnostics_tab,padding=12)
        # Consolidated into Diagnostics selector below
        self.protocol_tab=ttk.Frame(self.diagnostics_tab,padding=12)
        # Consolidated into Diagnostics selector below
        ttk.Label(self.protocol_tab,text="OFFLINE • Evidence-labeled command families • NO USB writes",font=("Segoe UI",10,"bold")).pack(anchor="w",pady=5)
        ttk.Label(self.protocol_tab,text="Select your existing captures (especially Q7, Q7M4, Q7M5). Alpha 5 compares text changes and header deltas offline; no USB writes.",wraplength=780,justify="left").pack(anchor="w",pady=5)
        ttk.Button(self.protocol_tab,text="Decode existing captures…",command=self.decode_protocol).pack(anchor="w",pady=6)
        ttk.Button(self.protocol_tab,text="Export decoder report…",command=self.export_protocol_report).pack(anchor="w",pady=6)
        self.protocol_log=tk.Text(self.protocol_tab,height=22,wrap="none",font=("Consolas",9))
        self.protocol_log.pack(fill="both",expand=True,pady=5)
        self.protocol_log.insert("end","Select your existing captures to inspect. No device connection required.\n")
        ttk.Label(self.offline_tab,text="OFFLINE CAPTURE ANALYSIS — no keypad connection or new recording needed",font=("Segoe UI",10,"bold")).pack(anchor="w",pady=5)
        ttk.Label(self.offline_tab,text="Choose one or two existing .pcapng captures. The tool lists outgoing HID reports and command-aligned byte differences. It does NOT infer safe write commands.",wraplength=780,justify="left").pack(anchor="w",pady=5)
        ttk.Button(self.offline_tab,text="Analyze saved capture(s)…",command=self.analyze_pcaps).pack(anchor="w",pady=6)
        ttk.Button(self.offline_tab,text="Export analysis to text…",command=self.export_pcap_analysis).pack(anchor="w",pady=6)
        self.pcap_log=tk.Text(self.offline_tab,height=22,wrap="none",font=("Consolas",9))
        self.pcap_log.pack(fill="both",expand=True,pady=5)
        self.pcap_log.insert("end","Choose existing USBPcap .pcapng files to begin.\n")
        self.memory_tab=ttk.Frame(self.diagnostics_tab,padding=12)
        # Consolidated into Diagnostics selector below
        ttk.Label(self.memory_tab,text="OFFLINE SOURCE AUDIT • no USB commands or device connection",font=("Segoe UI",10,"bold")).pack(anchor="w",pady=5)
        ttk.Label(self.memory_tab,text="Audit the existing Key 1 memory layout and boundary assumptions. Optionally compare previously saved diagnostic JSON snapshots. No new captures or hardware tests.",wraplength=790,justify="left").pack(anchor="w",pady=5)
        ttk.Button(self.memory_tab,text="Run source-only memory audit",command=self.run_memory_audit).pack(anchor="w",pady=5)
        ttk.Button(self.memory_tab,text="Audit with existing snapshot JSON files (optional)…",command=self.run_memory_audit_snapshots).pack(anchor="w",pady=5)
        ttk.Button(self.memory_tab,text="Export memory audit…",command=self.export_memory_audit).pack(anchor="w",pady=5)
        self.memory_log=tk.Text(self.memory_tab,height=21,wrap="word",font=("Consolas",9))
        self.memory_log.pack(fill="both",expand=True,pady=6)
        self.memory_log.insert("end","Click Run source-only memory audit. No device is accessed.\n")
        self.readback_tab=ttk.Frame(self.diagnostics_tab,padding=12)
        ttk.Label(self.readback_tab,text="KEY 2 READBACK EVIDENCE — OFFLINE ONLY",font=("Segoe UI",10,"bold")).pack(anchor="w",pady=5)
        ttk.Label(self.readback_tab,text="Examine existing captures for Key 2 readback evidence. This cannot contact or program the keypad. It will not invent a read command.",wraplength=770,justify="left").pack(anchor="w",pady=5)
        ttk.Button(self.readback_tab,text="Assess existing captures…",command=self.assess_readback).pack(anchor="w",pady=5)
        ttk.Button(self.readback_tab,text="Export assessment…",command=self.export_readback).pack(anchor="w",pady=5)
        self.readback_log=tk.Text(self.readback_tab,height=22,wrap="word",font=("Consolas",9))
        self.readback_log.pack(fill="both",expand=True,pady=5)
        self.readback_log.insert("end","Select your existing Q7 captures to assess evidence. No new recordings or hardware tests required.\n")
        # Alpha 10: live device readback baseline; only known F0 addresses 0..511.
        self.live_tab=ttk.Frame(self.diagnostics_tab,padding=12)
        ttk.Label(self.live_tab,text="LIVE READ-ONLY DEVICE BASELINE — KNOWN KEY 1 REGION ONLY",font=("Segoe UI",10,"bold")).pack(anchor="w",pady=5)
        ttk.Label(self.live_tab,text="Enumerates the device, then reads the established Key 1 region twice and checks consistency. No Key 2 address guesses, scans, writes or packet replay. This does not discover Key 2 readback.",wraplength=790,justify="left").pack(anchor="w",pady=5)
        ttk.Button(self.live_tab,text="Run known-safe live readback (Key 1 only)…",command=self.live_readback).pack(anchor="w",pady=6)
        ttk.Button(self.live_tab,text="Save diagnostic report…",command=self.export_live_readback).pack(anchor="w",pady=6)
        self.live_log=tk.Text(self.live_tab,height=20,wrap="word",font=("Consolas",10))
        self.live_log.pack(fill="both",expand=True,pady=6)
        self.live_log.insert("end","No device access yet. Explicit confirmation is required.\n")
        self.mapping_tab=ttk.Frame(self.diagnostics_tab)
        ttk.Label(self.mapping_tab,text="Key assignments: documented 0x16 READ, keys 0 and 1 only; four requests total.",wraplength=700).pack(anchor="w",pady=5)
        ttk.Button(self.mapping_tab,text="Read two key assignments twice (no writes)",command=self.live_key_mapping).pack(anchor="w",pady=5)
        self.mapping_log=tk.Text(self.mapping_tab,height=22,wrap="word",font=("Consolas",10))
        self.mapping_log.pack(fill="both",expand=True,pady=5)
        self.mapping_log.insert("end","No requests sent. Alpha 11 retains raw response bytes even if checksum validation fails. Protocol is unverified on O2L V2.\n")
        self.shared_tab=ttk.Frame(self.diagnostics_tab,padding=12)
        ttk.Label(self.shared_tab,text="ALPHA 13 — SHARED 512-BYTE SCRIPT INVESTIGATION",font=("Segoe UI",10,"bold")).pack(anchor="w",pady=5)
        ttk.Label(self.shared_tab,text="Reads ONLY the established 0..511 region twice, checks stability, then inspects the bytes for possible boundaries and references. This cannot prove that Key 2 shares the region. No unknown addresses or device writes.",wraplength=790,justify="left").pack(anchor="w",pady=5)
        ttk.Button(self.shared_tab,text="Read known 512 bytes twice and inspect…",command=self.run_shared_memory).pack(anchor="w",pady=5)
        ttk.Button(self.shared_tab,text="Save analysis report…",command=self.export_shared_memory).pack(anchor="w",pady=5)
        self.shared_log=tk.Text(self.shared_tab,height=24,wrap="none",font=("Consolas",9))
        self.shared_log.pack(fill="both",expand=True,pady=5)
        self.shared_log.insert("end","Awaiting explicit read-only inspection.\n")
        self.crosscheck_tab=ttk.Frame(self.diagnostics_tab,padding=12)
        ttk.Label(self.crosscheck_tab,text="KEY ASSIGNMENT CROSS-CHECK — OFFLINE",font=("Segoe UI",10,"bold")).pack(anchor="w",pady=5)
        ttk.Label(self.crosscheck_tab,text="Compare Alpha 11's stable key-index responses against existing website configuration evidence. No device connection, no new captures, no writes.",wraplength=790).pack(anchor="w",pady=5)
        ttk.Button(self.crosscheck_tab,text="Analyze existing Alpha 11 responses",command=self.run_crosscheck).pack(anchor="w",pady=5)
        self.crosscheck_log=tk.Text(self.crosscheck_tab,height=23,wrap="word",font=("Consolas",9))
        self.crosscheck_log.pack(fill="both",expand=True,pady=5)
        self.crosscheck_log.insert("end","Click Analyze to compare the previously collected responses.\n")
        # Alpha 14: controlled comparison of physical-key assignments to script slots.
        self.assignment_compare_tab=ttk.Frame(self.diagnostics_tab,padding=12)
        ttk.Label(self.assignment_compare_tab,text="ALPHA 14 — SCRIPT ASSIGNMENT COMPARATOR",font=("Segoe UI",10,"bold")).pack(anchor="w",pady=5)
        ttk.Label(self.assignment_compare_tab,text="Change the assignment in the OFFICIAL website. This tool only reads the two existing key assignment records (0x16) twice, then compares snapshots. No writes or Save commands from OpenSayo.",wraplength=790,justify="left").pack(anchor="w",pady=5)
        assignbar=ttk.Frame(self.assignment_compare_tab);assignbar.pack(fill="x",pady=5)
        ttk.Label(assignbar,text="Test label:").pack(side="left")
        self.assignment_label=tk.StringVar(value="A — both keys assigned Script 1")
        ttk.Entry(assignbar,textvariable=self.assignment_label,width=45).pack(side="left",padx=6)
        ttk.Button(assignbar,text="Capture both keys (read-only)",command=self.capture_assignment_comparison).pack(side="left",padx=4)
        ttk.Button(assignbar,text="Export comparison…",command=self.export_assignment_comparison).pack(side="left",padx=4)
        self.assignment_compare_log=tk.Text(self.assignment_compare_tab,height=24,wrap="none",font=("Consolas",9))
        self.assignment_compare_log.pack(fill="both",expand=True,pady=6)
        self.assignment_compare_log.insert("end","Step 1: In the official Sayo website, assign BOTH physical keys to Script 1.\nStep 2: Label A and click Capture.\nStep 3: Assign ONLY physical Key 2 to Script 2. Label B, capture again.\nStep 4: Repeat for Script 3 and beyond. Export the report.\n\nNo device writes are performed by this tool.\n")
        self.assignment_snapshots=[]
        # Alpha 15: known-region read-only comparisons across manual website changes.
        self.bank_tab=ttk.Frame(self.diagnostics_tab,padding=12)
        ttk.Label(self.bank_tab,text="ALPHA 16 — F0 PERSISTENCE INVESTIGATOR (READ ONLY)",font=("Segoe UI",10,"bold")).pack(anchor="w",pady=5)
        ttk.Label(self.bank_tab,text="Read the same verified F0 region before/after website script edits and after reconnect. Capture does NOT identify a permanent bank. No new commands or writes.",wraplength=790,justify="left").pack(anchor="w",pady=5)
        bankbar=ttk.Frame(self.bank_tab);bankbar.pack(fill="x",pady=5)
        ttk.Label(bankbar,text="Test label:").pack(side="left")
        self.bank_label=tk.StringVar(value="A — Script 8 O before reconnect")
        ttk.Entry(bankbar,textvariable=self.bank_label,width=42).pack(side="left",padx=6)
        ttk.Button(bankbar,text="Capture F0 region twice",command=self.capture_bank_snapshot).pack(side="left",padx=4)
        ttk.Button(bankbar,text="Export comparison…",command=self.export_bank_comparison).pack(side="left",padx=4)
        ttk.Button(self.bank_tab,text="Clear stored snapshots",command=self.clear_bank_snapshots).pack(anchor="w",pady=3)
        self.bank_log=tk.Text(self.bank_tab,height=24,wrap="none",font=("Consolas",9))
        self.bank_log.pack(fill="both",expand=True,pady=6)
        self.bank_log.insert("end","Capture A before unplug, B after unplug/reconnect, C after opening and closing official website WITHOUT editing, D after editing Script 8 O to P, E after restoring P to O. Disconnect website before each capture. Keep key assignments unchanged. Reads only established F0 addresses 0..511 twice.\n")
        self.bank_snapshots=[]
        # Alpha 7: one Diagnostics tab replaces four old investigation tabs.
        # Existing tools and reports are preserved, but only one tool is visible.
        self.testing_book.add(self.diagnostics_tab,text="Diagnostics")
        bar=ttk.Frame(self.diagnostics_tab)
        bar.pack(fill="x",pady=(0,8))
        ttk.Label(bar,text="Tool:").pack(side="left",padx=(0,8))
        self.diagnostic_choice=tk.StringVar(value="F0 Persistence Investigator (Alpha 16)")
        self.diagnostic_views={
            "F0 Persistence Investigator (Alpha 16)":self.bank_tab,
            "Script Assignment Comparator (Alpha 14)":self.assignment_compare_tab,
            "Live Device Readback (Key 1 only)":self.live_tab,
            "Shared Script Memory Inspector (live, read-only)":self.shared_tab,
            "Key Assignment Cross-Check (offline)":self.crosscheck_tab,
            "Key Assignments — Raw Response (experimental)":self.mapping_tab,
            "Memory Layout Audit (offline)":self.memory_tab,
            "Key 2 Readback Evidence (offline)":self.readback_tab,
            "Key 2 Evidence Decoder (offline)":self.protocol_tab,
            "Saved USB Capture Inspector (offline)":self.offline_tab,
            "Legacy Key 2 Snapshot Tools (device reads)":self.diag_tab,
        }
        picker=ttk.Combobox(bar,textvariable=self.diagnostic_choice,
                            values=list(self.diagnostic_views),state="readonly",width=45)
        picker.pack(side="left",fill="x",expand=True)
        picker.bind("<<ComboboxSelected>>",lambda event:self._show_diagnostic())
        ttk.Label(self.diagnostics_tab,text="Key 2 writes disabled. Offline tools do not contact the keypad.",foreground="#666").pack(anchor="w",pady=(0,6))
        self._show_diagnostic()
        self._build_definitions_tab()
        self._build_concepts_tab()
        self._build_form_designer()
        # Reparent the existing Dropdowns workspace once, preserving its widgets and callbacks.
        # Tk cannot reparent an existing frame; it is created under Debug at source.
        book.add(self.debug_tab,text="Debug")
        book.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        fields_tab.rowconfigure(1,weight=1);fields_tab.columnconfigure(0,weight=1)
        canvas=tk.Canvas(fields_tab,highlightthickness=0)
        sb=ttk.Scrollbar(fields_tab,orient="vertical",command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        canvas.grid(row=1,column=0,sticky="nsew");sb.grid(row=1,column=1,sticky="ns")
        inside=ttk.Frame(canvas,padding=8)
        inside.bind("<Configure>",lambda e:canvas.configure(scrollregion=canvas.bbox("all")))
        win=canvas.create_window((0,0),window=inside,anchor="nw")
        canvas.bind("<Configure>",lambda e:canvas.itemconfigure(win,width=e.width))
        # Never bind the form wheel globally: it also scrolls independent dialogs.
        def _form_wheel(event):
            if book.index(book.select()) == 0:
                canvas.yview_scroll(-int(event.delta/120),"units")
                return "break"
        canvas.bind("<MouseWheel>",_form_wheel)
        inside.bind("<MouseWheel>",_form_wheel)
        endpoint_row=ttk.Frame(fields_tab,padding=(10,4))
        endpoint_row.grid(row=0,column=0,columnspan=2,sticky="ew")
        choices=[f"{i+1:02d}. {name}" for i,name in enumerate([f["name"] for f in self.field_definitions])]
        self.endpoint_choice=tk.StringVar()
        self.key2_endpoint_choice=tk.StringVar()
        self.endpoint_labels={}
        for row,label,var,attr,handler in (
            (0,"Key 1 endpoint:",self.endpoint_choice,"endpoint_picker",self._endpoint_from_dropdown),
            (1,"Key 2 endpoint:",self.key2_endpoint_choice,"key2_endpoint_picker",self._key2_endpoint_from_dropdown)):
            endpoint_label=ttk.Label(endpoint_row,text=label,font=("Segoe UI",10,"bold"),width=17)
            endpoint_label.grid(row=row,column=0,sticky="w",pady=2)
            self.endpoint_labels[row]=endpoint_label
            picker=ttk.Combobox(endpoint_row,textvariable=var,values=choices,state="readonly",width=33)
            picker.grid(row=row,column=1,sticky="w",padx=6,pady=2)
            picker.bind("<<ComboboxSelected>>",handler)
            setattr(self,attr,picker)
        self.endpoint.trace_add("write",self._endpoint_sync_dropdown)
        self.key2_endpoint.trace_add("write",self._endpoint_sync_dropdown)
        self._endpoint_sync_dropdown()
        ttk.Button(endpoint_row,text="Open Form View ↗",command=self.open_form_preview).grid(row=0,column=2,rowspan=2,padx=14,sticky="w")
        ttk.Checkbutton(endpoint_row,text="Use Caps Lock at macro start/end (requires Caps Lock OFF initially)",variable=self.use_caps_lock,command=self._form_changed).grid(row=2,column=0,columnspan=3,sticky="w",pady=(4,0))
        for col,title in ((0,"Use"),(1,"Field"),(2,"Value / Action"),(3,"Format"),(4,"Options"),(5,"Navigate")):
            ttk.Label(inside,text=title,font=("Segoe UI",10,"bold")).grid(row=1,column=col,sticky="w",padx=5,pady=6)
        # Compact fixed-width controls; do not stretch the input boxes across the window.
        inside.columnconfigure(2,weight=0)
        inside.columnconfigure(3,weight=0)
        inside.columnconfigure(4,weight=0)
        self._form_inside=inside
        self._rebuild_field_rows(self.field_definitions)
        self._build_dropdown_tab(book)
        self.debug_book.insert(0,self.form_designer_tab)
        self.debug_book.insert(1,self.dropdowns_tab)
        self.debug_book.insert(2,self.definitions_tab)
        self.debug_book.insert(3,self.concepts_tab)
        self.debug_book.insert(4,self.testing_tab)
        book.forget(self.debug_tab)
        book.add(self.debug_tab,text="Debug")
        note=ttk.Label(fields_tab,text="Uncheck Use to show a label only and suppress its field action; its Tab position stays unchanged. No trailing Tab at the endpoint. Date actions depend on your definitions.",foreground="#555",wraplength=640,justify="left")
        note.grid(row=2,column=0,columnspan=2,sticky="ew",padx=10,pady=6)
        fields_tab.bind("<Configure>",lambda e:note.configure(wraplength=max(260,e.width-40)))
        ttk.Label(preview_tab,text="Compiled Macro: read-only bytecode view for device-write troubleshooting.",wraplength=800).pack(anchor="w",pady=(0,5))
        ttk.Button(preview_tab,text="Refresh Compiled Macro",command=self._refresh).pack(anchor="w",pady=(0,5))
        self.preview=tk.Text(preview_tab,font=("Consolas",10),wrap="none")
        self.preview.pack(fill="both",expand=True)
        self.preview.insert("1.0","Compiled macro will appear here when available.\n")
        ttk.Label(test_tab,text="Click Start Keyboard Test, then type with your normal keyboard or Sayo keypad. This is not a full form simulation.",wraplength=900).pack(anchor="w",pady=6)
        self.test_status=tk.StringVar(value="Not focused — press Start Keyboard Test")
        self.test_last=tk.StringVar(value="Last key: none")
        test_tools=ttk.Frame(test_tab);test_tools.pack(fill="x",pady=4)
        ttk.Button(test_tools,text="Start Keyboard Test",command=self._start_keyboard_test).pack(side="left",padx=3)
        ttk.Label(test_tools,textvariable=self.test_status).pack(side="left",padx=12)
        ttk.Label(test_tools,textvariable=self.test_last).pack(side="right",padx=8)
        self.test=tk.Text(test_tab,font=("Consolas",12),height=9,insertwidth=2)
        self.test.pack(fill="both",expand=True)
        self.test.bind("<FocusIn>",lambda e:self.test_status.set("Listening — input focused"))
        self.test.bind("<FocusOut>",lambda e:self.test_status.set("Not focused — press Start Keyboard Test"))
        self.test.bind("<KeyPress>",self._debug_keypress,add="+")
        self.test.configure(takefocus=True)
        self.debug_book.bind("<<NotebookTabChanged>>",self._debug_tab_changed,add="+")
        self.test_log=tk.Text(test_tab,font=("Consolas",9),height=6,wrap="none",state="disabled")
        self.test_log.pack(fill="x",pady=(7,3))
        clearrow=ttk.Frame(test_tab);clearrow.pack(fill="x")
        ttk.Button(clearrow,text="Clear Text",command=lambda:self.test.delete("1.0","end")).pack(side="left",padx=3)
        ttk.Button(clearrow,text="Clear Event Log",command=self._clear_test_log).pack(side="left",padx=3)
        # Compact per-key capacity meters, with counts in the labels alongside them.
        self._boss_values=(0,0)
        self.capacity_row=ttk.Frame(footer)
        self.capacity_row.pack(anchor="w",pady=(4,3))
        self.boss_bars={}
        for key in (1,2):
            title=ttk.Label(self.capacity_row,text=f"Key {key}",width=6)
            title.grid(row=key-1,column=0,sticky="w",pady=2)
            if not hasattr(self,"_capacity_titles"):self._capacity_titles={}
            self._capacity_titles[key]=title
            meter=tk.Canvas(self.capacity_row,width=125,height=13,bg="#272a30",highlightthickness=0)
            meter.grid(row=key-1,column=1,sticky="w",padx=(5,8),pady=2)
            meter.bind("<Configure>",lambda e:self._draw_boss_bar())
            self.boss_bars[key]=meter
            value_label=tk.StringVar(value="0/468 bytes")
            meter_label=ttk.Label(self.capacity_row,textvariable=value_label,width=32)
            meter_label.grid(row=key-1,column=2,sticky="w")
            if not hasattr(self,"_capacity_value_widgets"):self._capacity_value_widgets={}
            self._capacity_value_widgets[key]=meter_label
            if not hasattr(self,"_meter_labels"):self._meter_labels={}
            self._meter_labels[key]=value_label
        self.session_status_label=ttk.Label(footer,textvariable=self.session_status,foreground="#555")
        self.session_status_label.pack(anchor="w")
        self._sync_layout_details()
        device_tab=ttk.Frame(self.testing_book,padding=16)
        self.testing_book.add(device_tab,text="Device Programming")
        ttk.Label(device_tab,text="Key 1 — guarded device programming",font=("Segoe UI",13,"bold")).pack(anchor="w",pady=(0,8))
        ttk.Label(device_tab,text="Detect, back up, and verify a baseline before programming. Key 2 writes remain disabled.",wraplength=750).pack(anchor="w",pady=(0,10))
        bottom=ttk.Frame(device_tab,padding=(0,4,0,8));bottom.pack(fill="x")
        ttk.Button(bottom,text="Detect Keypad (read-only)",command=self.detect).pack(side="left",padx=3)
        ttk.Button(bottom,text="Backup Device (read-only)",command=self.backup).pack(side="left",padx=3)
        ttk.Button(bottom,text="Select Verified Baseline…",command=self.select_baseline).pack(side="left",padx=3)
        ttk.Button(bottom,text="Program Key 1 (guarded)",command=self.write_device).pack(side="right",padx=3)
        ttk.Label(device_tab,textvariable=self.device_status,foreground="#555",padding=(0,8,0,8)).pack(anchor="w")
        ttk.Label(device_tab,text="Device identification (read-only)",font=("Segoe UI",11,"bold")).pack(anchor="w",pady=(10,3))
        self.device_identity=tk.StringVar(value="Not scanned. Click Detect Device Configuration.")
        ttk.Label(device_tab,textvariable=self.device_identity,justify="left",wraplength=780).pack(anchor="w")
        ttk.Button(device_tab,text="Detect Device Configuration",command=self.detect_device_configuration).pack(anchor="w",pady=(8,0))

    def _remember_active_input(self,i):
        mode=self.format_vars[i].get()
        if mode=="Text":self._typed_values[i]=self.field_vars[i].get()
        elif mode=="Date" and self.option_vars[i].get()=="MM/DD/YY":
            self._date_values[i]=self.field_vars[i].get()

    def _validate_date_blur(self,i):
        if self._loading or self.format_vars[i].get()!="Date" or self.option_vars[i].get()!="MM/DD/YY":return True
        raw=self.field_vars[i].get().strip()
        if not raw:
            self._date_values[i]=""
            return True
        try:
            from datetime import datetime
            formats=("%m/%d/%Y","%m/%d/%y","%d/%m/%Y","%d/%m/%y","%d %b %Y","%d %B %Y","%m %d %Y")
            result=None
            for fmt in formats:
                try:
                    result=datetime.strptime(raw,fmt).strftime("%m/%d/%y")
                    break
                except ValueError:pass
            if result is None:raise ValueError("Invalid date")
            self._date_values[i]=result
            self.field_vars[i].set(result)
            self._form_entries[i].configure(bg="#ffffff")
            return True
        except ValueError:
            # Restore last accepted date instead of leaving invalid text behind.
            previous=self._date_values.get(i,"")
            self.field_vars[i].set(previous if valid_date(previous) else "")
            self._form_entries[i].configure(bg="#ffffff")
            return False

    def _dropdown_value_changed(self,i):
        self._dropdown_values[i]=self._dropdown_controls[i].get()
        if self.format_vars[i].get()=="Drop Down":self.field_vars[i].set(self._dropdown_values[i])

    def _update_format_row(self,i):
        if i not in self._option_widgets or self._format_sync:return
        mode=self.format_vars[i].get()
        previous=self._format_previous.get(i,mode)
        self._format_sync=True
        try:
            if previous!=mode:
                prior=self.field_vars[i].get()
                if previous=="Text":self._typed_values[i]=prior
                elif previous=="Date" and self.option_vars[i].get()=="MM/DD/YY":self._date_values[i]=prior
                elif previous=="Drop Down":self._dropdown_values[i]=prior
                self._format_previous[i]=mode
                if mode=="Text":self.field_vars[i].set(self._typed_values.get(i,""))
                elif mode=="Date":
                    self.option_vars[i].set(getattr(self,"_date_option_memory",{}).get(i,"MM/DD/YY"))
                    self.field_vars[i].set(self._date_values.get(i,""))
                elif mode=="Drop Down":
                    self.option_vars[i].set(getattr(self,"_dropdown_list_memory",{}).get(i,""))
                    self.field_vars[i].set(self._dropdown_values.get(i,""))
                else:self.field_vars[i].set("")
            widget=self._option_widgets[i]
            option=self.option_vars[i].get()
            if mode=="Date":
                widget.configure(values=["Blank","MM/DD/YY","Today's Date"],state="readonly")
                if option not in ("Blank","MM/DD/YY","Today's Date"):
                    self.option_vars[i].set("MM/DD/YY");option="MM/DD/YY"
                if option=="MM/DD/YY":
                    self.field_vars[i].set(self._date_values.get(i,""))
                else:
                    if previous==mode and self._form_entries[i].focus_get()==self._form_entries[i]:
                        self._date_values[i]=self.field_vars[i].get()
                    self.field_vars[i].set("")
            elif mode=="Drop Down":
                widget.configure(values=sorted(self.dropdown_libraries),state="readonly")
                values=self.dropdown_libraries.get(option,[])
                drop=self._dropdown_controls[i]
                drop.configure(values=values)
                # The visible combobox is authoritative while editing. Do not
                # erase a live selection using a stale cached dropdown value.
                chosen=drop.get() if previous==mode and not self._loading else self._dropdown_values.get(i,"")
                if chosen not in values:chosen=""
                self._dropdown_values[i]=chosen
                drop.set(chosen)
                self.field_vars[i].set(chosen)
            else:widget.configure(values=[],state="disabled")
            if mode=="Date":
                if not hasattr(self,"_date_option_memory"):self._date_option_memory={}
                self._date_option_memory[i]=self.option_vars[i].get()
            if mode=="Drop Down":
                if not hasattr(self,"_dropdown_list_memory"):self._dropdown_list_memory={}
                self._dropdown_list_memory[i]=self.option_vars[i].get()
            if mode in ("Text","Skip"):
                widget.grid_remove()
            else:widget.grid()
            self._sync_form_value_visibility(i)
            if self.enabled_vars[i].get() and (mode=="Text" or (mode=="Date" and option=="MM/DD/YY")):
                self._form_entries[i].configure(state="normal")
        finally:self._format_sync=False
        # Reconcile after Tk variable traces and key-ownership refreshes have finished.
        # This avoids an invisible-value Date field retaining a stale gridded Entry.
        self.root.after_idle(lambda idx=i:self._sync_form_value_visibility(idx))
        if self._form_last_valid is not None:
            self._form_edit_pending=True
            self._schedule_form_fade()

    def _date_option_selected(self,i):
        """Synchronize Date option and visibility after the combobox commits selection."""
        self.root.after_idle(lambda idx=i:self._apply_date_option_selection(idx))

    def _apply_date_option_selection(self,i):
        if i not in self._form_entries:return
        self._update_format_row(i)
        self._sync_form_value_visibility(i)

    def _sync_form_value_visibility(self,i):
        """Enforce exactly one visible Value/Action control for each format."""
        if i not in self._form_entries:return
        mode=self.format_vars[i].get()
        option=self.option_vars[i].get()
        entry=self._form_entries[i]
        drop=self._dropdown_controls[i]
        # grid_forget is deliberately used for hidden controls: grid_remove
        # retains prior geometry, which can be inadvertently restored by a
        # subsequent bare grid() from another update.
        entry.grid_forget()
        drop.grid_forget()
        # Disabled fields are displayed only as labels in Form View. The
        # settings and text are held in memory for later re-enabling.
        if not self.enabled_vars[i].get():
            self._format_widgets[i].configure(state="disabled")
            self._option_widgets[i].configure(state="disabled")
            self._navigate_controls[i].grid_remove()
            self._navigate_buttons[i].grid_remove()
            return
        self._format_widgets[i].configure(state="readonly")
        self._option_widgets[i].configure(state="readonly" if mode in ("Date","Drop Down") else "disabled")
        if mode=="Drop Down":
            drop.grid(row=i+2,column=2,sticky="w",padx=5,pady=3)
        elif mode=="Text" or (mode=="Date" and option=="MM/DD/YY"):
            entry.grid(row=i+2,column=2,sticky="w",padx=5,pady=3)
        # Skip, Date/Blank, Date/Today's Date: neither control is gridded.
        if i in self._navigate_controls:
            is_drop=mode=="Drop Down"
            if is_drop:
                self._navigate_controls[i].grid()
                self._navigate_buttons[i].grid()
                self._navigate_buttons[i].configure(state="normal" if self._navigate_vars[i].get() else "disabled")
            else:
                self._navigate_controls[i].grid_remove()
                self._navigate_buttons[i].grid_remove()

    def _rebuild_field_rows(self,fields):
        """Recreate form controls after a deliberate Debug structural edit."""
        inside=self._form_inside
        for child in inside.winfo_children():child.destroy()
        for col,title in ((0,"Use"),(1,"Field"),(2,"Value / Action"),(3,"Format"),(4,"Options"),(5,"Navigate")):
            ttk.Label(inside,text=title,font=("Segoe UI",10,"bold")).grid(row=1,column=col,sticky="w",padx=5,pady=6)
        self.field_vars=[];self.nav_vars=[];self.format_vars=[];self.option_vars=[]
        self.enabled_vars=[];self._enabled_controls={}
        self._format_widgets={};self._option_widgets={};self._dropdown_controls={};self._navigate_controls={};self._navigate_buttons={};self._navigate_vars=[];self._navigate_keys={}
        self._typed_values={};self._date_values={};self._dropdown_values={};self._format_previous={}
        self._format_sync=False
        self._form_entries={}
        for i,f in enumerate(fields):
            active=tk.BooleanVar(value=field_is_enabled(f))
            self.enabled_vars.append(active)
            toggle=ttk.Checkbutton(inside,variable=active,
                                   command=lambda idx=i:self._toggle_field_enabled(idx))
            toggle.grid(row=i+2,column=0,sticky="w",padx=5)
            self._enabled_controls[i]=toggle
            ttk.Label(inside,text=generic_field_display_label(i,f),width=27).grid(row=i+2,column=1,sticky="w",padx=5)
            v=tk.StringVar(value=f["value"]);self.field_vars.append(v)
            n=tk.StringVar(value=f["after"]);self.nav_vars.append(n)
            is_date=(f.get("format_type")=="Date" or False)
            fmt=tk.StringVar(value=f.get("format_type","Date" if is_date else "Text"))
            opt=tk.StringVar(value=f.get("format_option","Today's Date" if is_date else ""))
            self.format_vars.append(fmt);self.option_vars.append(opt)
            nav_var=tk.BooleanVar(value=bool(f.get("navigate",False)))
            self._navigate_vars.append(nav_var)
            self._navigate_keys[i]=str(f.get("navigate_keys",""))
            entry=tk.Entry(inside,textvariable=v,width=19,relief="solid",bd=1,foreground="#111111",background="#ffffff",readonlybackground="#e5e5e5")
            entry.grid(row=i+2,column=2,sticky="w",padx=5,pady=3)
            self._form_entries[i]=entry
            self._typed_values[i]=f["value"] if not is_date else ""
            self._date_values[i]=f["value"] if is_date else ""
            self._dropdown_values[i]=""
            self._format_previous[i]=fmt.get()
            entry.bind("<FocusOut>",lambda e,idx=i:self._validate_date_blur(idx))
            entry.bind("<KeyRelease>",lambda e,idx=i:self._remember_active_input(idx))
            drop=ttk.Combobox(inside,state="readonly",width=16)
            drop.grid(row=i+2,column=2,sticky="w",padx=5,pady=3)
            drop.bind("<<ComboboxSelected>>",lambda e,idx=i:self._dropdown_value_changed(idx))
            self._dropdown_controls[i]=drop
            fmt_box=ttk.Combobox(inside,textvariable=fmt,values=["Text","Drop Down","Date","Skip"],state="readonly",width=13)
            fmt_box.grid(row=i+2,column=3,sticky="w",padx=5)
            self._format_widgets[i]=fmt_box
            option_box=ttk.Combobox(inside,textvariable=opt,state="readonly",width=20)
            option_box.grid(row=i+2,column=4,sticky="w",padx=5)
            # A real combobox selection event is needed in addition to StringVar traces:
            # traces may be suppressed while another format update is in progress.
            option_box.bind("<<ComboboxSelected>>",lambda e,idx=i:self._date_option_selected(idx),add="+")
            self._option_widgets[i]=option_box
            nav_check=ttk.Checkbutton(inside,text="Navigate",variable=nav_var,command=lambda idx=i:(self._update_format_row(idx),self._form_changed()))
            nav_check.grid(row=i+2,column=5,sticky="w",padx=3)
            nav_button=ttk.Button(inside,text="Navigate Keys...",command=lambda idx=i:self._edit_navigate_keys(idx))
            nav_button.grid(row=i+2,column=6,sticky="w",padx=3)
            self._navigate_controls[i]=nav_check;self._navigate_buttons[i]=nav_button
            fmt.trace_add("write",lambda *_,idx=i:self._update_format_row(idx))
            opt.trace_add("write",lambda *_,idx=i:self._update_format_row(idx))
            self._update_format_row(i)
        if self._field_rows_ready:
            for i,v in enumerate(self.field_vars):
                v.trace_add("write",lambda *_,index=i:self._note_form_owner(index))
            for v in self.field_vars+self.format_vars+self.option_vars:
                v.trace_add("write",self._form_changed)
            for v in self.field_vars+self.nav_vars:
                v.trace_add("write",self._changed)
        self._form_previous_values={i:v.get() for i,v in enumerate(self.field_vars)}
        self._refresh_endpoint_choices()

    def _toggle_field_enabled(self,i):
        """Label-only means no editable control or emitted action, NOT a deleted step.

        Keep value, format, dropdown library, grid position, and Tab position
        intact so a later re-enable restores the user's form.
        """
        if self._loading:return
        self.field_definitions[i]["enabled"]=self.enabled_vars[i].get()
        self._sync_form_value_visibility(i)
        self._form_changed()
        self._changed()
        if self.form_preview_window is not None and self.form_preview_window.winfo_exists():
            self.show_form_preview()
        if getattr(self,"designer_body",None) is not None:self._designer_render()
        if self.manage_fields_window is not None and self.manage_fields_window.winfo_exists():
            self._manage_refresh()

    def _edit_navigate_keys(self,i):
        """Record supported navigation keys locally without injecting OS keystrokes.

        Only one field-navigation editor can be open at a time. A second click
        raises the current editor instead of creating an overlapping dialog.
        """
        if self._raise_dialog("navigate_keys_window"):return
        window=tk.Toplevel(self.root)
        self.navigate_keys_window=window
        window.title(f"Navigate Keys — {self.field_definitions[i]['name']}")
        window.geometry("490x470")
        ttk.Label(window,text="Record navigation keys in order, or edit the list manually.\nClick Record, then press keys in the capture box. Escape records Escape; use Stop Recording to finish.",wraplength=450).pack(anchor="w",padx=12,pady=10)
        status=tk.StringVar(value="Ready to record")
        ttk.Label(window,textvariable=status).pack(anchor="w",padx=12)
        capture=ttk.Label(window,text="Click Record to capture keys here",anchor="center",relief="ridge",padding=12,takefocus=True)
        capture.pack(fill="x",padx=12,pady=6)
        editor=tk.Text(window,height=11,width=48)
        editor.pack(fill="both",expand=True,padx=12,pady=5)
        editor.insert("1.0",self._navigate_keys.get(i,""))
        recording=[False]
        keymap={"Prior":"PageDown", "Next":"PageDown", "Page_Up":"PageUp", "Page_Down":"PageDown", "Return":"Enter", "KP_Enter":"Enter", "Escape":"Escape", "BackSpace":"Backspace", "Delete":"Delete", "space":"Space", "Left":"Left", "Right":"Right", "Up":"Up", "Down":"Down", "Home":"Home", "End":"End", "Tab":"Tab"}
        keymap["Prior"]="PageUp"
        def on_key(event):
            if not recording[0]:return "break"
            name=keymap.get(event.keysym)
            if name:
                existing=editor.get("1.0","end-1c").strip()
                editor.delete("1.0","end")
                editor.insert("1.0",existing+("\n" if existing else "")+name)
                status.set(f"Recorded {name}")
            else:
                status.set(f"Ignored unsupported key: {event.keysym}")
            return "break"
        capture.bind("<KeyPress>",on_key)
        # Keep capture focus, including for Tab, without moving into the form.
        capture.bind("<FocusOut>",lambda e:status.set("Recording paused: click Record to resume") if recording[0] else None)
        def record():
            recording[0]=True
            capture.focus_set()
            status.set("Recording navigation keys…")
        def stop():
            recording[0]=False
            status.set("Recording stopped; review keys before saving")
        def save():
            stop()
            value=editor.get("1.0","end-1c").strip()
            try:navigation_tokens(value)
            except ValueError as exc:
                messagebox.showerror("Navigate Keys",str(exc),parent=window);return
            self._navigate_keys[i]=value
            self._form_changed()
            window.destroy()
        buttons=ttk.Frame(window);buttons.pack(pady=10)
        ttk.Button(buttons,text="Record",command=record).pack(side="left",padx=5)
        ttk.Button(buttons,text="Stop Recording",command=stop).pack(side="left",padx=5)
        ttk.Button(buttons,text="Clear",command=lambda:editor.delete("1.0","end")).pack(side="left",padx=5)
        ttk.Button(buttons,text="Save Navigate Keys",command=save).pack(side="left",padx=5)

    def _refresh_endpoint_choices(self):
        if not hasattr(self,"endpoint_picker"):return
        choices=[generic_field_display_label(i,f) for i,f in enumerate(self.field_definitions)]
        self.endpoint_picker.configure(values=choices)
        self.key2_endpoint_picker.configure(values=choices)
        self._endpoint_sync_dropdown()

    def _build_dropdown_tab(self,book):
        self.dropdowns_tab=ttk.Frame(self.debug_book,padding=12)
        self.debug_book.add(self.dropdowns_tab,text="Dropdowns")
        ttk.Label(self.dropdowns_tab,text="Reusable text choices — the macro types the selected value literally.").pack(anchor="w",pady=(0,8))
        top=ttk.Frame(self.dropdowns_tab);top.pack(fill="x")
        ttk.Label(top,text="Library:").pack(side="left")
        self.dropdown_name=tk.StringVar(value="")
        self.dropdown_picker=ttk.Combobox(top,textvariable=self.dropdown_name,state="readonly",width=36)
        self.dropdown_picker.pack(side="left",padx=6)
        self.dropdown_picker.bind("<<ComboboxSelected>>",lambda event:self._dropdown_select())
        bar=ttk.Frame(self.dropdowns_tab);bar.pack(fill="x",pady=8)
        ttk.Button(bar,text="Create List",command=self._dropdown_create).pack(side="left",padx=3)
        ttk.Button(bar,text="Load Lists",command=self._dropdown_import).pack(side="left",padx=3)
        ttk.Button(bar,text="Save Lists",command=self._dropdown_export).pack(side="left",padx=3)
        ttk.Button(bar,text="Delete List",command=self._dropdown_delete).pack(side="left",padx=3)
        ttk.Label(self.dropdowns_tab,text="Values — one option per line; edits are saved automatically when you leave the editor.").pack(anchor="w",pady=(10,2))
        self.dropdown_editor=tk.Text(self.dropdowns_tab,height=14,undo=True)
        self.dropdown_editor.pack(fill="both",expand=True)
        self.dropdown_editor.bind("<FocusOut>",self._dropdown_commit_editor)
        self.dropdown_editor.bind("<KeyRelease>",self._dropdown_commit_editor)
        self.dropdown_editor.configure(state="disabled",background="#e5e5e5")
        self._dropdown_refresh()

    def _dropdown_refresh(self):
        names=sorted(self.dropdown_libraries)
        if hasattr(self,"dropdown_picker"):
            self.dropdown_picker.configure(values=names)
            if self.dropdown_name.get() not in self.dropdown_libraries:
                self.dropdown_name.set("")
                self.dropdown_editor.configure(state="normal")
                self.dropdown_editor.delete("1.0","end")
                self.dropdown_editor.configure(state="disabled",background="#e5e5e5")
        for i in self._option_widgets:
            if self.format_vars[i].get()=="Drop Down":
                self._option_widgets[i].configure(values=names)

    def _dropdown_select(self):
        name=self.dropdown_name.get()
        self.dropdown_editor.configure(state="normal",background="#ffffff")
        self.dropdown_editor.delete("1.0","end")
        if name not in self.dropdown_libraries:
            self.dropdown_editor.configure(state="disabled",background="#e5e5e5")
            return
        self.dropdown_editor.insert("1.0","\n".join(self.dropdown_libraries[name]))

    def _dropdown_commit_editor(self,event=None):
        name=self.dropdown_name.get()
        if name not in self.dropdown_libraries:return
        values=[line.strip() for line in self.dropdown_editor.get("1.0","end-1c").splitlines() if line.strip()]
        if values!=self.dropdown_libraries[name]:
            self.dropdown_libraries[name]=values
            self._changed()

    def _dropdown_create(self):
        name=simpledialog.askstring("Create List","New list name:",parent=self.root)
        if name is None:return
        name=name.strip()
        if not name:return messagebox.showwarning("Create List","Enter a list name.")
        if name.casefold() in {k.casefold() for k in self.dropdown_libraries}:
            return messagebox.showwarning("Create List","A list with that name already exists.")
        self.dropdown_libraries[name]=[]
        self._dropdown_refresh()
        self.dropdown_name.set(name)
        self._dropdown_select()
        self._changed()

    def _dropdown_delete(self):
        name=self.dropdown_name.get()
        if name in self.dropdown_libraries and messagebox.askyesno("Delete List",f"Delete '{name}' and its values?",parent=self.root):
            del self.dropdown_libraries[name]
            self.dropdown_name.set("")
            self._dropdown_refresh()
            self._changed()

    def _dropdown_export(self):
        self._dropdown_commit_editor()
        name=filedialog.asksaveasfilename(title="Save all dropdown lists",defaultextension=".osdrp",filetypes=[("OpenSayo dropdown libraries","*.osdrp"),("JSON","*.json")])
        if name:
            try:
                Path(name).write_text(json.dumps({"format":"OpenSayo-Dropdowns","version":1,"libraries":self.dropdown_libraries},indent=2,ensure_ascii=False),encoding="utf-8")
            except Exception as exc:messagebox.showerror("Save Lists",str(exc))

    def _dropdown_import(self):
        name=filedialog.askopenfilename(title="Load all dropdown lists",filetypes=[("OpenSayo dropdown libraries","*.osdrp")])
        if not name:return
        try:
            data=json.loads(Path(name).read_text(encoding="utf-8-sig"))
            if not isinstance(data,dict) or data.get("format")!="OpenSayo-Dropdowns" or not isinstance(data.get("libraries"),dict):
                raise ValueError("Not a valid OpenSayo dropdown library file")
            incoming=data["libraries"]
            if len(incoming)>1000:raise ValueError("Library contains too many lists")
            for key,values in incoming.items():
                if not isinstance(key,str) or not key.strip() or not isinstance(values,list) or not all(isinstance(v,str) for v in values):
                    raise ValueError("Invalid list name or values")
            current=dict(self.dropdown_libraries)
            added=sorted(set(incoming)-set(current))
            updated=sorted(k for k in incoming if k in current and current[k]!=incoming[k])
            unchanged=sorted(k for k in incoming if k in current and current[k]==incoming[k])
            removed=sorted(set(current)-set(incoming))
            win=tk.Toplevel(self.root);win.title("Load Lists — Review Changes")
            win.transient(self.root);win.grab_set();win.geometry("570x470")
            ttk.Label(win,text="Choose how to load the entire library",font=("Segoe UI",12,"bold")).pack(anchor="w",padx=14,pady=(14,6))
            summary=tk.Text(win,height=14,wrap="word",state="normal")
            summary.pack(fill="both",expand=True,padx=14,pady=5)
            def lines(title,items):return title+" ("+str(len(items))+"):\n"+("\n".join("  • "+v for v in items) if items else "  None")+"\n\n"
            summary.insert("1.0",lines("New lists",added)+lines("Existing lists updated",updated)+lines("Unchanged lists",unchanged)+lines("Existing lists removed ONLY by Replace",removed))
            summary.configure(state="disabled")
            ttk.Label(win,text="Merge keeps lists not present in the file. Replace removes them.",wraplength=530).pack(anchor="w",padx=14,pady=5)
            buttons=ttk.Frame(win);buttons.pack(fill="x",padx=14,pady=14)
            def apply_import(mode):
                if mode=="replace" and not messagebox.askyesno("Replace Entire Library?","This will remove existing lists that are not in the imported file. Continue?",parent=win):return
                result=({**current,**incoming} if mode=="merge" else dict(incoming))
                self.dropdown_libraries=result
                self.dropdown_name.set("")
                self._dropdown_refresh()
                self._changed()
                win.destroy()
            ttk.Button(buttons,text="Merge Libraries (recommended)",command=lambda:apply_import("merge")).pack(side="left",padx=3)
            ttk.Button(buttons,text="Replace Entire Library",command=lambda:apply_import("replace")).pack(side="left",padx=3)
            ttk.Button(buttons,text="Cancel",command=win.destroy).pack(side="right",padx=3)
            win.protocol("WM_DELETE_WINDOW",win.destroy)
        except Exception as exc:messagebox.showerror("Load Lists",str(exc))

    def _start_keyboard_test(self):
        self.debug_book.select(self.testing_tab)
        self.testing_book.select(self.test.master)
        self.test.focus_force()
        self.test.mark_set("insert","end-1c")
        self.test.see("insert")
        self.test_status.set("Listening — type in the input area")
        self.root.after_idle(self.test.focus_force)

    def _debug_tab_changed(self,event=None):
        try:
            selected=self.debug_book.nametowidget(self.debug_book.select())
            if selected is self.testing_tab:
                tool=self.testing_book.nametowidget(self.testing_book.select())
                if tool is self.preview.master:self._refresh(show_error=False)
                elif tool is self.test.master:self.test_status.set("Ready — click Start Keyboard Test")
        except (AttributeError, tk.TclError):
            pass

    def _debug_keypress(self,event):
        name=event.keysym or "Unknown"
        self.test_last.set("Last key: " + name)
        self.test_log.configure(state="normal")
        self.test_log.insert("end",f"Key press: {name} | char={event.char!r} | state={event.state}\n")
        self.test_log.see("end")
        self.test_log.configure(state="disabled")
        # Prevent Tab from moving focus out of the test field.
        if name in ("Tab","ISO_Left_Tab"):
            self.test.insert("insert","\t")
            return "break"

    def _clear_test_log(self):
        self.test_log.configure(state="normal")
        self.test_log.delete("1.0","end")
        self.test_log.configure(state="disabled")
        self.test_last.set("Last key: none")

    def _build_definitions_tab(self):
        """Shareable, validated reference profiles; never modifies hardware encoders."""
        tab=ttk.Frame(self.debug_book,padding=10)
        self.definitions_tab=tab
        self.debug_book.add(tab,text="Definitions")
        ttk.Label(tab,text="Key Definitions — shareable reference profiles",font=("Segoe UI",13,"bold")).pack(anchor="w")
        ttk.Label(tab,text="Import/export device-specific JSON reference profiles. These are documentation only: imported commands are not automatically enabled in the macro compiler or written to hardware.",wraplength=840,justify="left").pack(anchor="w",pady=7)
        from sayo_macro_language import SPECIAL,PUNCT,MODIFIER_KEYS
        defaults=[]
        for char in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789":
            defaults.append(["Alphanumeric",char,"hidkey_"+char,"Generator-supported; hardware unverified"])
        for label,name in sorted(SPECIAL.items()):
            defaults.append(["Navigation",label,"hidkey_"+name,"Generator-supported; hardware unverified"])
        for char,(name,shift) in sorted(PUNCT.items()):
            defaults.append(["Punctuation",repr(char),"hidkey_"+name+(" + Shift" if shift else ""),"Generator-supported; hardware unverified"])
        for name in MODIFIER_KEYS:
            defaults.append(["Modifier",name,"PRESS_SK hidkey_"+name,"Documented Sayo syntax; hardware unverified"])
        self._definitions_default=copy.deepcopy(defaults)
        self._definitions_rows=copy.deepcopy(defaults)
        self._definitions_device="Sayo (built-in)"
        bar=ttk.Frame(tab);bar.pack(fill="x",pady=6)
        self._definitions_label=tk.StringVar(value="Device profile: Sayo (built-in)")
        ttk.Label(bar,textvariable=self._definitions_label).pack(side="left",padx=(0,15))
        ttk.Button(bar,text="Import JSON",command=self._definitions_import_json).pack(side="left",padx=3)
        ttk.Button(bar,text="Export JSON",command=self._definitions_export_json).pack(side="left",padx=3)
        ttk.Button(bar,text="Restore Sayo Defaults",command=self._definitions_restore).pack(side="left",padx=3)
        filter_var=tk.StringVar()
        search=ttk.Entry(tab,textvariable=filter_var);search.pack(fill="x",pady=5)
        ttk.Label(tab,text="Search definitions (letters, numbers, navigation, punctuation, modifiers)").pack(anchor="w")
        tree=ttk.Treeview(tab,columns=("category","name","command","status"),show="headings")
        for name,width in (("category",135),("name",150),("command",255),("status",220)):
            tree.heading(name,text=name.title());tree.column(name,width=width,stretch=True)
        tree.pack(fill="both",expand=True,pady=6)
        self._definitions_tree=tree
        self._definitions_filter=filter_var
        filter_var.trace_add("write",lambda *_:self._definitions_refresh())
        self._definitions_refresh()
        ttk.Label(tab,text="Supported built-in raw syntax: PRESS_GK / RELEASE_GK, PRESS_SK / RELEASE_SK, SLEEP (1–255), SLEEP_U16 (1–65535), EXIT. JSON profiles do not extend supported syntax.",wraplength=840).pack(anchor="w",pady=5)

    def _definitions_refresh(self):
        tree=self._definitions_tree
        q=self._definitions_filter.get().casefold().strip()
        for item in tree.get_children():tree.delete(item)
        for entry in self._definitions_rows:
            if q in " ".join(entry).casefold():tree.insert("","end",values=entry)

    def _definitions_restore(self):
        if not messagebox.askyesno("Restore definitions","Restore built-in Sayo reference definitions? This does not change the keypad or saved JSON files.",parent=self.root):return
        self._definitions_rows=copy.deepcopy(self._definitions_default)
        self._definitions_device="Sayo (built-in)"
        self._definitions_label.set("Device profile: "+self._definitions_device)
        self._definitions_refresh()

    def _definitions_export_json(self):
        filename=filedialog.asksaveasfilename(parent=self.root,title="Export shareable definitions",defaultextension=".json",filetypes=[("JSON profiles","*.json")])
        if not filename:return
        payload={"file_type":"opensayo_key_definitions","schema_version":1,"device":self._definitions_device,"definitions":[dict(zip(("category","name","command","status"),row)) for row in self._definitions_rows]}
        try:
            Path(filename).write_text(json.dumps(payload,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        except OSError as exc:messagebox.showerror("Export failed",str(exc),parent=self.root)

    def _definitions_import_json(self):
        filename=filedialog.askopenfilename(parent=self.root,title="Import shareable definitions",filetypes=[("JSON profiles","*.json")])
        if not filename:return
        try:
            if Path(filename).stat().st_size>1024*1024:raise ValueError("Profile exceeds 1 MB")
            raw=json.loads(Path(filename).read_text(encoding="utf-8-sig"))
            if not isinstance(raw,dict) or raw.get("file_type")!="opensayo_key_definitions" or raw.get("schema_version")!=1:
                raise ValueError("Not an OpenSayo definitions profile (schema version 1)")
            device=raw.get("device")
            if not isinstance(device,str) or not 1<=len(device.strip())<=100:raise ValueError("Device name must be 1–100 characters")
            entries=raw.get("definitions")
            if not isinstance(entries,list) or not 1<=len(entries)<=1000:raise ValueError("Definitions must contain 1–1000 entries")
            parsed=[];seen=set()
            for i,entry in enumerate(entries):
                if not isinstance(entry,dict):raise ValueError(f"Definition {i+1} is not an object")
                row=[]
                for key in ("category","name","command","status"):
                    value=entry.get(key)
                    if not isinstance(value,str) or not value.strip() or len(value)>300 or any(ord(c)<32 for c in value):
                        raise ValueError(f"Definition {i+1} has an invalid {key}")
                    row.append(value)
                identity=(row[0].casefold(),row[1].casefold())
                if identity in seen:raise ValueError(f"Duplicate definition: {row[1]}")
                seen.add(identity);parsed.append(row)
            if not messagebox.askyesno("Import definitions",f"Load {len(parsed)} reference definitions for {device}?\n\nThis replaces the displayed reference list only. No device writes or compiler changes.",parent=self.root):return
            self._definitions_rows=parsed
            self._definitions_device=device.strip()
            self._definitions_label.set("Device profile: "+self._definitions_device)
            self._definitions_refresh()
        except (OSError,UnicodeError,ValueError,TypeError) as exc:
            messagebox.showerror("Invalid definitions JSON",str(exc),parent=self.root)

    def _build_concepts_tab(self):
        """Read-only, selectable roadmap and full freeform interface concept.

        This screen deliberately has no callbacks that write scripts or devices.
        """
        outer = ttk.Frame(self.debug_book, padding=8)
        self.concepts_tab=outer
        self.debug_book.add(outer, text="Explore Concepts")
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(2, weight=1)
        ttk.Label(
            outer, text="OpenSayo — Concepts & Development Roadmap",
            font=("Segoe UI", 14, "bold")
        ).grid(row=0, column=0, sticky="w", pady=(0, 5))
        ttk.Label(
            outer, text="Roadmap and milestone history are informational only; hardware discoveries "
                        "remain experimental until actual device readback is verified.",
            wraplength=850, foreground="#555"
        ).grid(row=1, column=0, sticky="ew", pady=(0, 8))

        self.concept_entries = [
            ("Current Release — v1.15", "GENERAL PURPOSE · flexible macro editing",
             "Customizable form editor, layout tools, macro previews, guarded device writing and configurable timing.",
             ["Navigation Guard and overcapacity editing hotfixes integrated",
              "Key 1 and Key 2 capacity bars flash red when oversized",
              "Adjacent SLEEP commands optimized; adjustable dropdown opening delay",
              "Confirm hardware persistence and final Windows regression before calling stable"]),
            ("Completed Milestones", "IMPLEMENTED · verify hardware-dependent behavior separately",
             "The v1.00 and v1.01 planning items have been absorbed into the current release; they are no longer future release milestones.",
             ["Alpha14/Alpha22: protocol research, macro compilation and guarded writer experiments",
              "v0.25: recovery baseline and script preview/editor work",
              "About time OpenSayo got a proper interface overhaul.",
              "v0.26: configurable form designer, half-height grid tiles, labels and exportable layouts",
              "v0.28 Build 6: earlier development baseline",
              "Improved navigation, oversized-project editing, and assignment controls",
              "Shinobi artwork/icon, optional user-imported definitions and layouts supported",
              "This entire GUI reminds me of something I'd find in the classic Windows of the '90s. Some aspects are a little loud.",
              "The '90s were a golden era for Konami. Some things from that decade are better left buried.",
              "Physical 1↔2 assignment swap observed working; reconnect persistence still to verify"]),
            ("Future Concepts", "RESEARCH · not release commitments",
             "Explore only after stable release and confirmed device readback.",
             ["Reliable host Caps Lock state detection beyond toggling",
              "RGB status indicators only if verified HID support exists",
              "Macro chaining and expanded script-bank operations subject to safe protocol verification",
              "Readback-based automatic clearing of assignment warnings",
              "Future improvements will be documented in subsequent version notes"]),
        ]
        chooser = ttk.Frame(outer)
        chooser.grid(row=2, column=0, sticky="nsew")
        chooser.rowconfigure(1, weight=1)
        chooser.columnconfigure(0, weight=1)
        top = ttk.Frame(chooser)
        top.grid(row=0, column=0, sticky="ew", pady=(0, 7))
        ttk.Label(top, text="Explore concept:").pack(side="left", padx=(0, 8))
        self.concept_choice = tk.StringVar(value=self.concept_entries[0][0])
        select = ttk.Combobox(
            top, textvariable=self.concept_choice, state="readonly", width=51,
            values=[x[0] for x in self.concept_entries] + ["Freeform Editor — Full UI Prototype"]
        )
        select.pack(side="left", fill="x", expand=True)
        ttk.Label(top, text="Read-only preview", foreground="#666").pack(side="left", padx=9)
        self.concept_host = ttk.Frame(chooser)
        self.concept_host.grid(row=1, column=0, sticky="nsew")
        self.concept_host.columnconfigure(0, weight=1)
        self.concept_host.rowconfigure(0, weight=1)
        self.concept_pages = {}
        for title, stage, description, points in self.concept_entries:
            page = ttk.Frame(self.concept_host)
            self.concept_pages[title] = page
            page.rowconfigure(0, weight=1)
            page.columnconfigure(0, weight=1)
            concept_canvas = tk.Canvas(page, highlightthickness=0, borderwidth=0)
            concept_scroll = ttk.Scrollbar(page, orient="vertical", command=concept_canvas.yview)
            concept_canvas.configure(yscrollcommand=concept_scroll.set)
            concept_canvas.grid(row=0, column=0, sticky="nsew")
            concept_scroll.grid(row=0, column=1, sticky="ns")
            content = ttk.Frame(concept_canvas, padding=12)
            content_id = concept_canvas.create_window((0, 0), window=content, anchor="nw")
            content.bind("<Configure>", lambda e, c=concept_canvas: c.configure(scrollregion=c.bbox("all")))
            concept_canvas.bind("<Configure>", lambda e, c=concept_canvas, cid=content_id: c.itemconfigure(cid, width=e.width))
            def _scroll_concept(event, c=concept_canvas):
                c.yview_scroll(-int(event.delta / 120) if event.delta else 0, "units")
                return "break"
            # Bind the wheel to the page content and its labels, not globally.
            content.bind("<MouseWheel>", _scroll_concept)
            concept_canvas.bind("<MouseWheel>", _scroll_concept)
            ttk.Label(content, text=title, font=("Segoe UI", 13, "bold")).pack(
                anchor="w", pady=(0, 4))
            ttk.Label(content, text=stage, foreground="#27659b").pack(
                anchor="w", pady=(0, 12))
            ttk.Label(content, text=description, wraplength=800,
                      justify="left").pack(anchor="w", pady=(0, 12))
            ttk.Label(content, text="Details and checkpoints",
                      font=("Segoe UI", 10, "bold")).pack(anchor="w")
            for point in points:
                ttk.Label(content, text="• " + point, wraplength=800,
                          justify="left").pack(anchor="w", pady=4)
            ttk.Label(
                content, text="Suggest improvements: dvangilder.work@gmail.com",
                foreground="#555"
            ).pack(anchor="w", pady=(20, 0))

            for child in content.winfo_children():
                child.bind("<MouseWheel>", _scroll_concept)

        prototype = ttk.Frame(self.concept_host)
        prototype.rowconfigure(0, weight=1)
        prototype.columnconfigure(0, weight=1)
        self.concept_pages["Freeform Editor — Full UI Prototype"] = prototype
        canvas = tk.Canvas(prototype, highlightthickness=0)
        scroll = ttk.Scrollbar(prototype, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        mock_content = ttk.Frame(canvas, padding=12)
        cid = canvas.create_window((0, 0), window=mock_content, anchor="nw")
        mock_content.bind("<Configure>",
                          lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfigure(cid, width=e.width))
        def _concept_wheel(event):
            canvas.yview_scroll(-int(event.delta / 120), "units")
            return "break"
        canvas.bind("<MouseWheel>", _concept_wheel)
        mock_content.bind("<MouseWheel>", _concept_wheel)
        ttk.Label(mock_content,text="FREEFORM MACRO EDITOR — INTERFACE CONCEPT ONLY",font=("Segoe UI",14,"bold"),foreground="#27659b").pack(anchor="w",pady=(0,5))
        ttk.Label(mock_content,text="No controls on this page record, save, change the form, or write to a keypad.",wraplength=770,foreground="#a04b00").pack(anchor="w",pady=(0,12))
        tools=ttk.LabelFrame(mock_content,text="Recording & timing",padding=8);tools.pack(fill="x",pady=5)
        r=ttk.Frame(tools);r.pack(fill="x")
        for name in ("● Record Macro","■ Stop Recording","Default All Delays to Presets","Undo"):
            ttk.Button(r,text=name,state="disabled").pack(side="left",padx=3)
        t=ttk.Frame(tools);t.pack(fill="x",pady=(9,0))
        for label,val in (("Key hold (ms)","5"),("After navigation (ms)","10"),("Repeated key gap (ms)","15")):
            ttk.Label(t,text=label).pack(side="left",padx=(3,2))
            ttk.Entry(t,width=6,state="disabled").pack(side="left",padx=(0,12))
        actions=ttk.LabelFrame(mock_content,text="Insert actions — planned",padding=8);actions.pack(fill="x",pady=5)
        for group in (("Insert Key","Insert Combo","Insert Text","Insert Tab","Insert Enter"),("Insert Wait","Insert Hold","Insert Release","Insert Repeat","Insert Mouse Action")):
            row=ttk.Frame(actions);row.pack(fill="x",pady=3)
            for name in group:ttk.Button(row,text=name,state="disabled").pack(side="left",padx=3)
        selector=ttk.LabelFrame(mock_content,text="Key selection — visual concept (no device effect)",padding=8)
        selector.pack(fill="x",pady=5)
        keyrow=ttk.Frame(selector);keyrow.pack(fill="x")
        ttk.Label(keyrow,text="Key selection:").pack(side="left",padx=4)
        sample_keys=["Tab","Enter","Escape","Backspace","ArrowUp","ArrowDown","ArrowLeft","ArrowRight"]
        selected_key=tk.StringVar(value="Tab")
        ttk.Combobox(keyrow,textvariable=selected_key,values=sample_keys,state="readonly",width=25).pack(side="left",padx=5)
        added=tk.StringVar(value="Example only — no keys added")
        def mock_add():
            key=selected_key.get()
            added.set("Mock action added: PRESS_GK hidkey_"+key+" / RELEASE_GK hidkey_"+key)
        ttk.Button(keyrow,text="Add",command=mock_add).pack(side="left",padx=4)
        ttk.Label(selector,textvariable=added,foreground="#555").pack(anchor="w",pady=5)
        ttk.Label(selector,text="These are example names only; the completed key map will supply verified definitions.",wraplength=750).pack(anchor="w")
        editors=ttk.Panedwindow(mock_content,orient="vertical");editors.pack(fill="both",expand=True,pady=8)
        readable=ttk.LabelFrame(editors,text="Human-readable macro — example only",padding=5)
        example=tk.Text(readable,height=7,wrap="word",font=("Consolas",10))
        example.pack(fill="both",expand=True)
        example.insert("1.0",'TYPE "Hello World!"\n{WAIT:15}\n{TAB}\n{CTRL+C}\n{WAIT:60}\n{CTRL+V}')
        example.configure(state="disabled")
        editors.add(readable,weight=1)
        generated=ttk.LabelFrame(editors,text="Generated Sayo Script — illustrative only",padding=5)
        sample=tk.Text(generated,height=6,wrap="none",font=("Consolas",9))
        sample.pack(fill="both",expand=True)
        sample.insert("1.0","PRESS_GK hidkey_h\nRELEASE_GK hidkey_h\n...\nPRESS_GK hidkey_Tab\nRELEASE_GK hidkey_Tab")
        sample.configure(state="disabled")
        editors.add(generated,weight=1)
        actionlist=ttk.LabelFrame(mock_content,text="Editable action list — proposed step view",padding=8);actionlist.pack(fill="x",pady=5)
        for n,kind,value in ((1,"Text","Hello World!"),(2,"Wait","15 ms"),(3,"Key","Tab"),(4,"Combo","Ctrl + C"),(5,"Wait","60 ms"),(6,"Combo","Ctrl + V")):
            row=ttk.Frame(actionlist);row.pack(fill="x",pady=2)
            ttk.Label(row,text=f"{n:02d}  {kind}",width=17).pack(side="left")
            ttk.Entry(row,state="disabled",width=42).pack(side="left",fill="x",expand=True)
            ttk.Label(row,text=value,width=19).pack(side="left",padx=5)
            ttk.Button(row,text="↑",state="disabled",width=3).pack(side="left")
            ttk.Button(row,text="↓",state="disabled",width=3).pack(side="left")
        device=ttk.LabelFrame(mock_content,text="Target keypad key — concept only",padding=8);device.pack(fill="x",pady=5)
        r=ttk.Frame(device);r.pack(fill="x")
        ttk.Label(r,text="Program to:").pack(side="left",padx=4)
        ttk.Combobox(r,values=("Key 1","Key 2"),state="disabled",width=15).pack(side="left",padx=4)
        ttk.Button(r,text="Validate Script",state="disabled").pack(side="left",padx=4)
        ttk.Button(r,text="Copy Sayo Script",state="disabled").pack(side="left",padx=4)
        ttk.Button(r,text="Save Macro",state="disabled").pack(side="left",padx=4)
        ttk.Label(device,text="Independent drafts for each editor; never overwrite the form macro. Key 2 writing is not implemented.",wraplength=750).pack(anchor="w",pady=6)
        fallback=ttk.LabelFrame(mock_content,text="Alternative Device Programming Method — planned",padding=8);fallback.pack(fill="x",pady=5)
        ttk.Label(fallback,text="Copy a generated script and use https://app.sayodevice.com/ if direct programming is unavailable. Website compatibility and saving are not guaranteed.",wraplength=760).pack(anchor="w")
        capacity=ttk.LabelFrame(mock_content,text="Device capacity — illustrative (not a real byte count)",padding=8);capacity.pack(fill="x",pady=5)
        ttk.Progressbar(capacity,maximum=100,value=22).pack(fill="x",pady=4)
        ttk.Label(capacity,text="Mock display only • Future implementation will calculate actual script size.").pack(anchor="w")


        def show_concept(event=None):
            for page in self.concept_pages.values():
                page.grid_forget()
            page = self.concept_pages[self.concept_choice.get()]
            page.grid(row=0, column=0, sticky="nsew")
        select.bind("<<ComboboxSelected>>", show_concept)
        show_concept()

    def _build_macro_tab(self):
        ttk.Label(self.macro_tab,text="Read-only generated previews. Edit fields in Field View or Form View. Millisecond timing settings remain editable. Full script editing is available in Freeform.",wraplength=900).pack(anchor="w",pady=(0,6))
        bar=ttk.Frame(self.macro_tab);bar.pack(fill="x",pady=3)
        ttk.Label(bar,text="Wait (ms):").pack(side="left",padx=(12,2))
        self.insert_wait_ms=tk.StringVar(value="15")
        ttk.Entry(bar,textvariable=self.insert_wait_ms,width=6).pack(side="left",padx=2)

        timings=ttk.Frame(self.macro_tab);timings.pack(fill="x",pady=3)
        self.macro_key_ms=tk.StringVar(value="15");self.macro_nav_ms=tk.StringVar(value="20");self.macro_repeat_ms=tk.StringVar(value="15");self.dropdown_open_ms=tk.StringVar(value="75")
        self.use_caps_lock=tk.BooleanVar(value=False)
        for label,var in [("Key hold (ms)",self.macro_key_ms),("After navigation (ms)",self.macro_nav_ms),("Repeated key gap (ms)",self.macro_repeat_ms),("Dropdown opening (ms)",self.dropdown_open_ms)]:
            ttk.Label(timings,text=label).pack(side="left",padx=(5,2))
            ttk.Entry(timings,textvariable=var,width=5).pack(side="left",padx=(0,8))
        ttk.Button(timings,text="Apply Timing to Key",command=self._apply_viewer_timing).pack(side="left",padx=8)
        pane=ttk.Panedwindow(self.macro_tab,orient="vertical");pane.pack(fill="both",expand=True,pady=5)
        top=ttk.LabelFrame(pane,text="Raw Text Preview — read-only",padding=5)
        self.macro_readable=tk.Text(top,height=8,wrap="word",undo=True,font=("Consolas",11))
        self.macro_readable.pack(side="left",fill="both",expand=True)
        readable_scroll=ttk.Scrollbar(top,orient="vertical",command=self.macro_readable.yview)
        readable_scroll.pack(side="right",fill="y")
        self.macro_readable.configure(yscrollcommand=readable_scroll.set)
        self._macro_from_form_pending = False
        self.macro_readable.bind("<KeyRelease>",self._macro_readable_changed,add="+")
        self.macro_readable.bind("<FocusOut>",self._macro_readable_changed,add="+")
        self.macro_readable.bind("<<Paste>>",lambda e:self.root.after(50,self._macro_readable_changed),add="+")
        self.macro_readable.bind("<Return>",self._macro_readable_enter,add="+")
        self.macro_readable.bind("<Control-Tab>",lambda event:(self._insert_readable_token("{TAB}"),"break")[1])
        pane.add(top,weight=1)
        bottom=ttk.LabelFrame(pane,text="Sayo Script — Key 1 above Key 2 (read-only)",padding=5)
        bottom.columnconfigure(0,weight=1)
        bottom.rowconfigure(1,weight=1);bottom.rowconfigure(3,weight=1)
        self.macro_key1_heading=ttk.Label(bottom,text="KEY 1",font=("Segoe UI",10,"bold"))
        self.macro_key1_heading.grid(row=0,column=0,sticky="w")
        self.macro_key2_heading=ttk.Label(bottom,text="KEY 2",font=("Segoe UI",10,"bold"))
        self.macro_key2_heading.grid(row=2,column=0,sticky="w",pady=(6,0))
        self.macro_key_title=ttk.Label(bottom,text="KEY 1 — ACTIVE")
        self.macro_other=tk.Text(bottom,height=7,wrap="none",font=("Consolas",10),foreground="#888888",background="#f1f1f1")
        self.macro_other.configure(state="disabled")
        self.macro_text=tk.Text(bottom,height=7,wrap="none",undo=True,font=("Consolas",10))
        self.macro_text.grid(row=1,column=0,sticky="nsew")
        self.macro_other.grid(row=3,column=0,sticky="nsew")
        self.macro_text.bind("<KeyRelease>",self._macro_script_changed,add="+")
        self.macro_text.bind("<FocusOut>",self._macro_on_blur,add="+")
        self.macro_text.bind("<<Paste>>",lambda e:self.root.after(50,self._macro_script_changed),add="+")
        self.macro_text.bind("<<Modified>>",self._macro_script_modified,add="+")
        pane.add(bottom,weight=2)
        # Alternative programming path remains available if experimental USB writing fails.
        fallback=ttk.LabelFrame(self.macro_tab,text="Alternative Device Programming Method",padding=(9,5))
        fallback.pack(fill="x",pady=(2,4))
        ttk.Label(fallback,text=(
            "If you encounter problems programming your device through OpenSayo, you can copy the generated script "
            "above and use the official Sayo website compiler to install it on your device. "
            "The Sayo website is a separate service and may have compatibility issues, script limitations, or saving "
            "errors. OpenSayo cannot guarantee that scripts will compile or save successfully through the website."
        ),wraplength=860,justify="left").pack(anchor="w",fill="x")
        fallback_buttons=ttk.Frame(fallback);fallback_buttons.pack(anchor="w",pady=(5,0))
        ttk.Button(fallback_buttons,text="Copy Key 1",command=lambda:self._macro_copy_key(1)).pack(side="left",padx=(0,8))
        ttk.Button(fallback_buttons,text="Copy Key 2",command=lambda:self._macro_copy_key(2)).pack(side="left",padx=(0,12))
        site=tk.Label(fallback_buttons,text="Open Sayo Website Compiler",fg="#1269bd",cursor="hand2",font=("Segoe UI",10,"underline"))
        site.pack(side="left")
        site.bind("<Button-1>",lambda event:webbrowser.open("https://app.sayodevice.com/"))
        controls=ttk.Frame(self.macro_tab);controls.pack(fill="x",pady=3)
        ttk.Button(controls,text="Validate Script",command=self._macro_validate).pack(side="left",padx=3)

        # Build 16: prevent editing in Form Mode previews without disabling selection/copy.
        # Tk Text programmatic insert/delete still work for form-driven regeneration.
        for preview in (self.macro_readable,self.macro_text,self.macro_other):
            preview.bind("<KeyPress>",self._viewer_block_key)
            preview.bind("<<Paste>>",lambda event:"break")
            preview.bind("<<Cut>>",lambda event:"break")
            preview.bind("<<Clear>>",lambda event:"break")
            preview.bind("<Button-2>",lambda event:"break")
        self._macro_sync_job=None;self._macro_script_job=None;self._macro_sync_lock=False
        self._macro_last_generated=""
        self.macro_status=tk.StringVar(value="Read-only previews generated from Field View. Edit scripts directly in Freeform.")
        ttk.Label(self.macro_tab,textvariable=self.macro_status,wraplength=900,foreground="#555").pack(anchor="w")

    def _load_debug_preference(self):
        try: return bool(json.loads(UI_PREFS_PATH.read_text(encoding="utf-8")).get("show_debug",False))
        except (OSError,ValueError,TypeError): return False

    def _toggle_debug(self):
        try:
            UI_PREFS_PATH.parent.mkdir(parents=True,exist_ok=True)
            try:prefs=json.loads(UI_PREFS_PATH.read_text(encoding="utf-8"))
            except (OSError,ValueError,TypeError):prefs={}
            prefs["show_debug"]=bool(self.show_debug.get())
            UI_PREFS_PATH.write_text(json.dumps(prefs),encoding="utf-8")
        except OSError: pass
        visible=str(self.debug_tab) in self.book.tabs()
        if self.show_debug.get() and not visible:
            self.book.add(self.debug_tab,text="Debug")
        elif not self.show_debug.get() and visible:
            self.book.forget(self.debug_tab)

    def _insert_custom_wait(self):
        try:
            ms=int(self.insert_wait_ms.get())
            if not 0 <= ms <= 60000: raise ValueError()
        except ValueError:
            return messagebox.showerror("Wait duration","Enter a whole number from 0 to 60000 milliseconds.")
        self._insert_readable_token(f"{{WAIT:{ms}}}")

    def _date_action_index(self):
        # A private form may mark its calendar field, or designate a Date field
        # with the existing Today's Date action. No default field is special.
        return next((i for i,f in enumerate(self.field_definitions)
                     if f.get("special_action")=="today_calendar" or
                     (f.get("format_type")=="Date" and f.get("format_option")=="Today's Date")),None)

    def _date_action_focus(self,event=None):
        i=self._date_action_index()
        if i is not None and self.field_vars[i].get().strip().lower().replace(" ","") in ("down,enter","down,enter,end"):
            self.field_vars[i].set("")

    def _raise_dialog(self, attr):
        win=getattr(self,attr,None)
        if win is not None and win.winfo_exists():
            win.deiconify(); win.lift(); win.focus_force()
            return True
        return False

    def _email_link(self, parent):
        import webbrowser
        address="dvangilder.work@gmail.com"
        link=tk.Label(parent,text=address,fg="#1269bd",cursor="hand2",font=("Segoe UI",10,"underline"))
        link.pack(anchor="w",pady=(0,5))
        link.bind("<Button-1>",lambda e:webbrowser.open("mailto:"+address))
        return link

    def _show_help(self):
        """User guide with a clickable table of contents; no form/device mutations."""
        if self._raise_dialog("help_window"): return
        win=tk.Toplevel(self.root); self.help_window=win
        win.title("OpenSayo — Help & Quick Reference")
        win.geometry("850x680"); win.minsize(580,420); win.transient(self.root)
        frame=ttk.Frame(win,padding=12); frame.pack(fill="both",expand=True)
        search_row=ttk.Frame(frame);search_row.pack(fill="x",pady=(0,6))
        ttk.Label(search_row,text="Find in Help:").pack(side="left",padx=(0,6))
        search_term=tk.StringVar()
        search_entry=ttk.Entry(search_row,textvariable=search_term)
        search_entry.pack(side="left",fill="x",expand=True)
        search_status=tk.StringVar(value="")
        ttk.Label(search_row,textvariable=search_status,foreground="#555").pack(side="right",padx=7)
        body=tk.Text(frame,wrap="word",padx=16,pady=12,font=("Segoe UI",10),borderwidth=0)
        scrollbar=ttk.Scrollbar(frame,orient="vertical",command=body.yview)
        body.configure(yscrollcommand=scrollbar.set)
        body.pack(side="left",fill="both",expand=True); scrollbar.pack(side="right",fill="y")
        body.tag_configure("title",font=("Segoe UI",15,"bold"),spacing3=10)
        body.tag_configure("heading",font=("Segoe UI",11,"bold"),spacing1=15,spacing3=6)
        body.tag_configure("body",spacing3=9)
        body.tag_configure("toc",foreground="#1269bd",underline=True,spacing3=4)
        sections=[('Start Here — Choose Your Workspace',
          'Use File > New Form Project to build a macro from a configurable list of fields, or File > New Freeform '
          'Macro to edit a keyboard-command sequence directly. A new Form Project starts with 25 empty fields: ten '
          'generic form labels, then numbered placeholders, arranged in three columns. It is a starting template, not '
          'a field limit. The Form and Freeform workspaces are separate; switch through File > New... or File > Open '
          'Project. OpenSayo can edit and preview offline. Saving a project or editing a macro never automatically '
          'programs a keypad. On a previously used computer, a saved local session may be restored instead of the '
          'blank starter; back up any personal project before choosing Reset Defaults.'),
         ('Where to Find Tools — Menus, Tabs and Debug',
          'The main tabs are Field View and Macro Viewer for a Form Project, or Freeform for a Freeform Macro. File '
          'contains project open/save, form-format, layout, field-list, script import/export, and Settings commands. '
          'To expose advanced tools, choose Help > About OpenSayo, check Show Debug tab, then close About. Debug '
          'contains Form Designer, Dropdowns, Definitions, Explore Concepts, and Testing Tools (Compiled Macro, '
          'Keyboard Test, Device Programming and Diagnostics). Uncheck Show Debug tab in About to hide advanced tools '
          'again. Explore Concepts contains prototypes and future ideas: its demonstration controls are not working '
          'device-programming functions.'),
         ('Restore Your Own Field, Grid and Dropdown Definitions',
          'Start with a Form Project. Load File > Load Field List (.osfld) FIRST; this replaces the starter field '
          'definitions and preserves their stable IDs. Next use File > Load Form Layout (.oslay) to restore positions '
          'and visual labels. Layout import requires matching field IDs, so an unrelated field list will be rejected '
          'instead of silently moving fields. Finally choose Debug > Dropdowns > Load Lists (.osdrp) if you have a '
          'separate dropdown file. Choose Merge Libraries to keep lists already loaded, or Replace Entire Library only '
          'if you intend to remove existing lists. A field-list file may already include dropdown libraries. As '
          'alternatives, File > Load Form Format (.osfrm) can restore a combined preset, and File > Open Project '
          '(.osayo) restores a saved working project. After loading, inspect the Form View, field types, endpoints and '
          'dropdown choices; these imports never program hardware. Keep configurations that contain private labels or '
          'record details on your own machine and out of public releases.'),
         ('Field View, Form View and Macro Viewer',
          "Field View is the editable form list in macro Tab order. Change a field's value, format, option or Navigate "
          'setting there, and choose Open Form View to see the same fields in a separate visual layout. Changes to the '
          'same field are synchronized between these views. Macro Viewer displays generated Raw Text Preview and Sayo '
          'Script for the selected keys; those previews are read-only in a Form Project. Copy Key 1 or Copy Key 2 to '
          'use the generated script elsewhere. Use a Freeform Macro workspace to change script actions directly; its '
          "text is not the Form Project's source of truth. The visual column placement is independent of the field's "
          'Tab order.'),
         ('Field Types — Text, Drop Down, Date and Skip',
          'Text types the entered characters with their exact capitalization. Drop Down uses a selected library value, '
          'either typing it directly or sending a separately configured Navigate Keys sequence. Date supports Blank, '
          "MM/DD/YY (type a validated date), and Today's Date (send Down then Enter for a compatible calendar "
          "control). Today's Date works from the configured field option, not from any particular field name. Skip "
          'emits no value or special action but leaves the usual Tab step when another field follows. Validate date '
          'formatting and target-control behavior on a harmless test screen. None of these field names or actions '
          'identifies a particular external form by default.'),
         ('Enable or Disable a Field — Label-Only Mode',
          'In Field View, use the Use checkbox beside a field. Checked means the field is active; '
          'unchecked makes it label-only in Form View, showing its label instead of a text box, dropdown, '
          'or date input. Manage Fields lets you edit field names, formats and layout settings. '
          'A disabled field retains its original field ID, grid '
          'position, settings and saved value, but generates no text, date, dropdown or custom action. '
          'IMPORTANT: it still contributes the normal Tab transition when another macro field follows, '
          'keeping subsequent fields aligned. There is no extra Tab after the endpoint. Recheck Use in Field '
          'View to restore its previous settings and input. An Add Label Only item created in Grid Mode is '
          'different: it is a visual caption with NO macro Tab step. Older definition files without an '
          'Enabled setting default to enabled.'),
         ('Form Designer — Grid, Field List and Layout',
          'Enable Debug through Help > About OpenSayo, then open Debug > Form Designer. Choose a grid size '
          '(three to eight columns) and Apply Grid Size; add rows or fields as needed. Open Grid Mode to '
          'position fields by selecting or dragging them into cells; occupied cells can swap. Shift/Ctrl-click '
          'selects multiple fields, Ctrl+A selects all, and Unload Selected Fields removes them from the '
          'visual grid WITHOUT deleting macro steps. Toggle Half Height changes the selected field tile; '
          'Add Label Only and Remove Label change purely visual captions. To make a macro field label-only, '
          'uncheck Use in Field View; its grid position and macro Tab step stay the same. '
          'Manage Fields lets you rename, add, '
          'remove and set field formats/options; Use is managed separately in Field View. Add Field After '
          'Selected inserts a new Tab-order step; Remove Selected Field deletes that step after confirmation. '
          'Layout changes alone do not reorder the keyboard sequence. Save/Load Grid Layout operates on '
          '.oslay; Save/Load Fields operates on .osfld; Save/Load Form Format (.osfrm) packages a combined '
          'preset. Reset Defaults replaces the current configuration with 25 generic fields and clears '
          'custom lists; save your work first.'),
         ('Key 1 / Key 2 Endpoints and Handoff (2-Key Layout)',
          'In 2-Key layout, Key 1 endpoint is the last form field handled by the first script; Key 2 endpoint marks '
          'where the second script stops. The endpoints use the numerical field Tab order, not screen columns. Key 2 '
          'must begin from the position left by Key 1; handoff navigation can differ depending on which actions ran. A '
          'disabled field keeps its Tab position even though its own action is skipped. Switching endpoint values '
          'changes the generated scripts, so review both previews and test the combined sequence in a safe editor '
          'before attempting device programming. Setting Key 2 Script to Off / Not loaded makes the second script '
          'inactive without deleting your definitions.'),
         ('Dropdown Libraries and Navigation Keys',
          'To create or edit lists, enable Debug and choose Debug > Dropdowns: Create List, select a library, then '
          'enter one value per line. Use Save Lists (.osdrp) to keep a reusable copy. In Field View, select Drop Down, '
          'choose a library and a value. With Navigate unchecked the macro TYPES that exact value (including case). '
          'With Navigate checked it runs the recorded sequence from Navigate Keys... instead. Record navigation while '
          'focused in its capture box, Stop Recording and Save Navigate Keys, or edit the command list manually. The '
          'navigation editor supports arrow/navigation keys such as Down, Up, Enter, Tab, Escape, Home, End, PageUp '
          'and PageDown. Dropdown opening delay inserts a pause after the first Down in a configured navigation '
          'sequence. Different applications respond differently: always test with a non-sensitive example.'),
         ('Date Actions and Calendar Behavior',
          "For a date field, select Date and choose Blank, MM/DD/YY or Today's Date. Blank leaves the value empty. "
          "MM/DD/YY validates an entered calendar date and types it rather than opening a picker. Today's Date sends "
          'Down then Enter to a compatible calendar control; this may choose today only if that control interprets '
          'those keys that way. The field may be named Date, Arrival or anything else; its label does not trigger the '
          'action. Clear the Use checkbox to omit its date action while retaining its Tab position. There is no '
          'automatic guarantee that a third-party date picker will react correctly—verify it on a safe form.'),
         ('Freeform Editor — Typed Text, Keys and Recording',
          'File > New Freeform Macro opens the separate Freeform workspace. Type ordinary text directly and use Insert '
          'Key, Insert Tab or Insert Enter for navigation tokens. Record Keys... opens a LOCAL recorder; click Start, '
          'type with the capture box focused; each captured key or navigation token appears immediately in that box. ' 'Click Stop, review the action list, then Apply Script. It does not monitor system-wide typing. '
          'Use Apply Script to compile your editable text into Sayo commands, and Validate Script before exporting or '
          'writing. Paste Sayo Macro and Decode to Human-Readable can turn supported raw scripts into an editable '
          'approximation; importing a raw script preserves its original instructions until you edit and regenerate. '
          'The editor supports editable typed text runs, but unknown commands or exact original timing may not '
          'round-trip through the readable view. Save the project before attempting a conversion or replacement.'),
         ('Macro Viewer, Timing and Waits',
          'Macro Viewer shows separate generated scripts and byte counts. Key hold (ms) sets key-press duration, After '
          'navigation (ms) sets delay after navigation, Repeated key gap (ms) separates repeated characters, and '
          'Dropdown opening (ms) pauses after the first Down in a dropdown navigation sequence. Click Apply Timing to '
          'Key after editing timing values; current Form Project timing is shared, so both generated key previews can '
          "change, despite the button's name. Defaults are 15 ms hold, 20 ms after navigation, 15 ms repeat gap and 75 "
          'ms dropdown opening. Freeform exposes the same timing controls as Macro Viewer plus a Wait (ms) / Insert Wait action. Apply Timing to Key updates the local readable macro preview without programming a device. For explicit waits, Freeform supports WAIT tokens (for example {WAIT:100}). Check the '
          'actual generated commands and capacity after every timing change.'),
         ('Settings, Local Session and Reset',
          'File > Settings lets you change typing delay, navigation delay and repeated-character gap. The window notes '
          'that changes are autosaved locally. Restore timing defaults uses the same built-in starting values as '
          'Macro Viewer: 15 ms typing/key hold, 20 ms navigation and 15 ms repeated-character gap. The reset also '
          'updates the Macro Viewer fields and generated previews; it does not program a connected device. The '
          'separate 75 ms dropdown opening setting is unchanged. A prior local session may '
          'reopen automatically. File > Save Project preserves a separate named .osayo copy; save one before clearing '
          'your session. Debug > Form Designer > Reset Defaults discards the current form setup in favor of the '
          'generic starter, so back up your personal fields/layout/dropdowns first.'),
         ('Caps Lock, Case Sensitivity and Keyboard Focus',
          'Text and dropdown choices preserve case. The main window shows a Caps Lock status warning. The optional '
          "Field View setting 'Use Caps Lock at macro start/end' expects Caps Lock to be OFF before the macro begins; "
          'an interruption can leave the state changed, so treat this as experimental and test first. The app sends '
          'keyboard input to the focused target; it cannot reliably tell whether the correct external control is '
          'focused. Test in a harmless editor before using a complex macro. Keyboard Test under Debug > Testing Tools '
          'records input into its own focused text area—it is not a simulation of an external application.'),
         ('2-Key and 8-Key Layouts — What Changes',
          'Use the 2-Key or 8-Key radio button above the editor to select the relevant layout. This changes the '
          'controls and capacity display; switching it does NOT detect a model, move scripts or program the attached '
          'device. In 2-Key layout, select the script banks and physical key assignments, and choose which key you are '
          'editing. The two displayed key meters use a 468-byte encoded script safety limit each. In 8-Key layout, '
          'choose a destination Script 0–63 in the Key Script picker; the original Form, Macro Viewer and Freeform '
          'editors remain the only editors. The eight-key meter follows the selected script and shows a 2028-byte '
          'observed limit including the required terminator. A script slot is not the same thing as a physical key: a '
          'separate assignment maps each of the eight physical buttons to a script slot.'),
         ('8-Key Device Management and Assignments',
          'In 8-Key layout, Device Management... opens the assignment window for eight physical keys. Read All 8 From '
          'Device requests the current mapping; Compare Selections compares it with the choices on screen; Apply '
          'Selections attempts an experimental change to all eight mappings and saves it to the device after '
          'confirmation. In the main 8-Key toolbar, Import Script loads a file into the active editor, Load Focused '
          'Key from Device is a guarded read test for the selected slot, and Save Focused Key to Device is a confirmed '
          'write to that selected slot. The 0–63 slot picker only selects a destination; it does not automatically '
          'load a script. Supported readback actions populate Field View with matching macro instructions and preserve ' 'the exact original Sayo command timing until a field or timing is edited. If the form cannot represent ' 'a script, loading is rejected without changing the existing editor or byte meter; Freeform supports ' 'more general instructions. Back up a known-good configuration and verify readback and physical key output after any '
          'programming action. Some model/slot read behavior remains under review.'),
         ('Device Programming — Before You Write',
          'Editing a script, copying/exporting it, saving a .osayo project, selecting a physical key, and writing to '
          'USB are DIFFERENT actions. Close other device-programming software first. Confirm the connected device '
          'model, target physical key and intended script bank/slot. Save a backup, inspect the generated script, '
          "check the byte meter and use a harmless test macro first. 'Load Focused Key from Device' is a read attempt, "
          "while 'Save Focused Key to Device' is a write. The advanced Debug > Testing Tools > Device Programming page "
          'contains guarded Key 1 and diagnostic controls; some 2-Key functions remain experimental or disabled. Never '
          'assume a connected indicator, a completed UI action, or a successful USB transfer proves the right script '
          'is stored. Read back and physically test after unplug/reconnect. Stop if the device behaves unexpectedly.'),
         ('Alternative Website Compiler — Optional',
          'Macro Viewer includes Copy Key 1, Copy Key 2 and an Open Sayo Website Compiler link as a fallback if direct '
          'device programming is unavailable. Copying a script or opening this link does not write to the keypad. The '
          'website is a separate service and may have different command support or saving limitations. OpenSayo is '
          'designed to edit and compile locally; using an external website is optional and may involve sharing the '
          'script contents with that service. Do not paste private record values, passwords or other sensitive '
          'information into a third-party site without appropriate approval.'),
         ('Assignment Warning and Capacity Limits',
          "The red 'Please verify key script assignments' notice means physical mapping has not been reliably "
          'confirmed. Merely selecting a script, changing layout or detecting USB presence does not clear that risk. A '
          "script's ENCODED byte count is not the same as its typed character count. The 2-Key editor uses a 468-byte "
          'safety cutoff per script; the 8-Key script writer uses a 2028-byte observed upper bound including its '
          'terminator. Oversized scripts should fail validation or be blocked from writing. Simplify the macro, '
          'shorten timing or deliberately split actions, and confirm that each segment starts with the correct '
          'keyboard focus. These capacities are model/protocol-specific safeguards, not promises for every compatible '
          'keypad.'),
         ('File Formats and Save/Export Differences',
          'File > Save Project / Save Project As writes a .osayo working project. File > Save Form Format writes a '
          'combined .osfrm preset; Save Field List writes an .osfld field preset (without form entry values), and Save '
          'Form Layout writes an .oslay visual placement preset. Debug > Dropdowns > Save Lists writes .osdrp library '
          'choices. File > Export Key 1 Script, Export Key 2 Script or Export Selected Script writes raw .sayo script '
          'text; Import Key 1/Key 2 Script reads .sayo files. Freeform also has its own Save Macro action. The UI does '
          'not offer a separate export command for every historic extension that may appear in old notes. Saving or '
          'exporting to disk never programs a physical keypad, and a project file may contain user-entered '
          'values—review it before sharing.'),
         ('Debug Testing Tools, Diagnostics and Reference Definitions',
          'Under Debug > Testing Tools, Compiled Macro shows the generated bytecode preview, Keyboard Test captures '
          'keys only while its text box has focus, and Device Programming contains guarded hardware actions. '
          'Diagnostics also includes read-only, offline comparison and protocol-audit utilities; clearly labeled live '
          'read operations access a connected device only after you initiate them. Debug > Definitions imports/exports '
          'JSON reference profiles for device command names and identifiers. Those profiles are DOCUMENTATION ONLY: '
          'importing JSON does not automatically enable unknown compiler commands or write anything to hardware. Debug '
          '> Explore Concepts contains design mockups, not finished features.'),
         ('Common Problems and Safe Recovery',
          'Missing field names or dropdowns after a clean start? Import your own .osfld first, then matching .oslay, '
          "then .osdrp if needed. Layout rejected? The file's field IDs must match the loaded field definitions. A "
          'disabled field showing only a label? Check Use in Field View. A blank date '
          'action? Check the Date option and whether the field is enabled. Macro preview differs from expected typing? '
          'Verify endpoint order, Caps Lock, dropdown Navigate setting, timing and input focus. Assignment warning '
          'still red? Treat mappings as unconfirmed and run verified readback/tests rather than clearing the warning '
          'by assumption. If a script exceeds capacity, reduce actions; never try an unverified write workaround. Save '
          'backups before Reset Defaults, replacing dropdown libraries, importing a project or programming a device. '
          'If an older .osayo file is unsupported, Open Project shows a friendly notice without replacing the current '
          'workspace. Import current field (.osfld), grid (.oslay), and dropdown (.osdrp) definition files instead.'),
         ('Independent Project and Support',
          'OpenSayo is a personal, independently developed programmable-keypad utility. It contains no preconfigured '
          'third-party business form, and users can load private definitions locally when needed. This public Help '
          'does not include those configurations. For suggestions, comments or concerns, email '
          "dvangilder.work@gmail.com. The About window contains the creator's full Independent Project Notice, contact "
          'information and GitHub link.')]
        body.insert("end","OpenSayo Help & Quick Reference\n","title")
        top_mark=body.index("end-1c")
        body.insert("end","Contents — click a topic to jump to it\n","heading")
        body.tag_add("help_top",top_mark,body.index("end-1c"))
        for idx,(heading,_) in enumerate(sections):
            tag=f"toc_{idx}"
            body.insert("end",f"{idx+1}. {heading}\n",("toc",tag))
            body.tag_bind(tag,"<Button-1>",lambda event,n=idx: body.see(f"section_{n}.first"))
            body.tag_bind(tag,"<Enter>",lambda event: body.configure(cursor="hand2"))
            body.tag_bind(tag,"<Leave>",lambda event: body.configure(cursor=""))
        body.insert("end","\n")
        for idx,(heading,content) in enumerate(sections):
            start=body.index("end-1c")
            body.insert("end",f"{idx+1}. {heading}\n","heading")
            body.tag_add(f"section_{idx}",start,body.index("end-1c"))
            body.insert("end",content+"\n","body")
            tag=f"back_{idx}"
            body.insert("end","Return to Top ↑\n\n",("toc",tag))
            body.tag_bind(tag,"<Button-1>",lambda event:body.see("help_top.first"))
            body.tag_bind(tag,"<Enter>",lambda event:body.configure(cursor="hand2"))
            body.tag_bind(tag,"<Leave>",lambda event:body.configure(cursor=""))
        body.tag_configure("email",foreground="#1269bd",underline=True)
        start=body.search("dvangilder.work@gmail.com","1.0")
        if start:
            end=f"{start}+{len('dvangilder.work@gmail.com')}c"
            body.tag_add("email",start,end)
            import webbrowser
            body.tag_bind("email","<Button-1>",lambda e:webbrowser.open("mailto:dvangilder.work@gmail.com"))
            body.tag_bind("email","<Enter>",lambda e:body.configure(cursor="hand2"))
            body.tag_bind("email","<Leave>",lambda e:body.configure(cursor=""))
        body.tag_configure("search_hit",background="#fff0a8",foreground="#161616")
        def _find_help(event=None):
            query=search_term.get().strip()
            body.tag_remove("search_hit","1.0","end")
            if not query:
                search_status.set("Enter text to search")
                return "break"
            # Find next match after the insertion cursor, wrapping to start.
            begin=body.index("insert")
            found=body.search(query,begin,stopindex="end",nocase=True)
            if not found:
                found=body.search(query,"1.0",stopindex=begin,nocase=True)
            if found:
                end=f"{found}+{len(query)}c"
                body.tag_add("search_hit",found,end)
                body.mark_set("insert",end)
                body.see(found)
                search_status.set("Match found · Enter for next")
            else:
                search_status.set("No match")
            return "break"
        ttk.Button(search_row,text="Find Next",command=_find_help).pack(side="right",padx=(5,0))
        search_entry.bind("<Return>",_find_help)
        win.bind("<Control-f>",lambda event:(search_entry.focus_set(),search_entry.select_range(0,"end"),"break")[-1])
        win.bind("<Escape>",lambda event:win.destroy())
        body.configure(state="disabled")
        def _help_wheel(event):
            if event.delta: body.yview_scroll(-int(event.delta/120),"units")
            return "break"
        body.bind("<MouseWheel>",_help_wheel)
        scrollbar.bind("<MouseWheel>",_help_wheel)

    def _attach_mascot_tooltip(self, widget):
        # Hover label only; the original mascot image is not edited.
        def enter(event):
            if getattr(widget,"_tip",None) is not None: return
            tip=tk.Toplevel(widget)
            tip.wm_overrideredirect(True)
            tip.wm_geometry(f"+{event.x_root+14}+{event.y_root+12}")
            tk.Label(tip,text="RIP Shinobi, the bestest boy.\n9/3/15 - 9/19/25",
                     background="#fff6d9",relief="solid",borderwidth=1,
                     padx=9,pady=5,justify="center").pack()
            widget._tip=tip
        def leave(event):
            tip=getattr(widget,"_tip",None)
            if tip is not None:
                tip.destroy();widget._tip=None
        widget.bind("<Enter>",enter)
        widget.bind("<Leave>",leave)

    def _show_about(self):
        if self._raise_dialog("about_window"): return
        win=tk.Toplevel(self.root);self.about_window=win
        win.title("About OpenSayo");win.resizable(False,False);win.transient(self.root)
        # About-only easter egg. No USB, scripts, sound, or network activity.
        konami=("Up","Up","Down","Down","Left","Right","Left","Right","b","a")
        sequence=[]
        def secret_key(event):
            key=event.keysym.lower() if len(event.keysym)==1 else event.keysym
            sequence.append(key)
            if len(sequence)>len(konami): sequence.pop(0)
            if tuple(sequence)==konami:
                sequence.clear()
                if self.scream_mode.get():
                    self._show_retro_easter_egg(win)
        win.bind("<KeyPress>",secret_key)

        frame=ttk.Frame(win,padding=16);frame.pack(fill="both",expand=True)
        # The About image is decoded in memory; no loose PNG is shipped.
        if True:
            try:
                from shinobi_embedded import photo_bytes
                import base64
                mascot=tk.PhotoImage(data=base64.b64encode(photo_bytes()).decode("ascii"))
                win._opensayo_mascot=mascot
                mascot_label=ttk.Label(frame,image=mascot)
                mascot_label.pack(side="left",anchor="n",padx=(0,14))
                self._attach_mascot_tooltip(mascot_label)
            except tk.TclError: pass
        details=ttk.Frame(frame);details.pack(side="left",fill="both",expand=True)
        ttk.Label(details,text="OpenSayo",font=("Segoe UI",18,"bold")).pack(anchor="w")
        ttk.Label(details,text=f"Version: {VERSION}").pack(anchor="w",pady=(5,2))
        ttk.Label(details,text="Compiled by David VanGilder using ChatGPT (GPT-6).",wraplength=440).pack(anchor="w",pady=(4,5))
        ttk.Label(details,text="For suggestions, comments, concerns or anything else please email:",wraplength=510).pack(anchor="w",pady=(5,0))
        self._email_link(details)
        ttk.Label(details,text="GitHub — Source Code, Updates & Bug Reports",font=("Segoe UI",9,"bold")).pack(anchor="w",pady=(8,1))
        github_url="https://github.com/VanGilDev/OpenSayo"
        github_link=ttk.Label(details,text=github_url,foreground="#1269bd",cursor="hand2")
        github_link.pack(anchor="w",pady=(0,4))
        github_link.bind("<Button-1>",lambda event:webbrowser.open(github_url,new=2))
        ttk.Label(details,text="Independent Project Notice",font=("Segoe UI",10,"bold","underline")).pack(anchor="w",pady=(7,3))
        # User-approved wording. Keep this personal notice separate from generic
        # project-form names; editable definitions do not depend on About text.
        ttk.Label(details,text=INDEPENDENT_PROJECT_NOTICE,wraplength=510,justify="left").pack(anchor="w",pady=(0,6))
        ttk.Label(details,text="Copyright © 2026 VanGilDev",wraplength=440).pack(anchor="w",pady=(4,0))
        ttk.Label(details,text="Licensed under the MIT License",wraplength=440).pack(anchor="w",pady=(2,0))
        ttk.Checkbutton(details,text="Show Debug tab",variable=self.show_debug,command=self._toggle_debug).pack(anchor="w",pady=(8,0))
        ttk.Button(details,text="Close",command=win.destroy).pack(anchor="e",pady=(12,0))
        # Size to actual requested content, not a fixed height with a dead gap.
        # Allow a modest buffer for native Windows DPI/font differences.
        win.update_idletasks()
        width=max(720, min(win.winfo_screenwidth()-80, win.winfo_reqwidth()+18))
        height=min(win.winfo_screenheight()-90, win.winfo_reqheight()+14)
        win.geometry(f"{width}x{height}")

    def _show_retro_easter_egg(self, parent):
        """Center a silent, deliberately gaudy 1997 overlay inside About."""
        if not self.scream_mode.get():
            return
        existing=getattr(self,"_retro_window",None)
        try:
            if existing is not None and existing.winfo_exists():
                existing.lift()
                return
        except tk.TclError:
            pass
        # A child Frame, not a second window: the joke lives in the middle of About.
        win=tk.Frame(parent,bg="#000080",highlightbackground="#00ffff",highlightthickness=4,bd=3,relief="ridge")
        self._retro_window=win
        win.place(relx=0.5,rely=0.5,anchor="center",width=620,height=365)
        win.lift()
        banner=tk.Label(win,text="★ WELCOME TO OPENSAYO ★",bg="#ffeb00",fg="#ff0000",font=("Comic Sans MS",19,"bold"),pady=7)
        banner.pack(fill="x",padx=7,pady=(7,3))
        skull=tk.Label(win,text="💀  ☠  💀",bg="#000080",fg="#ffffff",font=("Segoe UI Emoji",28,"bold"))
        skull.pack(pady=0)
        flames=tk.Label(win,text="🔥🔥 UNDER CONSTRUCTION 🔥🔥",bg="#000080",fg="#ff9900",font=("Comic Sans MS",15,"bold"))
        flames.pack(pady=1)
        tk.Label(win,text="BEST VIEWED IN NETSCAPE NAVIGATOR 4.0",bg="#000080",fg="#00ffff",font=("Courier New",11,"bold")).pack(pady=3)
        visits=getattr(self,"_retro_visits",0)+1
        self._retro_visits=visits
        tk.Label(win,text=f"YOU ARE VISITOR #{visits:06d}",bg="#000000",fg="#00ff00",font=("Courier New",12,"bold"),padx=8,pady=3).pack(pady=3)
        # A fake vintage MIDI player: animated visual only, absolutely no audio.
        midi=tk.Frame(win,bg="#c0c0c0",bd=2,relief="raised")
        midi.pack(pady=(4,2),padx=35,fill="x")
        tk.Label(midi,text="♫ MIDI PLAYER 1997  [▶ PLAYING]  [MUTED]",bg="#c0c0c0",fg="#000080",font=("Courier New",10,"bold")).pack(pady=(2,0))
        bars=tk.Label(midi,text="▂ ▅ ▇ ▃ ▆ ▂ ▄ ▇ ▅ ▃ ▆ ▂",bg="#000000",fg="#00ff00",font=("Consolas",13,"bold"))
        bars.pack(fill="x",padx=10,pady=(1,3))
        tk.Label(win,text="No sound • No internet • No device changes • Just 1997",bg="#000080",fg="#ffffff",font=("Segoe UI",8)).pack()
        tk.Button(win,text="EXIT THE 90s",command=win.destroy).pack(pady=(4,3))
        frames=[("#ffeb00","#ff0000","💀  ☠  💀","🔥🔥 UNDER CONSTRUCTION 🔥🔥","▂ ▅ ▇ ▃ ▆ ▂ ▄ ▇ ▅ ▃ ▆ ▂"),
                ("#ff7700","#000000","☠  💀  ☠","🔥  UNDER CONSTRUCTION  🔥","▇ ▃ ▂ ▆ ▄ ▇ ▅ ▂ ▆ ▃ ▇ ▄")]
        def animate(tick=0):
            try:
                if not win.winfo_exists(): return
                bg,fg,sk,fl,equalizer=frames[tick%2]
                banner.configure(bg=bg,fg=fg)
                skull.configure(text=sk,fg=bg)
                flames.configure(text=fl,fg=bg)
                bars.configure(text=equalizer)
                win.after(500,lambda:animate(tick+1))
            except tk.TclError: return
        animate()

    def _key2_handoff_tabs(self,project):
        """Calculate navigation from the real Key 1 script cursor, not an endpoint guess."""
        script=self._key_scripts.get(1,"EXIT")
        try:
            readable,_=script_to_readable(self._ensure_exit(script))
            cursor=readable.count("{TAB}")
        except Exception:
            cursor=project["endpoint"]
        return max(0,project["endpoint"]+1-cursor)

    def _macro_form_readable(self):
        """Mirror the form's active endpoint and navigation.
        No key is sent to the OS/device. The website script is generated separately.
        """
        project=self.current_project()
        parts=[]
        for i in range((0 if self.focused_key.get()==1 else project["endpoint"]+1), (project["endpoint"] if self.focused_key.get()==1 else project["key2_endpoint"])+1):
            field=project["fields"][i]
            mode=field.get("format_type","Text")
            option=field.get("format_option","")
            if not field_is_enabled(field):
                pass
            elif mode=="Date" and option=="Blank":
                pass
            elif mode=="Date" and option=="Today's Date":
                parts.extend(("{DOWN}","{ENTER}"))
            elif mode in ("Text","Drop Down") or (mode=="Date" and option=="MM/DD/YY"):
                parts.append(field["value"])
            if i<(project["endpoint"] if self.focused_key.get()==1 else project["key2_endpoint"]):
                parts.append("{TAB}")
        if self.focused_key.get()==2:
            parts.insert(0,"{TAB}"*self._key2_handoff_tabs(project))
        return "".join(parts)

    def _macro_pull_from_form(self,force=False):
        try:
            new_text=self._macro_form_readable()
            old=self.macro_readable.get("1.0","end-1c")
            if old and old!=getattr(self,"_macro_last_form_text",None) and old!=new_text:
                if not force:
                    self.macro_status.set("Form changed. Readable macro has manual edits; use Pull from Form to refresh.")
                    return
                if not messagebox.askyesno("Replace readable macro?","Replace your edited readable macro with the current form? The Sayo script below will not be overwritten."):
                    return
            self._macro_sync_lock=True
            self.macro_readable.delete("1.0","end")
            self.macro_readable.insert("1.0",new_text)
            self._macro_sync_lock=False
            self._macro_generate(silent=True)
            self._macro_last_form_text=new_text
            self.macro_status.set(f"Loaded form through: {self.project['fields'][self.endpoint.get()]['name']}. Click Generate Sayo Script when ready.")
        except Exception as exc:
            self.macro_status.set("Could not pull form: "+str(exc))

    def _insert_readable_token(self,token):
        self.macro_readable.insert("insert",token)
        self.macro_readable.focus_set()

    def _macro_generate(self,silent=False):
        try:
            text=self.macro_readable.get("1.0","end-1c")
            # Empty readable editor produces an empty script (no textual EXIT).
            script=compile_sayo_text(text,int(self.macro_key_ms.get()),int(self.macro_nav_ms.get()),int(self.macro_repeat_ms.get()))
            validate_script(script)
            existing=self.macro_text.get("1.0","end-1c")
            if not silent and existing.strip() and existing.strip()!=script.strip():
                if not messagebox.askyesno("Replace Sayo script?","This replaces the script in the lower pane. Save or copy any existing script first. Continue?"):
                    return
            self._macro_sync_lock=True
            self.macro_text.delete("1.0","end");self.macro_text.insert("1.0",script)
            self._macro_sync_lock=False
            self.macro_text.edit_modified(False)
            self._macro_last_generated=script
            self._key_scripts[self.focused_key.get()]=script
            self._sync_freeform(script,force=True)
            mapped=self._sync_raw_to_form(script)
            self._render_key_previews()
            self.macro_status.set(f"Generated {len(script.splitlines())} Sayo commands. " + ("Form synchronized." if mapped else "Form preserved: " + getattr(self,"_macro_form_sync_error","unsupported actions")))
        except Exception as exc:
            if silent:self.macro_status.set("Sayo generation pending: "+str(exc))
            else:messagebox.showerror("Generate Sayo script",str(exc))

    def _macro_readable_enter(self,event=None):
        """Enter commits editor changes; only {ENTER} emits a keyboard Enter."""
        if self._macro_sync_job:
            self.root.after_cancel(self._macro_sync_job)
            self._macro_sync_job=None
        self._macro_generate(silent=True)
        return "break"

    def _macro_readable_changed(self,event=None):
        if self.workspace_kind == "form_project":return
        if self._macro_sync_lock:return
        if self._macro_sync_job:self.root.after_cancel(self._macro_sync_job)
        self._macro_sync_job=self.root.after(350,lambda:self._macro_generate(silent=True))

    def _macro_script_modified(self,event=None):
        if self.workspace_kind == "form_project":
            self.macro_text.edit_modified(False)
            return
        if self.macro_text.edit_modified():
            self.macro_text.edit_modified(False)
            self._macro_script_changed()

    def _macro_script_changed(self,event=None):
        if self.workspace_kind == "form_project":return
        if self._macro_sync_lock or self._editor_swap:return
        if self._macro_script_job:self.root.after_cancel(self._macro_script_job)
        self._editor_owner="raw"
        self._macro_script_job=self.root.after(450,self._macro_reverse)
        self.root.after_idle(self._validate_active_capacity)
        self.root.after_idle(self._freeform_from_macro)
        # Do not refresh from a partially edited script; commit after validation.

    def _validate_active_capacity(self):
        """Show overflow without reverting user edits or losing the script."""
        if self._editor_swap:
            return
        from alpha22_device_ops import encode_script
        key=self.focused_key.get()
        src=self.macro_text.get("1.0","end-1c")
        self._key_scripts[key]=self._ensure_exit(src)
        try:
            size=len(encode_script(self._ensure_exit(src)))
        except ValueError as exc:
            self.macro_status.set(f"Script not yet compilable: {exc}")
            self._refresh()
            return
        if size>SAFE_CUTOFF:
            self.macro_status.set(
                f"Key {key}: {size}/{SAFE_CUTOFF} bytes — OVER CAPACITY; "
                "device write blocked until reduced")
        else:
            self._last_valid_scripts[key]=self._ensure_exit(src)
        self._render_key_previews()
        self._refresh()

    def _macro_reverse(self, auto_apply=True):
        self._macro_script_job=None
        script=self.macro_text.get("1.0","end-1c")
        try:
            readable,count=script_to_readable(script)
            self._macro_sync_lock=True
            self.macro_readable.delete("1.0","end")
            self.macro_readable.insert("1.0",readable)
            self._macro_sync_lock=False
            self._macro_last_form_text=None
            self._macro_last_generated=script
            self._key_scripts[self.focused_key.get()]=self._ensure_exit(script)
            self._sync_freeform(script,force=True)
            mapped=self._sync_raw_to_form(script) if auto_apply else False
            self._render_key_previews()
            self.macro_status.set(f"Decoded {count} keystrokes. " + ("Form synchronized." if mapped else "Form preserved: " + getattr(self,"_macro_form_sync_error","not applied")))
        except Exception as exc:
            self.macro_status.set("Freeform retained; incomplete or unsupported script: "+str(exc))

    def _form_readback_signature(self,project,key):
        """Deterministic fingerprint of the exact fields and options for a key."""
        start=0 if key==1 else project["endpoint"]+1
        end=project["endpoint"] if key==1 else project["key2_endpoint"]
        inputs=[(f.get("value",""),f.get("format_type","Text"),
                 f.get("format_option",""),bool(f.get("enabled",True)),
                 bool(f.get("navigate",False)),f.get("navigate_keys",""))
                for f in project["fields"][start:end+1]]
        payload=(start,end,inputs,bool(project.get("use_caps_lock",False)),
                 project.get("text_delay_ms"),project.get("action_delay_ms"),
                 project.get("repeat_gap_ms"),project.get("dropdown_open_ms"))
        return hashlib.sha256(repr(payload).encode('utf-8')).hexdigest()

    def _install_raw_form_readback(self,key,source):
        """Retain exact hardware timing until the user actually changes the form."""
        project=self.current_project()
        if not hasattr(self,"_form_raw_readbacks"):
            self._form_raw_readbacks={}
        self._form_raw_readbacks[str(key)]={
            "source":self._ensure_exit(source),
            "signature":self._form_readback_signature(project,key)}

    def _device_form_candidate(self,source,key):
        """Build a complete form candidate before applying any readback data."""
        script= self._ensure_exit(source)
        validate_script(script)
        readable,_=script_to_readable(script)
        candidate=self.current_project()
        start=0 if key==1 else candidate["endpoint"]+1
        if start>=len(candidate["fields"]):
            raise ValueError("No available form fields for the selected key")
        rows,end_local=device_readback_form_rows(readable,len(candidate["fields"])-start)
        end=start+end_local
        for offset,(new_mode,new_option,text) in enumerate(rows):
            field=candidate["fields"][start+offset]
            old_mode=field.get("format_type","Text")
            old_option=field.get("format_option", "")
            # Keep compatible private definitions, including dropdown library
            # selections and date actions, without assuming arbitrary text fits.
            if old_mode=="Drop Down" and new_mode=="Text" and not ("{" in text or "}" in text):
                valid_values=candidate.get("dropdowns",{}).get(old_option,[])
                if text in valid_values or not text:
                    new_mode,new_option="Drop Down",old_option
            elif old_mode=="Date" and new_mode=="Text":
                if old_option=="MM/DD/YY" and valid_date(text):
                    new_mode,new_option="Date",old_option
                elif old_option=="Blank" and not text:
                    new_mode,new_option="Date",old_option
            elif old_mode=="Skip" and not text:
                new_mode,new_option="Skip",old_option
            field.update(format_type=new_mode,format_option=new_option,value=text,
                         format_values={"Text":text if new_mode=="Text" else "",
                                        "Date":text if new_mode=="Date" else "",
                                        "Drop Down":text if new_mode=="Drop Down" else ""},
                         navigate=False,navigate_keys="",
                         date_option_memory=new_option if new_mode=="Date" else field.get("date_option_memory","MM/DD/YY"))
            if text:field["enabled"]=True
        if key==1:
            candidate["endpoint"]=end
            candidate["key2_endpoint"]=max(end,candidate["key2_endpoint"])
        else:
            candidate["key2_endpoint"]=end
        # A dry-run against the real macro compiler validates the complete map.
        pieces=[]
        for offset,(mode,option,value) in enumerate(rows):
            if mode=="Date" and option=="Today's Date":pieces.append("{DOWN}{ENTER}")
            else:pieces.append(value)
            if offset<len(rows)-1:pieces.append("{TAB}")
        compile_sayo_text("".join(pieces),15,20,15)
        return candidate,readable,end

    def _apply_device_form_readback(self,source,key):
        """Atomically restore field values/actions and keep the raw Sayo script."""
        candidate,readable,end=self._device_form_candidate(source,key)
        self.apply(candidate)
        self._install_raw_form_readback(key,source)
        self._set_active_script(source,update_freeform=False)
        self._macro_sync_lock=True
        try:
            self.macro_readable.delete("1.0","end")
            self.macro_readable.insert("1.0",readable)
        finally:self._macro_sync_lock=False
        self._form_last_valid=self._form_snapshot()
        self._render_key_previews()
        return end

    def _sync_raw_to_form(self,script):
        """Apply readable device actions without dropping unsupported instructions.

        Safe on failure: the active raw script remains and the form is not
        partially modified. Shared by two-key reads and raw-script imports.
        """
        if self.workspace_kind!="form_project":return False
        try:
            key=self.focused_key.get()
            self._apply_device_form_readback(script,key)
            self._macro_form_sync_error=""
            return True
        except Exception as exc:
            self._macro_form_sync_error=str(exc)
            return False

    def _macro_form_mapping(self, readable=None):
        """Parse navigation by literal TAB tokens, independent of selected endpoint.

        EXIT is the Sayo-script terminator; {END} remains a real keyboard key.
        Never infer additional keystrokes from a visual end-of-macro marker.
        """
        if readable is None:readable=self.macro_readable.get("1.0","end-1c")
        # Text-widget line breaks are visual separators, not typed keys.
        # Remove them before mapping to single-line form fields.
        readable=readable.replace("\r", "").replace("\n", "")
        parts=readable.split("{TAB}")
        endpoint=len(parts)-1
        if endpoint>=len(self.field_definitions):
            raise ValueError(f"Macro reaches field {endpoint+1}, but this form defines only {len(self.field_definitions)} fields. The complete macro remains in the editor.")
        changes=[]
        for i,part in enumerate(parts):
            field=self.field_definitions[i]
            if (field.get("special_action")=="today_calendar" or
                (field.get("format_type")=="Date" and field.get("format_option")=="Today's Date")):
                if part not in ("{DOWN}{ENTER}","{DOWN}{ENTER}{END}") and not valid_date(part):
                    raise ValueError("Date action needs {DOWN}{ENTER} or a valid MM/DD/YY date to map into the form.")
                changes.append((i,part if valid_date(part) else "Down, Enter"))
            elif field["kind"]=="text":
                if "{" in part or "}" in part:
                    raise ValueError(f"Field {i+1} ({field['name']}) contains actions the form cannot represent.")
                changes.append((i,part))
            elif part:
                raise ValueError(f"Field {i+1} ({field['name']}) is navigation-only; cannot map {part!r}.")
        return endpoint,changes

    def _macro_auto_apply_form(self):
        """Move the form endpoint to the last field reached by TAB navigation."""
        if getattr(self,"_form_sync_job",None):
            self.root.after_cancel(self._form_sync_job)
            self._form_sync_job=None
        try:
            endpoint,changes=self._macro_form_mapping()
        except ValueError as exc:
            self._macro_form_sync_error=str(exc)
            return False
        self._macro_form_sync_error=""
        changed=self.endpoint.get()!=endpoint or any(self.field_vars[i].get()!=value for i,value in changes)
        if not changed:
            return True
        self._loading=True
        try:
            self.endpoint.set(endpoint)
            for i,value in changes:
                self.field_vars[i].set(value)
        finally:
            self._loading=False
        self._changed()
        if getattr(self,"form_preview_window",None) is not None and self.form_preview_window.winfo_exists():
            self.show_form_preview()
        return True

    def _macro_apply_to_form(self):
        """Explicitly apply the same tab-derived mapping used by autosync."""
        try:
            endpoint,changes=self._macro_form_mapping()
        except ValueError as exc:
            messagebox.showerror("Cannot map to form",str(exc))
            return
        if not messagebox.askyesno("Update Form?",f"Update fields through {self.field_definitions[endpoint]['name']} (field {endpoint+1}) using the macro's {endpoint} Tabs?"):
            return
        self._loading=True
        try:
            self.endpoint.set(endpoint)
            for i,value in changes:
                self.field_vars[i].set(value)
        finally:
            self._loading=False
        self._changed()
        self.macro_status.set(f"Form updated through field {endpoint+1} ({self.field_definitions[endpoint]['name']}).")

    def _macro_validate(self):
        try:
            count=validate_script(self.macro_text.get("1.0","end-1c"))
            self.macro_status.set(f"Syntax and key balance passed for {count} commands. Device compatibility still requires website testing.")
        except Exception as exc:messagebox.showerror("Script validation",str(exc))

    def _viewer_block_key(self,event):
        # Allow navigation, selection, copy and search shortcuts, but never mutations.
        if (event.state & 0x4) and event.keysym.lower() in ("c","a","f"):
            return None
        if event.keysym in ("Left","Right","Up","Down","Home","End","Prior","Next"):
            return None
        return "break"

    def _macro_copy_key(self,key):
        # Refresh from form first to avoid copying an outdated preview.
        if self.workspace_kind != "form_project":
            return
        self._sync_form_to_editor()
        content=self._key_scripts.get(key,"EXIT")
        try:
            validate_script(content)
        except Exception as exc:
            messagebox.showerror("Cannot copy invalid script",str(exc));return
        self.root.clipboard_clear()
        self.root.clipboard_append(content)
        self.root.update()
        self.macro_status.set(f"Copied Key {key} Sayo Script ({len(content)} characters).")

    def _macro_copy(self):
        content=self.macro_text.get("1.0","end-1c")
        try:validate_script(content)
        except Exception as exc:
            messagebox.showerror("Cannot copy invalid script",str(exc));return
        self.root.clipboard_clear();self.root.clipboard_append(content);self.root.update()
        self.macro_status.set(f"Copied {len(content)} characters. Paste into app.sayodevice.com script editor, then save using the website.")

    def _macro_open(self):
        filename=filedialog.askopenfilename(title="Open Sayo script",filetypes=[("Sayo scripts","*.sayo")])
        if not filename:return
        try:
            content=Path(filename).read_text(encoding="utf-8-sig")
            if self.macro_text.get("1.0","end-1c").strip() and not messagebox.askyesno("Replace script?","Replace the current lower-pane script?"):return
            validate_script(content)
            self._macro_sync_lock=True
            self.macro_text.delete("1.0","end");self.macro_text.insert("1.0",content)
            self._macro_sync_lock=False
            self.macro_text.edit_modified(False)
            self._macro_reverse()
            self.macro_status.set("Imported and decoded Sayo script; original commands/timing preserved: "+filename)
        except Exception as exc:messagebox.showerror("Open Sayo script",str(exc))

    def _macro_save(self):
        filename=filedialog.asksaveasfilename(title="Save Sayo script",defaultextension=".sayo",filetypes=[("Sayo scripts","*.sayo")])
        if not filename:return
        try:
            content=self.macro_text.get("1.0","end-1c")
            validate_script(content)
            Path(filename).write_text(content,encoding="utf-8")
            self.macro_status.set("Saved script: "+filename)
        except Exception as exc:messagebox.showerror("Save Sayo script",str(exc))

    def _macro_save_readable(self):
        filename=filedialog.asksaveasfilename(title="Save readable macro",defaultextension=".txt",filetypes=[("Text files","*.txt"),("All files","*.*")])
        if not filename:return
        try:
            Path(filename).write_text(self.macro_readable.get("1.0","end-1c"),encoding="utf-8")
            self.macro_status.set("Saved readable macro: "+filename)
        except Exception as exc:messagebox.showerror("Save readable macro",str(exc))

    def _macro_clear(self):
        if not messagebox.askyesno("Clear macro editor","Clear both editor panes? Save your scripts first."):return
        self.macro_text.delete("1.0","end");self.macro_readable.delete("1.0","end")
        self.macro_status.set("Both editor panes cleared")

    def _restore_date_default(self,event=None):
        # Keep an explicit visible default; never force it while someone is typing.
        i=self._date_action_index()
        if i is not None and not self.field_vars[i].get().strip():
            self.field_vars[i].set("Down, Enter")

    def _form_snapshot(self):
        return (tuple(v.get() for v in self.field_vars),self.endpoint.get(),self.key2_endpoint.get(),tuple(v.get() for v in self.format_vars),tuple(v.get() for v in self.option_vars),tuple(v.get() for v in self._navigate_vars),tuple(self._navigate_keys.get(i,"") for i in range(len(self._navigate_vars))),self.use_caps_lock.get())

    def _note_form_owner(self,index):
        if self._loading or self._form_reverting:return
        value=self.field_vars[index].get()
        if value!=self._form_previous_values.get(index):
            self._form_field_owners[index]=self.focused_key.get()
            self._form_previous_values[index]=value
            self._form_edit_pending=True
            self._schedule_form_fade()

    def _schedule_form_fade(self):
        """Coalesce repeated field updates when large forms are imported.

        Importing hundreds of fields previously queued one full-form visibility
        pass for every field, causing quadratic Tcl/Tk work and UI stalls.
        """
        if getattr(self,"_form_fade_job",None) is None:
            self._form_fade_job=self.root.after_idle(self._run_scheduled_form_fade)

    def _run_scheduled_form_fade(self):
        self._form_fade_job=None
        self._update_form_fade()

    def _update_form_fade(self):
        """Never hide values: only editability changes with key ownership."""
        if not hasattr(self,"_form_entries"):return
        eight_mode=self.layout_mode.get()=="8"
        key=self.focused_key.get()
        key2_enabled=self.key2_bank.get().isdigit()
        for i,entry in self._form_entries.items():
            editable=(i<=self.endpoint.get()) if eight_mode else (
                (key==1 and i<=self.endpoint.get()) or
                (key==2 and key2_enabled and self.endpoint.get()<i<=self.key2_endpoint.get()))
            # tkinter Entry's readonlybackground is reliable across Windows ttk themes.
            mode=self.format_vars[i].get()
            option=self.option_vars[i].get()
            owner_editable=editable
            if i in self._format_widgets:self._format_widgets[i].configure(state="readonly" if owner_editable else "disabled")
            if i in self._option_widgets:self._option_widgets[i].configure(state="readonly" if owner_editable and mode in ("Date","Drop Down") else "disabled")
            editable=editable and (mode=="Text" or (mode=="Date" and option=="MM/DD/YY"))
            if i in self._dropdown_controls:
                self._dropdown_controls[i].configure(state="readonly" if owner_editable else "disabled")
            entry.configure(state="normal" if editable else "readonly",
                            foreground="#111111" if editable else "#444444",
                            readonlybackground="#e5e5e5")
            self._sync_form_value_visibility(i)

    def _restore_form_snapshot(self,snapshot):
        if snapshot is None:return
        self._form_reverting=True
        self._loading=True
        try:
            values,endpoint,key2_endpoint,*extra=snapshot
            if extra:
                for var,val in zip(self.format_vars,extra[0]):var.set(val)
                for var,val in zip(self.option_vars,extra[1]):var.set(val)
            for var,value in zip(self.field_vars,values):var.set(value)
            self.endpoint.set(endpoint)
            self.key2_endpoint.set(key2_endpoint)
            self._accepted_key1_endpoint=endpoint
            self._form_previous_values={i:v.get() for i,v in enumerate(self.field_vars)}
        finally:
            self._loading=False
            self._form_reverting=False
        self._form_edit_pending=False
        self._update_form_fade()

    def _validate_form_capacity(self):
        """Keep oversized form edits; only device programming enforces capacity."""
        if not self._form_edit_pending:
            return True
        self._form_edit_pending=False
        try:
            _,required=self._compile_form_key(1)
        except Exception as exc:
            # Preserve incomplete edits and show the real compile error.
            self.macro_status.set(f"Form compile pending: {exc}")
            return True
        if required>SAFE_CUTOFF:
            self.macro_status.set(
                f"Key 1 OVER CAPACITY: {required}/{SAFE_CUTOFF} bytes; "
                "editing and project save allowed, device write blocked")
        return True

    def _form_changed(self,*_):
        """Form edits regenerate the authoritative macro, retaining field/TAB positions."""
        if self._loading or getattr(self,"_macro_sync_lock",False):
            return
        if getattr(self,"_form_sync_job",None):
            self.root.after_cancel(self._form_sync_job)
        self._form_sync_job=self.root.after(150,self._sync_form_to_editor)
        self.root.after_idle(self._refresh)
        # Preview entries share StringVars; rebuilding while typing would lose focus.

    def _sync_form_to_editor(self):
        self._form_sync_job=None
        if self._loading or self.workspace_kind=="freeform":return
        if not self._validate_form_capacity():
            self._refresh()
            return
        try:
            # Rebuild both device scripts from their current field ranges.
            # Endpoint transfers cannot leave stale data assigned to either key.
            compiled={1:self._compile_form_key(1)[0]}
            self._key_scripts[1]=compiled[1]
            compiled[2]=self._compile_form_key(2)[0]
            self._key_scripts.update(compiled)
            self._editor_owner="form"
            active=self.focused_key.get()
            self._macro_sync_lock=True
            try:
                self._set_active_script(compiled[active])
                self.macro_readable.delete("1.0","end")
                self.macro_readable.insert("1.0",self._macro_form_readable())
                self._macro_last_generated=compiled[active]
                self._macro_last_form_text=self._macro_form_readable()
            finally:
                self._macro_sync_lock=False
            self._render_key_previews()
            self._refresh()
            self._update_form_fade()
        except Exception as exc:
            self.macro_status.set("Form synchronization failed: "+str(exc))

    def _changed(self,*_):
        if self._loading:return
        if self._save_job:self.root.after_cancel(self._save_job)
        if self._meter_job:self.root.after_cancel(self._meter_job)
        self._save_job=self.root.after(500,self.save_session)
        self._meter_job=self.root.after(120,self._refresh)

    # Full application workspace management. Form and standalone Freeform data are
    # separate; switching workspaces never treats the Form's Freeform tab as a new project.
    def _validate_endpoint_move(self,*_):
        """Allow Key 1 endpoint growth beyond capacity, just like Key 2."""
        if self._loading or self._endpoint_guard or self._form_reverting:return
        proposed=self.endpoint.get()
        old=self._accepted_key1_endpoint
        if proposed==old:return
        self._accepted_key1_endpoint=proposed
        if self.key2_endpoint.get()<proposed:
            self._endpoint_guard=True
            try:self.key2_endpoint.set(proposed)
            finally:self._endpoint_guard=False
        self._update_form_fade()
        self._form_changed()

    def _validate_key2_endpoint_move(self,*_):
        if self._loading or self._endpoint_guard or self._form_reverting:return
        if self.key2_endpoint.get()<self.endpoint.get():
            self._endpoint_guard=True
            try:self.key2_endpoint.set(self.endpoint.get())
            finally:self._endpoint_guard=False
            messagebox.showwarning("Key 2 endpoint","Key 2 cannot end before Key 1.")
        self._update_form_fade()
        self.root.after_idle(self._refresh)

    def _key2_endpoint_from_dropdown(self,event=None):
        idx=self.key2_endpoint_picker.current()
        if idx>=0:self.key2_endpoint.set(idx)
        self._endpoint_sync_dropdown()

    def _endpoint_sync_dropdown(self,*_):
        if not hasattr(self,"endpoint_choice"):return
        idx=self.endpoint.get()
        if 0<=idx<len(self.field_definitions):
            label=f"{idx+1:02d}. {self.field_definitions[idx]['name']}"
            if self.endpoint_choice.get()!=label:self.endpoint_choice.set(label)
        if hasattr(self,"key2_endpoint_choice"):
            idx2=self.key2_endpoint.get()
            if 0<=idx2<len(self.field_definitions):
                label2=f"{idx2+1:02d}. {self.field_definitions[idx2]['name']}"
                if self.key2_endpoint_choice.get()!=label2:self.key2_endpoint_choice.set(label2)

    def _endpoint_from_dropdown(self,event=None):
        idx=self.endpoint_picker.current()
        if idx>=0 and idx!=self.endpoint.get():
            # Reuse the existing endpoint change validation and callbacks.
            self.endpoint.set(idx)
            self._endpoint_sync_dropdown()

    def _workspace_capture_form(self):
        scripts=dict(self._key_scripts)
        scripts[self.focused_key.get()]=self._ensure_exit(self.macro_text.get("1.0","end-1c"))
        return {"form":self.current_project(),"scripts":{str(k):v for k,v in scripts.items()},
                "key2_bank":self.key2_bank.get(),"key1_bank":self.device_bank.get(),
                "physical_key1":self.physical_key1.get(),"physical_key2":self.physical_key2.get()}

    def _workspace_snapshot(self):
        if self.workspace_kind=="freeform":
            return json.dumps({"kind":"freeform","script":self.macro_text.get("1.0","end-1c"),"readable":self.freeform_text.get("1.0","end-1c"),"destination":self.freeform_destination},sort_keys=True)
        return json.dumps({"kind":"form_project",**self._workspace_capture_form()},sort_keys=True)

    def _workspace_confirm_leave(self):
        if self._workspace_saved_snapshot==self._workspace_snapshot():return True
        answer=messagebox.askyesnocancel("Save changes before switching projects?",
                                         "Save changes before switching projects?")
        if answer is None:return False
        if answer and not self._workspace_save():return False
        return True

    def _workspace_activate(self,kind,form_data=None,script=None,readable=None):
        if kind not in ("form_project","freeform"):raise ValueError("Unknown workspace type")
        if self.workspace_kind=="form_project":
            self._form_workspace_cache=self._workspace_capture_form()
        else:
            self.freeform_standalone=self.macro_text.get("1.0","end-1c")
        self.workspace_kind=kind
        if kind=="form_project":
            data=form_data or self._form_workspace_cache or {"form":blank_project(),"scripts":{"1":"EXIT","2":"EXIT"}}
            self.apply(normalize_project(data["form"]))
            self._key_scripts={1:data.get("scripts",{}).get("1","EXIT"),2:data.get("scripts",{}).get("2","EXIT")}
            self.device_bank.set(data.get("key1_bank",self.device_bank.get()))
            self.key2_bank.set(data.get("key2_bank",self.key2_bank.get()))
            self.physical_key1.set(data.get("physical_key1",self.physical_key1.get()))
            self.physical_key2.set(data.get("physical_key2",self.physical_key2.get()))
            self.focused_key.set(self._preferred_focused_key if self.key2_bank.get().isdigit() else 1);self._previous_key=self.focused_key.get()
            self._set_active_script(self._key_scripts[self.focused_key.get()])
            self.book.tab(self.fields_tab,state="normal")
            self.book.add(self.macro_outer,text="Macro Viewer")
            self.book.hide(self.freeform_tab)
            self.debug_book.tab(self.dropdowns_tab,state="normal")
            # Workspace switches must honor the actual Show Debug preference.
            # Do not unconditionally re-add the tab after it was hidden.
            self._toggle_debug()
            self.book.select(self.fields_tab)
            self.workspace_label.configure(text="Form Project • Key 1 and Key 2")
        else:
            self._key_scripts[1]=self._ensure_exit(script if script is not None else self.freeform_standalone)
            self.focused_key.set(1);self._previous_key=1
            self._set_active_script(self._key_scripts[1])
            self.book.hide(self.fields_tab)
            self._close_form_preview()
            self.book.hide(self.macro_outer)
            self.debug_book.tab(self.dropdowns_tab,state="normal")
            self.book.add(self.freeform_tab,text="Freeform")
            self.book.select(self.freeform_tab)
            self.workspace_label.configure(text="Freeform Macro • independent standalone script")
        if kind=="freeform":
            if readable is None:
                try:readable,_=script_to_readable(self._key_scripts[1])
                except Exception:readable=""
            self.freeform_text.delete("1.0","end")
            self.freeform_text.insert("1.0",readable)
            self.freeform_text.edit_modified(False)
            self.root.after_idle(self._freeform_live_preview)
        self._update_key_switch()
        self._render_key_previews();self._refresh()

    def _workspace_new(self,kind):
        if not self._workspace_confirm_leave():return
        self._workspace_activate(kind,form_data={"form":approved_default_project(),"scripts":{"1":"EXIT","2":"EXIT"}} if kind=="form_project" else None,script="" if kind=="freeform" else None)
        self.workspace_path=None
        self._workspace_saved_snapshot=self._workspace_snapshot()

    def _workspace_save(self,as_new=False):
        name=self.workspace_path
        if as_new or not name:
            name=filedialog.asksaveasfilename(title="Save OpenSayo project",defaultextension=".osayo",
                    filetypes=[("OpenSayo projects","*.osayo")])
        if not name:return False
        try:
            if self.workspace_kind=="form_project":
                for idx in range(len(self.field_definitions)):
                    if self.format_vars[idx].get()=="Date" and self.option_vars[idx].get()=="MM/DD/YY":
                        value=self.field_vars[idx].get().strip()
                        if value and not valid_date(value):
                            raise ValueError(f"{self.field_definitions[idx]['name']} requires a real MM/DD/YY date")
            if self.workspace_kind=="freeform":
                generated=(self._freeform_source() if self.layout_mode.get()=="8" else
                    compile_sayo_text(self.freeform_text.get("1.0","end-1c"),int(self.macro_key_ms.get()),int(self.macro_nav_ms.get()),int(self.macro_repeat_ms.get())))
                from alpha22_device_ops import encode_script
                limit=EIGHT_SCRIPT_CAP if self.layout_mode.get()=="8" else SAFE_CUTOFF
                if len(encode_script(generated))+(1 if self.layout_mode.get()=="8" else 0)>limit:
                    raise ValueError(f"Freeform macro exceeds {limit}-byte device capacity")
                self._key_scripts[1]=generated
                self._editor_swap=True
                try:
                    self.macro_text.delete("1.0","end");self.macro_text.insert("1.0",generated)
                finally:self._editor_swap=False
            data=json.loads(self._workspace_snapshot())
            data["format"]="opensayo-v023";data["version"]=1
            target=Path(name);tmp=target.with_name(target.name+".tmp")
            with tmp.open("w",encoding="utf-8") as f:
                json.dump(data,f,indent=2,ensure_ascii=False);f.flush();os.fsync(f.fileno())
            tmp.replace(target)
            self.workspace_path=str(target)
            self._workspace_saved_snapshot=self._workspace_snapshot()
            return True
        except Exception as exc:
            messagebox.showerror("Save Project",str(exc));return False

    def _workspace_open(self):
        name=filedialog.askopenfilename(title="Open OpenSayo project",filetypes=[("OpenSayo projects","*.osayo")])
        if not name:return
        # Preflight BEFORE the save/discard prompt or any mutation. A rejected
        # file leaves the current project and its unsaved changes untouched.
        try:
            kind,form_data,script,readable=read_workspace_project(name)
        except UnsupportedProjectFormat:
            messagebox.showwarning("Unsupported Project Format",UNSUPPORTED_PROJECT_NOTICE)
            return
        except ValueError:
            messagebox.showerror("Cannot Open Project",UNREADABLE_PROJECT_NOTICE)
            return
        if not self._workspace_confirm_leave():return
        try:
            self._workspace_activate(kind,form_data=form_data,script=script,readable=readable)
            self.workspace_path=name
            self._workspace_saved_snapshot=self._workspace_snapshot()
        except Exception as exc:
            messagebox.showerror("Cannot Open Project",f"The project could not be opened: {exc}")

    def _workspace_export_script(self,key):
        script=self.macro_text.get("1.0","end-1c") if self.workspace_kind=="freeform" or key==self.focused_key.get() else self._key_scripts.get(key,"EXIT")
        name=filedialog.asksaveasfilename(title=f"Export Key {key} Script",defaultextension=".sayo",filetypes=[("Sayo scripts","*.sayo"),("Text","*.txt")])
        if not name:return
        try:
            validate_script(script)
            Path(name).write_text(script,encoding="utf-8")
        except Exception as exc:messagebox.showerror("Export Script",str(exc))

    def _workspace_import_script(self,key):
        if self.workspace_kind=="freeform":
            key=self.freeform_destination
        name=filedialog.askopenfilename(title=f"Import Key {key} Script",filetypes=[("Sayo scripts","*.sayo")])
        if not name:return
        try:
            script=Path(name).read_text(encoding="utf-8-sig")
            validate_script(script)
            old=self.macro_text.get("1.0","end-1c") if key==self.focused_key.get() else self._key_scripts.get(key,"EXIT")
            if old.strip() not in ("","EXIT") and not messagebox.askyesno("Replace existing script?",
                    f"Importing will replace Key {key}'s raw script. Existing form values are not deleted. Continue?"):
                return
            self._key_scripts[key]=self._ensure_exit(script)
            if self.workspace_kind=="freeform":
                # File Import and Paste Sayo Macro must populate the SAME Freeform
                # workspace. Keep the original script authoritative: the readable
                # translation is approximate and cannot retain arbitrary timings.
                self._set_active_script(self._key_scripts[key],update_freeform=False)
                try:
                    readable,_=script_to_readable(script)
                except ValueError:
                    readable=""
                self.freeform_text.delete("1.0","end")
                self.freeform_text.insert("1.0",readable)
                self.freeform_text.edit_modified(False)
                self._freeform_imported_raw=self._ensure_exit(script)
                self._freeform_live_preview()
                self.session_status.set("Imported original Sayo script; timing preserved. Readable text is a preview. Edit to regenerate.")
            elif key==self.focused_key.get():
                self._set_active_script(self._key_scripts[key]);self._macro_reverse()
            self._render_key_previews();self._refresh()
            if self.workspace_kind!="freeform":
                try:
                    legacy_script_fields(script)
                except ValueError:
                    self.macro_status.set("Raw script imported; Form unchanged because commands cannot be mapped safely")
                else:
                    self._import_legacy_to_form(script,key)
        except Exception as exc:messagebox.showerror("Import Script",str(exc))

    def _import_legacy_to_form(self,source,key=1):
        """Convert tab-delimited legacy script to editable form settings atomically."""
        if self.workspace_kind=="freeform":
            raise ValueError("Switch to a Form Project before importing a legacy form script")
        rows,local_endpoint=legacy_script_fields(source)
        candidate=self.current_project()
        start=0 if key==1 else candidate["endpoint"]+1
        end=start+local_endpoint
        if end>=len(self.field_definitions):raise ValueError("Imported script extends beyond the last form field")
        if key==1 and end>candidate["key2_endpoint"]:
            raise ValueError("Imported Key 1 endpoint would overlap Key 2; adjust Key 2 endpoint first")
        for offset,(mode,option,value) in enumerate(rows):
            f=candidate["fields"][start+offset]
            f["format_type"]=mode
            f["format_option"]=option
            f["value"]=value
            f["format_values"]={"Text":value if mode=="Text" else "", "Date":"", "Drop Down":""}
            f["date_option_memory"]=option if mode=="Date" else "MM/DD/YY"
        if key==1:candidate["endpoint"]=end
        else:candidate["key2_endpoint"]=end
        # Validate candidate against the same compiler/capacity limits as normal edits.
        if not messagebox.askyesno("Import legacy macro",f"Recognized {len(rows)} fields for Key {key}, ending at field {end+1} ({self.field_definitions[end]['name']}).\n\nConvert them to Text / Today's Date and replace those field settings? Other key settings will be preserved."):
            return False
        self.apply(candidate)
        self.save_session()
        return True

    def _export_form_format(self):
        """Portable form layout; does not export a compiled macro or device assignment."""
        if self.workspace_kind=="freeform":
            return messagebox.showinfo("Form format", "Switch to a Form Project to export a format.")
        filename=filedialog.asksaveasfilename(title="Save Form Format",defaultextension=".osfrm",filetypes=[("OpenSayo Form Format","*.osfrm")])
        if not filename:return
        try:
            project=self.current_project()
            data={"file_type":"opensayo_form_format","format_version":1,
                  "endpoint":project["endpoint"],"key2_endpoint":project["key2_endpoint"],
                  "fields":project["fields"],"layout":project["layout"],"dropdowns":project.get("dropdowns",{})}
            Path(filename).write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding="utf-8")
            messagebox.showinfo("Form format saved",f"Saved {len(data['fields'])} field settings to:\n{filename}")
        except Exception as exc:messagebox.showerror("Save Form Format",str(exc))

    def _import_form_format(self):
        if self.workspace_kind=="freeform":
            return messagebox.showinfo("Form format", "Switch to a Form Project to import a format.")
        filename=filedialog.askopenfilename(title="Load Form Format",filetypes=[("OpenSayo Form Format","*.osfrm")])
        if not filename:return
        try:
            raw_text=Path(filename).read_text(encoding="utf-8-sig")
            try:data=json.loads(raw_text)
            except json.JSONDecodeError:
                if self._import_legacy_to_form(raw_text,1):
                    messagebox.showinfo("Legacy macro imported","Older tab-based script converted into editable Form fields.")
                return
            if isinstance(data,dict) and data.get("format")==DEFAULT_PROJECT["format"]:
                # Older OpenSayo project JSON had no per-field format metadata.
                if not messagebox.askyesno("Load older OpenSayo project", "This is an older OpenSayo project. Import its field settings into the current form?"):
                    return
                self.apply(normalize_project(data));self.save_session()
                messagebox.showinfo("Older project loaded","Legacy project imported.")
                return
            if not isinstance(data,dict) or data.get("file_type")!="opensayo_form_format" or data.get("format_version")!=1:
                raise ValueError("Not a supported OpenSayo Form Format v1 file or legacy tab script")
            fields=data.get("fields")
            if not isinstance(fields,list) or not fields:
                raise ValueError("A form format must contain at least one field")
            if not all(isinstance(f,dict) and f.get("format_type","Text") in ("Text","Date","Drop Down","Skip") for i,f in enumerate(fields)):
                raise ValueError("Field names/order or format type do not match this application")
            a,b=data.get("endpoint"),data.get("key2_endpoint")
            if not isinstance(a,int) or not isinstance(b,int) or not 0<=a<=b<len(fields):
                raise ValueError("Invalid key endpoints")
            libs=data.get("dropdowns",{})
            if not isinstance(libs,dict) or any(not isinstance(k,str) or not isinstance(v,list) or any(not isinstance(x,str) for x in v) for k,v in libs.items()):
                raise ValueError("Invalid dropdown library data")
            candidate=self.current_project()
            candidate["fields"]=fields
            candidate["dynamic_form"]=True
            candidate["layout"]=data.get("layout",default_layout(len(fields)))
            candidate["endpoint"]=a;candidate["key2_endpoint"]=b
            # Include referenced libraries but leave unrelated local libraries intact.
            candidate["dropdowns"]={**candidate.get("dropdowns",{}),**libs}
            if not messagebox.askyesno("Load Form Format",f"Apply format from {Path(filename).name}?\n\nThis replaces field values, formats and key endpoints. Existing dropdown lists not in the file are retained. Device assignments are unchanged."):
                return
            self.apply(candidate)
            self.save_session()
            messagebox.showinfo("Form format loaded","Form format applied successfully.")
        except Exception as exc:messagebox.showerror("Load Form Format",str(exc))

    def _save_form_layout(self):
        """Only grid geometry and stable field identities; no field values or hardware data."""
        filename=filedialog.asksaveasfilename(title="Save Form Layout",defaultextension=".oslay",filetypes=[("OpenSayo Layout","*.oslay")])
        if not filename:return
        try:
            data={"file_type":"opensayo_layout","version":1,"layout":copy.deepcopy(self.form_layout),"field_ids":[f["field_id"] for f in self.field_definitions]}
            Path(filename).write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding="utf-8")
        except Exception as exc:messagebox.showerror("Save Form Layout",str(exc))

    def _load_form_layout(self):
        filename=filedialog.askopenfilename(title="Load Form Layout",filetypes=[("OpenSayo Layout","*.oslay")])
        if not filename:return
        try:
            data=json.loads(Path(filename).read_text(encoding="utf-8-sig"))
            if data.get("file_type")!="opensayo_layout" or data.get("version")!=1:raise ValueError("Not an OpenSayo layout file")
            ids=data.get("field_ids")
            if not isinstance(ids,list) or any(not isinstance(x,str) for x in ids) or len(ids)!=len(set(ids)):raise ValueError("Invalid field identity list")
            current={f["field_id"]:i for i,f in enumerate(self.field_definitions)}
            if set(ids)!=set(current):raise ValueError("This layout uses different fields. Load its Field List first.")
            raw=data.get("layout")
            if not isinstance(raw,dict):raise ValueError("Invalid layout")
            if not isinstance(raw.get("positions",{}),dict):raise ValueError("Invalid layout positions")
            positions={str(current[ids[int(k)]]):v for k,v in raw.get("positions",{}).items() if isinstance(k,str) and k.isdigit() and int(k)<len(ids)}
            self.form_layout=normalized_layout({"columns":raw.get("columns",5),"rows":raw.get("rows",25),"positions":positions,"allow_unplaced":True,"half_fields":[current[ids[i]] for i in raw.get("half_fields",[]) if isinstance(i,int) and 0<=i<len(ids)],"half_slots":{str(current[ids[int(k)]]):v for k,v in raw.get("half_slots",{}).items() if str(k).isdigit() and int(k)<len(ids)},"labels":raw.get("labels",[])},len(self.field_definitions))
            self._designer_render();self._designer_persist()
        except Exception as exc:messagebox.showerror("Load Form Layout",str(exc))

    def _save_field_list(self):
        filename=filedialog.asksaveasfilename(title="Save Field List",defaultextension=".osfld",filetypes=[("OpenSayo Field List","*.osfld")])
        if not filename:return
        try:
            fields=copy.deepcopy(self.current_project()["fields"])
            for f in fields:
                f["value"]=""  # Presets never include form entry data.
                f.pop("format_values",None)
                f.pop("date_option_memory",None)
                f.pop("_typed_value",None)
            data={"file_type":"opensayo_fields","version":1,"fields":fields,"dropdowns":self.dropdown_libraries}
            Path(filename).write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding="utf-8")
        except Exception as exc:messagebox.showerror("Save Field List",str(exc))

    def _load_field_list(self):
        filename=filedialog.askopenfilename(title="Load Field List",filetypes=[("OpenSayo Field List","*.osfld")])
        if not filename:return
        try:
            data=json.loads(Path(filename).read_text(encoding="utf-8-sig"))
            if data.get("file_type")!="opensayo_fields" or data.get("version")!=1:raise ValueError("Not an OpenSayo field list")
            fields=data.get("fields")
            if not isinstance(fields,list) or not fields:raise ValueError("Expected at least one field")
            p=self.current_project();p["fields"]=fields;p["dynamic_form"]=True
            p["endpoint"]=min(p["endpoint"],len(fields)-1)
            p["key2_endpoint"]=min(max(p["endpoint"],p["key2_endpoint"]),len(fields)-1)
            previous_ids=[f["field_id"] for f in self.field_definitions]
            incoming_ids=[f.get("field_id") for f in fields]
            if previous_ids==incoming_ids:
                p["layout"]=copy.deepcopy(self.form_layout)
            else:
                # Do not silently remap grid positions onto unrelated field identities.
                p["layout"]={"columns":self.form_layout["columns"],"rows":self.form_layout["rows"],"positions":{},"allow_unplaced":True}
            libs=data.get("dropdowns",{})
            if not isinstance(libs,dict):raise ValueError("Invalid dropdown libraries")
            p["dropdowns"]={**p.get("dropdowns",{}),**libs}
            p=normalize_project(p)
            if not messagebox.askyesno("Load Field List",f"Replace current field definitions with {len(fields)} imported fields? Field properties will be replaced. Grid placement is retained when field IDs match; otherwise unplaced. No device writes occur."):return
            self.designer_selected=None;self.apply(p);self._designer_render();self._designer_persist();self._manage_refresh()
        except Exception as exc:messagebox.showerror("Load Field List",str(exc))

    def current_project(self):
        p=blank_project()
        p["fields"]=copy.deepcopy(self.field_definitions)
        p["layout"]=copy.deepcopy(self.form_layout)
        p["dynamic_form"]=True
        p["endpoint"]=self.endpoint.get()
        p["dropdowns"]=dict(self.dropdown_libraries)
        p["key2_endpoint"]=self.key2_endpoint.get()
        p["use_caps_lock"]=self.use_caps_lock.get()
        for key,var in (("text_delay_ms",self.text_delay),("action_delay_ms",self.action_delay),("repeat_gap_ms",self.repeat_gap),("dropdown_open_ms",self.dropdown_open_ms)):
            p[key]=int(var.get())
        if hasattr(self,"_form_raw_readbacks"):
            p["form_raw_readbacks"]=copy.deepcopy(self._form_raw_readbacks)
        for i,f in enumerate(p["fields"]):
            # Read the actual dropdown widget, not an asynchronously updated
            # StringVar. This also handles selection changes during UI refresh.
            if self.format_vars[i].get()=="Drop Down":
                chosen=self._dropdown_controls[i].get()
                f["value"]=chosen
                self._dropdown_values[i]=chosen
                if self.field_vars[i].get()!=chosen:self.field_vars[i].set(chosen)
            else:
                f["value"]=self.field_vars[i].get()
            f["after"]=self.nav_vars[i].get()
            f["format_values"]={"Text":self._typed_values.get(i,""),"Date":self._date_values.get(i,""),"Drop Down":self._dropdown_values.get(i,"")}
            mode=self.format_vars[i].get()
            if mode=="Text":f["format_values"]["Text"]=self.field_vars[i].get()
            elif mode=="Date" and self.option_vars[i].get()=="MM/DD/YY":f["format_values"]["Date"]=self.field_vars[i].get()
            elif mode=="Drop Down":f["format_values"]["Drop Down"]=self._dropdown_controls[i].get()
            f["format_type"]=self.format_vars[i].get()
            f["format_option"]=self.option_vars[i].get()
            f["date_option_memory"]=getattr(self,"_date_option_memory",{}).get(i,"MM/DD/YY")
            f["dropdown_library_memory"]=getattr(self,"_dropdown_list_memory",{}).get(i, self.option_vars[i].get() if mode=="Drop Down" else "")
            f["navigate"]=self._navigate_vars[i].get()
            f["navigate_keys"]=self._navigate_keys.get(i,"")
            f["enabled"]=self.enabled_vars[i].get()
        return p

    def apply(self,p):
        self._loading=True
        # Loading a different form invalidates previous hardware-only source.
        # Project/session loads may restore a matching, validated readback.
        existing_overrides=p.get("form_raw_readbacks",{})
        self._form_raw_readbacks={}
        if isinstance(existing_overrides,dict):
            for key,record in existing_overrides.items():
                if key not in ("1","2") or not isinstance(record,dict):continue
                try:
                    source=record["source"]
                    signature=record["signature"]
                    if not isinstance(source,str) or not isinstance(signature,str):continue
                    validate_script(source)
                    self._form_raw_readbacks[key]={"source":source,"signature":signature}
                except (KeyError,ValueError,TypeError):continue
        try:
            incoming=copy.deepcopy(p["fields"])
            structure=[(f.get("field_id"),f.get("name")) for f in incoming]
            existing=[(f.get("field_id"),f.get("name")) for f in self.field_definitions]
            self.field_definitions=incoming
            self.endpoint.set(min(self.endpoint.get(),len(incoming)-1))
            self.key2_endpoint.set(min(self.key2_endpoint.get(),len(incoming)-1))
            self.form_layout=normalized_layout(p.get("layout"),len(incoming))
            if structure!=existing:self._rebuild_field_rows(incoming)
            self.dropdown_libraries=dict(p.get("dropdowns",{}))
            self._invalid_navigation_on_load=[]
            for i,f in enumerate(p["fields"]):
                saved=f.get("format_values",{})
                self._typed_values[i]=saved.get("Text",f["value"] if f.get("format_type","Text")=="Text" else "")
                self._date_values[i]=saved.get("Date",f["value"] if f.get("format_type")=="Date" else "")
                self._dropdown_values[i]=saved.get("Drop Down",f["value"] if f.get("format_type")=="Drop Down" else "")
                if not hasattr(self,"_dropdown_list_memory"):self._dropdown_list_memory={}
                self._dropdown_list_memory[i]=f.get("dropdown_library_memory",f.get("format_option","") if f.get("format_type")=="Drop Down" else "")
                if not hasattr(self,"_date_option_memory"):self._date_option_memory={}
                self._date_option_memory[i]=f.get("date_option_memory",f.get("format_option","MM/DD/YY") if f.get("format_type")=="Date" else "MM/DD/YY")
                self.field_vars[i].set(f["value"]);self.nav_vars[i].set(f["after"])
                self.enabled_vars[i].set(field_is_enabled(f))
                self._navigate_keys[i]=str(f.get("navigate_keys", ""))
                # A stale session may request Navigate with no recorded keys.
                # Never compile an empty sequence or silently invent key presses.
                # Disable the invalid mode on load so both previews remain usable.
                invalid_nav=(bool(f.get("navigate",False)) and
                             f.get("format_type")=="Drop Down" and
                             not self._navigate_keys[i].strip())
                self._navigate_vars[i].set(bool(f.get("navigate",False)) and not invalid_nav)
                if invalid_nav:
                    self._invalid_navigation_on_load.append(f.get("name",f"Field {i+1}"))
                self.format_vars[i].set(f.get("format_type","Text"))
                self.option_vars[i].set(f.get("format_option",""))
                self._format_previous[i]=self.format_vars[i].get()
                self._update_format_row(i)
            self._dropdown_refresh()
            self.endpoint.set(p["endpoint"])
            self.key2_endpoint.set(p.get("key2_endpoint",p["endpoint"]))
            self._accepted_key1_endpoint=self.endpoint.get()
            self.text_delay.set(str(p["text_delay_ms"]));self.action_delay.set(str(p["action_delay_ms"]));self.repeat_gap.set(str(p["repeat_gap_ms"]))
            self.use_caps_lock.set(bool(p.get("use_caps_lock",False)))
            self.macro_key_ms.set(str(p["text_delay_ms"]));self.macro_nav_ms.set(str(p["action_delay_ms"]));self.macro_repeat_ms.set(str(p["repeat_gap_ms"]));self.dropdown_open_ms.set(str(p.get("dropdown_open_ms",75)))
        finally:self._loading=False
        self._changed()
        if getattr(self,"_invalid_navigation_on_load",[]):
            self.macro_status.set("Disabled Navigate with no recorded keys: " +
                                  ", ".join(self._invalid_navigation_on_load) +
                                  ". Record Navigate Keys before re-enabling.")

    def save_session(self):
        self._save_job=None
        try:
            p=self.current_project()
            SESSION_PATH.parent.mkdir(parents=True,exist_ok=True)
            tmp=SESSION_PATH.with_suffix(".tmp")
            with tmp.open("w",encoding="utf-8") as f:
                json.dump(p,f,indent=2,ensure_ascii=False);f.flush();os.fsync(f.fileno())
            os.replace(tmp,SESSION_PATH)
            self.session_status.set(f"Autosaved: {SESSION_PATH}")
        except Exception as exc:self.session_status.set(f"Autosave FAILED: {exc}")

    def load_session(self):
        if not SESSION_PATH.exists():
            self.apply(approved_default_project())
            return
        try:
            self.apply(normalize_project(json.loads(SESSION_PATH.read_text(encoding="utf-8"))))
            self.session_status.set(f"Restored: {SESSION_PATH}")
        except Exception as exc:
            self.apply(approved_default_project());messagebox.showwarning("Session recovery",f"Could not restore session: {exc}\nThe existing file was not overwritten yet. Approved defaults loaded.")

    def clear(self):
        if not messagebox.askyesno("Clear Fields", "Clear all typed values? This updates autosave."):
            return
        p=self.current_project()
        for f in p["fields"]: f["value"]=""
        self.apply(p);self.save_session()

    def save_as(self):
        try:p=self.current_project()
        except Exception as exc:return messagebox.showerror("Invalid settings",str(exc))
        name=filedialog.asksaveasfilename(defaultextension=".json",filetypes=[("OpenSayo project","*.json")])
        if name:Path(name).write_text(json.dumps(p,indent=2),encoding="utf-8")

    def open_project(self):
        name=filedialog.askopenfilename(filetypes=[("OpenSayo project","*.json")])
        if not name:return
        try:self.apply(normalize_project(json.loads(Path(name).read_text(encoding="utf-8"))))
        except Exception as exc:messagebox.showerror("Cannot open project",str(exc))

    def settings(self):
        if self.settings_window is not None and self.settings_window.winfo_exists():
            self.settings_window.deiconify()
            self.settings_window.lift()
            self.settings_window.focus_force()
            return
        win=tk.Toplevel(self.root);self.settings_window=win
        win.title("OpenSayo Settings");win.geometry("370x250");win.transient(self.root)
        win.protocol("WM_DELETE_WINDOW",win.destroy)
        frame=ttk.Frame(win,padding=18);frame.pack(fill="both",expand=True)
        for i,(label,var) in enumerate((("Typing delay (ms)",self.text_delay),("Navigation delay (ms)",self.action_delay),("Repeated-character gap (ms)",self.repeat_gap))):
            ttk.Label(frame,text=label).grid(row=i,column=0,sticky="w",pady=9)
            ttk.Entry(frame,textvariable=var,width=9).grid(row=i,column=1,sticky="e",padx=8)
        ttk.Button(frame,text="Restore timing defaults",command=self._restore_timing_defaults).grid(row=4,column=0,columnspan=2,pady=14)
        ttk.Label(frame,text="Settings autosave automatically.",foreground="#666").grid(row=5,column=0,columnspan=2)

    def _restore_timing_defaults(self):
        """Reset Settings and Macro Viewer to the current built-in project defaults.

        No device access occurs; only local timing values and generated previews
        are refreshed. Keeps both timing editors consistent after a reset.
        """
        defaults=(DEFAULT_PROJECT["text_delay_ms"],
                  DEFAULT_PROJECT["action_delay_ms"],
                  DEFAULT_PROJECT["repeat_gap_ms"])
        settings=(self.text_delay,self.action_delay,self.repeat_gap)
        viewer=(self.macro_key_ms,self.macro_nav_ms,self.macro_repeat_ms)
        for setting,preview,value in zip(settings,viewer,defaults):
            setting.set(str(value))
            preview.set(str(value))
        self._sync_form_to_editor()
        self._refresh()
        self.save_session()

    def _show_diagnostic(self):
        for panel in self.diagnostic_views.values():
            panel.pack_forget()
        panel=self.diagnostic_views[self.diagnostic_choice.get()]
        # Live readback requires explicit user action; other views remain offline.
        panel.pack(fill="both",expand=True)

    def _on_tab_changed(self, event=None):
        if self.book.select() == str(self.macro_tab):
            # Switching tabs must never regenerate and replace a saved key script.
            self._render_key_previews()

    def _preview_date_action_edit(self, event=None):
        # The preview displays today's date for the Down, Enter action.
        # Only explicit edits replace the action with a typed date.
        value=self.preview_date_action_var.get().strip()
        i=self._date_action_index()
        if value and i is not None:
            self.field_vars[i].set(value)

    def _preview_date_action_blur(self, event=None):
        i=self._date_action_index()
        if i is not None and not self.preview_date_action_var.get().strip():
            self.field_vars[i].set("Down, Enter")
            self.preview_date_action_var.set(date.today().strftime("%m/%d/%y"))

    def open_form_preview(self):
        """One independent window, never multiple instances."""
        win=getattr(self,"form_preview_window",None)
        if win is not None and win.winfo_exists():
            win.deiconify();win.lift();win.focus_set()
            return
        win=tk.Toplevel(self.root)
        self.form_preview_window=win
        win.title("OpenSayo — Form View")
        win.geometry(getattr(self,"_form_preview_geometry","1240x820"))
        win.minsize(700,420)
        self.form_preview_tab=ttk.Frame(win,padding=10)
        self.form_preview_tab.pack(fill="both",expand=True)
        win.protocol("WM_DELETE_WINDOW",self._close_form_preview)
        self.show_form_preview()

    def _close_form_preview(self):
        win=getattr(self,"form_preview_window",None)
        if win is not None and win.winfo_exists():
            self._form_preview_geometry=win.geometry()
            try:
                UI_PREFS_PATH.parent.mkdir(parents=True,exist_ok=True)
                try:prefs=json.loads(UI_PREFS_PATH.read_text(encoding="utf-8"))
                except (OSError,ValueError,TypeError):prefs={}
                prefs["preview_geometry"]=self._form_preview_geometry
                UI_PREFS_PATH.write_text(json.dumps(prefs),encoding="utf-8")
            except OSError:pass
            win.destroy()
        self.form_preview_window=None

    def show_form_preview(self):
        """Editable form following the currently loaded layout (blank 3-column default)."""
        self._preview_refresh_job=None
        win=getattr(self,"form_preview_window",None)
        if win is None or not win.winfo_exists():return
        # Toggling a field should not throw the user back to row one.
        old_canvas=getattr(self,"_form_preview_canvas",None)
        old_scroll=(old_canvas.xview()[0],old_canvas.yview()[0]) if old_canvas is not None and old_canvas.winfo_exists() else (0.0,0.0)
        for child in self.form_preview_tab.winfo_children():child.destroy()
        ttk.Label(self.form_preview_tab,text="Form View",font=("Segoe UI",12,"bold")).pack(anchor="w",pady=(0,2))
        ttk.Label(self.form_preview_tab,text="Configure which fields are used in Field View. Disabled fields appear as labels only; their Tab positions are preserved.",foreground="#555",wraplength=1000).pack(anchor="w",pady=(0,5))
        holder=ttk.Frame(self.form_preview_tab);holder.pack(fill="both",expand=True)
        canvas=tk.Canvas(holder,highlightthickness=0)
        self._form_preview_canvas=canvas
        vs=ttk.Scrollbar(holder,orient="vertical",command=canvas.yview)
        hs=ttk.Scrollbar(holder,orient="horizontal",command=canvas.xview)
        canvas.configure(yscrollcommand=vs.set,xscrollcommand=hs.set)
        canvas.grid(row=0,column=0,sticky="nsew")
        vs.grid(row=0,column=1,sticky="ns")
        hs.grid(row=1,column=0,sticky="ew")
        holder.rowconfigure(0,weight=1);holder.columnconfigure(0,weight=1)
        body=ttk.Frame(canvas,padding=(3,2))
        window_id=canvas.create_window((0,0),window=body,anchor="nw")
        def fit_canvas(event):
            canvas.itemconfigure(window_id,width=max(body.winfo_reqwidth(),event.width))
        canvas.bind("<Configure>",fit_canvas)
        body.bind("<Configure>",lambda e:canvas.configure(scrollregion=canvas.bbox("all")))
        cols=self.form_layout["columns"];rows=self.form_layout["rows"]
        positions=self.form_layout["positions"]
        half=set(self.form_layout.get("half_fields",[]))
        slots=self.form_layout.get("half_slots",{})
        labels=self.form_layout.get("labels",[])
        for c in range(cols):body.columnconfigure(c,weight=1,uniform="formfields",minsize=225)
        half_rows=set()
        for i,pos in positions.items():
            if int(i) in half and pos is not None:half_rows.add(pos[1])
        for r in range(rows):body.rowconfigure(r,minsize=40 if r in half_rows else 27)
        cells={}
        for c in range(cols):
            for r in range(rows):
                cell=ttk.Frame(body)
                cell.grid(row=r,column=c,sticky="nsew",padx=(3,7),pady=0)
                cell.columnconfigure(0,weight=1)
                cell.rowconfigure(0,weight=1);cell.rowconfigure(1,weight=1)
                cells[c,r]=cell
        def field_line(parent,name,variable=None,kind="text",values=(),field_index=None):
            line=ttk.Frame(parent)
            line.columnconfigure(1,weight=1)
            ttk.Label(line,text=name,anchor="e",justify="right",width=21).grid(row=0,column=0,sticky="e",padx=(0,4))
            if kind=="text":
                ttk.Entry(line,textvariable=variable,width=12).grid(row=0,column=1,sticky="ew")
            elif kind=="dropdown":
                ttk.Combobox(line,textvariable=variable,values=values,width=12).grid(row=0,column=1,sticky="ew")
            elif kind!="label":
                ttk.Label(line,text="Today" if kind=="today" else "—",foreground="#666").grid(row=0,column=1,sticky="w")
            return line
        preview_inputs={}
        self._preview_date_error_style="OpenSayoInvalidDate.TEntry"
        ttk.Style().configure(self._preview_date_error_style,fieldbackground="#ffd9d9")
        def check_preview_date(idx,widget,notify=False):
            value=self.field_vars[idx].get().strip()
            good=(not value) or valid_date(value)
            if not good:
                previous=self._date_values.get(idx,"")
                self.field_vars[idx].set(previous if valid_date(previous) else "")
                good=True
            else:
                self._date_values[idx]=value
            widget.configure(style="TEntry" if good else self._preview_date_error_style)
            if not good and notify:
                messagebox.showwarning("Invalid date",f"{self.field_definitions[idx]['name']} must be a real date in MM/DD/YY format.",parent=win)
            return good
        def next_preview_field(idx,backward=False):
            order=sorted(preview_inputs)
            if idx not in order:return None
            n=order.index(idx)+( -1 if backward else 1)
            return preview_inputs[order[n%len(order)]] if order else None
        def preview_tab(event,idx,backward=False):
            widget=preview_inputs.get(idx)
            if widget is None:return "break"
            if self.format_vars[idx].get()=="Date" and self.option_vars[idx].get()=="MM/DD/YY":
                check_preview_date(idx,widget)
            target=next_preview_field(idx,backward)
            if target is not None:target.focus_set()
            return "break"
        for i,f in enumerate(self.field_definitions):
            pos=positions.get(str(i))
            if pos is None:continue
            c,r=pos
            if (c,r) not in cells:continue
            is_half=i in half;side=int(slots.get(str(i),0)) if is_half else 0
            mode=self.format_vars[i].get();opt=self.option_vars[i].get()
            enabled=self.enabled_vars[i].get()
            if not enabled:
                line=field_line(cells[c,r],generic_field_display_label(i,f),kind="label",field_index=i)
            elif mode=="Text" or (mode=="Date" and opt=="MM/DD/YY"):
                line=field_line(cells[c,r],generic_field_display_label(i,f),self.field_vars[i],field_index=i)
            elif mode=="Drop Down":
                line=field_line(cells[c,r],generic_field_display_label(i,f),self.field_vars[i],"dropdown",self.dropdown_libraries.get(opt,[]),field_index=i)
            else:line=field_line(cells[c,r],generic_field_display_label(i,f),kind="today" if mode=="Date" else "skip",field_index=i)
            line.grid(row=side,column=0,rowspan=1 if is_half else 2,sticky="ew",pady=0)
            if enabled and (mode in ("Text","Drop Down") or (mode=="Date" and opt=="MM/DD/YY")):
                control=line.grid_slaves(row=0,column=1)[0]
                preview_inputs[i]=control
                control.bind("<Tab>",lambda event,idx=i:preview_tab(event,idx))
                control.bind("<Shift-Tab>",lambda event,idx=i:preview_tab(event,idx,True))
                control.bind("<ISO_Left_Tab>",lambda event,idx=i:preview_tab(event,idx,True))
                if mode=="Date" and opt=="MM/DD/YY":
                    control.bind("<FocusOut>",lambda event,idx=i,w=control:check_preview_date(idx,w))
                    control.bind("<KeyRelease>",lambda event,idx=i,w=control:check_preview_date(idx,w))
        self._preview_inputs=preview_inputs
        # Geometry settles after rows are placed; then restore scroll on refresh.
        win.after_idle(lambda cv=canvas,scroll=old_scroll:
                       (cv.xview_moveto(scroll[0]),cv.yview_moveto(scroll[1])) if cv.winfo_exists() else None)
        for label in labels:
            pos=label.get("position")
            if not pos:continue
            c,r=pos;side=int(label.get("side",0))
            if (c,r) not in cells:continue
            ttk.Label(cells[c,r],text=label["name"],anchor="e",justify="right").grid(row=side,column=0,sticky="e",padx=(0,5))

    def _build_form_designer(self):
        """Debug-only entry point; editing tools use independent, single-instance dialogs."""
        panel=self.form_designer_tab
        ttk.Label(panel,text="Form Designer",font=("Segoe UI",15,"bold")).pack(anchor="w",pady=8)
        ttk.Label(panel,text="Edit the form definition and place fields visually. Dragging never changes field Tab order.",wraplength=850).pack(anchor="w",pady=5)
        tools=ttk.LabelFrame(panel,text="Grid Size & Layout",padding=12);tools.pack(fill="x",pady=8)
        ttk.Label(tools,text="Columns (3–8):").pack(side="left")
        self.designer_columns=tk.StringVar(value="3")
        ttk.Combobox(tools,textvariable=self.designer_columns,values=[str(x) for x in range(3,9)],state="readonly",width=4).pack(side="left",padx=6)
        ttk.Label(tools,text="Rows (25+):").pack(side="left")
        self.designer_rows=tk.StringVar(value="25")
        ttk.Entry(tools,textvariable=self.designer_rows,width=5).pack(side="left",padx=6)
        ttk.Button(tools,text="Apply Grid Size",command=self._designer_resize).pack(side="left",padx=5)
        ttk.Button(tools,text="Load Grid Layout",command=self._load_form_layout).pack(side="left",padx=5)
        ttk.Button(tools,text="Save Grid Layout",command=self._save_form_layout).pack(side="left",padx=5)
        fields_box=ttk.LabelFrame(panel,text="Field List Management",padding=12);fields_box.pack(fill="x",pady=8)
        field_actions=ttk.Frame(fields_box);field_actions.pack(anchor="w")
        ttk.Button(field_actions,text="Manage Fields",command=self._open_manage_fields).pack(side="left",padx=5)
        ttk.Button(field_actions,text="Save Fields",command=self._save_field_list).pack(side="left",padx=5)
        ttk.Button(field_actions,text="Load Fields",command=self._load_field_list).pack(side="left",padx=5)
        ttk.Button(panel,text="Open Grid Mode",command=self._open_grid_mode).pack(anchor="w",pady=(10,4))
        ttk.Button(panel,text="Reset Defaults",command=self._designer_reset).pack(anchor="w",pady=(4,10))
        ttk.Label(panel,text="The blank numbered form contains no application-specific preset. Import your own definitions and layout. Field and layout files do not program hardware.",wraplength=850,foreground="#555").pack(anchor="w",pady=8)
        self.designer_selected=None
        self.designer_status=tk.StringVar(value="Open Grid Mode to place fields.")
        self.designer_grid_window=None
        self.manage_fields_window=None
        self.designer_body=None

    def _open_grid_mode(self):
        win=self.designer_grid_window
        if win is not None and win.winfo_exists():
            win.deiconify();win.lift();win.focus_force();return
        win=tk.Toplevel(self.root);self.designer_grid_window=win
        win.title("OpenSayo — Grid Mode");win.geometry("1250x760");win.minsize(850,480)
        win.protocol("WM_DELETE_WINDOW",lambda:self._close_grid_mode())
        split=ttk.Panedwindow(win,orient="horizontal");split.pack(fill="both",expand=True,padx=8,pady=8)
        library=ttk.LabelFrame(split,text="Fields — field Tab order",padding=6)
        gridpane=ttk.LabelFrame(split,text="Placement Grid — drag or click a destination",padding=6)
        split.add(library,weight=1);split.add(gridpane,weight=4)
        self.designer_library=tk.Listbox(library,exportselection=False,selectmode="extended",font=("Segoe UI",10))
        lscroll=ttk.Scrollbar(library,orient="vertical",command=self.designer_library.yview)
        self.designer_library.configure(yscrollcommand=lscroll.set)
        self.designer_library.pack(side="left",fill="both",expand=True);lscroll.pack(side="right",fill="y")
        self.designer_library.bind("<<ListboxSelect>>",self._library_select)
        self.designer_library.bind("<Control-a>",lambda e:(self.designer_library.selection_set(0,"end"),"break")[-1])
        self.designer_library.bind("<ButtonPress-1>",self._library_drag_start,add="+")
        self.designer_library.bind("<ButtonRelease-1>",self._library_drag_end,add="+")
        holder=ttk.Frame(gridpane);holder.pack(fill="both",expand=True)
        self.designer_canvas=tk.Canvas(holder,highlightthickness=0)
        y=ttk.Scrollbar(holder,orient="vertical",command=self.designer_canvas.yview)
        x=ttk.Scrollbar(holder,orient="horizontal",command=self.designer_canvas.xview)
        self.designer_canvas.configure(yscrollcommand=y.set,xscrollcommand=x.set)
        self.designer_canvas.grid(row=0,column=0,sticky="nsew");y.grid(row=0,column=1,sticky="ns");x.grid(row=1,column=0,sticky="ew")
        holder.rowconfigure(0,weight=1);holder.columnconfigure(0,weight=1)
        self.designer_body=ttk.Frame(self.designer_canvas,padding=5)
        self.designer_canvas.create_window((0,0),window=self.designer_body,anchor="nw")
        self.designer_body.bind("<Configure>",lambda e:self.designer_canvas.configure(scrollregion=self.designer_canvas.bbox("all")))
        ttk.Button(gridpane,text="Unload Selected Fields (Shift/Ctrl select; Ctrl+A selects all)",command=self._designer_unplace).pack(anchor="w",pady=5)
        ttk.Label(gridpane,textvariable=self.designer_status).pack(anchor="w")
        ttk.Label(gridpane,text="Arrange fields and visual labels here. To enable or disable a field, use its Use checkbox in Field View; Tab order stays unchanged.",foreground="#555",wraplength=820).pack(anchor="w",pady=(2,3))
        actions=ttk.Frame(gridpane);actions.pack(anchor="w",pady=4)
        ttk.Button(actions,text="Toggle Half Height (selected)",command=self._designer_toggle_half).pack(side="left",padx=3)
        ttk.Button(actions,text="Add Label Only",command=self._designer_add_label).pack(side="left",padx=3)
        ttk.Button(actions,text="Remove Label",command=self._designer_remove_label).pack(side="left",padx=3)
        self._designer_render()

    def _designer_toggle_half(self):
        indices=list(self.designer_library.curselection()) or ([self.designer_selected] if self.designer_selected is not None else [])
        half=set(self.form_layout.get("half_fields",[]))
        for i in indices:
            if i in half:half.remove(i)
            else:half.add(i)
        self.form_layout["half_fields"]=sorted(half)
        self.form_layout=normalized_layout(self.form_layout,len(self.field_definitions))
        self._designer_render();self._designer_persist()

    def _designer_add_label(self):
        name=simpledialog.askstring("Label Only","Visual label (no macro Tab step):",parent=self.designer_grid_window)
        if not name or not name.strip():return
        labels=self.form_layout.setdefault("labels",[])
        if len(labels)>=150:return messagebox.showwarning("Labels","Maximum 150 visual labels")
        # First available cell; user can move via grid click after selecting label.
        posslot=next(((c,r,side) for r in range(self.form_layout["rows"]) for c in range(self.form_layout["columns"]) for side in (0,1) if not self._designer_occupants(c,r,side)[0] and not self._designer_occupants(c,r,side)[1]),None)
        pos=list(posslot[:2]) if posslot else None
        if pos is None:return messagebox.showwarning("Labels","No empty cells; unload a field first")
        label={"id":uuid.uuid4().hex,"name":name.strip()[:100],"position":pos,"side":posslot[2]}
        labels.append(label);self._designer_label_selected=label["id"]
        self._designer_render();self._designer_persist()

    def _designer_remove_label(self):
        selected=getattr(self,"_designer_label_selected",None)
        if not selected:return messagebox.showinfo("Labels","Click a label in the grid first")
        self.form_layout["labels"]=[x for x in self.form_layout.get("labels",[]) if x["id"]!=selected]
        self._designer_label_selected=None;self._designer_render();self._designer_persist()

    def _close_grid_mode(self):
        if self.designer_grid_window is not None:
            self.designer_grid_window.destroy()
        self.designer_grid_window=None;self.designer_body=None

    def _library_select(self,event=None):
        selection=self.designer_library.curselection()
        if selection:
            self.designer_selected=selection[-1]
            f=self.field_definitions[self.designer_selected]
            self.designer_status.set(f"Selected {self.designer_selected+1:02d} {f['name']} — click a grid cell to place")
            self._designer_render(refresh_library=False)

    def _library_drag_start(self,event):
        self._library_drag_index=self.designer_library.nearest(event.y)

    def _library_drag_end(self,event):
        if not self.field_definitions:return
        index=getattr(self,"_library_drag_index",None)
        if index is None or not 0<=index<len(self.field_definitions):return
        self.designer_selected=index
        target=self.designer_grid_window.winfo_containing(event.x_root,event.y_root)
        while target is not None and target not in self._designer_cells:target=target.master
        if target in self._designer_cells:self._designer_move(index,*self._designer_cells[target])
        else:self._designer_render()

    def _designer_unplace(self):
        selected=list(self.designer_library.curselection()) if hasattr(self,"designer_library") else []
        if not selected and self.designer_selected is not None:selected=[self.designer_selected]
        if not selected:return
        for i in selected:self.form_layout["positions"].pop(str(i),None)
        self.form_layout["allow_unplaced"]=True
        self.designer_status.set(f"Unplaced {len(selected)} fields; macro Tab order unchanged")
        self._designer_render();self._designer_persist()

    def _open_manage_fields(self):
        win=self.manage_fields_window
        if win is not None and win.winfo_exists():win.deiconify();win.lift();return
        win=tk.Toplevel(self.root);self.manage_fields_window=win
        win.title("OpenSayo — Manage Fields");win.geometry("760x580");win.minsize(550,400)
        win.protocol("WM_DELETE_WINDOW",lambda:(win.destroy(),setattr(self,"manage_fields_window",None)))
        outer=ttk.Frame(win,padding=12);outer.pack(fill="both",expand=True)
        left=ttk.Frame(outer);left.pack(side="left",fill="both",expand=True,padx=(0,12))
        ttk.Label(left,text="Fields in macro Tab order (use Field View to enable or disable)",wraplength=400).pack(anchor="w")
        self.manage_field_list=tk.Listbox(left,exportselection=False)
        self.manage_field_list.pack(fill="both",expand=True)
        self.manage_field_list.bind("<<ListboxSelect>>",self._manage_select)
        right=ttk.Frame(outer);right.pack(side="right",fill="y")
        ttk.Label(right,text="Field name").pack(anchor="w")
        self.manage_name=tk.StringVar();ttk.Entry(right,textvariable=self.manage_name,width=32).pack(fill="x",pady=(0,10))
        ttk.Label(right,text="Default format").pack(anchor="w")
        self.manage_format=tk.StringVar()
        ttk.Combobox(right,textvariable=self.manage_format,values=["Text","Drop Down","Date","Skip"],state="readonly").pack(fill="x",pady=(0,10))
        ttk.Label(right,text="Default option / library").pack(anchor="w")
        self.manage_option=tk.StringVar()
        self.manage_option_widget=ttk.Combobox(right,textvariable=self.manage_option,state="readonly",width=29)
        self.manage_option_widget.pack(fill="x",pady=(0,10))
        self.manage_half=tk.BooleanVar(value=False)
        ttk.Checkbutton(right,text="Half-height field (upper/lower slot)",variable=self.manage_half).pack(anchor="w",pady=(0,10))
        self.manage_format.trace_add("write",lambda *_:self._manage_update_options())
        ttk.Button(right,text="Apply Field Changes",command=self._manage_apply).pack(fill="x",pady=4)
        ttk.Button(right,text="Add Field After Selected",command=self._manage_add).pack(fill="x",pady=4)
        ttk.Button(right,text="Remove Selected Field",command=self._manage_remove).pack(fill="x",pady=4)
        self._manage_refresh()

    def _manage_refresh(self):
        if self.manage_fields_window is None or not self.manage_fields_window.winfo_exists():return
        self.manage_field_list.delete(0,"end")
        for i,f in enumerate(self.field_definitions):
            suffix="  [label only]" if not self.enabled_vars[i].get() else ""
            self.manage_field_list.insert("end",generic_field_display_label(i,f)+suffix)
        if self.designer_selected is not None and self.designer_selected<len(self.field_definitions):
            self.manage_field_list.selection_set(self.designer_selected)
            self._manage_select()

    def _manage_select(self,event=None):
        selected=self.manage_field_list.curselection()
        if not selected:return
        i=selected[0];self.designer_selected=i
        f=self.field_definitions[i]
        self.manage_name.set(f["name"])
        self.manage_format.set(self.format_vars[i].get())
        self.manage_option.set(self.option_vars[i].get())
        self.manage_half.set(i in self.form_layout.get("half_fields",[]))
        self._manage_update_options()

    def _manage_update_options(self):
        """Use exactly the same format-dependent choices as Form View."""
        mode=self.manage_format.get()
        if mode=="Date":
            choices=["Blank","MM/DD/YY","Today's Date"]
        elif mode=="Drop Down":
            choices=sorted(self.dropdown_libraries)
        else:
            choices=[]
        self.manage_option_widget.configure(values=choices,state="readonly" if choices else "disabled")
        if self.manage_option.get() not in choices:
            self.manage_option.set("MM/DD/YY" if mode=="Date" else "")

    def _manage_apply(self):
        i=self.designer_selected
        if i is None:return
        name=self.manage_name.get().strip()
        if not name:return messagebox.showwarning("Field name","Name cannot be blank",parent=self.manage_fields_window)
        mode=self.manage_format.get()
        if mode not in ("Text","Drop Down","Date","Skip"):return
        p=self.current_project();f=p["fields"][i]
        f["name"]=name[:100];f["format_type"]=mode;f["format_option"]=self.manage_option.get()[:200]
        half=set(self.form_layout.get("half_fields",[]))
        if self.manage_half.get():half.add(i)
        else:half.discard(i)
        p["layout"]["half_fields"]=sorted(half)
        p["layout"]=normalized_layout(p["layout"],len(p["fields"]))
        self.apply(p);self._designer_render();self._designer_persist();self._manage_refresh()

    def _manage_add(self):
        self._designer_add();self._manage_refresh()

    def _manage_remove(self):
        self._designer_remove();self._manage_refresh()

    def _designer_render(self,refresh_library=True):
        if self.designer_body is None:return
        for child in self.designer_body.winfo_children():child.destroy()
        cols=self.form_layout["columns"];rows=self.form_layout["rows"]
        self.designer_columns.set(str(cols));self.designer_rows.set(str(rows))
        positions=self.form_layout["positions"]
        half=set(self.form_layout.get("half_fields",[]));slots=self.form_layout.setdefault("half_slots",{})
        self._designer_cells={}
        if refresh_library:
            selected_before=list(self.designer_library.curselection())
            self.designer_library.delete(0,"end")
            for i,f in enumerate(self.field_definitions):
                marker="✓" if str(i) in positions else "○"
                suffix=" [label only]" if not self.enabled_vars[i].get() else ""
                self.designer_library.insert("end",f"{marker} {i+1:02d}. {f['name']}{suffix}")
            for i in selected_before:
                if i<len(self.field_definitions):self.designer_library.selection_set(i)
        for c in range(cols):ttk.Label(self.designer_body,text=f"Column {c+1}",anchor="center").grid(row=0,column=c+1,sticky="ew")
        for r in range(rows):
            ttk.Label(self.designer_body,text=f"{r+1:02d}",width=3).grid(row=r+1,column=0,sticky="e")
            for c in range(cols):
                frame=ttk.Frame(self.designer_body,relief="solid",borderwidth=1)
                frame.grid(row=r+1,column=c+1,sticky="nsew",padx=2,pady=2)
                frame.columnconfigure(0,minsize=168,weight=1)
                frame.rowconfigure(0,minsize=22,weight=1);frame.rowconfigure(1,minsize=22,weight=1)
                occupants=[i for i,pos in ((int(k),v) for k,v in positions.items()) if pos==[c,r]]
                full=next((i for i in occupants if i not in half),None)
                labels=[x for x in self.form_layout.get("labels",[]) if x["position"]==[c,r]]
                for slot in (0,1):
                    idx=full if full is not None else next((i for i in occupants if int(slots.get(str(i),0))==slot),None)
                    label=next((x for x in labels if int(x.get("side",0))==slot),None)
                    title=(f"{idx+1:02d} {self.field_definitions[idx]['name']}" + (" [label only]" if not self.enabled_vars[idx].get() else "") if idx is not None else "[Label] "+label["name"] if label else "＋")
                    if full is not None and slot==1:continue
                    bg="#d6e7ff" if idx==self.designer_selected else "#f0f0f0" if idx is None or not self.enabled_vars[idx].get() else "#ffffff"
                    tile_container=tk.Frame(frame,bg=bg,relief="ridge",bd=1)
                    tile_container.grid(row=0 if full is not None else slot,column=0,rowspan=2 if full is not None else 1,sticky="nsew")
                    tile=tk.Label(tile_container,text=title,anchor="w",width=21,height=2 if full is not None else 1,cursor="hand2",bg=bg)
                    tile.pack(side="left",fill="both",expand=True)
                    self._designer_cells[tile_container]=(c,r,slot)
                    self._designer_cells[tile]=(c,r,slot)
                    tile.bind("<ButtonPress-1>",lambda e,col=c,row=r,side=slot:self._designer_press(col,row,side))
                    tile.bind("<ButtonRelease-1>",self._designer_release)

    def _designer_press(self,c,r,slot=0):
        self._designer_drag_origin=(c,r,slot)

    def _designer_release(self,event):
        target=self.designer_body.winfo_containing(event.x_root,event.y_root)
        while target is not None and target not in self._designer_cells:target=target.master
        origin=getattr(self,"_designer_drag_origin",None)
        if origin is None:return
        c,r,side=origin
        half=set(self.form_layout.get("half_fields",[]));slots=self.form_layout.get("half_slots",{})
        occupants=[int(k) for k,v in self.form_layout["positions"].items() if v==[c,r]]
        source=next((i for i in occupants if i not in half or int(slots.get(str(i),0))==side),None)
        label=next((x for x in self.form_layout.get("labels",[]) if x["position"]==[c,r] and int(x.get("side",0))==side),None)
        destination=self._designer_cells.get(target,origin)
        if label is not None and source is None:
            self._designer_label_selected=label["id"]
            if origin!=destination:
                dc,dr,ds=destination
                if not self._designer_occupants(dc,dr,ds):
                    label["position"]=[dc,dr];label["side"]=ds;self._designer_persist()
            self.designer_status.set("Selected visual label: "+label["name"])
            self._designer_render()
        elif source is not None and origin!=destination:self._designer_move(source,*destination)
        elif source is None and self.designer_selected is not None:self._designer_move(self.designer_selected,*destination)
        else:
            self.designer_selected=source
            self.designer_status.set(f"Selected field {source+1}: {self.field_definitions[source]['name']}" if source is not None else "Select a populated field first")
            self._designer_render()
        self._designer_drag_origin=None

    def _designer_occupants(self,c,r,slot):
        half=set(self.form_layout.get("half_fields",[]));slots=self.form_layout.get("half_slots",{})
        fields=[int(k) for k,v in self.form_layout["positions"].items() if v==[c,r] and (int(k) not in half or int(slots.get(k,0))==slot)]
        labels=[x for x in self.form_layout.get("labels",[]) if x["position"]==[c,r] and int(x.get("side",0))==slot]
        return fields,labels

    def _designer_move(self,index,c,r,slot=0):
        positions=self.form_layout["positions"]
        half=set(self.form_layout.get("half_fields",[]));slots=self.form_layout.setdefault("half_slots",{})
        old=positions.get(str(index));oldslot=int(slots.get(str(index),0))
        wanted=(slot,) if index in half else (0,1)
        collisions=set()
        for side in wanted:
            fields,labels=self._designer_occupants(c,r,side)
            collisions.update(i for i in fields if i!=index)
            if labels:
                self.designer_status.set("Destination contains a visual label; move the label first")
                self._designer_render();return
        # Only swap when both field footprints fit. Otherwise refuse instead of silently unloading.
        if collisions:
            if len(collisions)!=1 or old is None:
                self.designer_status.set("Destination occupied; select an empty half or move the existing fields first")
                self._designer_render();return
            other=next(iter(collisions))
            other_wanted=(oldslot,) if other in half else (0,1)
            for side in other_wanted:
                fields,labels=self._designer_occupants(old[0],old[1],side)
                if labels or any(i not in (index,other) for i in fields):
                    self.designer_status.set("Cannot swap: destination halves are occupied")
                    self._designer_render();return
            positions[str(other)]=old[:]
            if other in half:slots[str(other)]=oldslot
        positions[str(index)]=[c,r]
        if index in half:slots[str(index)]=slot
        else:slots.pop(str(index),None)
        self.form_layout["allow_unplaced"]=True
        self.designer_selected=index
        self.designer_status.set(f"Field {index+1} placed in column {c+1}, row {r+1}"+(f", {'upper' if slot==0 else 'lower'} half" if index in half else ""))
        self._designer_render();self._designer_persist()

    def _designer_resize(self):
        try:
            cols=int(self.designer_columns.get());rows=int(self.designer_rows.get())
        except ValueError:
            return messagebox.showwarning("Grid size","Columns and rows must be whole numbers.")
        if rows<25:
            return messagebox.showwarning("Grid size","Use at least 25 rows.")
        old=self.form_layout
        if cols*rows<len(self.field_definitions):
            return messagebox.showwarning("Grid too small",f"{len(self.field_definitions)} fields need at least {len(self.field_definitions)} cells. Increase columns or rows.")
        # Preserve existing positions wherever possible; relocate out-of-bounds fields.
        self.form_layout=normalized_layout({"columns":cols,"rows":rows,"positions":old["positions"],"half_fields":old.get("half_fields",[]),"half_slots":old.get("half_slots",{}),"labels":old.get("labels",[]),"allow_unplaced":True},len(self.field_definitions))
        self._designer_render();self._designer_persist()

    def _designer_rename(self):
        i=self.designer_selected
        if i is None:return messagebox.showinfo("Rename field","Select a field first.",parent=self.root)
        name=simpledialog.askstring("Rename field","New field name:",initialvalue=self.field_definitions[i]["name"],parent=self.root)
        if name is None:return
        name=name.strip()
        if not name:return messagebox.showwarning("Rename field","Name cannot be blank.")
        p=self.current_project();p["fields"][i]["name"]=name[:100]
        self.apply(p);self._designer_render();self._designer_persist()

    def _designer_add(self):
        # Insert with a numbered placeholder by default. Custom names are optional.
        index=(self.designer_selected+1 if self.designer_selected is not None else len(self.field_definitions))
        name=simpledialog.askstring("Add field","Name (numbered by default):",
                                    initialvalue=str(index+1),parent=self.root)
        if name is None:return
        name=name.strip() or str(index+1)
        p=self.current_project()
        # Preserve custom names, but keep all generic labels in sequence.
        for old_index in range(index,len(p["fields"])):
            if p["fields"][old_index].get("name")==str(old_index+1):
                p["fields"][old_index]["name"]=str(old_index+2)
        f={"field_id":"custom_"+uuid.uuid4().hex,"name":name.strip()[:100],"value":"","after":"Tab","kind":"text","format_type":"Text","format_option":""}
        p["fields"].insert(index,f)
        p["endpoint"]+=int(p["endpoint"]>=index)
        p["key2_endpoint"]+=int(p["key2_endpoint"]>=index)
        positions=p["layout"]["positions"]
        p["layout"]["positions"]={str(int(k)+(int(k)>=index)):v for k,v in positions.items()}
        p["layout"]["half_fields"]=[i+int(i>=index) for i in p["layout"].get("half_fields",[])]
        p["layout"]["half_slots"]={str(int(k)+int(int(k)>=index)):v for k,v in p["layout"].get("half_slots",{}).items()}
        p["layout"]["allow_unplaced"]=True
        p["layout"]=normalized_layout(p["layout"],len(p["fields"]))
        # Add Field must also appear in the Form View/grid, not just the field
        # library. Find a free cell after the last occupied one; extend rows
        # as needed without discarding the user's existing layout.
        grid=p["layout"]
        taken={tuple(pos) for pos in grid["positions"].values()}
        cols,rows=grid["columns"],grid["rows"]
        last=max(taken,key=lambda pos:(pos[0],pos[1])) if taken else (-1,-1)
        next_cell=next(((c,r) for c in range(cols) for r in range(rows)
                        if (c,r) not in taken and (c,r)>last),None)
        if next_cell is None:
            next_cell=next(((c,r) for c in range(cols) for r in range(rows)
                            if (c,r) not in taken),None)
        if next_cell is None:
            grid["rows"]+=1
            next_cell=(0,grid["rows"]-1)
        grid["positions"][str(index)]=list(next_cell)
        p["layout"]=normalized_layout(grid,len(p["fields"]))
        self.designer_selected=index
        self.apply(p);self._designer_render();self._designer_persist()

    def _designer_remove(self):
        i=self.designer_selected
        if i is None:return messagebox.showinfo("Remove field","Select a field first.")
        if len(self.field_definitions)<=1:return messagebox.showwarning("Remove field","At least one field is required.")
        if not messagebox.askyesno("Remove field",f"Delete field {i+1}: {self.field_definitions[i]['name']}?\n\nThis also removes its macro Tab step.",parent=self.root):return
        p=self.current_project();p["fields"].pop(i)
        for new_index in range(i,len(p["fields"])):
            if p["fields"][new_index].get("name")==str(new_index+2):
                p["fields"][new_index]["name"]=str(new_index+1)
        p["endpoint"]=max(0,p["endpoint"]-int(p["endpoint"]>=i))
        p["key2_endpoint"]=max(p["endpoint"],p["key2_endpoint"]-int(p["key2_endpoint"]>=i))
        positions=p["layout"]["positions"]
        p["layout"]["positions"]={str(int(k)-(int(k)>i)):v for k,v in positions.items() if int(k)!=i}
        p["layout"]["half_fields"]=[x-int(x>i) for x in p["layout"].get("half_fields",[]) if x!=i]
        p["layout"]["half_slots"]={str(int(k)-int(int(k)>i)):v for k,v in p["layout"].get("half_slots",{}).items() if int(k)!=i}
        p["layout"]=normalized_layout(p["layout"],len(p["fields"]))
        self.designer_selected=None
        self.apply(p);self._designer_render();self._designer_persist()

    def _designer_reset(self):
        if not messagebox.askyesno("Restore blank defaults","Replace all field definitions, values, dropdown libraries, and layout with the 25-field starter form (ten generic labels plus numbered placeholders)?",parent=self.root):return
        self.designer_selected=None;self.apply(approved_default_project());self._designer_render();self._designer_persist()

    def _designer_persist(self):
        self._form_last_valid=self._form_snapshot()
        self._form_edit_pending=True
        self._form_changed()
        self.save_session()
        if self.form_preview_window is not None and self.form_preview_window.winfo_exists():self.show_form_preview()

    def _refresh(self,show_error=False):
        self._meter_job=None
        if getattr(self,"layout_mode",None) is not None and self.layout_mode.get()=="8":
            self._update_eight_meter()
        try:
            p=self.current_project()
            # Use the same authoritative script compiler as the Macro Viewer and
            # device encoder. The legacy v0.18 preview compiler does not support
            # newer Field View actions/Caps Lock and could blank the entire meter.
            from alpha22_device_ops import encode_script
            active_script=(self._freeform_source() if self.workspace_kind=="freeform"
                           else self._compile_form_key(1)[0])
            script=encode_script(self._ensure_exit(active_script))
            used=len(script)
            active=self.focused_key.get()
            if hasattr(self,"macro_text"):
                self._key_scripts[active]=self.macro_text.get("1.0","end-1c")
            sizes={}
            errors=[]
            for key in (1,2):
                try:sizes[key]=len(encode_script(self._ensure_exit(self._key_scripts.get(key,"EXIT"))))
                except Exception as exc:
                    sizes[key]=None
                    errors.append(f"Key {key}: {exc}")
            if self.workspace_kind!="freeform":
                for key in (1,2):
                    try:
                        _,sizes[key]=self._compile_form_key(key)
                    except Exception as exc:
                        sizes[key]=None
                        errors.append(f"Form Key {key}: {exc}")
            n1=sizes[1] if sizes[1] is not None else 0
            n2=sizes[2] if sizes[2] is not None else 0
            enabled=self.key2_bank.get().isdigit()
            self._boss_values=(n1,n2)
            self._draw_boss_bar()
            if hasattr(self,"_meter_labels"):
                self._meter_labels[1].set(f"{n1}/{SAFE_CUTOFF} bytes")
                self._meter_labels[2].set((f"{n2}/{SAFE_CUTOFF} bytes" if enabled else f"Inactive · {n2}/{SAFE_CUTOFF} bytes"))
            self.memory_status.set(f"Key 1: {n1}/{SAFE_CUTOFF} bytes" + (" • OVER CAPACITY — upload blocked" if n1>SAFE_CUTOFF else "") + (" • " + "; ".join(errors) if errors else " • Independent script workspace"))
            self.key2_memory_status.set((f"Key 2: {n2}/{SAFE_CUTOFF} bytes • " + (f"{n2-SAFE_CUTOFF} OVER — device upload blocked" if n2>SAFE_CUTOFF else f"{SAFE_CUTOFF-n2} remaining")) if enabled else f"Key 2: inactive; {n2}/{SAFE_CUTOFF} bytes retained")
            lines=[f"OpenSayo v{VERSION} — READ-ONLY COMPILE PREVIEW",f"Endpoint: {p['fields'][p['endpoint']]['name']}",
                   f"Compiled bytes including FF FF: {used}/{SAFE_CUTOFF}",f"Typing {p['text_delay_ms']}ms; navigation {p['action_delay_ms']}ms; repeat gap {p['repeat_gap_ms']}ms",
                   "Overflow is planned only; no automatic hardware writes.","", "Actions:"]
            for f in p["fields"][:p["endpoint"]+1]:
                lines.append(f"{f['step']:02d}. {f['name']}: {f['value']!r}" + (" | Down, Enter = navigation" if f.get("format_type")=="Date" and f.get("format_option")=="Today's Date" else ""))
            lines.extend(["","Bytecode:"])
            lines += [f"{i:04X}: "+" ".join(f"{b:02X}" for b in script[i:i+16]) for i in range(0,len(script),16)]
            self.preview.configure(state="normal");self.preview.delete("1.0","end");self.preview.insert("1.0","\n".join(lines));self.preview.configure(state="disabled")
        except Exception as exc:
            self.memory_status.set(f"Invalid macro/settings: {exc}")
            self.key2_memory_status.set("Key 2: unavailable until macro compiles")
            self.macro_status.set(f"Macro preview unavailable: {type(exc).__name__}: {exc}")
            try:
                self.preview.configure(state="normal")
                self.preview.delete("1.0","end")
                self.preview.insert("1.0",f"COMPILE FAILED — {type(exc).__name__}: {exc}\n\nCheck macro fields and timing settings.")
                self.preview.configure(state="disabled")
            except (AttributeError,tk.TclError):
                pass
            if show_error:messagebox.showerror("Cannot compile",str(exc))

    def _save_layout_preferences(self):
        try:
            UI_PREFS_PATH.parent.mkdir(parents=True,exist_ok=True)
            try: prefs=json.loads(UI_PREFS_PATH.read_text(encoding="utf-8"))
            except (OSError,ValueError,TypeError): prefs={}
            prefs.update(device_layout=self.layout_mode.get(),scream_mode=self.scream_mode.get())
            UI_PREFS_PATH.write_text(json.dumps(prefs),encoding="utf-8")
        except OSError:pass

    def _on_scream_changed(self):
        if not self.scream_mode.get():
            retro=getattr(self,"_retro_window",None)
            if retro is not None:
                try:
                    if retro.winfo_exists():
                        retro.destroy()
                except tk.TclError:
                    pass
                self._retro_window=None
        self._save_layout_preferences()
        self._poll_caps()

    def _switch_device_layout(self):
        self._save_layout_preferences()
        if self.layout_mode.get()=="8":
            self.two_key_toolbar.pack_forget()
            self.eight_key_toolbar.pack(fill="x",padx=12,pady=3,after=self.workspace_label)
        else:
            self.eight_key_toolbar.pack_forget()
            self.two_key_toolbar.pack(fill="x",padx=2,pady=2,after=self.workspace_label)
        self._sync_layout_details()
        self._sync_eight_workspace_visibility()
        # Refresh field ownership immediately when changing device layouts.
        # Eight-key field editing must not inherit the two-key Key 2 lockout.
        self._update_form_fade()
        if self.workspace_kind=="freeform":self._freeform_live_preview()

    def _sync_eight_workspace_visibility(self):
        """The original Step 41 editors remain the only editors in v1.11."""
        return

    def _show_eight_workspace(self):
        """Return to the appropriate original editor, never a duplicate 8-key tab."""
        if self.layout_mode.get()!="8":
            self.layout_mode.set("8")
            self._switch_device_layout()
        if self.workspace_kind=="freeform":
            self.book.select(self.freeform_tab)
        else:
            self.book.select(self.macro_outer)

    def _eight_selected_slot(self):
        slot=int(self.eight_script_slot.get())
        if slot not in range(64):
            raise ValueError("Script index must be 0–63.")
        return slot

    def _eight_slot_changed(self):
        """Top picker sets ONLY the target slot, never overwrites current editor."""
        if getattr(self,"_eight_busy",False):return
        self._update_eight_meter()
        if hasattr(self,"session_status"):
            self.session_status.set(f"8-key destination Script {self.eight_script_slot.get()} selected; editor unchanged.")

    def _eight_source(self):
        """Exactly mirror two-button Source selection, without stale 8-key drafts."""
        if self.workspace_kind=="freeform":
            return self._freeform_source()
        # In eight-key Form View there is only one visible endpoint. Do not
        # accidentally use hidden two-button Key 2 focus as the macro source.
        return self._compile_form_key(1)[0]

    @staticmethod
    def _eight_encode(source):
        from alpha22_device_ops import encode_script
        from eight_key_protocol_v111 import OBSERVED_WRITE_EXTENT
        validate_script(source)
        # The tested 8-key protocol uses an explicit bytecode EXIT (0xFF).
        code=encode_script(source)+b"\xFF"
        if len(code)<2:
            raise ValueError("Empty script blocked; enter a macro first")
        if len(code)>OBSERVED_WRITE_EXTENT:
            raise ValueError(f"Macro is {len(code)} bytes, observed limit {OBSERVED_WRITE_EXTENT}")
        return code

    def _eight_import_into_original_editor(self,source,slot):
        """Show validated readback in the original editor without discarding actions."""
        validate_script(source)
        self._eight_encode(source)
        readable,_=script_to_readable(source)
        if self.workspace_kind=="freeform":
            self._set_active_script(source,update_freeform=False)
            self._freeform_sync=True
            try:
                self.freeform_text.delete("1.0","end")
                self.freeform_text.insert("1.0",readable)
                self.freeform_text.edit_modified(False)
                self._freeform_imported_raw=source
            finally:self._freeform_sync=False
            self._freeform_live_preview()
            mapped=True
        else:
            try:
                # Validate before touching any field or script; no partial import.
                self._device_form_candidate(source,1)
                end=self._apply_device_form_readback(source,1)
                self._macro_form_sync_error=""
                self.macro_status.set(f"Script {slot} loaded into Field View through field {end+1}; original script timing retained.")
                mapped=True
            except ValueError as exc:
                # Unlike Freeform, Form View is the active editor in this mode.
                # Never install a raw script the form cannot compile, because
                # the byte meter and a future Save would then use stale fields.
                self._last_unmapped_device_script=source
                self._macro_form_sync_error=str(exc)
                raise ValueError("Readback not installed: " + str(exc) +
                                 ". Current form, script and byte meter preserved.") from exc
        self.eight_slot_drafts[slot]=source
        self._show_eight_workspace()
        if self.workspace_kind=="form_project" and mapped:
            self.book.select(self.fields_tab)
            self.root.after_idle(lambda:self.book.select(self.fields_tab))
        self._update_eight_meter()
        return mapped

    def _eight_import_focused(self):
        from tkinter import filedialog
        from pathlib import Path
        if getattr(self,"_eight_busy",False):return
        slot=self._eight_selected_slot()
        name=filedialog.askopenfilename(title=f"Import Script {slot}",
             filetypes=[("Sayo macros","*.sayo *.txt *.macro"),("All files","*.*")],parent=self.root)
        if not name:return
        try:
            source=Path(name).read_text(encoding="utf-8-sig")
            self._eight_encode(source)
            if not messagebox.askyesno("Import Script",f"Replace the current editor with Script {slot} from file?\n\nNo device write.",parent=self.root):return
            self._eight_import_into_original_editor(source,slot)
            self.session_status.set(f"Imported Script {slot} into original editor; device unchanged")
        except Exception as exc:messagebox.showerror("Script import rejected",str(exc)+"\n\nEditor unchanged if validation failed.",parent=self.root)

    def _eight_busy_set(self,busy):
        self._eight_busy=busy
        for button in (self._eight_import_button,self._eight_load_button,self._eight_save_button):
            button.configure(state="disabled" if busy else "normal")
        self.eight_script_picker.configure(state="disabled" if busy else "readonly")

    def _eight_start_transfer(self,kind,slot,job):
        if self._eight_busy:return
        self._eight_busy_set(True)
        self._eight_transfer_token=(kind,slot)
        self.session_status.set(f"8-key Script {slot}: {kind} in progress (background HID task)")
        def worker():
            try: self._eight_transfer_queue.put((kind,slot,True,job()))
            except Exception as exc:self._eight_transfer_queue.put((kind,slot,False,str(exc)))
        threading.Thread(target=worker,daemon=True,name=f"OpenSayo-8key-{kind}").start()

    def _poll_eight_transfer(self):
        import queue
        try:
            while True:
                kind,slot,success,result=self._eight_transfer_queue.get_nowait()
                self._eight_busy_set(False)
                if not success:
                    self.session_status.set(f"8-key Script {slot}: {kind} stopped; no automatic retry")
                    messagebox.showerror(f"8-key {kind} stopped",str(result)+"\n\nCurrent editor was preserved if this was a Load. Don't blindly retry a write.",parent=self.root)
                elif kind=="load":
                    # Still no data changed until response and parser were validated.
                    source=result
                    if self._eight_selected_slot()!=slot:
                        messagebox.showwarning("Load not applied","Selected script changed during read; editor unchanged.",parent=self.root)
                    else:
                        try:
                            mapped=self._eight_import_into_original_editor(source,slot)
                        except (ValueError,TypeError) as exc:
                            self.session_status.set(f"8-key Script {slot}: readback not applied")
                            messagebox.showwarning("Script not applied",str(exc),parent=self.root)
                            continue
                        if mapped:
                            self.session_status.set(f"8-key Script {slot}: read back and loaded into original editor")
                            messagebox.showinfo("Script loaded",f"Script {slot} loaded from device. Field View / Freeform synchronized.",parent=self.root)
                        else:
                            self.session_status.set(f"8-key Script {slot}: raw script loaded; form unchanged")
                            messagebox.showwarning("Form mapping unavailable",f"Script {slot} was read and preserved in Macro Viewer, but some instructions cannot be represented by the current field definitions. The form was left unchanged. Do not write from Form View until reconciled.",parent=self.root)
                elif kind=="save":
                    self.session_status.set(f"8-key Script {slot}: USB save sent; physical test still required")
                    messagebox.showinfo("Physical verification required",
                         f"Script {slot} write sent.\n\nUnplug/reconnect, then test the physical button assigned to Script {slot} in Notepad. "
                         "Check other buttons before calling it successful. USB acknowledgment is not proof of persistence.",parent=self.root)
        except queue.Empty:pass
        try:self.root.after(125,self._poll_eight_transfer)
        except tk.TclError:pass

    def _eight_load_focused(self):
        """8-key slot-specific READ, bytecode and parser checks before editor mutation."""
        if getattr(self,"_eight_busy",False):return
        slot=self._eight_selected_slot()
        if not messagebox.askyesno("Read-only 8-key Load",
            f"Attempt a read-only hardware load from Script {slot}?\n\n"
            "The 8-key slot READ has not yet been physically verified. "
            "If its response is unexpected, the current editor will be preserved. No flash save will be sent.",parent=self.root):return
        def job():
            import hid
            from eight_key_script_read_v111 import read_script_slot
            from device_readback import decode
            image=read_script_slot(hid,slot)
            source,unknown,used=decode(image)
            if unknown or not source.strip():
                raise ValueError("Device replied with unknown or empty bytecode. Editor left unchanged.")
            self._eight_encode(source)
            return source
        self._eight_start_transfer("load",slot,job)

    def _eight_save_focused(self):
        """Save directly from original Form or Freeform; no second editor."""
        if getattr(self,"_eight_busy",False):return
        slot=self._eight_selected_slot()
        try:
            source=self._eight_source()
            code=self._eight_encode(source)
        except Exception as exc:return messagebox.showerror("Macro not ready",str(exc)+"\nNo device write attempted.",parent=self.root)
        warning=(f"Save the current {'Freeform' if self.workspace_kind=='freeform' else 'Form View'} macro to Script {slot}?\n"
                 f"Encoded size: {len(code)} / 2028 bytes\n\n"
                 "This replaces the script on the 8-key device and performs a flash save. "
                 "Back up your script first; there is no automatic rollback.\n\n"
                 "Continue?")
        if not messagebox.askyesno("Save focused 8-key script",warning,parent=self.root):return
        self.eight_slot_drafts[slot]=source
        def job():
            import hid
            from eight_key_protocol_v111 import guarded_write_one
            return guarded_write_one(hid,slot,code)
        self._eight_start_transfer("save",slot,job)

    def _sync_layout_details(self):
        if not hasattr(self,"endpoint_labels"):return
        eight=self.layout_mode.get()=="8"
        self.endpoint_labels[0].configure(text="Endpoint:" if eight else "Key 1 endpoint:")
        if eight:
            self.endpoint_labels[1].grid_remove()
            self.key2_endpoint_picker.grid_remove()
        else:
            self.endpoint_labels[1].grid()
            self.key2_endpoint_picker.grid()
        if hasattr(self,"eight_capacity_label"):
            if eight:
                # Two-key bars and the redundant eight-key status line are
                # hidden; only the selected script's one byte bar is visible.
                self.capacity_row.pack_forget()
                self.eight_capacity_label.pack_forget()
                self.eight_meter_row.pack(anchor="w",pady=(4,4))
                self._update_eight_meter()
            else:
                self.eight_capacity_label.pack_forget()
                self.eight_meter_row.pack_forget()
                self.capacity_row.pack(anchor="w",pady=(4,3))
        if not eight and self._eight_flash_job is not None:
            self.root.after_cancel(self._eight_flash_job)
            self._eight_flash_job=None
            self._eight_flash_on=True
        if hasattr(self,"_draw_boss_bar") and not eight:self._draw_boss_bar()

    def _update_eight_meter(self):
        if not hasattr(self,"eight_meter") or self.layout_mode.get()!="8":return
        slot=self.eight_script_slot.get()
        self.eight_meter_title.set(f"Script {slot}")
        # Script selector chooses the destination. The bar measures the
        # current editor that will be sent to that destination; it must NOT
        # claim to know the stored hardware script (slot read is unverified).
        try:
            source=self._eight_source()
            from alpha22_device_ops import encode_script
            if source.strip():
                validate_script(source)
                size=len(encode_script(source))+1  # v2 script terminator
            else:
                size=0
            self.eight_meter_label.set(f"{size}/{EIGHT_SCRIPT_CAP} bytes")
            color=("#dc3535" if self._eight_flash_on else "#801919") if size>EIGHT_SCRIPT_CAP else "#edb92e" if size>1600 else "#25a64e"
        except Exception:
            size=0;color="#929292"
            self.eight_meter_label.set("Invalid/incomplete script")
        self.eight_meter.delete("all")
        width=max(170,self.eight_meter.winfo_width())
        self.eight_meter.create_rectangle(0,0,width,13,fill="#272a30",outline="")
        if size:self.eight_meter.create_rectangle(0,0,width*min(1,size/EIGHT_SCRIPT_CAP),13,fill=color,outline="")
        # Run a timer only while the selected editor exceeds the 8-key limit.
        # Cancel on recovery or layout change; never alter the macro contents.
        if self._eight_flash_job is not None:
            self.root.after_cancel(self._eight_flash_job)
            self._eight_flash_job=None
        if size>EIGHT_SCRIPT_CAP:
            self._eight_flash_job=self.root.after(650,self._flash_eight_capacity)
        else:
            self._eight_flash_on=True

    def _flash_eight_capacity(self):
        self._eight_flash_job=None
        if self.layout_mode.get()!="8":return
        self._eight_flash_on=not self._eight_flash_on
        self._update_eight_meter()

    def _focus_eight_key(self,number):
        # Keep physical-key assignment selection separate from script-slot editing.
        self.eight_focused_key.set(number)
        slot=self.eight_key_vars[number-1].get()
        self.eight_focused_label.set(f"Physical Key {number}: {slot}")

    def _eight_import_script(self):
        path=filedialog.askopenfilename(title="Import eight-key Sayo macro",filetypes=[("Sayo macro text","*.txt"),("All files","*.*")],parent=self.root)
        if not path:return
        try:
            from alpha22_device_ops import encode_script
            source=Path(path).read_text(encoding="utf-8-sig")
            validate_script(source)
            size=len(encode_script(source))
            if size>EIGHT_SCRIPT_CAP:raise ValueError(f"{size} bytes exceeds {EIGHT_SCRIPT_CAP} byte limit")
            slot=int(self.eight_script_slot.get())
            self.eight_slot_drafts[slot]=source
            self._update_eight_meter()
            self.eight_focused_label.set(f"Script {slot} imported locally ({size} bytes)")
            self.session_status.set(f"Imported Script {slot} locally; device NOT programmed")
            messagebox.showinfo("Script imported",f"Imported {size} compiled bytes into local Script {slot} draft.\nUse Save Focused Key for the experimental global-stream test.",parent=self.root)
        except Exception as exc:messagebox.showerror("Import failed",str(exc),parent=self.root)

    def _eight_load_notice(self):
        messagebox.showinfo("8-key script load", "Physical-key assignment readback is verified. The 0xF0 memory read currently exposes a global stream; independent script-slot reads are not yet established.",parent=self.root)

    def _eight_save_notice(self):
        slot=int(self.eight_script_slot.get())
        if slot!=0:
            messagebox.showwarning("Slot isolation not verified", "Only global stream Script 0 can be previewed. No writes are enabled.",parent=self.root)
            return
        try:
            from alpha22_device_ops import encode_script
            if self.workspace_kind=="freeform":source=self._freeform_source()
            else:source=self.eight_slot_drafts.get(slot) or self.macro_text.get("1.0","end-1c")
            validate_script(source)
            code=encode_script(source)
            if not code:raise ValueError("Cannot preview an empty macro")
            if len(code)>EIGHT_SCRIPT_CAP:raise ValueError(f"Compiled macro {len(code)} bytes exceeds {EIGHT_SCRIPT_CAP}")
            from eight_key_macro_writer import preview_global_memory_changes
            report,changed,backup=preview_global_memory_changes(code)
            self.session_status.set(f"PROTECTED READ-ONLY preview: {changed} bytes differ; no writes performed")
            messagebox.showinfo("PROTECTED memory comparison",f"No device memory was written.\n\n{changed} of 2048 bytes differ after preserving offsets 1998–2027.\n\nBackup: {backup}\n\nDiff report: {report}\n\nThis is NOT an isolated script-slot write. No writes are enabled.",parent=self.root)
        except Exception as exc:messagebox.showerror("Memory preview failed",str(exc),parent=self.root)

    def _eight_device_management(self):
        # Reuse the existing window instead of creating duplicates on every click.
        if self._raise_dialog("eight_device_management_window"):
            return
        win=tk.Toplevel(self.root)
        self.eight_device_management_window=win
        win.protocol("WM_DELETE_WINDOW",lambda: (win.destroy(),setattr(self,"eight_device_management_window",None)))
        win.title("8-Key Device Management — Experimental Apply")
        win.geometry("760x290")
        win.minsize(700,275)
        frame=ttk.Frame(win,padding=14);frame.pack(fill="both",expand=True)
        ttk.Label(frame,text="SayoDevice 2x4V RGB — Physical Key Assignments",font=("Segoe UI",12,"bold")).pack(anchor="w",pady=(0,8))
        ttk.Label(frame,text="Assign scripts 0–63 to physical keys. Choose script slots, then Apply Selections to write, verify and persist all eight assignments.",wraplength=710).pack(anchor="w",pady=(0,9))
        grid=ttk.Frame(frame);grid.pack(fill="x",pady=5)
        for i in range(8):
            cell=ttk.Frame(grid,padding=3);cell.grid(row=i//4,column=i%4,sticky="ew",padx=5,pady=4)
            ttk.Label(cell,text=f"Physical Key {i+1}").pack(anchor="w")
            ttk.Combobox(cell,textvariable=self.eight_key_vars[i],values=[f"Script {n}" for n in range(64)],state="readonly",width=15).pack(fill="x")
        for c in range(4):grid.columnconfigure(c,weight=1)
        row=ttk.Frame(frame);row.pack(fill="x",pady=8)
        ttk.Button(row,text="Read All 8 From Device",command=self._read_inline_eight_keys).pack(side="left",padx=3)
        ttk.Button(row,text="Compare Selections",command=self._compare_inline_eight_keys).pack(side="left",padx=3)
        ttk.Button(row,text="Apply Selections",command=self._apply_inline_eight_keys).pack(side="left",padx=3)
        ttk.Button(row,text="Close",command=win.destroy).pack(side="right",padx=3)
        ttk.Label(frame,textvariable=self.eight_key_status,wraplength=700).pack(anchor="w",pady=(4,0))
        ttk.Label(frame,text="Experimental device programming: write → readback → SAVE. Close other Sayo software before applying.",foreground="#a10016").pack(anchor="w",pady=(5,0))

    def _apply_inline_eight_keys(self):
        try:
            slots=[]
            for i,var in enumerate(self.eight_key_vars):
                value=var.get()
                if not value.startswith("Script "):
                    raise ValueError(f"Physical Key {i+1}: select Script 0–63 first")
                n=int(value.split()[-1])
                if not 0<=n<=63:raise ValueError(f"Invalid slot {n}")
                slots.append(n)
            if not messagebox.askyesno("Apply 8 physical-key assignments",
                "EXPERIMENTAL DEVICE WRITE\n\nThis will change all eight physical-key script assignments and save them to the keypad.\n\n"+
                "\n".join(f"Key {i+1} → Script {slot}" for i,slot in enumerate(slots))+"\n\nProceed?",parent=self.root):return
            from eight_key_writer import apply_assignments
            verified=apply_assignments(slots)
            self.eight_key_actual=verified
            self.eight_key_status.set("APPLIED + VERIFIED + SAVED: "+", ".join(f"K{i+1}=S{v}" for i,v in enumerate(verified)))
            messagebox.showinfo("8-key assignments saved","All eight assignments match device readback after persistent SAVE. Unplug/replug to confirm persistence.",parent=self.root)
        except Exception as exc:
            self.eight_key_status.set(f"APPLY STOPPED: {exc}")
            messagebox.showerror("8-key apply stopped",str(exc),parent=self.root)

    def _read_inline_eight_keys(self):
        if not messagebox.askyesno("Read 8-key device", "Read eight assignments from the 2x4V RGB? No changes will be made.",parent=self.root):return
        try:
            from eight_key_ui import read_eight
            records=read_eight()
            self.eight_key_actual=[slot for _,slot,_ in records]
            for i,slot in enumerate(self.eight_key_actual):
                self.eight_key_vars[i].set(f"Script {slot}" if slot is not None else "Unknown assignment")
            self.eight_key_status.set("8/8 records read. " + ("All script assignments decoded." if all(v is not None for v in self.eight_key_actual) else "Some keys have unknown assignments; no verification claimed."))
        except Exception as exc:
            self.eight_key_actual=[None]*8
            self.eight_key_status.set(f"Read failed: {exc}")
            messagebox.showerror("8-key read failed",str(exc),parent=self.root)

    def _compare_inline_eight_keys(self):
        if any(v is None for v in self.eight_key_actual):
            messagebox.showwarning("Not verified","Read all eight script assignments first.",parent=self.root)
            return
        count=sum(self.eight_key_vars[i].get()==f"Script {v}" for i,v in enumerate(self.eight_key_actual))
        self.eight_key_status.set(f"{count}/8 selections match device readback. No writes performed.")

    def _poll_caps(self):
        try:
            if sys.platform=="win32":
                on=bool(ctypes.windll.user32.GetKeyState(0x14)&1)
                if self.scream_mode.get():
                    if on:self.caps.configure(text="📢 SCREAM AWAY!!! — CAPS LOCK WARNINGS MUTED",bg="#e6e6e6",fg="#555")
                    else:
                        flash=(int(time.monotonic()*5)%2)==0
                        self.caps.configure(text="📢 I CAN'T HEAR YOU!!! 📢",bg="#ff7900" if flash else "#ffe500",fg="#000000")
                elif on:
                    phase=(int(time.monotonic()*2)%2)==0
                    self.caps.configure(text="⚠ CAPS LOCK ON — TURN IT OFF BEFORE RUNNING MACROS ⚠",bg="#b51621" if phase else "#ff5555",fg="white")
                else:self.caps.configure(text="✓ CAPS LOCK OFF — READY",bg="#d9f4e3",fg="#17673b")
            else:self.caps.configure(text="CAPS LOCK STATE: WINDOWS ONLY",bg="#eee",fg="#444")
        except Exception:self.caps.configure(text="CAPS LOCK STATE UNAVAILABLE — CHECK MANUALLY",bg="#ffe6e6",fg="#9a2222")
        if not getattr(self,"_caps_poll_scheduled",False):
            self._caps_poll_scheduled=True
            self.root.after(100,self._caps_tick)

    def _caps_tick(self):
        self._caps_poll_scheduled=False
        self._poll_caps()

    def _read_verified_assignments(self, info):
        """Read-only 0x16 twice per key; never treat mere USB presence as verification."""
        import hid
        from key_mapping_read import read_two_keys_twice
        dev=hid.device()
        try:
            dev.open_path(info["path"])
            reads=read_two_keys_twice(dev,make_packet)
        finally:
            dev.close()
        decoded=[]
        for key in (0,1):
            pairs=[r for r in reads if r["key"]==key]
            if len(pairs)!=2:raise ValueError(f"Key {key+1}: missing repeated response")
            a,b=pairs
            if a["received_bytes"]!=64 or b["received_bytes"]!=64 or a["raw"]!=b["raw"]:
                raise ValueError(f"Key {key+1}: incomplete or inconsistent readback")
            raw=bytes.fromhex(a["raw"])
            if raw[0]!=2 or raw[1]!=0 or raw[4]!=key or raw[2]!=0x1c:
                raise ValueError(f"Key {key+1}: unexpected response framing")
            selector=raw[19]
            if 0x40<=selector<=0x47 and raw[22]==0:
                decoded.append(("script",selector-0x3f))
            elif selector==0 and raw[22]!=0:
                decoded.append(("default",None))
            else:
                decoded.append(("unknown",None))
        return decoded

    def _open_eight_key_editor(self):
        from eight_key_ui import EightKeyWindow
        EightKeyWindow(self.root)

    def detect_device_configuration(self):
        """Read USB identity and compare repeated read-only assignment responses."""
        try:
            import hid
            devices=identify_supported_devices(hid)
            if len(devices) != 1:
                raise RuntimeError(f"Expected one supported SayoDevice configuration interface; found {len(devices)}. No commands sent.")
            model, detected_info = devices[0]
            if detected_info.get("product_id") == 0x000B:
                product = str(detected_info.get("product_string") or model)
                self._assignment_verified = False
                self._verified_serial = None
                self._update_assignment_warning()
                lines = [f"Detected: {product}", "Model: 8-key SayoDevice 2x4V RGB",
                         "USB VID/PID: 8089/000B", "Configuration collection: interface 1, FF11/0002",
                         "USB identity confirmed (enumeration only).",
                         "8-key readback available through 8-Key Editor; programming still disabled.",
                         "No USB reports sent. Existing 2-key writer remains locked to 8089/000C."]
                self.device_identity.set("\n".join(lines))
                self.device_status.set("Connected: 8-key SayoDevice — detection only; assignments unverified")
                messagebox.showinfo("Detected Device Configuration", "\n".join(lines), parent=self.root)
                return
            info=select_device(hid)
            def hexfmt(v):return f"0x{v:04X}" if isinstance(v,int) else "Not reported"
            product=str(info.get("product_string") or "Unknown")
            lines=[f"Product: {product}",f"Manufacturer: {info.get('manufacturer_string') or 'Not reported'}",
                   f"USB VID / PID: {hexfmt(info.get('vendor_id'))} / {hexfmt(info.get('product_id'))}",
                   f"Interface: {info.get('interface_number')}",
                   f"Usage page / usage: {hexfmt(info.get('usage_page'))} / {hexfmt(info.get('usage'))}",
                   f"Serial number: {info.get('serial_number') or 'Not reported'}"]
            verified=False
            try:
                if info.get('vendor_id')!=0x8089 or info.get('product_id')!=0x000c:
                    raise ValueError('Device model not validated for O2L V2 assignment decoding')
                mappings=self._read_verified_assignments(info)
                for key,(mode,bank) in enumerate(mappings,1):
                    lines.append(f"Physical Key {key}: "+(f"Script {bank} (read twice)" if mode=='script' else "Default Mode" if mode=='default' else "Unknown / unverified"))
                verified=all(mode=='script' for mode,_ in mappings) and all(
                    bank==int(var.get()) for (mode,bank),var in zip(mappings,(self.physical_key1,self.physical_key2)))
                lines.append("Assignments match selected values: "+("YES — readback verified" if verified else "NO / not verified"))
            except Exception as exc:
                lines.append(f"Assignment readback: Unverified ({exc})")
            self._assignment_verified=verified
            self._verified_serial=info.get("serial_number") if verified else None
            self._update_assignment_warning()
            self.device_identity.set("\n".join(lines))
            self.device_status.set(f"Connected: {product} — "+("assignments verified" if verified else "assignments unverified"))
            messagebox.showinfo("Detected Device Configuration","\n".join(lines),parent=self.root)
        except Exception as exc:
            self._assignment_verified=False
            self._update_assignment_warning()
            self.device_status.set("Device unavailable — assignments unverified")
            messagebox.showwarning("Device Detection",str(exc),parent=self.root)

    def detect(self):
        self.detect_device_configuration()

    def backup(self):
        try:
            import hid
            info=select_device(hid);dev=hid.device();dev.open_path(info["path"])
            try:a=read_script(dev);b=read_script(dev)
            finally:dev.close()
            if len(a)!=MEMORY_SIZE or a!=b:raise RuntimeError("Incomplete or inconsistent reads. No backup saved.")
            folder=Path.home()/"Downloads";folder.mkdir(exist_ok=True)
            name=folder/f"opensayo_v018_readonly_{time.strftime('%Y%m%d_%H%M%S')}.bin"
            with name.open("xb") as f:f.write(a)
            messagebox.showinfo("Backup complete",f"Read-only 512-byte backup saved:\n{name}\nSHA-256: {sha(a)}")
        except Exception as exc:messagebox.showerror("Backup failed",str(exc))

    def decode_protocol(self):
        paths=filedialog.askopenfilenames(title="Choose existing Key 2 captures (multiple allowed)",filetypes=[("Wireshark captures","*.pcapng")])
        if not paths:return
        try:
            report=analyze_key2(paths) + "\n\n" + ("="*70) + "\n\n" + decode(paths)
            self.protocol_log.delete("1.0","end")
            self.protocol_log.insert("end",report)
            self.protocol_log.see("1.0")
        except Exception as exc:
            messagebox.showerror("Offline decoder",str(exc))

    def export_protocol_report(self):
        content=self.protocol_log.get("1.0","end-1c")
        path=filedialog.asksaveasfilename(defaultextension=".txt",filetypes=[("Text files","*.txt")],initialfile="OpenSayo_Alpha5_Key2_Evidence.txt")
        if path:
            Path(path).write_text(content,encoding="utf-8")

    def analyze_pcaps(self):
        paths=filedialog.askopenfilenames(title="Choose one or two existing USB captures",filetypes=[("Wireshark captures","*.pcapng")])
        if not paths:return
        if len(paths)>2:
            messagebox.showwarning("Choose fewer files","Please choose at most two captures per comparison.")
            return
        try:
            report=describe(paths)
            self.pcap_log.delete("1.0","end")
            self.pcap_log.insert("end",report)
            self.pcap_log.see("1.0")
        except Exception as exc:
            messagebox.showerror("Offline inspection failed",str(exc))

    def export_pcap_analysis(self):
        content=self.pcap_log.get("1.0","end-1c")
        target=filedialog.asksaveasfilename(title="Export offline USB analysis",defaultextension=".txt",initialfile="OpenSayo_Key2_Analysis.txt",filetypes=[("Text file","*.txt")])
        if target:
            try:Path(target).write_text(content,encoding="utf-8")
            except Exception as exc:messagebox.showerror("Export failed",str(exc))

    def run_memory_audit(self):
        self._run_memory_audit(())

    def run_memory_audit_snapshots(self):
        paths=filedialog.askopenfilenames(title="Select existing diagnostic JSON snapshots (optional)",filetypes=[("JSON snapshots","*.json")])
        if paths:
            self._run_memory_audit(paths)

    def _run_memory_audit(self, paths):
        try:
            source=Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "opensayo_v019_alpha6_audit_source.txt"
            report=audit_memory(source, paths)
            self.memory_log.delete("1.0","end")
            self.memory_log.insert("end",report)
        except Exception as exc:
            messagebox.showerror("Offline memory audit",str(exc))

    def export_memory_audit(self):
        content=self.memory_log.get("1.0","end").strip()
        if not content:
            return
        path=filedialog.asksaveasfilename(title="Save memory audit",defaultextension=".txt",initialfile="OpenSayo_Alpha6_Memory_Audit.txt",filetypes=[("Text files","*.txt")])
        if path:
            Path(path).write_text(content+"\n",encoding="utf-8")

    def assess_readback(self):
        paths=filedialog.askopenfilenames(title="Choose existing captures (Q7, Q7M4, Q7M5)",filetypes=[("USBPcap captures","*.pcapng"),("All files","*.*")])
        if not paths:return
        try:
            report=assess_readback(paths)
            self.readback_log.delete("1.0","end")
            self.readback_log.insert("end",report)
        except Exception as exc:messagebox.showerror("Readback evidence analysis",str(exc))

    def export_readback(self):
        content=self.readback_log.get("1.0","end").strip()
        if not content:return
        path=filedialog.asksaveasfilename(title="Save Key 2 readback assessment",defaultextension=".txt",initialfile="OpenSayo_Alpha8_Readback_Evidence.txt",filetypes=[("Text files","*.txt")])
        if path:Path(path).write_text(content+"\n",encoding="utf-8")

    def live_readback(self):
        if not messagebox.askyesno("Known-region readback only",
            "Open the SayoDevice configuration interface and issue only the established "
            "F0 READ requests for Key 1 addresses 0 through 511, twice?\n\n"
            "This sends USB read requests but NO write commands. It will NOT probe "
            "Key 2 or unknown addresses. Continue?"):
            return
        dev=None
        lines=["OpenSayo Alpha 10 — LIVE KNOWN-REGION READBACK",
               "USB requests: F0 READ ONLY, addresses within 0..511; no script writes.",
               "This test cannot establish Key 2 readback.",""]
        try:
            import hid
            info=select_device(hid)
            lines.extend(["Device matched:",
                f"  VID/PID: {VID:04X}/{PID:04X}",
                f"  Product: {info.get('product_string')}",
                f"  Interface: {info.get('interface_number')}",
                f"  Usage page/usage: {info.get('usage_page')}/{info.get('usage')}",""])
            dev=hid.device();dev.open_path(info["path"])
            first=read_script(dev)
            second=read_script(dev)
            lines.extend([f"First read: {len(first)} bytes, SHA-256 {sha(first)}",
                          f"Second read: {len(second)} bytes, SHA-256 {sha(second)}",
                          f"Exact match: {first==second}",
                          f"Complete stable Key 1 baseline: {len(first)==MEMORY_SIZE and first==second}",""])
            if len(first)!=MEMORY_SIZE or first!=second:
                lines.append("INCOMPLETE/INCONSISTENT: Do not use this read as a trusted baseline.")
            else:
                lines.append("Verified: established Key 1 region is readable and stable.")
            lines.extend(["NOT verified: Key 2 address, selection, response, or storage.",
                          "No unknown addresses were queried. No USB writes were issued."])
        except Exception as exc:
            lines.append(f"STOPPED: {type(exc).__name__}: {exc}")
        finally:
            if dev is not None:
                try:dev.close()
                except Exception:pass
            self.live_log.delete("1.0","end")
            self.live_log.insert("end","\n".join(lines)+"\n")

    def run_crosscheck(self):
        from key_assignment_crosscheck import analyze
        self.crosscheck_log.delete("1.0","end")
        self.crosscheck_log.insert("end",analyze()+"\n")

    def capture_assignment_comparison(self):
        label=self.assignment_label.get().strip()
        if not label:
            messagebox.showwarning("Label required","Enter a label describing the CURRENT website assignments.");return
        if not messagebox.askyesno("Read-only assignment capture",f"Have you applied the assignments on the official website?\n\nCapture: {label}\n\nOpenSayo sends only FOUR 0x16 READ requests (key indexes 0 and 1, twice). No writes, Save, F0, or unknown addresses. Continue?"):
            return
        dev=None
        try:
            import hid
            from key_mapping_read import read_two_keys_twice
            info=select_device(hid)
            dev=hid.device();dev.open_path(info['path'])
            results=read_two_keys_twice(dev,make_packet)
            grouped={key:[x for x in results if x['key']==key] for key in (0,1)}
            if any(len(grouped[key])!=2 or grouped[key][0]['raw']!=grouped[key][1]['raw'] or grouped[key][0]['received_bytes']!=64 or grouped[key][0].get('report_id')!=2 or grouped[key][0].get('status')!=0 for key in (0,1)):
                raise ValueError("Both key records must be complete, status 0, and repeat exactly; capture discarded")
            snap={'label':label,'device':str(info.get('product_string')),'key0':grouped[0][0]['raw'],'key1':grouped[1][0]['raw']}
            updated_snapshots = self.assignment_snapshots + [snap]
            rendered = assignment_report(updated_snapshots)
            self.assignment_compare_log.delete('1.0','end')
            self.assignment_compare_log.insert('end',rendered)
            self.assignment_snapshots.append(snap)
        except Exception as exc:
            messagebox.showerror("Capture not stored",f"{type(exc).__name__}: {exc}\n\nExisting snapshots remain intact.")
        finally:
            if dev is not None:
                try:dev.close()
                except Exception:pass

    def export_assignment_comparison(self):
        if not self.assignment_snapshots:
            messagebox.showinfo("Nothing to export","Capture at least one assignment first.");return
        target=filedialog.asksaveasfilename(defaultextension='.txt',filetypes=[('Text report','*.txt')],initialfile='OpenSayo_Alpha14_Assignment_Comparison.txt')
        if target:
            Path(target).write_text(assignment_report(self.assignment_snapshots),encoding='utf-8')
            messagebox.showinfo("Report saved",f"Saved: {target}")

    def live_key_mapping(self):
        if not messagebox.askyesno("Experimental mapping READ (0x16)",
            "This sends exactly four 0x16 mapping READ requests: key indexes 0 and 1, twice.\n"
            "It sends NO mapping writes, NO flash Save, and NO script writes.\n\n"
            "The command is documented for a related SayoDevice model but has NOT been verified on your O2L V2.\n\n"
            "Proceed?"):
            return
        lines=["OpenSayo Alpha 12 — RAW KEY ASSIGNMENT RESPONSE INSPECTOR", "Protocol source: ikagawa/SayoDeviceConfigViewer (different model)",
               "Only command 0x16, payload [0, key_index], key indexes 0 and 1, two passes.", "No writes, no Save, no F0 probing.\n"]
        dev=None
        try:
            import hid
            from key_mapping_read import read_two_keys_twice
            info=select_device(hid)
            lines.append("Matched device: "+str(info.get('product_string')))
            dev=hid.device();dev.open_path(info['path'])
            results=read_two_keys_twice(dev,make_packet)
            for item in results:
                lines.append(f"Pass {item['pass']} key {item['key']}: status={item['status']} bytes={item['received_bytes']} declared_length={item['length']}")
                lines.append(f"  checksum valid={item['checksum_ok']} offset={item.get('checksum_offset')} received={item.get('checksum_received')} calculated={item.get('checksum_calculated')}")
                lines.append(f"  alternatives: payload_sum={item.get('sum_payload_only')} no_report_id_sum={item.get('sum_without_report_id')} complement={item.get('sum_complement')}")
                if item.get('note'):lines.append('  NOTE: '+item['note'])
                if item.get('stop_reason'):lines.append('  STOP: '+item['stop_reason'])
                if item['status']==0 and item['checksum_ok']:
                    lines.append(f"  payload bytes={item['length']}; layers={len(item['layers'])}")
                    for layer in item['layers']:
                        lines.append(f"  Fn{layer['layer']}: mode=0x{layer['mode']:02X}, flags=0x{layer['flags']:02X}, values={layer['values']}")
                    if item.get('note'):lines.append('  '+item['note'])
                lines.append('  raw='+item['raw'])
            for key in (0,1):
                pair=[x for x in results if x['key']==key]
                if len(pair)==2:lines.append(f"Key {key} exact repeat: {pair[0]['raw']==pair[1]['raw']}")
                else:lines.append(f'Key {key} exact repeat: unavailable (only {len(pair)} response(s))')
            lines.append("Key index 1 is a CANDIDATE for physical Key 2, not independently proven.")
            lines.append("This reads assignments, NOT a separate macro-script memory bank.")
        except Exception as exc:
            lines.append(f"STOPPED: {type(exc).__name__}: {exc}")
        finally:
            if dev is not None:
                try:dev.close()
                except Exception:pass
            self.mapping_log.delete('1.0','end');self.mapping_log.insert('end','\n'.join(lines)+'\n')

    def clear_bank_snapshots(self):
        if messagebox.askyesno("Clear bank snapshots", "Discard all Alpha 15 snapshots from memory?"):
            self.bank_snapshots=[]
            self.bank_log.delete('1.0','end')
            self.bank_log.insert('end',"No stored snapshots.\n")

    def capture_bank_snapshot(self):
        label=self.bank_label.get().strip() or f"Snapshot {len(self.bank_snapshots)+1}"
        if not messagebox.askyesno("Read-only F0 capture",f"Have you disconnected the official website? (For reconnect tests, reconnect the keypad before capturing.)\n\nCapture: {label}\n\nOnly known F0 region addresses 0..511 will be read twice. No writes, no Save commands, no unknown addresses. Continue?"):
            return
        dev=None
        try:
            import hid
            info=select_device(hid)
            dev=hid.device();dev.open_path(info['path'])
            first=read_script(dev);second=read_script(dev)
            if len(first)!=MEMORY_SIZE or first!=second:
                raise ValueError(f"Unstable or incomplete known-region reads: lengths {len(first)}/{len(second)}, identical={first==second}. Snapshot NOT stored.")
            snapshot={'label':label,'device':str(info.get('product_string')),'data':first}
            updated=self.bank_snapshots+[snapshot]
            rendered=self._render_bank_snapshots(updated)
            self.bank_log.delete('1.0','end');self.bank_log.insert('end',rendered)
            self.bank_snapshots.append(snapshot)
        except Exception as exc:
            messagebox.showerror("F0 capture not stored",f"{type(exc).__name__}: {exc}\nExisting snapshots remain intact.")
        finally:
            if dev is not None:
                try:dev.close()
                except Exception:pass

    @staticmethod
    def _render_bank_snapshots(snapshots):
        import hashlib
        lines=["OpenSayo Alpha 16 — F0 PERSISTENCE COMPARISON", "Read-only F0 addresses 0..511; two identical reads required per snapshot.", "This is one known region, NOT a verified per-key bank or library slot selector.", "No device writes or unknown addresses were accessed.", ""]
        previous=None
        for index,snap in enumerate(snapshots,1):
            data=snap['data']
            lines.append(f"SNAPSHOT {index}: {snap['label']}  Device: {snap['device']}")
            lines.append(f"  Length: {len(data)}  SHA-256: {hashlib.sha256(data).hexdigest()}")
            lines.append(f"  Nonzero bytes: {sum(b!=0 for b in data)}; FF bytes: {data.count(255)}")
            known={
              '44ae545e032b7e731fe6ae29b355f0274372b4bd10e47418e042a45237205dcd':'Previously observed after reconnect / original Alpha 15 captures',
              '85e8e5647ff488a10294215ea9b512093deee302bb2d587da4ebf850bfe35086':'Previously observed while Script 8 began with P',
              '16d9790fe9e2e3c8e213b79c9088db46ca2e62e99265ab3f155995ff1387a88c':'Previously observed after restoring Script 8 to O, before reconnect',
            }
            match=known.get(hashlib.sha256(data).hexdigest())
            if match:lines.append(f"  Historical fingerprint match: {match} (association only; NOT proof of bank identity)")
            if previous is not None:
                changed=[i for i,(a,b) in enumerate(zip(previous,data)) if a!=b]
                lines.append(f"  Previous -> this: {len(changed)} byte positions changed")
                lines.append("  Changed offsets (decimal): "+(str(changed) if changed else "NONE"))
                for pos in changed[:100]:lines.append(f"    [{pos}] {previous[pos]:02X} -> {data[pos]:02X}")
                if len(changed)>100:lines.append(f"    ... {len(changed)-100} additional changes omitted")
            previous=data
            lines.append("")
        lines.append("Interpretation: F0 may be a working buffer, a read window, or a fixed region. Matching historical hashes show identical bytes, NOT which permanent slot is addressed. No save/commit protocol is inferred.")
        return '\n'.join(lines)+'\n'

    def export_bank_comparison(self):
        if not self.bank_snapshots:
            messagebox.showinfo("Nothing to export", "Capture a snapshot first.");return
        target=filedialog.asksaveasfilename(title="Export Alpha 16 F0 comparison",defaultextension=".txt",initialfile="OpenSayo_Alpha16_F0_Persistence.txt",filetypes=[("Text files","*.txt")])
        if target:Path(target).write_text(self._render_bank_snapshots(self.bank_snapshots),encoding='utf-8')

    def run_shared_memory(self):
        if not messagebox.askyesno("Read-only shared-memory investigation",
            "Read the already verified 512-byte F0 script region twice?\n\n"
            "This sends read requests ONLY at established addresses 0..511. "
            "No unknown addresses, programming, or Save operations. Continue?"):
            return
        dev=None
        lines=["OpenSayo Alpha 13 — SHARED SCRIPT MEMORY INSPECTION",
               "F0 reads ONLY in known 0..511 region, twice. No writes.",""]
        try:
            import hid
            info=select_device(hid)
            lines.append(f"Device: {info.get('product_string')} interface={info.get('interface_number')}")
            dev=hid.device();dev.open_path(info['path'])
            first=read_script(dev);second=read_script(dev)
            lines.extend([f"First read: {len(first)} bytes; SHA-256 {sha(first)}",
                          f"Second read: {len(second)} bytes; SHA-256 {sha(second)}",
                          f"Identical: {first==second}"])
            if len(first)==MEMORY_SIZE and first==second:
                from shared_memory_inspector import inspect
                lines.append(inspect(first))
            else:
                lines.append("STOP: Region incomplete or unstable. Byte interpretation withheld.")
        except Exception as exc:
            lines.append(f"STOPPED: {type(exc).__name__}: {exc}")
        finally:
            if dev is not None:
                try:dev.close()
                except Exception:pass
            self.shared_log.delete('1.0','end')
            self.shared_log.insert('end','\n'.join(lines)+'\n')

    def export_shared_memory(self):
        content=self.shared_log.get('1.0','end').strip()
        if not content:return
        target=filedialog.asksaveasfilename(title="Save shared-memory inspection",defaultextension=".txt",initialfile="OpenSayo_Alpha13_Shared_Memory.txt",filetypes=[("Text files","*.txt")])
        if target:Path(target).write_text(content+'\n',encoding='utf-8')

    def export_live_readback(self):
        content=self.live_log.get("1.0","end").strip()
        if not content:return
        target=filedialog.asksaveasfilename(title="Save live readback report",defaultextension=".txt",initialfile="OpenSayo_Alpha9_Live_Readback.txt",filetypes=[("Text files","*.txt")])
        if target:Path(target).write_text(content+"\n",encoding="utf-8")

    def capture_key2_snapshot(self):
        if not messagebox.askyesno("Read-only exploratory scan",
            "This will read the known 0–511 script region twice and issue "
            "read requests at addresses 512–2047 using the known F0 read command. "
            "These additional addresses are NOT verified for this firmware. "
            "No script data will be written. Continue?"):
            return
        try:
            import hid
            info=select_device(hid)
            dev=hid.device()
            dev.open_path(info["path"])
            try:
                first=read_script(dev)
                second=read_script(dev)
                if len(first)!=MEMORY_SIZE or first!=second:
                    raise RuntimeError("Key 1 region did not return two matching 512-byte reads.")
                blocks=[]
                for address in range(512,2048,MAX_DATA):
                    try:
                        data,status=read_report(dev,address)
                        blocks.append({"address":address,"status":status,
                                       "hex":data.hex() if data is not None else None})
                        if status or data is None or not data:
                            break
                    except Exception as exc:
                        blocks.append({"address":address,"error":str(exc)})
                        break
            finally:
                dev.close()
            snapshot={"format":"OpenSayo key2 exploratory snapshot v1",
                      "timestamp":time.strftime("%Y-%m-%d %H:%M:%S"),
                      "device":{"vid":VID,"pid":PID,"interface":INTERFACE},
                      "key1_512_hex":first.hex(),
                      "key1_sha256":sha(first),
                      "extended_read_blocks":blocks}
            target=filedialog.asksaveasfilename(
                title="Save diagnostic snapshot",
                defaultextension=".json",
                initialfile=f"opensayo_key2_snapshot_{time.strftime('%Y%m%d_%H%M%S')}.json",
                filetypes=[("JSON snapshot","*.json")])
            if not target:
                self.diag_log.insert("end","Capture completed, but snapshot was not saved.\\n")
                return
            Path(target).write_text(json.dumps(snapshot,indent=2),encoding="utf-8")
            self.diag_log.insert("end",f"Saved: {target}\\nKey 1 SHA-256: {sha(first)}\\n"
                                     f"Extended read blocks: {len(blocks)}\\n\\n")
            self.diag_log.see("end")
            messagebox.showinfo("Snapshot saved","Read-only snapshot saved. Do not change Key 1. "
                                "For the second snapshot, change only Key 2 x → z using the website, "
                                "press its Save, then capture again.")
        except Exception as exc:
            messagebox.showerror("Diagnostic stopped",str(exc))

    def compare_key2_snapshots(self):
        before=filedialog.askopenfilename(title="Choose BEFORE snapshot (Key 2 = x)",
                     filetypes=[("JSON snapshot","*.json")])
        if not before:return
        after=filedialog.askopenfilename(title="Choose AFTER snapshot (Key 2 = z)",
                     filetypes=[("JSON snapshot","*.json")])
        if not after:return
        try:
            a=json.loads(Path(before).read_text(encoding="utf-8"))
            b=json.loads(Path(after).read_text(encoding="utf-8"))
            if a.get("format")!="OpenSayo key2 exploratory snapshot v1" or b.get("format")!=a["format"]:
                raise ValueError("Unsupported snapshot format.")
            x=bytes.fromhex(a["key1_512_hex"])
            y=bytes.fromhex(b["key1_512_hex"])
            if len(x)!=512 or len(y)!=512:raise ValueError("Invalid 512-byte snapshot.")
            changes=[(i,x[i],y[i]) for i in range(512) if x[i]!=y[i]]
            aa={v["address"]:v for v in a["extended_read_blocks"]}
            bb={v["address"]:v for v in b["extended_read_blocks"]}
            changed_ext=[]
            for addr in sorted(set(aa)|set(bb)):
                if aa.get(addr)!=bb.get(addr):
                    changed_ext.append((addr,aa.get(addr),bb.get(addr)))
            lines=[f"BEFORE: {before}",f"AFTER:  {after}",
                   f"Key 1 region differences: {len(changes)} byte(s)"]
            lines += [f"  offset {i:03d}: {old:02X} → {new:02X}" for i,old,new in changes[:100]]
            if len(changes)>100:lines.append(f"  ... {len(changes)-100} additional differences")
            lines.append(f"Extended read block differences: {len(changed_ext)}")
            for addr,old,new in changed_ext[:40]:
                lines.append(f"  address {addr}:")
                lines.append(f"    before: {old}")
                lines.append(f"    after:  {new}")
            lines.append("\\nDifferences are clues, NOT proof of Key 2 memory layout. No writes performed.")
            self.diag_log.delete("1.0","end")
            self.diag_log.insert("end","\\n".join(lines))
            self.diag_log.see("1.0")
        except Exception as exc:messagebox.showerror("Comparison failed",str(exc))

    def select_baseline(self):
        path=filedialog.askopenfilename(
            title="Select verified 512-byte backup matching this keypad",
            initialdir=str(Path.home()/"Downloads"),
            filetypes=[("Binary backup","*.bin")])
        if not path:
            return
        try:
            data=Path(path).read_bytes()
            if len(data)!=MEMORY_SIZE:
                raise ValueError(f"Backup contains {len(data)} bytes; exactly 512 required.")
            self.baseline_path=Path(path)
            self.device_status.set(f"Selected baseline: {self.baseline_path.name}")
            messagebox.showinfo("Baseline selected",
                f"Backup: {path}\nSHA-256: {sha(data)}\n\n"
                "The device must match this backup in two fresh reads before any write.")
        except Exception as exc:
            self.baseline_path=None
            messagebox.showerror("Invalid baseline",str(exc))

    def write_device(self):
        if self.baseline_path is None:
            messagebox.showerror("Baseline required",
                "Select a verified 512-byte device backup first. "
                "You can create a fresh one with Backup Device (read-only).")
            return
        try:
            p=self.current_project()
            script=compile_v018(p["fields"],p["endpoint"],
                p["text_delay_ms"],p["action_delay_ms"],p["repeat_gap_ms"],
                enforce_limit=True)
            expected=self.baseline_path.read_bytes()
            if len(expected)!=MEMORY_SIZE:
                raise RuntimeError("Baseline is no longer exactly 512 bytes.")
            import hid
        except Exception as exc:
            messagebox.showerror("Preparation failed — no write sent",str(exc))
            return
        if not messagebox.askyesno("Experimental Key 1 write",
            f"Write {len(script)} compiled bytes + 2 EXIT bytes to Key 1?\n\n"
            f"Endpoint: {p['fields'][p['endpoint']]['name']}\n"
            f"Safe limit: {SAFE_CUTOFF} bytes\n"
            f"Baseline: {self.baseline_path.name}\n"
            f"SHA-256: {sha(expected)}\n\n"
            "Two matching live reads and a verified fresh backup are required. "
            "USB interruption could leave a partial script. Key 2 is untouched. "
            "Do not test on a live record. Continue?"):
            return
        if not messagebox.askyesno("Final hardware confirmation",
            "LAST CHECK: This will modify device memory. "
            "Keep the keypad connected. If an error occurs, DO NOT RETRY BLINDLY. Proceed?"):
            return
        try:
            info=select_device(hid)
            dev=hid.device()
            dev.open_path(info["path"])
            try:
                backup,after=write_script(dev,script,expected)
            finally:
                dev.close()
            self.device_status.set("Key 1: script write/readback verified; website Save may still be required")
            messagebox.showinfo("Key 1 readback verified",
                f"Full 512-byte readback matched the intended memory image.\n"
                f"Fresh prewrite backup: {backup}\nSHA-256: {sha(after)}\n\n"
                "Execution and persistence are not yet verified. "
                "The official SayoDevice website may still require Save.")
            try:
                if not webbrowser.open("https://app.sayodevice.com/",new=2):
                    messagebox.showwarning("Website", "Open https://app.sayodevice.com/ manually to Save.")
            except Exception as exc:
                messagebox.showwarning("Website",
                    f"Open https://app.sayodevice.com/ manually to Save.\n{exc}")
        except Exception as exc:
            self.device_status.set("Key 1: WRITE STOPPED — investigate before retry")
            messagebox.showerror("Write stopped",
                f"{exc}\n\nDO NOT RETRY BLINDLY.")

    def close(self):
        if not self._workspace_confirm_leave():return
        if self._save_job:self.root.after_cancel(self._save_job)
        self.save_session();self._save_key_preferences();self._close_form_preview();self.root.destroy()

    def _a22_device_load(self):
        """Read a bank without modifying the device or existing text on failure."""
        try:
            from device_readback import read_bank,decode
            bank=self._focused_bank()
            image=read_bank(bank)
            decoded,unknown,used=decode(image)
            if unknown:
                messagebox.showwarning("Unknown instructions", "Script includes unsupported instructions. The editor was not replaced. Raw data is retained in memory for this session.")
                self._a22_last_raw=image
                return
            # Textual EXIT is optional; keep device readback as observed.
            content=decoded.rstrip()
            # A device read is untrusted bytecode. Never replace the editor with
            # malformed/incomplete key names; retain the exact original bytes.
            try:
                validate_script(content)
            except ValueError as parse_error:
                self._a22_last_raw=image
                self._a22_loaded_bank=None
                import re as _re
                malformed = [(n, line) for n, line in enumerate(content.splitlines(), 1)
                             if _re.fullmatch(r"(?:PRESS|RELEASE)_(?:GK|SK)\s+hidkey_", line.strip())]
                detail = ("Incomplete HID key name in device readback: " +
                          ", ".join(f"line {n} ({line})" for n, line in malformed)
                          if malformed else str(parse_error))
                self.macro_status.set("Readback needs inspection — editor unchanged")
                messagebox.showwarning("Device readback not imported",
                    detail + "\n\nNo device writes were attempted. The existing editor "
                    "was NOT changed. Raw device bytes were retained for this session. "
                    "This may indicate an unsupported key code or decoder mismatch; "
                    "do not save this readback to hardware.")
                return
            if self.workspace_kind=="form_project":
                try:
                    self._device_form_candidate(content,self.focused_key.get())
                except (ValueError,TypeError) as exc:
                    self._a22_last_raw=image
                    self._a22_loaded_bank=None
                    self.macro_status.set("Readback not imported — form and macro preserved")
                    messagebox.showwarning("Device readback not imported",
                        str(exc)+"\n\nThe current Form View and Macro Viewer were left unchanged. "
                        "Switch to Freeform for scripts that cannot fit the form.",parent=self.root)
                    return
            self._macro_sync_lock=True
            try:
                self.macro_text.delete("1.0","end")
                self.macro_text.insert("1.0",content)
            finally:self._macro_sync_lock=False
            self._set_active_script(content)
            self._last_valid_scripts[self.focused_key.get()]=self._ensure_exit(content)
            self._macro_reverse()
            self._a22_last_raw=image
            self._a22_loaded_bank=bank
            self.macro_status.set(f"Load successful — Script {bank}, {used} instruction bytes")
            messagebox.showinfo("OpenSayo","Load successful")
        except Exception as exc:messagebox.showerror("Device load failed",str(exc))

    def _a22_device_save(self):
        try:bank=self._focused_bank()
        except ValueError as exc:return messagebox.showwarning("Key not assigned",str(exc))
        try:
            from alpha22_device_ops import encode_script
            from hardware_protocol import make_bank_reports,send
            from device_readback import read_bank
            # Freeform is a single live macro: never write the stale raw-key buffer.
            if self.workspace_kind=="freeform":
                from sayo_macro_language import compile_macro
                source=self._freeform_source()
            else:
                source=self._compile_form_key(self.focused_key.get())[0]
            script=encode_script(source)
            if not script:
                raise ValueError("Empty device script blocked. Enter or load a nonempty macro before saving; no hardware write attempted.")
            if len(script)>SAFE_CUTOFF:raise ValueError(f"{len(script)} bytes exceeds the {SAFE_CUTOFF}-byte write cap")
            if not messagebox.askyesno("SAVE TO DEVICE — CONFIRM",f"Overwrite hardware Script {bank} with {len(script)} instruction bytes?\n\nBack up this bank first. A failed write may erase the stored macro.\nContinue?"):
                return
            from hardware_protocol import ROOT as PROTOCOL_ROOT
            template=PROTOCOL_ROOT/'captures'/('script7_40_baseline.pcapng' if bank<=7 else 'script8_40_baseline.pcapng')
            assignment_template=PROTOCOL_ROOT/'captures'/'key_swap_reference.pcapng'
            if not template.is_file() or not assignment_template.is_file():
                raise FileNotFoundError("Required Sayo protocol templates are missing from this application folder. No write attempted. Restore the approved OpenSayo package before attempting device writes; do not add arbitrary USB recordings.")
            reports=make_bank_reports(bank,script)
            send(reports)
            # Reopen device after write, verify the returned bytes.
            image=read_bank(bank)
            if image[:len(script)]!=script or any(image[len(script):]):
                raise IOError("Write sent, but readback differs. Save NOT confirmed; inspect the device before retrying.")
            messagebox.showinfo("OpenSayo","Save successful")
        except Exception as exc:messagebox.showerror("Save not confirmed",str(exc))

    def _a22_assign(self):
        k1,k2=int(self.physical_key1.get()),int(self.physical_key2.get())
        if not messagebox.askyesno("Apply physical key mapping",f"Assign physical Key 1 → Script {k1}\nKey 2 → Script {k2}?\n\nNo script contents will be edited."):
            return
        try:
            from hardware_protocol import assignment_packets,send
            seq,commit=assignment_packets(k1,k2)
            send(seq+[commit])
            self._assignment_verified=False
            self._update_assignment_warning()
            messagebox.showinfo("Assignments sent","Key assignments sent. Reconnect and verify persistence; readback verification is not yet implemented for assignments.")
        except Exception as exc:messagebox.showerror("Assignment failed",str(exc))

    def _a22_dual_key(self):
        from dual_key_ui import DualKeyWindow
        DualKeyWindow(self.root,self)

    def _focused_bank(self):
        if self.workspace_kind=="freeform":
            if self.freeform_destination==1:return int(self.device_bank.get())
            value=self.key2_bank.get()
            if not value.isdigit():raise ValueError("Choose a Key 2 device bank first.")
            return int(value)
        if self.focused_key.get()==1:return int(self.device_bank.get())
        value=self.key2_bank.get()
        if not value.isdigit():raise ValueError("Key 2 is Off / Not loaded. Select a script bank first.")
        return int(value)

    @staticmethod
    def _ensure_exit(source):
        lines=[line.rstrip() for line in source.splitlines()]
        while lines and not lines[-1].strip(): lines.pop()
        while lines and lines[-1].strip()=="EXIT": lines.pop()
        # Preserve any embedded EXIT so validation can flag it; never silently
        # discard a user command while normalizing the trailing terminator.
        return "\n".join(lines)+( "\n" if lines else "")

    def _set_active_script(self,source,update_freeform=True):
        source=self._ensure_exit(source)
        self._editor_swap=True
        try:
            self.macro_text.delete("1.0","end")
            self.macro_text.insert("1.0",source)
            self.macro_text.edit_modified(False)
            if update_freeform:self._sync_freeform(source,force=True)
        finally:self._editor_swap=False
        self._key_scripts[self.focused_key.get()]=source
        self._render_key_previews()

    def _sync_freeform(self,source=None,force=False):
        if not hasattr(self,"freeform_text") or self.workspace_kind=="freeform":return
        if source is None:source=self.macro_text.get("1.0","end-1c")
        if not force and self.root.focus_get()==self.freeform_text:return
        self._freeform_sync=True
        try:
            if self.freeform_text.get("1.0","end-1c")!=source:
                self.freeform_text.delete("1.0","end")
                self.freeform_text.insert("1.0",source)
            self.freeform_text.edit_modified(False)
        finally:self._freeform_sync=False

    def _render_key_previews(self):
        if not hasattr(self,"macro_other"):return
        active=self.focused_key.get()
        other=3-active
        for widget,content in ((self.macro_other,self._key_scripts.get(other,"EXIT")),
                               (self.freeform_other,getattr(self,"_freeform_preview_script","EXIT\n"))):
            widget.configure(state="normal")
            widget.delete("1.0","end")
            widget.insert("1.0",content)
            widget.configure(state="disabled")
        self.macro_key_title.configure(text=f"KEY {active} — ACTIVE / READ ONLY")
        self.macro_text.grid(row=1 if active==1 else 3,column=0,sticky="nsew")
        self.macro_other.grid(row=3 if active==1 else 1,column=0,sticky="nsew")
        self.macro_key1_heading.configure(text="KEY 1 — ACTIVE / READ ONLY" if active==1 else "KEY 1 — INACTIVE / READ ONLY")
        self.macro_key2_heading.configure(text="KEY 2 — ACTIVE / READ ONLY" if active==2 else "KEY 2 — INACTIVE / READ ONLY")
        self.freeform_key_title.configure(text="FREEFORM — EDITABLE")

    def _update_key_focus(self):
        target=self.focused_key.get()
        if self.workspace_kind=="freeform" and target!=1:
            self.focused_key.set(1)
            messagebox.showinfo("Freeform Macro","Freeform projects contain one independent script.")
            return
        if target==2 and not self.key2_bank.get().isdigit():
            self.focused_key.set(self._previous_key)
            messagebox.showinfo("Key 2 disabled","Key 2 is temporarily inactive. Its saved contents are preserved; select a bank to reactivate editing.")
            return
        previous=self._previous_key
        if previous!=target:
            self._key_scripts[previous]=self._ensure_exit(self.macro_text.get("1.0","end-1c"))
            self._previous_key=target
            self._set_active_script(self._key_scripts.get(target,"EXIT"))
            self._macro_reverse(auto_apply=False)
        self._render_key_previews()
        self._update_key_switch()
        self._save_key_preferences()
        self._update_form_fade()
        if getattr(self,"form_preview_window",None) is not None and self.form_preview_window.winfo_exists():self.show_form_preview()
        self._refresh()

    def _draw_boss_bar(self):
        """Two compact independent meters; only Freeform shows one script."""
        if not hasattr(self,"boss_bars"):return
        n1,n2=getattr(self,"_boss_values",(0,0))
        freeform=self.workspace_kind=="freeform"
        if hasattr(self,"_capacity_titles"):
            self._capacity_titles[1].configure(text="Key" if freeform else "Key 1")
            self._capacity_titles[2].grid_remove() if freeform else self._capacity_titles[2].grid()
            if hasattr(self,"_capacity_value_widgets"):
                self._capacity_value_widgets[2].grid_remove() if freeform else self._capacity_value_widgets[2].grid()
        if freeform:
            n1=getattr(self,"_freeform_preview_size",0)
            if hasattr(self,"_meter_labels"):
                self._meter_labels[1].set(f"{n1}/{SAFE_CUTOFF} bytes")
            if hasattr(self,"boss_label_vars"):
                self.boss_label_vars[1].set("Key")
        for key,canvas in self.boss_bars.items():
            if freeform and key==2:
                canvas.grid_remove()
                if hasattr(self,"_meter_labels"):self._meter_labels[key].set("")
                continue
            canvas.grid()
            canvas.delete("all")
            width=max(canvas.winfo_width(),125)
            height=max(canvas.winfo_height(),13)
            used=n1 if key==1 else n2
            overflow=used>SAFE_CUTOFF
            fraction=min(1,used/SAFE_CUTOFF)
            color=("#dc3535" if self._key2_flash_on else "#801919") if overflow else ( "#edb92e" if fraction>=.9 else "#edb92e" if fraction>=.7 else "#25a64e")
            if key==2 and not self.key2_bank.get().isdigit():color="#929292"
            canvas.create_rectangle(0,0,width,height,fill="#777777" if key==2 and not self.key2_bank.get().isdigit() else "#272a30",outline="")
            if used:canvas.create_rectangle(0,0,width*fraction,height,fill=color,outline="")
        if self._key2_flash_job is not None:
            self.root.after_cancel(self._key2_flash_job)
            self._key2_flash_job=None
        if n1>SAFE_CUTOFF or (not freeform and n2>SAFE_CUTOFF):
            self._key2_flash_job=self.root.after(650,self._flash_key2_capacity)

    def _apply_viewer_timing(self):
        """Commit timing settings and rebuild Form Mode previews for both key ranges."""
        try:
            values=[int(v.get().strip()) for v in (self.macro_key_ms,self.macro_nav_ms,self.macro_repeat_ms,self.dropdown_open_ms)]
            if any(v<0 or v>60000 for v in values):
                raise ValueError("Timing must be between 0 and 60000 milliseconds")
            # The form compiler reads these shared settings. The selected key is
            # refreshed immediately; both keys are regenerated for consistency.
            for variable,value in zip((self.text_delay,self.action_delay,self.repeat_gap),values[:3]):
                variable.set(str(value))
            self._sync_form_to_editor()
            self._refresh()
            self.save_session()
            self.macro_status.set(f"Applied timing: hold {values[0]}ms, navigation {values[1]}ms, repeat {values[2]}ms, dropdown +{values[3]}ms")
            return True
        except (ValueError,TypeError) as exc:
            messagebox.showerror("Timing settings",str(exc))
            return False

    def _compile_form_key(self,key):
        """Compile only the fields currently assigned to a given key."""
        from alpha22_device_ops import encode_script
        project=self.current_project()
        start=0 if key==1 else project["endpoint"]+1
        end=project["endpoint"] if key==1 else project["key2_endpoint"]
        # A device read contains exact, observed SLEEP durations. Preserve it
        # until the user changes a field/timing; ordinary redraws must not
        # silently rewrite the macro or produce a misleading byte meter.
        imported=getattr(self,"_form_raw_readbacks",{}).get(str(key))
        if imported:
            if imported.get("signature")==self._form_readback_signature(project,key):
                source=imported["source"]
                validate_script(source)
                return source,len(encode_script(source))
            self._form_raw_readbacks.pop(str(key),None)
        if start>end:return "EXIT",len(encode_script("EXIT"))
        parts=["{TAB}"*self._key2_handoff_tabs(project)] if key==2 else []
        for i in range(start,end+1):
            field=project["fields"][i]
            mode=field.get("format_type","Text")
            option=field.get("format_option","")
            if not field_is_enabled(field):
                pass
            elif mode=="Date" and option=="Today's Date":
                parts.extend(("{DOWN}","{ENTER}"))
            elif mode=="Date" and option=="Blank":
                pass
            elif mode=="Date" and option=="MM/DD/YY":
                if field["value"]:
                    from datetime import datetime
                    try:parts.append(normalize_date(field["value"]))
                    except ValueError:raise ValueError(f"Invalid date for {field['name']}: {field['value']}")
            elif mode=="Drop Down":
                if field["value"] and field["value"] not in project.get("dropdowns",{}).get(option,[]):
                    raise ValueError(f"Invalid dropdown selection for {field['name']}")
                if field.get("navigate"):
                    if not str(field.get("navigate_keys","")).strip():
                        raise ValueError(f"{field['name']}: Navigate is ON but Navigate Keys is empty. Record keys or turn Navigate OFF.")
                    sequence=navigation_tokens(field.get("navigate_keys",""))
                    parts.extend(sequence)
                    # Exactly one opening pause, immediately after the first Down.
                    for j in range(len(parts)-len(sequence),len(parts)):
                        if parts[j]=="{DOWN}":
                            parts.insert(j+1,f"{{WAIT:{int(project.get('dropdown_open_ms',75))}}}")
                            break
                else:parts.append(field["value"])
            elif mode=="Skip":
                pass
            elif mode=="Text":
                parts.append(field["value"])
            if i<end:parts.append("{TAB}")
        script=compile_sayo_text("".join(parts),int(self.macro_key_ms.get()),int(self.macro_nav_ms.get()),int(self.macro_repeat_ms.get()),caps_mode=bool(project.get("use_caps_lock",False)))
        return script,len(encode_script(script))

    def _flash_key2_capacity(self):
        self._key2_flash_job=None
        self._key2_flash_on=not self._key2_flash_on
        self._draw_boss_bar()

    def _insert_freeform_wait(self):
        """Insert an explicit wait into the readable Freeform editor, not hardware."""
        try:
            ms=int(self.insert_wait_ms.get().strip())
            if not 0<=ms<=60000:raise ValueError()
        except (ValueError,AttributeError):
            messagebox.showerror("Wait duration","Enter a whole number from 0 to 60000 milliseconds.")
            return
        self.freeform_text.insert("insert",f"{{WAIT:{ms}}}")
        self.freeform_text.focus_set()
        self._freeform_live_preview()

    def _apply_freeform_timing(self):
        """Apply shared timing to the currently readable Freeform script preview."""
        if not self._apply_viewer_timing():return
        if self.workspace_kind=="freeform":
            self._freeform_live_preview()
        self.freeform_timing_status.set(
            "Applied locally (hold/navigation/repeat/dropdown); device not programmed.")

    def _insert_freeform_key(self,key=None):
        key=key or self._insert_key_choice.get()
        names={"ArrowDown":"DOWN","ArrowUp":"UP","ArrowLeft":"LEFT","ArrowRight":"RIGHT"}
        token="{"+names.get(key,key).upper()+"}"
        self.freeform_text.insert("insert",token)
        self.freeform_text.focus_set()

    def _freeform_from_macro(self):
        # Standalone Freeform owns its readable text. Raw scripts are only decoded
        # when a different key/script is explicitly loaded.
        if self.workspace_kind!="freeform":return

    def _freeform_modified(self,event=None):
        if not self.freeform_text.edit_modified():return
        self.freeform_text.edit_modified(False)
        self._freeform_imported_raw=None
        if self.workspace_kind=="freeform":
            if getattr(self,"_freeform_live_job",None):self.root.after_cancel(self._freeform_live_job)
            self._freeform_live_job=self.root.after(120,self._freeform_live_preview)

    def _select_key_button(self,wanted):
        current=self.freeform_destination if self.workspace_kind=="freeform" else self.focused_key.get()
        if wanted==current:return
        if self.workspace_kind=="freeform":
            self.freeform_destination=wanted
            self._update_key_switch()
            self._freeform_live_preview()
            self._save_key_preferences()
        else:
            self.focused_key.set(wanted)
            self._update_key_focus()

    def _update_key_switch(self):
        if not hasattr(self,"key1_switch_label"):return
        key=self.freeform_destination if self.workspace_kind=="freeform" else self.focused_key.get()
        for number,label in ((1,self.key1_switch_label),(2,self.key2_switch_label)):
            selected=number==key
            label.configure(font=("Segoe UI",10,"bold" if selected else "normal"),
                            bg="#d9ecff" if selected else self.root.cget("bg"),
                            fg="#124d8b" if selected else "#777777",
                            relief="raised" if selected else "flat",bd=2 if selected else 0,
                            highlightthickness=1 if selected else 0,
                            highlightbackground="#3685d6")

    def _toggle_key_switch(self):
        if self.workspace_kind=="freeform":
            # Freeform is a single script: destination choice only.
            self.freeform_destination=2 if getattr(self,"freeform_destination",1)==1 else 1
            self._update_key_switch()
            self._freeform_live_preview()
            return
        self.focused_key.set(3-self.focused_key.get())
        self._update_key_focus()

    def _open_recorder(self):
        """Record only keys typed into this explicit local dialog, not system-wide input.

        Repeated Recorder clicks bring forward the single active recorder.
        """
        if self._raise_dialog("recorder_window"):return
        win=tk.Toplevel(self.root)
        self.recorder_window=win
        win.title("OpenSayo — Local Macro Recorder")
        win.geometry("540x340")
        ttk.Label(win,text="Click Start, then type in the capture box. Only keys typed here are recorded.",wraplength=510).pack(padx=12,pady=8)
        light=tk.Label(win,text="●  NOT RECORDING",fg="#777777",font=("Segoe UI",11,"bold"))
        light.pack()
        capture=tk.Text(win,height=7,wrap="word")
        capture.pack(fill="both",expand=True,padx=12,pady=8)
        events=[]
        recording=[False]
        held=set()
        used=set()
        modifier={"Shift_L":"L_Shift","Shift_R":"R_Shift","Control_L":"L_Ctrl","Control_R":"R_Ctrl","Alt_L":"L_Alt","Alt_R":"R_Alt"}
        def echo(recorded):
            """Display locally captured actions immediately; not a global logger."""
            capture.insert("end",recorded+"\n")
            capture.see("end")
        def keypress(event):
            if not recording[0]:return
            mod=modifier.get(event.keysym)
            if mod:
                held.add(mod)
                return "break"
            special={"Tab":"TAB","Return":"ENTER","Down":"DOWN","Up":"UP","Left":"LEFT","Right":"RIGHT","BackSpace":"BACKSPACE","Delete":"DELETE","End":"END","Escape":"ESCAPE","Home":"HOME","Prior":"PAGEUP","Next":"PAGEDOWN"}
            key=special.get(event.keysym)
            if key is None:
                if len(event.keysym)==1 and event.keysym.isascii() and event.keysym.isalnum():key=event.keysym.upper()
                elif event.char and event.char.isprintable():key=event.char
                else:return "break"
            active=[m for m in ("L_Ctrl","R_Ctrl","L_Alt","R_Alt","L_Shift","R_Shift") if m in held]
            if active:
                used.update(active)
                if len(key)==1 and key.isalpha() and any(m.endswith("Shift") for m in active):key=key.upper()
                events.append("{"+"+".join(active+[key])+"}")
            elif len(key)==1:events.append(event.char if event.char and event.char.isprintable() else key.lower())
            else:events.append("{"+key+"}")
            echo(events[-1])
            light.configure(text="●  RECORDING",fg="#18a558")
            return "break"
        def keyrelease(event):
            mod=modifier.get(event.keysym)
            if mod and mod in held:
                held.remove(mod)
                if mod not in used and recording[0]:
                    events.append("{"+mod+"}")
                    echo(events[-1])
                used.discard(mod)
            return "break" if mod else None
        capture.bind("<KeyPress>",keypress)
        capture.bind("<KeyRelease>",keyrelease)
        def start():
            events.clear();held.clear();used.clear();capture.delete("1.0","end")
            recording[0]=True;light.configure(text="●  RECORDING",fg="#18a558")
            capture.focus_set()
        def stop():
            recording[0]=False;light.configure(text="●  STOPPED",fg="#777777")
        def apply_recording():
            stop()
            readable="".join(events)
            if not readable:return
            try:
                compiled=compile_sayo_text(readable,int(self.macro_key_ms.get()),int(self.macro_nav_ms.get()),int(self.macro_repeat_ms.get()))
                from alpha22_device_ops import encode_script
                limit=EIGHT_SCRIPT_CAP if self.layout_mode.get()=="8" else SAFE_CUTOFF
                if len(encode_script(compiled))+(1 if self.layout_mode.get()=="8" else 0)>limit:
                    raise ValueError(f"Recording exceeds {limit}-byte device limit")
                target=self.freeform_text if self.workspace_kind=="freeform" else self.macro_readable
                target.delete("1.0","end");target.insert("1.0",readable)
                if self.workspace_kind=="freeform":self._freeform_live_preview()
                else:self._macro_generate(silent=True)
                win.destroy()
            except Exception as exc:messagebox.showerror("Recorder",str(exc),parent=win)
        buttons=ttk.Frame(win);buttons.pack(pady=8)
        ttk.Button(buttons,text="Start",command=start).pack(side="left",padx=4)
        ttk.Button(buttons,text="Stop",command=stop).pack(side="left",padx=4)
        ttk.Button(buttons,text="Apply Script",command=apply_recording).pack(side="left",padx=4)
        ttk.Button(buttons,text="Cancel",command=win.destroy).pack(side="left",padx=4)

    def _macro_on_blur(self,event=None):
        if self.workspace_kind == "form_project":return
        if self._editor_swap or self._macro_sync_lock:return
        raw=self.macro_text.get("1.0","end-1c")
        normalized=self._ensure_exit(raw)
        if raw!=normalized:
            self._editor_swap=True
            try:
                self.macro_text.delete("1.0","end")
                self.macro_text.insert("1.0",normalized)
                self.macro_text.edit_modified(False)
            finally:self._editor_swap=False
        if self._macro_script_job:
            self.root.after_cancel(self._macro_script_job)
            self._macro_script_job=None
        self._macro_reverse()

    def _freeform_on_blur(self,event=None):
        # EXIT is a raw-script terminator, never editable readable text.
        pass

    def _freeform_decode(self):
        try:
            readable,_=script_to_readable(self._ensure_exit(self.macro_text.get("1.0","end-1c")))
            if self.freeform_text.get("1.0","end-1c").strip() and not messagebox.askyesno("Replace readable macro?","Decode the current raw script and replace your readable editor?"):
                return
            self.freeform_text.delete("1.0","end")
            self.freeform_text.insert("1.0",readable)
        except Exception as exc:messagebox.showerror("Decode macro",str(exc))

    def _freeform_live_preview(self):
        self._freeform_live_job=None
        if self.workspace_kind!="freeform":return
        try:
            from alpha22_device_ops import encode_script
            source=self._freeform_source()
            validate_script(source)
            size=len(encode_script(source))
            self._freeform_preview_script=source
            self._freeform_preview_size=size
            self._update_eight_meter()
            self.freeform_key_title.configure(text=(f"SCRIPT {self.eight_script_slot.get()} — {size}/{EIGHT_SCRIPT_CAP} bytes" + (" — OVER CAPACITY" if size>EIGHT_SCRIPT_CAP else "") if self.layout_mode.get()=="8" else f"KEY — {size}/{SAFE_CUTOFF} bytes" + (" — OVER CAPACITY" if size>SAFE_CUTOFF else "")))
        except Exception as exc:
            self._freeform_preview_script=f"Preview error: {exc}"
        self.freeform_other.configure(state="normal")
        self.freeform_other.delete("1.0","end")
        self.freeform_other.insert("1.0",self._freeform_preview_script)
        self.freeform_other.configure(state="disabled")

    def _freeform_paste_sayo(self):
        """Validate clipboard as raw Sayo text before replacing any current macro.

        Non-roundtrippable raw scripts remain authoritative until readable text changes.
        """
        try:
            from alpha22_device_ops import encode_script
            raw=self.root.clipboard_get().replace("\r\n","\n").strip()+"\n"
            validate_script(raw)
            size=len(encode_script(raw))
            if self.layout_mode.get()=="8" and size>EIGHT_SCRIPT_CAP:raise ValueError(f"{size} bytes exceeds {EIGHT_SCRIPT_CAP}-byte eight-key cap")
            if self.layout_mode.get()!="8" and size>SAFE_CUTOFF:raise ValueError(f"{size} bytes exceeds {SAFE_CUTOFF}-byte cap")
            try:
                readable,_=script_to_readable(raw)
                roundtrip=compile_sayo_text(readable,int(self.macro_key_ms.get()),int(self.macro_nav_ms.get()),int(self.macro_repeat_ms.get()))==raw
            except Exception:
                readable=""
                roundtrip=False
            if not roundtrip:
                # Never pretend a timing-sensitive raw script can be represented losslessly.
                messagebox.showwarning("Raw script preserved", "Valid Sayo script, but its exact timing/actions cannot be represented by the readable editor. The raw script will be kept intact and used for Apply/Copy/Save until you edit the readable text. No hardware write occurred.")
            self.freeform_text.delete("1.0","end")
            self.freeform_text.insert("1.0",readable)
            self.freeform_text.edit_modified(False)
            self._freeform_imported_raw=raw
            self._freeform_live_preview()
        except Exception as exc:
            messagebox.showerror("Paste Sayo Macro rejected",str(exc)+"\n\nExisting macro unchanged.")

    def _freeform_source(self):
        if getattr(self,"_freeform_imported_raw",None) is not None:
            return self._freeform_imported_raw
        return compile_sayo_text(self.freeform_text.get("1.0","end-1c"),int(self.macro_key_ms.get()),int(self.macro_nav_ms.get()),int(self.macro_repeat_ms.get()))

    def _freeform_copy_sayo(self):
        """Copy freshly generated Sayo commands; never copy stale or invalid preview."""
        try:
            source=self._freeform_source()
            validate_script(source)
        except Exception as exc:
            messagebox.showerror("Cannot copy Sayo macro",str(exc))
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(source)
        self.root.update()
        self.macro_status.set(f"Copied Sayo macro ({len(source)} characters).")

    def _freeform_generate(self):
        """Apply the readable macro to the selected software key, never USB."""
        try:
            from alpha22_device_ops import encode_script
            source=self._freeform_source()
            validate_script(source)
            size=len(encode_script(source))
            if self.layout_mode.get()=="8":
                slot=int(self.eight_script_slot.get())
                if not 0<=slot<=63:raise ValueError("Select a valid 8-key script slot 0–63")
                if size>EIGHT_SCRIPT_CAP:raise ValueError(f"Macro needs {size} bytes; maximum is {EIGHT_SCRIPT_CAP}")
                self.eight_slot_drafts[slot]=source
                self._freeform_preview_script=source
                self._freeform_preview_size=size
                self.session_status.set(f"Saved Freeform draft for 8-key Script {slot} ({size} bytes) in this session. DEVICE NOT PROGRAMMED.")
                self._freeform_live_preview()
                return
            if size>SAFE_CUTOFF:
                messagebox.showwarning("Freeform capacity",f"Generated script needs {size} bytes; maximum {SAFE_CUTOFF}. No changes applied.")
                return
            self._freeform_preview_script=source
            self._key_scripts[self.freeform_destination]=source
            self.focused_key.set(self.freeform_destination)
            self._editor_swap=True
            try:
                self.macro_text.delete("1.0","end")
                self.macro_text.insert("1.0",source)
                self.macro_text.edit_modified(False)
            finally:self._editor_swap=False
            self._render_key_previews()
            self._refresh()
            self.session_status.set(f"Applied Freeform script to Key {self.freeform_destination} ({size}/{SAFE_CUTOFF} bytes); device not programmed.")
        except Exception as exc:messagebox.showerror("Apply script",str(exc))


def main():
    root=tk.Tk()
    App(root)
    root.mainloop()

if __name__=="__main__":main()
