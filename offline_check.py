"""Strictly offline syntax / bytecode / packaging check (never imports hid)."""
from __future__ import annotations
from pathlib import Path
import sys
import json
root=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(root/'py'))
from eight_key_protocol_v111 import offline_selftest, script_packets, OBSERVED_WRITE_EXTENT
from alpha22_device_ops import encode_script
from sayo_macro_language import validate_script
from opensayo_v019_alpha22 import approved_default_project, normalize_project, default_layout, generic_field_display_label, field_is_enabled, STARTER_LABELS, INDEPENDENT_PROJECT_NOTICE, compile_v018, migrate_legacy_calendar_fields, VERSION
assert VERSION=='1.15'
# Approved friendly About notice: source-level check only; visual fit on Windows
# remains in the release verification checklist.
assert "myself and my coworkers" in INDEPENDENT_PROJECT_NOTICE
assert "systems that might slightly resemble this" in INDEPENDENT_PROJECT_NOTICE
assert "I hope this little tool makes someone's day a bit easier!" in INDEPENDENT_PROJECT_NOTICE
assert approved_default_project()['format']=='OpenSayo-Form'
# A generic past format ID exercises structural backward-compatibility without
# bundling any private identifying values or form definitions.
previous=approved_default_project()
previous['format']='OpenSayo-PreviousForm'
previous['dynamic_form']=False
previous['fields']=[dict(name=f'Example {i+1}',value='',format_type='Text') for i in range(69)]
previous['fields'][68].update(name='Example Date',value='Down, Enter')
previous['endpoint']=68
previous['key2_endpoint']=68
old_restored=normalize_project(previous)
assert len(old_restored['fields'])==69
assert old_restored['endpoint']==68 and old_restored['key2_endpoint']==68
assert old_restored['fields'][68]['format_type']=='Date'
assert old_restored['fields'][68]['format_option']=="Today's Date"
configured=approved_default_project()
configured['fields'][0].update(name='Configured Action',special_action='today_calendar',format_type='Text')
assert normalize_project(configured)['fields'][0]['format_type']=='Date'
assert not any(f['value'] for f in approved_default_project()['fields'])
# A generic date action is compiled based on format settings, never name.
calendar_fields=[dict(approved_default_project()['fields'][0],name='Date',value='',format_type='Date',format_option="Today's Date")]
assert compile_v018(calendar_fields,0,enforce_limit=False)
assert offline_selftest()
for i in range(8):
    source=f'PRESS_GK hidkey_{chr(65+i)}\nSLEEP 15\nRELEASE_GK hidkey_{chr(65+i)}\nEXIT\n'
    validate_script(source)
    code=encode_script(source)+b'\xff'
    blocks,end,save=script_packets(i,code)
    assert len(blocks)==39 and sum(x[6]==0x1a for x in blocks)==39
    assert sum(len(x) for x in blocks)==39*64
    assert end[6:8]==bytes((0x1a,i)) and save[6:8]==b'\r\0'
for filename in ['script7_40_baseline.pcapng','script8_40_baseline.pcapng','key_swap_reference.pcapng']:
    assert (root/'py'/'captures'/filename).stat().st_size>100
