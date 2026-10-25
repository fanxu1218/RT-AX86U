#!/usr/bin/env python3
"""Keep source and build contracts needed for the software-center integration."""
import json
import tarfile
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parent.parent
dest = root/'sources/gpl24436'
dest.mkdir(exist_ok=True)
inventory = []
selected = 0
with zipfile.ZipFile(root/'sources/GPL_RT_AX86U_300438824436.zip') as z:
    with z.open(z.namelist()[0]) as compressed:
        with tarfile.open(fileobj=compressed, mode='r|gz') as tar:
            for member in tar:
                name = member.name
                inventory.append({'path': name, 'bytes': member.size, 'type': member.type.decode('ascii', 'replace')})
                if name.startswith('/') or '..' in Path(name).parts:
                    raise ValueError(name)
                relevant = any('/router/'+component+'/' in name for component in
                               ['httpd','rc','shared','skipdb','skipdbv3','include','libbcmcrypto'])
                relevant |= ('/release/' in name and '/include/' in name and '/linux/' not in name
                             and '/kernel/' not in name and '/openssl/' not in name and '/src/router/' not in name)
                relevant |= (member.size < 2_000_000 and any(x in Path(name).name for x in
                             ['.config', 'autoconf.h', 'target.mak', 'platform.mak', 'version.conf', 'License']))
                relevant |= name.endswith('/router/Makefile') or name.endswith('/httpd')
                if relevant:
                    tar.extract(member, dest, filter='tar')
                    selected += 1
                if len(inventory) % 20000 == 0:
                    print('scanned',len(inventory),'selected',selected,flush=True)
(root/'build/gpl_inventory.json').write_text(json.dumps(inventory, indent=2))
print('done',len(inventory),'selected',selected,flush=True)
