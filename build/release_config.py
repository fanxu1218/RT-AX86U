"""One version identity; old images/tags are never implicit build targets."""
import json,re
from device_config import ROOT, DEVICE, require

def resolve_config(raw, device):
    require(raw['schema']==1 and bool(re.fullmatch(r'r[1-9][0-9]*(?:-r[1-9][0-9]*)?',raw['revision'])), 'Invalid release revision')
    require(raw['device']==device['id'], 'Release/device mismatch')
    require(raw['variant']=='localmod2', 'Unsupported release variant')
    require(raw['tag']==f"localmod2-{raw['revision']}-experimental", 'Invalid release tag')
    require(raw['image']==f"output/{device['base']['image_prefix']}_localmod2_{raw['revision'].replace('-','_')}_EXPERIMENTAL.w", 'Release image/device mismatch')
    require(raw['status']=='EXPERIMENTAL_NOT_DEVICE_TESTED', 'Device acceptance must remain explicit')
    for key in ['base', 'vendor_image']:
        require(key not in raw, 'Base identity belongs in the device profile: '+key)
    result=dict(raw)
    result.update(base=device['base']['version'], vendor_image=device['base']['vendor_image'])
    return result

CONFIG=resolve_config(json.loads((ROOT/'build/release_config.json').read_text()), DEVICE)
