<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>官改状态与恢复</title>
<style>body{font:16px/1.7 system-ui,sans-serif;background:#202b33;color:#eee;margin:2em auto;padding:0 1.3em;max-width:850px}a{color:#a9dcff}button{font:inherit;padding:.5em 1em;background:#466778;color:white;border:1px solid #93b2c1;border-radius:5px;cursor:pointer}button:disabled{opacity:.6}section{background:#2c3b46;border:1px solid #49606e;border-radius:8px;padding:1em 1.3em;margin:1em 0}h1{font-size:1.65em}h2{font-size:1.15em}dl{display:grid;grid-template-columns:8em 1fr;gap:.5em}dd{margin:0;overflow-wrap:anywhere}.note{color:#c5d3db}.error{color:#ffd6ad}li{margin:.5em 0}@media(max-width:500px){dl{grid-template-columns:1fr;gap:.2em}dd{margin-bottom:.6em}}</style>
</head><body>
<h1>官改状态与恢复 · @REVISION@</h1>
<p>华硕 RT-AX86U · 官方 3.0.0.4.388_24437 · 软件中心 1.9.50 · 官方网易 UU</p>
<p class="note">试验版，尚未完成实机验收。此页只读取状态，不会修改配置或删除恢复副本。</p>
<p><a href="/Module_Softcenter.asp">软件中心</a> · <a href="/UUAccelerator.asp">网易 UU</a> · <a href="/Module_FancyssLocalmod.asp">安装 Fancyss</a> · <a href="/index.asp">管理首页</a></p>
<section aria-labelledby="health-title"><h2 id="health-title">当前状态</h2>
<p id="message" role="status">正在读取…</p>
<dl><dt>软件中心进程</dt><dd id="center">等待查询</dd><dt>事件进程</dt><dd id="events">等待查询</dd><dt>UU 进程</dt><dd id="uu">等待查询</dd><dt>JFFS 可用空间</dt><dd id="space">等待查询</dd><dt>恢复检查点</dt><dd id="checkpoint">等待查询</dd><dt>最近插件操作</dt><dd id="operation">等待查询</dd></dl>
<p><button id="refresh" type="button">刷新状态</button> · <a href="/_localmod/diagnostics" download="localmod-diagnostics.json">导出脱敏诊断</a></p>
<p class="note">进程数量不能证明插件或 UU 加速正常。UU 状态请进入官方页面确认。诊断仅含脱敏摘要，不导出日志、配置、密码、证书或账号。记录时间以路由器时钟为准。</p></section>
<section><h2>最近安装与恢复记录</h2><p id="history-message" role="status">等待查询</p><ol id="history"></ol><p class="note">最多保留 32 条事件，正常保存后可跨重启查看。异常中断由启动标识及原进程状态推断，不代表插件已经回退。记录损坏或未完成写入时保留文件；记录失败不影响插件和 UU 的运行。</p></section>
<section><h2>异常时怎么处理</h2><ol>
<li>先保存脱敏诊断，并备份配置、JFFS 和插件数据。存在检查点时，暂停新的插件写入。</li>
<li>安装中断后可重启一次，随后检查插件配置、软件中心和 UU。检查点的存在仅表示有待处理记录，页面不会验证副本是否完整。</li>
<li>若提示副本损坏、空间不足或重启后仍不能恢复，保留副本并停止操作。请按验收文档检查空间和备份，勿手工删除检查点或反复安装。</li>
<li>需要回退时，使用已核验的原 Alpha 3 固件及对应备份；跨版本请按文档恢复，勿把新版 NVRAM 配置直接导入旧版。</li></ol></section>
<script>
(function(){
 'use strict';
 var busy=false,button=document.getElementById('refresh');
 function text(id,value){document.getElementById(id).textContent=value;}
 function size(n){return (n/1048576).toFixed(1)+' MiB';}
 async function refresh(){
  if(busy)return;busy=true;button.disabled=true;
  var controller=new AbortController(),timer=setTimeout(function(){controller.abort();},8000);
  try{
   var r=await fetch('/_localmod/status',{credentials:'same-origin',cache:'no-store',signal:controller.signal});
   if(r.status===401||r.status===403)throw new Error('登录已失效，请返回管理首页重新登录。');
   if(!r.ok)throw new Error('状态读取失败，请保留现有数据并稍后重试。');
   var s=await r.json();if(s.schema!==1)throw new Error('状态格式不兼容。');
   text('center','Web 服务 '+s.services.httpdb+' / 数据服务 '+s.services.skipd+' 个进程');
   text('events',s.services.events+' 个可识别进程');
   text('uu',s.services.uuplugin>0?s.services.uuplugin+' 个可识别进程（请进入 UU 确认）':'未检测到可识别进程，请进入 UU 页面确认');
   text('space',s.jffs.available?size(s.jffs.free_bytes)+' / '+size(s.jffs.total_bytes):'暂时无法读取');
   text('checkpoint',({'none':'未发现活动检查点','pending':'存在检查点：暂停插件写入并检查恢复记录','store-invalid':'恢复存储异常：保留副本并停止插件操作','unavailable':'暂时无法读取：保留副本并停止插件操作'})[s.checkpoint]||'状态未知');
   var o=s.last_operation;
   function eventText(o){return o.module+' · '+({'install':'安装','update':'更新','uninstall':'卸载','offline':'离线安装','recovery':'恢复','manual':'记录'})[o.kind]+' · '+(o.closed?'开始（后续已结束）':o.inferred_interruption?'记录未结束（推断，请核验插件状态）':({'running':'执行中','finished':'已结束，返回码 '+o.code,'interrupted':'异常中断'})[o.state])+' · '+new Date(o.epoch*1000).toLocaleString()+(o.persisted?'':'（本次暂存，未确认持久保存）');}
   text('operation',o?eventText(o):'暂无记录');
   var h=s.history||{},labels={'ready':'已保存，可跨重启查看','empty':'暂无历史记录','busy':'记录正在写入，请稍后刷新','corrupt':'记录副本校验失败：保留文件，已有可信记录仍可查看','write-interrupted':'存在未完成的记录写入：保留文件，暂停持久化记录','store-invalid':'记录存储异常：保留文件，暂停持久化记录','space-low':'记录空间不足：保留已有记录，本次记录可能仅暂存','unavailable':'暂时无法读取记录'};
   text('history-message',(labels[h.status]||'记录状态未知')+(h.last_write_error&&h.last_write_error!=='ready'?'；最近一次保存未成功':''));
   var list=document.getElementById('history');list.textContent='';(h.events||[]).forEach(function(e){var item=document.createElement('li');item.textContent=eventText(e);list.appendChild(item);});
   text('message','已刷新 · '+new Date().toLocaleTimeString());document.getElementById('message').className='note';
  }catch(e){text('message',e.name==='AbortError'?'读取超时，请稍后刷新。':e.message);document.getElementById('message').className='error';}
  finally{clearTimeout(timer);busy=false;button.disabled=false;}
 }
 button.addEventListener('click',refresh);refresh();
})();
</script></body></html>
