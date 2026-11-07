// Execute functions from the pinned distributed frontend, with no network.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import crypto from 'node:crypto';
const root = path.resolve(import.meta.dirname, '..');
const jsPath = 'build/casefs/rootfs/rom/etc/koolshare/res/soft-v19/assets/index-DhXhkv_Y.js';
const js = fs.readFileSync(path.join(root, jsPath), 'utf8');
const asp = fs.readFileSync(path.join(root, 'build/casefs/rootfs/rom/etc/koolshare/webs/Module_Softcenter.asp'), 'utf8');
function between(start, end) {
  const begin = js.indexOf(start), stop = js.indexOf(end, begin + start.length);
  assert(begin >= 0 && stop > begin && js.indexOf(start, begin + 1) === -1, start);
  const result = js.slice(begin, stop);
  assert(asp.includes(result), 'inline ASP and JS functions diverged: ' + start);
  return result;
}
const snippets = [between('function K_(', 'const G_='), between('function Ek(', 'async function Ck('),
  between('function wk(', 'async function Sk('), between('function RE(', 'function PE('),
  between('async function Ln(', 'async function dd('), between('async function ok(', 'function c0('),
  between('const Pp=', 'const ak='), between('const uk=', 'const ck='),
  between('function Y_(', 'async function tk(')];
const context = vm.createContext({URL, FormData, File, window:{location:{origin:'https://router.fixture.test:34443'}},
  cd:()=>123400, fetch:async()=>{throw Error('No frontend network transport installed');}});
vm.runInContext(snippets.join('\n')+'\nglobalThis.api={K_,Ek,wk,RE,Ln,ok,d0,m0,Y_,l0};', context, {timeout:2000});
const api=context.api, checks={};
const record=name=>{checks[name]=true;};
const app={name:'onlineprobe',title:'Owned 1.9.60 插件',version:'@VERSION@',md5:'@MD5@',tar_url:'@TAR_URL@'};
const clean=value=>JSON.parse(JSON.stringify(value));
const payloads={install:clean(api.K_({app,homeUrl:'@HOME_URL@',id:123401})),
  update:clean(api.Ek({app,id:123402})),uninstall:clean(api.wk({app,id:123403})),offline:clean(api.RE({name:'owned-1960.tar.gz'},123404))};
assert.equal(payloads.install.method,'ks_app_install.sh');assert.deepEqual(payloads.install.params,['ks_app_install']);
assert.equal(payloads.install.fields.softcenter_home_url,'@HOME_URL@');
assert.equal(payloads.update.method,'ks_app_install.sh');assert(!('softcenter_home_url' in payloads.update.fields));
assert.equal(payloads.uninstall.method,'ks_app_remove.sh');assert.deepEqual(payloads.uninstall.params,['ks_app_remove']);
assert.equal(payloads.offline.uploadUrl,'/_upload');assert.equal(payloads.offline.installPayload.method,'ks_tar_install.sh');
record('actual_release_functions_generate_install_update_uninstall_and_offline_payloads');
const calls=[];let response={ok:true,json:async()=>({result:123402})};
context.fetch=async(url,options)=>{calls.push({url:String(url),options});return response;};
await api.Ln(payloads.update);assert.equal(calls.length,1);
assert.equal(calls[0].url,'https://router.fixture.test:34443/_api/');
assert.deepEqual(JSON.parse(calls[0].options.body),payloads.update);
record('update_uses_same_origin_original_https_json_rpc_without_requiring_redundant_source_field');
for(const status of [401,423]) {
  response={ok:false,status};const count=calls.length;
  await assert.rejects(api.Ln(payloads.update),new RegExp(String(status)));
  assert.equal(calls.length,count+1);
}
record('authentication_and_operation_lock_errors_surface_without_replaying_write');
response={ok:true,json:async()=>({error:{code:17,message:'owned backend refusal'}})};
await assert.rejects(api.Ln(payloads.update),/owned backend refusal/);
record('backend_error_is_not_reported_as_success');
response={ok:true};await api.ok(new File(['owned'], 'owned-1960.tar.gz'));
const upload=calls.at(-1);assert.equal(upload.url,'https://router.fixture.test:34443/_upload');
assert.equal(upload.options.method,'POST');assert.equal(upload.options.body.get('owned-1960.tar.gz').name,'owned-1960.tar.gz');
record('actual_offline_upload_uses_filename_field_and_same_origin');
assert.equal(api.d0('').status,'empty');assert.equal(api.d0('running').canClose,false);
assert.equal(api.d0('complete\nXU6J03M6').status,'complete');
assert.equal(api.m0({isOpen:true,isLogReadEnabled:true,parsedLog:api.d0('running')}).canClose,false);
assert.equal(api.m0({isOpen:true,isLogReadEnabled:true,parsedLog:api.d0('XU6J03M6')}).canClose,true);
record('log_dialog_requires_backend_completion_marker');
api.Y_({...app,version:'2.0',md5:'0123456789abcdef0123456789abcdef',tar_url:'onlineprobe/new.tar.gz'});
assert.throws(()=>api.Y_({...app,version:'',tar_url:'x.tar.gz'}),/版本/);
assert.throws(()=>api.Y_({...app,tar_url:'javascript:owned'}),/安全/);
record('ordinary_relative_package_updates_are_allowed_missing_metadata_or_unsafe_urls_are_rejected');
fs.writeFileSync(path.join(root,'build/softcenter_frontend_payloads.json'),JSON.stringify(payloads,null,2)+'\n');
const v=JSON.parse(fs.readFileSync(path.join(root,'output/verification.json'),'utf8'));
const cfg=JSON.parse(fs.readFileSync(path.join(root,'build/release_config.json'),'utf8'));
const candidateReady=v.image===cfg.image;
assert(candidateReady || process.argv.includes('--stage-only'), 'Rebuild current candidate before binding frontend proof');
const sha=buffer=>crypto.createHash('sha256').update(buffer).digest('hex');
assert.equal(sha(fs.readFileSync(path.join(root,v.image))),v.sha256);
const report={status:candidateReady?'LOCAL_DISTRIBUTED_FRONTEND_CONTRACT_PASS':'LOCAL_STAGED_FRONTEND_CONTRACT_PASS',
  checks,node_version:process.version,frontend_sha256:sha(Buffer.from(js)),payloads_sha256:sha(fs.readFileSync(path.join(root,'build/softcenter_frontend_payloads.json'))),
  source_sha256:sha(fs.readFileSync(import.meta.filename)),
  limits:['Actual functions extracted from pinned distributed JS and verified against inline ASP; fetch and DOM are not a live browser/router',
          'No WAN requests, real accounts or physical router; separate native VM checks exercise these payloads through retained authentication/backend']};
if(candidateReady){report.candidate_image=v.image;report.candidate_sha256=v.sha256;}
else {report.base_candidate_image=v.image;report.base_candidate_sha256=v.sha256;report.source_overlay_used=true;}
fs.writeFileSync(path.join(root,'output/softcenter_frontend_tests.json'),JSON.stringify(report,null,2)+'\n');
console.log('PASS',Object.keys(checks).length,'distributed frontend contract checks');
