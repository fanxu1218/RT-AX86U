"""One version identity; old images/tags are never implicit build targets."""
import json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
CONFIG=json.loads((ROOT/'build/release_config.json').read_text())
assert CONFIG['schema']==1 and re.fullmatch(r'r[1-9][0-9]*(?:-r[1-9][0-9]*)?',CONFIG['revision'])
assert CONFIG['variant']=='localmod2'
assert CONFIG['tag']==f"localmod2-{CONFIG['revision']}-experimental"
assert CONFIG['image']==f"output/RT-AX86U_388_24437_localmod2_{CONFIG['revision'].replace('-','_')}_EXPERIMENTAL.w"
assert CONFIG['status']=='EXPERIMENTAL_NOT_DEVICE_TESTED'
