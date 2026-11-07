#!/usr/bin/env python3
"""Publish an immutable prerelease only after exact local release gates pass."""
import gzip,hashlib,json,subprocess
from pathlib import Path
from release_config import ROOT,CONFIG
from check import owned_sources,sha
REPO='fanxu1218/RT-AX86U'
def api(path):return json.loads(subprocess.check_output(['gh','api','repos/'+REPO+'/'+path],cwd=ROOT))
def identity(r):return (r['id'],r['body'],sorted((a['id'],a['name'],a['size'],a.get('digest')) for a in r['assets']))
def main():
 assert not subprocess.check_output(['git','status','--porcelain'],cwd=ROOT).strip(),'Commit reviewed source/evidence before publishing'
 gate=json.loads((ROOT/'output/release_gates.json').read_text());v=json.loads((ROOT/'output/verification.json').read_text())
 assert gate['status']=='LOCAL_RELEASE_GATES_PASS' and gate['config']==CONFIG and gate['source_sha256']==owned_sources()
 for name,digest in gate['resumed_validation']['artifact_bound_reports'].items():assert sha(ROOT/name)==digest,('Gate report changed after validation',name)
 assert v['image']==CONFIG['image'] and sha(ROOT/v['image'])==gate['candidate_sha256']==v['sha256'] and all(v['checks'].values()) and not v['errors']
 head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip();assert api('commits/main')['sha']==head
 old={tag:api('releases/tags/'+tag) for tag in ['localmod2-r8-experimental','localmod2-r7-experimental','localmod2-r6-experimental','localmod2-r5-experimental','localmod2-r4-experimental','localmod2-r3-experimental','localmod2-r2-experimental']}
 r8head=api('commits/localmod2-r8-experimental')['sha'];assert r8head=='2f47bf9bddaa27839302326233f542ada76153c2'
 r7ref=api('git/ref/tags/localmod2-r7-experimental')['object'];assert r7ref['sha']=='e442ec2d8ae550490661b0fbe1ad4e16ec242c3c'
 assert api('git/tags/'+r7ref['sha'])['object']['sha']=='98255f1187c93ffc3e9ba8fcf88409b85a1787da'
 tag=CONFIG['tag'];version=CONFIG['variant']+'-'+CONFIG['revision'];source=ROOT/('output/'+version.replace('-','_')+'_sources.tar.gz')
 raw=subprocess.check_output(['git','archive','--format=tar','--prefix='+version+'/','HEAD'],cwd=ROOT);source.write_bytes(gzip.compress(raw,mtime=0))
 names=[CONFIG['image'],str(Path(CONFIG['image']).with_suffix('.build.json')),'output/SHA256SUMS','output/verification.json','output/structure.json','output/changes.json','output/release_gates.json','output/hardening_tests.json','output/tls_input_tests.json','output/health_tests.json','output/installer_boundaries_tests.json','output/resource_bounds_tests.json','output/httpd_memory_tests.json','output/httpd_cache_tests.json','output/httpd_cache_bounded_tests.json','output/uu_recovery_tests.json','output/native_runtime_tests.json','output/lifecycle_tests.json','output/compatibility_tests.json','output/hooks_tests.json','output/uu_compatibility_tests.json','output/online_plugin_tests.json','output/real_plugin_tests.json','output/interruption_tests.json','output/recovery_safety_tests.json','output/https_stability_tests.json','output/官改加固与优化说明.md','output/构建与发布校验.md','output/Alpha3升级localmod2与实机验收.md',str(source.relative_to(ROOT))]
 fancy=json.loads((ROOT/'output/fancyss_tests.json').read_text());assert fancy['candidate_sha256']==v['sha256'] and fancy['status'].endswith('_PASS')
 package=next(p for p in fancy['sources']['packages'] if p['phase']=='current')
 assert sha(ROOT/package['adapted_path'])==package['adapted_sha256']
 names+=['output/fancyss_tests.json','output/Fancyss集成说明.md','build/fancyss_sources.json','sources/localmod/fancyss-LICENSE.txt',package['adapted_path'],'output/history_tests.json','output/持久化操作记录说明.md','output/shard_tests.json','output/base_migration_tests.json','build/base_contracts.json','output/隔离分片与底包升级说明.md','output/model_isolation_tests.json','output/构建模型隔离说明.md']
 names+=['output/softcenter_upgrade_tests.json','output/softcenter_frontend_tests.json','output/softcenter_ui_mock_tests.json','output/merlin_component_tests.json','output/merlin_component_tests.log','build/softcenter_sources.json','build/merlin_sources.json','build/merlin_system_sources.json','sources/localmod/MERLIN_COMPONENTS_NOTICE.txt','output/软件中心1.9.60升级说明.md','output/梅林组件移植说明.md']
 # Match the existing releases' ASCII attachment naming. Keep Chinese source
 # paths/content in Git; only the transport filename is aliased byte-for-byte.
 aliases={'官改加固与优化说明.md':'HARDENING_NOTES.zh-CN.md','构建与发布校验.md':'BUILD_RELEASE_CHECKS.zh-CN.md','Alpha3升级localmod2与实机验收.md':'UPGRADE_ACCEPTANCE.zh-CN.md','Fancyss集成说明.md':'FANCYSS_INTEGRATION.zh-CN.md','持久化操作记录说明.md':'OPERATION_HISTORY.zh-CN.md','隔离分片与底包升级说明.md':'ISOLATION_BASE_MIGRATION.zh-CN.md','构建模型隔离说明.md':'MODEL_ISOLATION.zh-CN.md'}
 aliases.update({'软件中心1.9.60升级说明.md':'SOFTWARE_CENTER_1960.zh-CN.md','梅林组件移植说明.md':'MERLIN_COMPONENTS.zh-CN.md'})
 folder=ROOT/('build/'+version+'-release-assets');assert not folder.is_symlink();folder.mkdir(mode=0o700,exist_ok=True)
 assets=[];entries=[]
 for name in names:
  original=ROOT/name;p=original
  if original.name in aliases:
   p=folder/aliases[original.name];assert not p.is_symlink();p.write_bytes(original.read_bytes());assert sha(p)==sha(original)
  assert p.name.isascii();assets.append(p);entries.append({'name':p.name,'source_path':name,'bytes':p.stat().st_size,'sha256':sha(p)})
 manifest={'tag':tag,'commit':head,'candidate_sha256':v['sha256'],'assets':entries}
 assert len({p.name for p in assets})==len(assets),'Duplicate release attachment name'
 m=ROOT/('output/'+version.replace('-','_')+'_release_manifest.json');m.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n');assets.append(m)
 notes=ROOT/('build/'+version+'_release_notes.md');notes.write_text(f'''基于官方 24437，软件中心升级到 {CONFIG['software_center_version']}，保留官方 UU 和 Fancyss 3.5.29 HND v8 Full 兼容包。普通 HND 插件经受管理的安装器升级；未经适配的 Fancyss 和直接覆盖核心仍受限制。\n\n移植 Merlin 3004.388.12_2 的 OpenVPN 2.7.6、dnsmasq 2.93、curl 8.17.0、wget 1.25.0、Dropbear 2026.94、miniupnpd 2.3.11 及私有依赖。六个原入口默认使用新版，保留原厂程序和全局认证/TLS 库。原厂 OpenVPN 的 ncp-disable/静态密钥旧配置自动使用原厂程序；miniupnpd 适配原厂私网 WAN 和缺少 postrouting 链的启动/NAT 重载流程。详细范围、回退开关、许可证与测试边界见附件。\n\n本地验证和镜像回读绑定 SHA256：`{v['sha256']}`。真实插件运行在无外网网卡、宿主只读导出的临时 VM 中。组件服务另外通过完整 Cortex-A53 系统仿真验证实际 ARM32 程序和内核调用。保留事务检查点、UU 数据保护、脱敏操作记录和全部 VM 输入/状态隔离。\n\n实验候选版，未访问或刷写物理路由器；真实代理节点、UU 账号/加速、设备无线/NAT/DNS/IPv6、实机升级与断电恢复仍待验收。保留 r8 及历史附件。源码提交：{head}。\n''')
 subprocess.run(['gh','release','create',tag,*[str(p) for p in assets],'--repo',REPO,'--target',head,'--title',version+' experimental','--prerelease','--notes-file',str(notes)],cwd=ROOT,check=True)
 release=api('releases/tags/'+tag);remote={a['name']:a for a in release['assets']}
 assert release['prerelease'] and not release['draft'] and len(remote)==len(assets)
 for p in assets:
  a=remote[p.name];assert a['state']=='uploaded' and a['size']==p.stat().st_size and a['digest']=='sha256:'+sha(p),p.name
 for t,before in old.items():assert identity(api('releases/tags/'+t))==identity(before),t
 assert api('commits/localmod2-r8-experimental')['sha']==r8head
 assert api('commits/'+tag)['sha']==head and api('commits/main')['sha']==head
 report=dict(status='PUBLISHED_AND_ASSETS_VERIFIED',url=release['html_url'],commit=head,tag=tag,release_id=release['id'],assets_verified=len(assets),candidate_sha256=v['sha256'],old_releases_preserved={t:len(r['assets']) for t,r in old.items()},r7_tag_object_preserved=r7ref['sha'],router_accessed_or_flashed=False)
 (ROOT/'output/release_delivery.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
if __name__=='__main__':main()
