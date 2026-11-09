#!/usr/bin/env python3
"""Run native Fancyss with a strict check of its upstream system-JQ branch.

Keep the already verified generic/HND harness source unchanged. This adapter
checks the expected native jq symlink/hash/execution, instead of requiring a
second, package-owned jq that the upstream installer intentionally removes.
"""
import builtins,hashlib,json,sys,tarfile,types
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE))
import check_native_plugins as shared

def run_derived(code,namespace):
 assert shared.SUITE=='fancyss'
 folder=ROOT/'build/merlin38813-native-plugins-fancyss';source=(folder/'derived_check.py').read_text()
 def change(old,new):
  nonlocal source
  assert source.count(old)==1,(old,source.count(old));source=source.replace(old,new)
 candidate=json.loads((ROOT/'output/merlin38813_native_candidate_tests.json').read_text());p=ROOT/candidate['rootfs']/'usr/bin/jq'
 assert p.is_file() and not p.is_symlink()
 expected=hashlib.sha256(p.read_bytes()).hexdigest()
 change("'candidate_runtime.go','check_native_plugins.py']]]+","'candidate_runtime.go','check_native_plugins.py','check_native_fancyss.py','vendor/fancyss_uninstall_p1.json']]]+")
 manifest=json.loads((ROOT/'build/fancyss_inputs.json').read_text())['packages']
 package=next(p for p in manifest if p['phase']=='current')
 with tarfile.open(ROOT/package['adapted_path'],'r:gz') as archive:data=archive.extractfile('shadowsocks/uninstall.sh').read()
 marker=b'# localmod: retain shared JQ binaries and system aliases for other plugins.'
 assert data.count(marker)==1
 old=data.replace(marker,b'if [ -x /usr/bin/jq ] && [ -L /koolshare/bin/jq ] && [ "$(readlink /koolshare/bin/jq)" = /usr/bin/jq ];then\n\trm -rf /koolshare/bin/jq >/dev/null 2>&1\nfi')
 pin=json.loads((HERE/'vendor/fancyss_uninstall_p1.json').read_text())['packages']
 assert hashlib.sha256(old).hexdigest()==pin[0]['old_uninstall_sha256']
 (folder/'prior-uninstall-fixture.sh').write_bytes(old)
 block='''if name == "bin/jq" {
                target, err := os.Readlink("/koolshare/bin/jq")
                if err != nil || target != "/usr/bin/jq" || fancySHA(nrRead("/usr/bin/jq")) != "@SHA@" || fancySHA(nrRead("/koolshare/bin/jq")) != "@SHA@" {
                    panic("Fancyss native system-JQ link or immutable bytes changed")
                }
                if strings.TrimSpace(nrCommand("/koolshare/bin/jq", "-nr", "--arg", "owned", "native-merlin-jq", "$owned")) != "native-merlin-jq" {
                    panic("Fancyss native system-JQ could not process JSON")
                }
                continue
            }
            '''.replace('@SHA@',expected)
 change("text=(ROOT/n).read_text()",'''text=(ROOT/n).read_text()
  if n.endswith('test_fancyss.go'):
   marker='// Official curl supports proxy; upstream intentionally links this name.'
   assert text.count(marker)==1
   text=text.replace(marker,%r+marker)
   text=text.replace('_installed_disabled_original_binaries_auth_page_no_803_and_uu','_installed_disabled_pinned_binaries_native_jq_auth_page_no_803_and_uu')
   marker='record("center_restart_keeps_fancyss_configuration_and_uu")'
   assert text.count(marker)==1
   text=text.replace(marker,marker+'\\n nrMust(os.WriteFile("/koolshare/scripts/uninstall_shadowsocks.sh",nrRead("/work/build/merlin38813-native-plugins-fancyss/prior-uninstall-fixture.sh"),0755))\\n record("prior_adaptation_uninstaller_retained_as_upgrade_fixture_before_shared_jq_uninstall")')'''%block)
 (folder/'derived_check.py').write_text(source)
 builtins.exec(compile(source,str(folder/'derived_check.py'),'exec'),namespace)

if __name__=='__main__':
 shared.builtins=types.SimpleNamespace(exec=run_derived)
 shared.main()
