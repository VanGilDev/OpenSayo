"""Read-only 0x16 response inspection for O2L V2. Never issues writes or Save.
The protocol is documented for a related model; raw evidence is retained even
when checksum, response size, or status do not match expectations.
"""
import hashlib

def decode_mapping_response(raw, key):
    raw=bytes(raw)
    result={'key':key,'raw':raw.hex(' '),'received_bytes':len(raw),
            'sha256':hashlib.sha256(raw).hexdigest(),'layers':[],
            'status':None,'length':None,'checksum_ok':False,'note':''}
    if not raw:
        result['note']='No response bytes (timeout or empty read)';return result
    result['report_id']=raw[0]
    if len(raw)>1:result['status']=raw[1]
    if len(raw)>2:result['length']=raw[2]
    if len(raw)!=64:
        result['note']=f'Unexpected response size: {len(raw)} (expected 64); no decode attempted';return result
    if raw[0]!=2:
        result['note']='Unexpected report ID; raw response retained';return result
    n=raw[2]
    result['checksum_offset']=3+n
    if n>60:
        result['note']='Declared length exceeds packet capacity; raw response retained';return result
    result['checksum_received']=raw[3+n]
    result['checksum_calculated']=sum(raw[:3+n])&255
    result['checksum_ok']=result['checksum_received']==result['checksum_calculated']
    result['sum_payload_only']=sum(raw[3:3+n])&255
    result['sum_without_report_id']=sum(raw[1:3+n])&255
    result['sum_complement']=(-result['checksum_calculated'])&255
    if result['status']!=0:
        result['note']='Nonzero device status; raw response retained, not treated as assignment';return result
    if not result['checksum_ok']:
        result['note']='Checksum mismatch; assignment interpretation withheld; raw response retained';return result
    data=raw[3:3+n]
    if n>=22 and (n-16)%6==0:
        for layer in range((n-16)//6):
            offset=16+layer*6
            record=data[offset:offset+6]
            result['layers'].append({'layer':layer,'mode':record[0],'flags':record[1], 'values':list(record[2:6])})
    else:
        result['note']='Checksum valid, but payload shape unrecognized; raw response retained'
    return result

def read_two_keys_twice(dev, make_packet):
    """At most four 0x16 read requests. Stop on malformed/empty responses."""
    output=[]
    for pass_number in (1,2):
        for key in (0,1):
            req=make_packet(0x16,bytes((0,key)))
            count=dev.write(req)
            if count!=64:raise IOError(f'Short request ({count}/64) at pass {pass_number}, key {key}')
            raw=bytes(dev.read(64,timeout_ms=1500))
            result={'pass':pass_number,**decode_mapping_response(raw,key)}
            output.append(result)
            if result['received_bytes']!=64 or result.get('report_id')!=2:
                result['stop_reason']='Unexpected response framing; no further requests sent'
                return output
    return output
