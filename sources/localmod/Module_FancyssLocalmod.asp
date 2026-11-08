<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>安装 Fancyss</title>
<style>body{font:16px/1.7 system-ui,sans-serif;background:#202b33;color:#eee;margin:2em auto;padding:0 1.3em;max-width:800px}a{color:#a9dcff}section{background:#2c3b46;border:1px solid #49606e;border-radius:8px;padding:1.3em;margin:1em 0}button{font:inherit;padding:.6em 1em;background:#466778;color:white;border:1px solid #93b2c1;border-radius:5px;cursor:pointer}button:disabled{opacity:.6}pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:24em;overflow:auto}.note{color:#c5d3db}</style>
</head><body>
<h1>Fancyss · @FANCYSS_VERSION@</h1>
<p><a href="/Module_Softcenter.asp">软件中心</a> · <a href="/Module_Localmod.asp">官改状态与恢复</a> · <a href="/UUAccelerator.asp">网易 UU</a></p>
<section><p>适用于普通 @MODEL@ 的 @PLUGIN_PLATFORM@ 适配包。安装后保持关闭，节点和代理模式由你配置。</p>
<p>适配包保留 UU 文件与原厂日志，通过原厂登录和 HTTPS 管理；状态与日志使用 HTTP 查询。插件内自更新已改为提示使用软件中心安装兼容包。</p>
<p class="note">安装需要联网下载约 19 MiB，并预留插件及恢复检查点所需的 JFFS 空间。空间不足会拒绝安装。此候选版尚未完成实机网络、DNS、防火墙和真实 UU 加速验收。</p>
<button id="install" type="button">安装 @FANCYSS_VERSION@ 适配包</button>
<p id="message" role="status">准备就绪。已有 Fancyss 时请先备份节点和插件配置。</p>
<pre id="log" aria-label="安装日志"></pre>
<p><a href="/Module_shadowsocks.asp">打开 Fancyss</a> · <a href="/_temp/soft_install_log.txt" target="_blank" rel="noopener">查看完整安装日志</a></p></section>
<p class="note">上游：<a href="https://github.com/hq450/fancyss_history_package">hq450/fancyss_history_package</a>；适配来源与变更记录随官改版本发布。请使用与固件匹配的兼容包。</p>
<script>
(function(){
 'use strict';
 var button=document.getElementById('install'),message=document.getElementById('message'),log=document.getElementById('log');
 async function install(){
  button.disabled=true;message.textContent='正在提交安装请求…';
  var controller=new AbortController(),timer=setTimeout(function(){controller.abort();},15000);
  try{
   var id=Math.floor(Math.random()*90000000)+10000000;
   var body={id:id,method:'ks_app_install.sh',params:['ks_app_install'],fields:{softcenter_home_url:'https://github.com/fanxu1218/RT-AX86U/releases/download/@TAG@',softcenter_installing_todo:'shadowsocks',softcenter_installing_title:'Fancyss',softcenter_installing_version:'@FANCYSS_VERSION@',softcenter_installing_md5:'@FANCYSS_MD5@',softcenter_installing_tar_url:'@FANCYSS_FILENAME@'}};
   var response=await fetch('/_api/',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal:controller.signal});
   if(response.status===423)throw new Error('正在安装或等待恢复。请查看官改状态，保留现有数据。');
   if(response.status===401||response.status===403)throw new Error('登录已失效，请返回管理首页重新登录。');
   if(!response.ok)throw new Error('未能确认安装请求，请先检查安装日志，勿重复提交。');
   var result=await response.json();if(String(result.result)!==String(id))throw new Error('未能确认安装请求，请先检查安装日志，勿重复提交。');
   message.textContent='安装请求已接受。请查看安装日志，完成后再打开 Fancyss。';
   var report=await fetch('/_temp/soft_install_log.txt',{credentials:'same-origin',cache:'no-store',signal:controller.signal});
   if(report.ok)log.textContent=(await report.text()).slice(-131072);
  }catch(error){message.textContent=error.name==='AbortError'?'请求超时，安装可能仍在继续。请先检查日志，勿重复提交。':error.message;}
  finally{clearTimeout(timer);button.disabled=false;}
 }
 button.addEventListener('click',install);
})();
</script></body></html>
