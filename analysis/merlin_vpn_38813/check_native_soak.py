#!/usr/bin/env python3
"""Adapt the established integrated soak to the immutable full-Merlin image.

--probe checks setup and handshake boundaries. --smoke runs a measured five
minute event preflight. Default is the full measured one-hour coexistence run.
No firmware, physical device, or GitHub state is changed by this checker.
"""
import builtins,hashlib,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]

def main():
 source=(ROOT/'analysis/r9r1_coexist/check.py').read_text()
 def change(old,new):
  nonlocal source
  assert source.count(old)==1,(old[:120],source.count(old));source=source.replace(old,new)
 change('seconds=600 if a.smoke or a.probe else 3600','seconds=300 if a.smoke or a.probe else 3600')
 begin=source.index(" v=json.load(open('output/verification.json'))")
 end=source.index(' source=[',begin)
 source=source[:begin]+''' assert not a.bridge_overlay,'This checker uses only the built native candidate'
 candidate=json.loads((ROOT/'output/merlin38813_native_candidate_tests.json').read_text())
 assert candidate['status']=='NATIVE_MERLIN_CANDIDATE_BUILT_READBACK_PASS_NOT_FLASH_READY'
 tree=ROOT/candidate['rootfs'];assert hashlib.sha256(encoded(inventory(tree))).hexdigest()==candidate['stage_inventory_sha256']
 v=dict(image=candidate['image']['image'],sha256=candidate['image']['sha256']);assert sha(ROOT/v['image'])==v['sha256']
 prefix='merlin38813_native_coexist'
 baseline={n:sha(ROOT/n) for n in [*candidate['protected_sha256'],'output/merlin38813_native_candidate_tests.json',v['image']]}
 real=json.loads((ROOT/'build/real_plugin_inputs.json').read_text());fancy=json.loads((ROOT/'build/fancyss_inputs.json').read_text())
 for p in real['packages']:assert sha(ROOT/p['path'])==p['sha256']
 for p in fancy['packages']:assert sha(ROOT/p['adapted_path'])==p['adapted_sha256']
 '''+source[end:].lstrip(' ')
 change("before={p:sha(ROOT/p) for p in source}","source+=['analysis/merlin_vpn_38813/check_native_soak.py','analysis/merlin_vpn_38813/native_preview.go','analysis/merlin_vpn_38813/launcher_exec_fixture.c']\n before={p:sha(ROOT/p) for p in source}")
 source=source.replace("dest=ROOT/'build/coexist-compile'","dest=ROOT/'build/merlin38813-native-soak/compile'").replace('dest.mkdir(exist_ok=True)','dest.mkdir(parents=True,exist_ok=True)')
 change("if not n.endswith('.go'):continue","if n=='analysis/merlin_vpn_38813/native_preview.go' or not n.endswith('.go'):continue")
 marker="  p=dest/Path(n).name;p.write_text(s);"
 transform='''  s=s.replace('OpenVPN 2.7.6','OpenVPN 2.7.8')
  s=s.replace('onlineUUStart(', 'previewUUStart(').replace('/usr/libexec/localmod/merlin/vendor/dropbearkey','/usr/bin/dropbearkey')
  if n.endswith('test_online.go'):s=s.replace('func previewUUStart(', 'func onlineUUStart(')
  if n.endswith('native_runtime_client.go'):
   old='program := "/usr/bin/qemu-arm"';assert s.count(old)==1;s=s.replace(old,'program := "/usr/libexec/localmod/httpd"')
   old='argv := []string{"-L", nrQEMURoot(), "-E", "LD_PRELOAD=" + preload, "/usr/libexec/localmod/httpd", "-s", "-p", "34443"}'
   assert s.count(old)==1;s=s.replace(old,'argv := []string{"-s", "-p", "34443"}')
   old='cmd.Dir = "/www"';assert s.count(old)==1;s=s.replace(old,'cmd.Env = append(os.Environ(),"LD_PRELOAD="+preload)\\n\\t'+old)
  if n.endswith('workload.go'):
   s=s.replace('seconds != 600 && seconds != 3600','seconds != 300 && seconds != 600 && seconds != 3600').replace('if seconds == 600 {','if seconds <= 600 {')
   old='nrMust(os.Setenv("HOME", "/tmp"))';assert s.count(old)==1;s=s.replace(old,'// SSH uses the synthetic passwd home; do not repurpose HOME.')
   old='{"-N", "FUPNP"}}';assert s.count(old)==1;s=s.replace(old,'{"-N", "FUPNP"}, {"-t", "nat", "-N", "LOCALMOD_UPNP"}, {"-t", "nat", "-A", "POSTROUTING", "-j", "LOCALMOD_UPNP"}}')
   old='upnp_nat_chain=VUPNP\\\\n';assert s.count(old)==1;s=s.replace(old,old+'upnp_nat_postrouting_chain=LOCALMOD_UPNP\\\\next_allow_private_ipv4=yes\\\\n')
   old=':VUPNP - [0:0]\\\\n-A VSERVER';assert s.count(old)==1;s=s.replace(old,':VUPNP - [0:0]\\\\n:LOCALMOD_UPNP - [0:0]\\\\n-A POSTROUTING -j LOCALMOD_UPNP\\\\n-A VSERVER')
  if n.endswith('test_soak.go'):
   old='x.u = previewUUStart(x.ctx)';assert s.count(old)==1;s=s.replace(old,'nrCommand("/bin/nvram","set","ntp_ready=0")\\n\\t\\t'+old)
  if n.endswith('test_merlin.go'):
   key='c := exec.Command(args[0], args[1:]...)';assert s.count(key)==1
   s=s.replace(key,key+'\\n if name=="miniupnpd" {c.Env=append(os.Environ(),"LD_PRELOAD=/work/build/native_hw_fixture.so")}')
   old='b, e := exec.CommandContext(ctx, args[0], args[1:]...).CombinedOutput()';assert s.count(old)==1
   s=s.replace(old,'cmd := exec.CommandContext(ctx,args[0],args[1:]...)\\n if args[0]=="/usr/bin/dbclient" { for _,value:=range os.Environ(){if !strings.HasPrefix(value,"HOME="){cmd.Env=append(cmd.Env,value)}} }\\n b,e:=cmd.CombinedOutput()')
  s=s.replace('/work/build/test-merlin','/work/build/merlin38813-native-soak/probe')
 '''
 change(marker,transform.rstrip()+'\n'+marker)
 old="subprocess.run(['go','build','-trimpath','-o','build/test-merlin',*files]"
 add=''' original=(ROOT/'analysis/merlin_vpn_38813/native_preview.go').read_text();start=original.index('func previewUUStart(');end=original.index('func previewForm(')
 function=original[start:end].replace('LD_PRELOAD=/work/build/native_hw_fixture.so:','LD_PRELOAD=/work/build/merlin38813-native-soak/launcher_exec_fixture.so:/work/build/native_hw_fixture.so:').replace('/work/build/merlin38813-native-preview/clear_preload.so','/work/build/merlin38813-native-soak/clear_preload.so')
 function=function.replace('u := &onlineUU{}','nrCommand("/bin/nvram","set","ntp_ready=0"); os.Remove("/tmp/native-ntp-synced"); os.Remove("/tmp/owned-uu-worker.pid"); u := &onlineUU{}')
 p=dest/'native_uu.go';p.write_text('package main\\nimport("context";"crypto/md5";"fmt";"net";"net/http";"os";"os/exec";"strconv";"strings";"time")\\n'+function);files.append(str(p));transforms['native_uu_owned_fixture']=dict(sha256=sha(p),changes=['Native Merlin launcher and ntpd_synced callback; reset only owned volatile NTP/PID fixture state on planned starts'])
 '''
 change(old,add.lstrip(' ')+"subprocess.run(['go','build','-trimpath','-o','build/merlin38813-native-soak/probe',*files]")
 source=source.replace("'build/https_trace_fixture.so','analysis/r9r1_coexist/tls_trace.c'","'build/merlin38813-native-soak/https_trace_fixture.so','analysis/r9r1_coexist/tls_trace.c'")
 change("Path('build/merlin_nested_job.sh').write_text(job);subprocess.run(['python3','build/make_merlin_system_initramfs.py'],check=True)",'''setup=(ROOT/'build/real_plugins_setup.sh').read_text();cut='/bin/sh /usr/libexec/localmod/bootstrap.sh prepare ||';assert setup.count(cut)==1
 setup=setup[:setup.index(cut)]+'/sbin/service start_softcenter || exit 1\\nexec /work/build/merlin38813-native-soak/probe\\n'
 (ROOT/'build/merlin38813-native-soak/setup.sh').write_text(setup);job=job.replace('/work/build/real_plugins_setup.sh','/work/build/merlin38813-native-soak/setup.sh')
 (ROOT/'build/merlin38813-native-soak/nested_job.sh').write_text(job)
 generator=(ROOT/'build/make_merlin_system_initramfs.py').read_text();token="p=base/'merlin_nested_initramfs.gz'";assert generator.count(token)==1
 generator=generator.replace(token,"p=Path('build/merlin38813-native-soak/nested_initramfs.gz')");exec(compile(generator,'owned_native_soak_initramfs','exec'),{})''')
 change("extras=['build/fancyss_inputs.json','build/real_plugin_inputs.json',current['adapted_path'],ddns['path'],'build/https_trace_fixture.so']","extras=['build/fancyss_inputs.json','build/real_plugin_inputs.json',current['adapted_path'],ddns['path']]")
 marker="   for name in extras:"
 change(marker,'''   target=self.workspace/'build/casefs/rootfs';assert self.workspace in target.parents and not target.is_symlink();shutil.rmtree(target);shutil.copytree(tree,target,symlinks=True,copy_function=copy_file)
   expected=inventory(tree);assert expected==inventory(target) and hashlib.sha256(encoded(expected)).hexdigest()==candidate['stage_inventory_sha256'];self.inputs['build/casefs/rootfs']=candidate['stage_inventory_sha256']
   native=json.loads((ROOT/'output/merlin38813_candidate_runtime_tests.json').read_text())
   for name in ['launcher_exec_fixture.so','clear_preload.so','native_hw_fixture.so','native_uu_transport.so','native-nvram']:
    original=ROOT/'build/merlin38813-native-candidate-runtime'/name;assert sha(original)==native['vm']['inputs']['build/merlin38813-native-candidate-runtime/'+name]
    target=ROOT/'build/merlin38813-native-soak'/name;target.unlink(missing_ok=True);copy_file(original,target)
   for original in (ROOT/'build/merlin38813-native-soak').rglob('*'):
    if not original.is_file():continue
    name=str(original.relative_to(ROOT));target=self.workspace/name;target.parent.mkdir(parents=True,exist_ok=True);copy_file(original,target);self.inputs[name]=sha(original)
   for src,dst in [('native_hw_fixture.so','native_hw_fixture.so'),('native_uu_transport.so','native_uu_transport.so'),('native-nvram','native-nvram'),('https_trace_fixture.so','https_trace_fixture.so'),('nested_job.sh','merlin_nested_job.sh'),('nested_initramfs.gz','merlin_nested_initramfs.gz')]:
    target=self.workspace/'build'/dst;target.unlink(missing_ok=True);copy_file(ROOT/'build/merlin38813-native-soak'/src,target);self.inputs['build/'+dst]=sha(target)
   target=self.workspace/'build/httpd_bridge.so';target.unlink();copy_file(tree/'usr/lib/localmod/httpd_bridge.so',target);self.inputs['build/httpd_bridge.so']=sha(target)
 '''.rstrip()+'\n'+marker)
 change("limits=['Networkless full Cortex-A53", "limits=['Native Merlin candidate; direct owned daemon configs include a declared UPnP postrouting chain/private documentation WAN allowance and synthetic passwd home. Native RC firewall template generation is a separate boundary','Networkless full Cortex-A53")
 folder=ROOT/'build/merlin38813-native-soak';folder.mkdir(exist_ok=True);(folder/'derived_check.py').write_text(source)
 builtins.exec(compile(source,str(folder/'derived_check.py'),'exec'),dict(__name__='__main__',__file__=str(ROOT/'analysis/r9r1_coexist/check.py')))
if __name__=='__main__':main()