assert len(approved_default_project()['fields'])==25
assert [f['name'] for f in approved_default_project()['fields']]==STARTER_LABELS+[str(i) for i in range(11,26)]
assert all(f.get('value')=='' and f.get('format_type')=='Text' for f in approved_default_project()['fields'])
assert approved_default_project()['dropdowns']=={}
assert approved_default_project()['layout']['columns']==3
assert generic_field_display_label(0,approved_default_project()['fields'][0])=='01. First Name'
synthetic=approved_default_project()
# Form imports can restore substantially more fields than shipped defaults.
source_69=approved_default_project()
source_69['fields']=[dict(source_69['fields'][0],name=str(i+1),field_id=f'private_{i:03d}',step=i+1) for i in range(69)]
source_69['layout']=default_layout(69)
assert len(normalize_project(source_69)['fields'])==69
source_300=approved_default_project()
source_300['fields']=[dict(source_300['fields'][0],name=str(i+1),field_id=f'extended_{i:04d}',step=i+1) for i in range(300)]
source_300['layout']=default_layout(300)
assert len(normalize_project(source_300)['fields'])==300
assert normalize_project(source_300)['layout']['rows']>=100
# 300 is a successful test size, not a hardcoded maximum.
source_500=approved_default_project()
source_500['fields']=[dict(source_500['fields'][0],name=str(i+1),field_id=f'extended_{i:04d}',step=i+1) for i in range(500)]
source_500['layout']=default_layout(500)
assert len(normalize_project(source_500)['fields'])==500
assert normalize_project(source_500)['layout']['rows']>=167

synthetic['fields'][0]['name']='Example Status'
synthetic['fields'][1]['name']='Example Choice'
synthetic['fields'][1]['format_type']='Drop Down'
synthetic['fields'][1]['format_option']='Examples'
synthetic['fields'][2]['format_type']='Date'
synthetic['fields'][2]['format_option']="Today's Date"
synthetic['dropdowns']={'Examples':['Yes','No']}
synthetic['layout']=default_layout(25)
synthetic['layout']['columns']=5
synthetic['layout']['positions']={str(i):[i//9,i%9] for i in range(25)}
restored=normalize_project(synthetic)
assert [f['name'] for f in restored['fields']][:2]==['Example Status','Example Choice']
assert restored['dropdowns']=={'Examples':['Yes','No']}
assert restored['layout']['columns']==5
assert restored['fields'][2]['format_option']=="Today's Date"
# Field enable/disable is a UI/view preference plus action suppression, NOT a
# deletion or reordering of fields. Old definition files default to enabled.
assert all(field_is_enabled(f) for f in approved_default_project()["fields"])
legacy_field=dict(name="Example",value="A",format_type="Text",format_option="")
assert field_is_enabled(legacy_field)
with_flag=dict(legacy_field,enabled=True)
assert compile_v018([legacy_field],0,enforce_limit=False)==compile_v018([with_flag],0,enforce_limit=False)
actions=[dict(name=n,value=v,format_type="Text",enabled=True) for n,v in (("First","A"),("Second","B"),("Third","C"))]
all_three=compile_v018(actions,2,enforce_limit=False)
actions[1]["enabled"]=False
label_only=compile_v018(actions,2,enforce_limit=False)
assert len(label_only)<len(all_three)
assert label_only.count(bytes((0x11,0x2B)))==2 # two Tabs, disabled middle field keeps its place
assert bytes((0x11,0x05)) not in label_only  # no B keystroke
assert bytes((0x11,0x04)) in label_only and bytes((0x11,0x06)) in label_only
cal=dict(name="Date",value="",format_type="Date",format_option="Today's Date",enabled=True)
assert compile_v018([cal],0,enforce_limit=False)
cal["enabled"]=False
assert compile_v018([cal],0,enforce_limit=False)==b""
sample_project=approved_default_project()
sample_project["fields"][1]["enabled"]=False
saved_and_restored=normalize_project(json.loads(json.dumps(sample_project)))
assert saved_and_restored["fields"][1]["enabled"] is False
saved_and_restored["fields"][1]["enabled"]=True
assert normalize_project(saved_and_restored)["fields"][1]["enabled"] is True
# Large forms support mixed active and label-only fields without a field-count cap.
source_500["fields"][499]["enabled"]=False
assert normalize_project(source_500)["fields"][499]["enabled"] is False
print('PASS: Step41 base, 8 slot packet syntax, 2028-byte guard, three sanitized USB protocol templates, 25-field starter template, 69-, 300-, and 500-field restoration, field enable/disable defaults and macro suppression')
print('NO device access or USB writes were performed.')
