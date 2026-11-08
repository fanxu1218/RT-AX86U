#!/usr/bin/env python3
"""Stage pinned Fancyss v2 policy and safe handling of known old uninstallers."""
import hashlib,json,re,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def sha(data):return hashlib.sha256(data).hexdigest()
def stage_policy(source,tools,put):
 pin=json.loads((Path(__file__).parent/'vendor/fancyss_uninstall_p1.json').read_text())['packages']
 manifest=json.loads((ROOT/'build/fancyss_inputs.json').read_text())['packages']
 current=next(p for p in manifest if p['phase']=='current');old=next(p for p in pin if p['version']==current['version'])
 for p in manifest:
  assert sha((ROOT/p['adapted_path']).read_bytes())==p['adapted_sha256']
 policy=''.join(p['adapted_sha256']+'  shadowsocks\n' for p in manifest)
 p=tools/'fancyss-packages.sha256';p.write_text(policy);put(p,'usr/libexec/localmod/fancyss-packages.sha256',0o444)
 page=(source/'www/Module_FancyssLocalmod.asp').read_text()
 for before,after in [(old['old_adapted_md5'],current['adapted_md5']),(Path(old['old_adapted_path']).name,Path(current['adapted_path']).name)]:
  assert page.count(before)==1,(before,page.count(before));page=page.replace(before,after)
 p=tools/'Module_FancyssLocalmod.asp';p.write_text(page);put(p,'www/Module_FancyssLocalmod.asp',0o444)
 with tarfile.open(ROOT/current['adapted_path'],'r:gz') as archive:
  entry=archive.getmember('shadowsocks/uninstall.sh');assert entry.isfile()
  data=archive.extractfile(entry).read();assert sha(data)==current['files']['uninstall.sh']['sha256']
 assert b'$0' not in data and b'rm -rf /koolshare/bin/jq' not in data
 for p in manifest:assert p['files']['uninstall.sh']['sha256']==sha(data)
 p=tools/'fancyss-uninstall.sh';p.write_bytes(data);put(p,'usr/libexec/localmod/fancyss-uninstall.sh',0o755)
 hashes=sorted({p[k] for p in pin for k in ['upstream_uninstall_sha256','old_uninstall_sha256']})
 assert all(re.fullmatch('[0-9a-f]{64}',v) for v in hashes)
 guard=(source/'usr/libexec/localmod/installer-guard.sh').read_text()
 before='ks_run_script(){\n /usr/libexec/localmod/plugin-run 300 - 0 start-stop-daemon -S -q -x "$1"\n}'
 after='''ks_run_script(){
 KS_RUN_SCRIPT=$1
 if [ "${KS_OPERATION_KIND:-}" = uninstall ] && [ "${softcenter_installing_todo:-}" = shadowsocks ] && [ -f "$1" ] && [ ! -L "$1" ]; then
  KS_RUN_SHA=$(/usr/sbin/openssl dgst -sha256 "$1") || return 1
  KS_RUN_SHA=${KS_RUN_SHA##* }
  case "$KS_RUN_SHA" in
   @HASHES@) KS_RUN_SCRIPT=/usr/libexec/localmod/fancyss-uninstall.sh;;
  esac
 fi
 /usr/libexec/localmod/plugin-run 300 - 0 start-stop-daemon -S -q -x "$KS_RUN_SCRIPT"
}'''.replace('@HASHES@','|'.join(hashes))
 assert guard.count(before)==1
 p=tools/'installer-guard.sh';p.write_text(guard.replace(before,after));put(p,'usr/libexec/localmod/installer-guard.sh',0o755)
 put(ROOT/'sources/localmod/fancyss-LICENSE.txt','usr/libexec/localmod/fancyss-LICENSE.txt',0o444)
 p=tools/'fancyss-uninstall-NOTICE.txt';p.write_text('Fancyss GPL-3.0 uninstaller adaptation 2: retain shared JQ files and system aliases.\nCorresponding source: https://github.com/hq450/fancyss/tree/9fc37ef7fc452de2740a9f1c03a2aac90a7e0b12\nChanges: build/prepare_fancyss.py and analysis/merlin_vpn_38812/fancyss_policy.py in the matching localmod source snapshot.\n');put(p,'usr/libexec/localmod/fancyss-uninstall-NOTICE.txt',0o444)
 return dict(adaptation=2,allowed_archive_sha256=[p['adapted_sha256'] for p in manifest],current_version=current['version'],current_filename=Path(current['adapted_path']).name,current_md5=current['adapted_md5'],shared_uninstall_sha256=sha(data),recognized_previous_uninstaller_sha256=hashes)
