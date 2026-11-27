"""Halaman HTML untuk Web UI onno-x.

Self-contained: tidak ada CDN, tidak ada build step, tidak butuh internet.
Semua aset (CSS + JS + markdown renderer) inline di satu string.
"""

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark light"><title>onno-x</title>
<style>
:root{--bg:#202123;--side:#191a1c;--panel:#262729;--panel2:#303236;--fg:#ececec;--muted:#a1a1aa;--line:#38393d;--accent:#d6b98c;--danger:#f87171;--green:#6fcf97;--shadow:0 18px 55px #0006;--radius:14px}
:root[data-theme="light"]{--bg:#fff;--side:#f5f5f4;--panel:#fff;--panel2:#eeefed;--fg:#262626;--muted:#737373;--line:#e5e5e5;--accent:#8b6b43;--shadow:0 18px 55px #0002}
*{box-sizing:border-box}html,body{height:100%;margin:0}body{background:var(--bg);color:var(--fg);font:14px/1.55 Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;overflow:hidden}button,input,textarea,select{font:inherit;color:inherit}button{cursor:pointer}button:focus-visible,input:focus-visible,textarea:focus-visible,select:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.app{height:100%;display:flex}.sidebar{width:270px;flex:0 0 270px;background:var(--side);border-right:1px solid var(--line);display:flex;flex-direction:column;padding:15px 12px;transition:transform .2s,width .2s;z-index:5}.brandrow{display:flex;align-items:center;justify-content:space-between;padding:3px 7px 18px}.brand{font-size:18px;font-weight:750;letter-spacing:-.6px}.brand small{font-size:11px;color:var(--muted);font-weight:500;margin-left:5px}.iconbtn{width:34px;height:34px;border:0;background:transparent;border-radius:9px;color:var(--muted);display:grid;place-items:center;font-size:17px}.iconbtn:hover,.navbtn:hover,.historyitem:hover{background:var(--panel2);color:var(--fg)}.nav{display:grid;gap:4px}.navbtn{border:0;background:transparent;text-align:left;border-radius:9px;padding:10px 11px;color:var(--fg);display:flex;gap:11px;align-items:center}.navbtn .ico{width:18px;text-align:center;color:var(--muted);font-size:16px}.navbtn.primary{background:var(--panel2);font-weight:600}.sideheading{font-size:11px;color:var(--muted);letter-spacing:.08em;text-transform:uppercase;padding:23px 9px 8px;display:flex;justify-content:space-between;align-items:center}.history-search{width:100%;background:var(--panel);border:1px solid var(--line);border-radius:9px;padding:9px 10px;margin:0 0 8px}.history{overflow:auto;flex:1;min-height:80px}.historyitem{width:100%;display:flex;align-items:center;gap:7px;text-align:left;padding:9px 9px;border:0;border-radius:8px;background:transparent;color:var(--muted);font-size:13px}.historyitem.active{background:var(--panel2);color:var(--fg)}.historyitem .histtitle{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1}.historyitem .del{opacity:.45;flex:0 0 auto;border:0;background:transparent;color:var(--danger);font-size:15px;padding:2px 6px;border-radius:6px;cursor:pointer}.historyitem:hover .del,.historyitem .del:focus{opacity:1}.historyitem .del:hover{background:var(--panel2)}.histopen{flex:1;min-width:0;display:flex;align-items:center;gap:7px;border:0;background:transparent;color:inherit;text-align:left;padding:0;font:inherit;cursor:pointer}.emptyhist{color:var(--muted);font-size:12px;padding:10px}.sidebottom{border-top:1px solid var(--line);padding-top:10px;margin-top:10px}.profile{display:flex;align-items:center;gap:10px;padding:9px;border-radius:9px}.avatar{width:30px;height:30px;border-radius:50%;background:var(--panel2);display:grid;place-items:center;font-weight:700}.profile .sub{font-size:11px;color:var(--muted)}
.main{min-width:0;flex:1;display:flex;flex-direction:column;position:relative}.topbar{height:58px;display:flex;align-items:center;gap:10px;padding:0 20px;border-bottom:1px solid var(--line)}.topmodel{border:0;background:transparent;font-weight:600;padding:7px 9px;border-radius:8px}.topmodel:hover{background:var(--panel2)}.topright{margin-left:auto;display:flex;align-items:center;gap:7px}.status{font-size:11px;color:var(--muted)}.dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--muted);margin-right:5px}.dot.busy{background:#eab308}.dot.ok{background:var(--green)}.dot.err{background:var(--danger)}
.log{flex:1;overflow:auto;padding:30px 22px 24px;scroll-behavior:smooth}.messages{max-width:790px;margin:0 auto}.welcome{text-align:center;padding:11vh 15px 30px}.welcome h1{font-size:30px;letter-spacing:-1px;font-weight:550;margin:0 0 8px}.welcome p{color:var(--muted);font-size:15px}.suggestions{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;max-width:610px;margin:27px auto}.suggestion{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:13px;text-align:left;color:var(--fg)}.suggestion:hover{border-color:var(--accent)}.suggestion b{display:block;font-size:13px;margin-bottom:3px}.suggestion span{color:var(--muted);font-size:12px}.msg{margin:0 0 25px;animation:appear .16s ease}.who{font-size:11px;color:var(--muted);margin-bottom:7px}.bubble{
  user-select: text;overflow-wrap:anywhere}.user .bubble{
  user-select: text;background:var(--panel2);padding:11px 15px;border-radius:17px;display:inline-block;max-width:88%;white-space:pre-wrap}.assistant .bubble{
  user-select: text;padding:0 1px}.assistant p{margin:.4em 0 .8em}.assistant h1,.assistant h2,.assistant h3{line-height:1.25;margin:1em 0 .45em}.assistant h1{font-size:1.5em}.assistant h2{font-size:1.28em}.assistant h3{font-size:1.1em}.assistant ul,.assistant ol{padding-left:1.5em}.assistant li{margin:.25em 0}.assistant code{font-family:ui-monospace,Menlo,monospace;background:var(--panel2);padding:2px 5px;border-radius:5px;font-size:.88em}.assistant pre{background:var(--side);border:1px solid var(--line);border-radius:11px;padding:14px;overflow:auto;position:relative}.assistant pre code{background:none;padding:0}.assistant a{color:var(--accent)}.assistant blockquote{border-left:3px solid var(--line);padding-left:12px;color:var(--muted);margin:12px 0}.assistant hr{border:0;border-top:1px solid var(--line);margin:18px 0}.err .bubble{
  user-select: text;color:var(--danger);white-space:pre-wrap}.statusline{font-size:12px;color:var(--muted);padding:4px 0 12px}.tool{border:1px solid var(--line);border-radius:10px;margin:8px 0;background:var(--side);overflow:hidden}.tool summary{cursor:pointer;padding:9px 11px;color:var(--muted);font-size:12px}.tool pre{margin:0;padding:12px;border-top:1px solid var(--line);white-space:pre-wrap;overflow:auto;font-size:11px}
.composer-area{padding:10px 22px 22px}.composer-wrap{max-width:790px;margin:auto}.composer{border:1px solid var(--line);background:var(--panel);border-radius:17px;padding:10px 11px 8px;box-shadow:0 5px 25px #0001}.composer:focus-within{border-color:#8c806e}.composer textarea{display:block;width:100%;resize:none;min-height:48px;max-height:190px;border:0;outline:0;background:transparent;padding:7px 7px;color:var(--fg);line-height:1.5}.composer textarea::placeholder{color:var(--muted)}.composer-bottom{display:flex;align-items:center;gap:8px;padding:3px 2px 0}.composehint{font-size:11px;color:var(--muted)}.spacer{flex:1}.send,.stop{border:0;border-radius:10px;padding:8px 14px;font-weight:650}.send{background:var(--fg);color:var(--bg)}.send:disabled{opacity:.4;cursor:not-allowed}.stop{background:var(--panel2);color:var(--danger)}.footnote{text-align:center;color:var(--muted);font-size:10px;margin-top:8px}
.overlay{position:fixed;inset:0;background:#0008;display:none;align-items:center;justify-content:center;padding:18px;z-index:20}.overlay.open{display:flex}.modal{width:min(520px,100%);max-height:85vh;overflow:auto;background:var(--side);border:1px solid var(--line);border-radius:16px;box-shadow:var(--shadow)}.modalhead{display:flex;align-items:center;padding:17px 19px;border-bottom:1px solid var(--line)}.modalhead h2{font-size:16px;margin:0}.modalbody{padding:18px}.setting{display:flex;align-items:center;justify-content:space-between;gap:20px;padding:12px 0;border-bottom:1px solid var(--line)}.setting:last-child{border:0}.setting label{font-weight:550}.setting small{display:block;color:var(--muted);font-size:11px}.setting select{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:8px;max-width:190px}.modalactions{display:flex;gap:8px;justify-content:flex-end;margin-top:17px}.btn{background:var(--panel2);border:1px solid var(--line);border-radius:9px;padding:8px 12px}.btn.danger{color:var(--danger)}.btn.accent{background:var(--fg);color:var(--bg);border-color:transparent}.toast{position:fixed;bottom:22px;left:50%;transform:translateX(-50%);background:var(--panel2);border:1px solid var(--line);border-radius:10px;padding:9px 14px;display:none;z-index:30;box-shadow:var(--shadow)}.toast.show{display:block}
@media(max-width:760px){.sidebar{position:fixed;inset:0 auto 0 0;width:280px;transform:translateX(-102%);box-shadow:var(--shadow)}.sidebar.open{transform:translateX(0)}.topbar{padding:0 12px}.log{padding:22px 15px}.composer-area{padding:8px 12px 15px}.suggestions{grid-template-columns:1fr}.welcome{padding-top:7vh}.welcome h1{font-size:25px}.status{display:none}}
</style>
</head>
<body>
<div class="app">
<aside class="sidebar" id="sidebar">
 <div class="brandrow"><div class="brand">onno-x <small>workspace</small></div><button class="iconbtn" id="closeSide" aria-label="Tutup sidebar">×</button></div>
 <nav class="nav">
  <button class="navbtn primary" id="newChat"><span class="ico">＋</span>New chat</button>
  <button class="navbtn" id="newSearch"><span class="ico">⌕</span>New search</button>
 </nav>
 <div class="sideheading">Recent <button class="iconbtn" id="refreshHistory" title="Muat ulang">↻</button></div>
 <input class="history-search" id="historySearch" placeholder="Cari percakapan..." autocomplete="off">
 <div class="history" id="history"><div class="emptyhist">Memuat histori…</div></div>
 <div class="sidebottom">
  <button class="navbtn" id="settingsBtn"><span class="ico">⚙</span>Settings</button>
  <div class="profile"><div class="avatar">O</div><div><b>onno-x</b><div class="sub">Multi-model coding agent</div></div></div>
 </div>
</aside>
<main class="main">
 <div class="topbar">
  <button class="iconbtn" id="menuBtn" aria-label="Buka menu">☰</button>
  <button class="topmodel" id="modelButton">onno-x <span style="color:var(--muted)">⌄</span></button>
  <div class="topright"><span class="status"><i class="dot" id="dot"></i><span id="state">idle</span></span><button class="iconbtn" id="topSettings" title="Settings">⚙</button></div>
 </div>
 <section class="log" id="log"><div class="messages" id="msgs">
  <div class="welcome" id="welcome"><h1>ONNO X CODE</h1><p>Mulai percakapan baru dengan onno-x.</p>
   <div class="suggestions">
    <button class="suggestion" data-prompt="Bantu saya memahami dan memperbaiki kode ini."><b>⌘ Debug code</b><span>Temukan bug dan solusi</span></button>
    <button class="suggestion" data-prompt="Buatkan rencana implementasi fitur baru."><b>✳ Plan a feature</b><span>Rancang langkah implementasi</span></button>
    <button class="suggestion" data-prompt="Review struktur project dan berikan saran perbaikan."><b>⌕ Explore project</b><span>Pahami struktur project</span></button>
    <button class="suggestion" data-prompt="Jelaskan kode ini secara bertahap."><b>↗ Explain code</b><span>Pelajari cara kerja kode</span></button>
   </div>
  </div>
 </div></section>
 <footer class="composer-area"><div class="composer-wrap">
  <div class="composer"><textarea id="input" rows="1" placeholder="Message onno-x…" autofocus></textarea>
   <div class="composer-bottom"><span class="composehint">Enter untuk kirim · Shift+Enter untuk baris baru</span><span class="spacer"></span><button class="stop" id="stop" hidden>Stop</button><button class="send" id="send">↑</button></div>
  </div><div class="footnote">onno-x dapat membuat kesalahan. Periksa hasil penting.</div>
 </div></footer>
</main></div>
<div class="overlay" id="settingsModal" role="dialog" aria-modal="true" aria-label="Settings">
 <div class="modal"><div class="modalhead"><h2>Settings</h2><span class="spacer"></span><button class="iconbtn" data-close="settingsModal">×</button></div>
 <div class="modalbody">
  <div class="setting"><div><label for="settingModel">Model</label><small>Pilih model AI aktif</small></div><select id="settingModel"></select></div>
  <div class="setting"><div><label for="settingMode">Permission mode</label><small>Kontrol izin penggunaan tools</small></div><select id="settingMode"><option value="auto">Auto</option><option value="manual">Manual</option><option value="all">All / YOLO</option></select></div>
  <div class="setting"><div><label for="settingTheme">Appearance</label><small>Tampilan aplikasi</small></div><select id="settingTheme"><option value="dark">Dark</option><option value="light">Light</option><option value="system">System</option></select></div>
  <div class="setting"><div><label>Conversation history</label><small>Hapus semua percakapan tersimpan</small></div><button class="btn danger" id="clearHistory">Clear all</button></div>
  <div class="setting"><div><label>Session</label><small>Mulai percakapan kosong</small></div><button class="btn" id="settingsNew">New chat</button></div>
  <div class="modalactions"><button class="btn" data-close="settingsModal">Close</button></div>
 </div></div>
</div>
<div class="overlay" id="confirmModal" role="dialog" aria-modal="true">
 <div class="modal"><div class="modalhead"><h2 id="confirmTitle">Konfirmasi</h2><span class="spacer"></span><button class="iconbtn" data-close="confirmModal">×</button></div>
 <div class="modalbody"><p id="confirmText">Yakin ingin melanjutkan?</p><div class="modalactions"><button class="btn" data-close="confirmModal">Batal</button><button class="btn danger" id="confirmYes">Hapus</button></div></div></div>
</div>
<div class="toast" id="toast"></div>
<script>
"use strict";
const TOKEN=new URLSearchParams(location.search).get("t")||"";
const $=s=>document.querySelector(s);
let es=null,busy=false,turnId=null,curAssistant=null,curBuf="",sessions=[],activeSession=null,confirmAction=null,models=[];
function api(path,opts={}){const sep=path.includes("?")?"&":"?";return fetch(path+sep+"t="+encodeURIComponent(TOKEN),{...opts,headers:{"Content-Type":"application/json","X-Onno-Token":TOKEN,...(opts.headers||{})}})}
function toast(s){const t=$("#toast");t.textContent=s;t.classList.add("show");setTimeout(()=>t.classList.remove("show"),2600)}
function safeUrl(raw){try{const u=new URL(raw,location.href);return ["http:","https:","mailto:"].includes(u.protocol)?u.href:null}catch{return null}}
function esc(s){return String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]))}
function inlineMd(s){let t=esc(s);t=t.replace(/`([^`]+)`/g,"<code>$1</code>").replace(/\*\*([^*]+)\*\*/g,"<strong>$1</strong>").replace(/(^|[^*\w])\*([^*\n]+)\*/g,"$1<em>$2</em>");
 t=t.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g,(m,a,b)=>{const u=safeUrl(b);return u?'<a href="'+esc(u)+'" target="_blank" rel="noopener noreferrer">'+a+"</a>":a});
 t=t.replace(/(^|\s)(https?:\/\/[^\s<]+)/g,(m,p,u)=>{const clean=safeUrl(u);return clean?p+'<a href="'+esc(clean)+'" target="_blank" rel="noopener noreferrer">'+u+"</a>":m});return t}
function md(src){const lines=String(src).split("\n"),out=[];let code=null,list=null,ordered=false,para=[];
 const fp=()=>{if(para.length){out.push("<p>"+inlineMd(para.join(" "))+"</p>");para=[]}};
 const fl=()=>{if(list){const tag=ordered?"ol":"ul";out.push("<"+tag+">"+list.map(x=>"<li>"+inlineMd(x)+"</li>").join("")+"</"+tag+">");list=null}};
 for(const raw of lines){if(code!==null){if(/^\s*```/.test(raw)){out.push("<pre><code>"+esc(code.join("\n"))+"</code></pre>");code=null}else code.push(raw);continue}
 if(/^\s*```/.test(raw)){fp();fl();code=[];continue}const l=raw.trimEnd();
 if(/^#{1,6}\s/.test(l)){fp();fl();const n=l.match(/^#+/)[0].length;out.push("<h"+n+">"+inlineMd(l.slice(n).trim())+"</h"+n+">");continue}
 if(/^\s*[-*+]\s+/.test(l)||/^\s*\d+[.)]\s+/.test(l)){fp();const ord=/^\s*\d/.test(l);if(list&&ordered!==ord)fl();ordered=ord;list=list||[];list.push(l.replace(/^\s*(?:[-*+]|\d+[.)])\s+/,""));continue}
 if(/^\s*>\s?/.test(l)){fp();fl();out.push("<blockquote>"+inlineMd(l.replace(/^\s*>\s?/,""))+"</blockquote>");continue}
 if(/^\s*(-{3,}|\*{3,})\s*$/.test(l)){fp();fl();out.push("<hr>");continue}
 if(!l.trim()){fp();fl();continue}fl();para.push(l.trim())}
 if(code!==null)out.push("<pre><code>"+esc(code.join("\n"))+"</code></pre>");fp();fl();return out.join("")}
function scroll(){const l=$("#log");l.scrollTop=l.scrollHeight}
function clearWelcome(){$("#welcome")?.remove()}
function addPlain(cls,who,text){clearWelcome();const e=document.createElement("div");e.className="msg "+cls;const w=document.createElement("div");w.className="who";w.textContent=who;const b=document.createElement("div");b.className="bubble";b.textContent=text;e.append(w,b);$("#msgs").append(e);scroll();return e}
function addAssistant(){clearWelcome();const e=document.createElement("div");e.className="msg assistant";const w=document.createElement("div");w.className="who";w.textContent="onno-x";const b=document.createElement("div");b.className="bubble";e.append(w,b);$("#msgs").append(e);curAssistant=b;curBuf="";return b}
function addTool(name,args,result=false){clearWelcome();const d=document.createElement("details");d.className="tool";const s=document.createElement("summary");s.textContent=(result?"▤ ":"⚙ ")+name+(result?" · hasil":" · "+JSON.stringify(args).slice(0,100));const p=document.createElement("pre");p.textContent=result?String(args):JSON.stringify(args,null,2);d.append(s,p);$("#msgs").append(d);scroll()}
function setBusy(v,label){busy=v;$("#send").hidden=v;$("#stop").hidden=!v;$("#dot").className="dot "+(v?"busy":"ok");$("#state").textContent=label||(v?"working":"idle")}
function connect(turn){if(es)es.close();es=new EventSource("/api/stream?turn="+encodeURIComponent(turn)+"&t="+encodeURIComponent(TOKEN));es.onmessage=e=>{let v;try{v=JSON.parse(e.data)}catch{return}switch(v.type){
 case"user":addPlain("user","kamu",v.text);break;
 case"token":if(!curAssistant)addAssistant();curBuf+=v.text;curAssistant.innerHTML=md(curBuf);scroll();break;
 case"status":{clearWelcome();const n=document.createElement("div");n.className="statusline";n.textContent=v.detail;$("#msgs").append(n);scroll();break}
 case"tool_call":addTool(v.name,v.args);break;case"tool_result":addTool(v.name,v.text,true);break;
 case"permission":permission(v);break;
 case"error":addPlain("err","error",v.message);setBusy(false,"error");$("#dot").className="dot err";break;
 case"done":if(curAssistant)curAssistant.innerHTML=md(curBuf);setBusy(false);updateState();if(es){es.close();es=null}loadSessions();break;
 }}}
async function permission(v){clearWelcome();const d=document.createElement("div");d.className="tool";const s=document.createElement("div");s.style.padding="12px";s.textContent="Izin dibutuhkan: "+v.name;const pre=document.createElement("pre");pre.textContent=JSON.stringify(v.args,null,2);d.append(s,pre);for(const [c,label] of [["y","Izinkan"],["n","Tolak"],["a","Selalu izinkan"]]){const b=document.createElement("button");b.className="btn";b.textContent=label;b.onclick=async()=>{b.disabled=true;try{const r=await api("/api/permission",{method:"POST",body:JSON.stringify({request_id:v.request_id,choice:c})});if(!r.ok)throw Error("Gagal menyimpan izin");d.textContent="Izin: "+label}catch(e){toast(e.message)}};s.append(b)}$("#msgs").append(d);scroll()}
async function send(){if(busy)return;const ta=$("#input"),message=ta.value.trim();if(!message)return;ta.value="";resizeInput();if(message.startsWith("/")){await localSlash(message);return}setBusy(true);try{const r=await api("/api/turn",{method:"POST",body:JSON.stringify({message})});const d=await r.json();if(!r.ok||d.error)throw Error(d.error||"Permintaan gagal");turnId=d.turn_id;connect(turnId)}catch(e){addPlain("err","error",e.message);setBusy(false)}}
async function localSlash(cmd){const [name,...rest]=cmd.split(/\s+/),arg=rest.join(" ");if(name==="/new"||name==="/clear"){await newChat();return}
 if(name==="/help"){addAssistant();curBuf="**Perintah web UI**\n\n- `/help` — bantuan\n- `/model <nama>` — ganti model\n- `/new` — sesi baru\n- `/sessions` — muat histori\n- `/clear` — sesi baru\n\nPerintah lainnya diteruskan ke agent.";curAssistant.innerHTML=md(curBuf);return}
 if(name==="/sessions"){await loadSessions();toast("Histori diperbarui");return}
 if(name==="/model"){await changeModel(arg);return}
 setBusy(true);try{const r=await api("/api/turn",{method:"POST",body:JSON.stringify({message:cmd})});const d=await r.json();if(!r.ok||d.error)throw Error(d.error||"Permintaan gagal");connect(d.turn_id)}catch(e){addPlain("err","error",e.message);setBusy(false)}}
async function newChat(){try{const r=await api("/api/session/new",{method:"POST",body:"{}"});const d=await r.json().catch(()=>({}));if(!r.ok||d.error)throw Error(d.error||"Tidak dapat membuat sesi");if(es){es.close();es=null}activeSession=d.session_id||null;$("#msgs").innerHTML='<div class="welcome" id="welcome"><h1>Apa yang ingin kamu kerjakan?</h1><p>Mulai percakapan baru dengan onno-x.</p><div class="suggestions"><button class="suggestion" data-prompt="Bantu saya memahami dan memperbaiki kode ini."><b>⌘ Debug code</b><span>Temukan bug dan solusi</span></button><button class="suggestion" data-prompt="Buatkan rencana implementasi fitur baru."><b>✳ Plan a feature</b><span>Rancang langkah implementasi</span></button><button class="suggestion" data-prompt="Review struktur project dan berikan saran perbaikan."><b>⌕ Explore project</b><span>Pahami struktur project</span></button><button class="suggestion" data-prompt="Jelaskan kode ini secara bertahap."><b>↗ Explain code</b><span>Pelajari cara kerja kode</span></button></div></div>';setBusy(false);loadSessions();$("#input").focus()}catch(e){toast(e.message)}}
async function loadSessions(){try{const r=await api("/api/sessions");const d=await r.json();if(!r.ok)throw Error(d.error||"Histori tidak dapat dimuat");sessions=d.sessions||[];renderHistory()}catch(e){$("#history").innerHTML='<div class="emptyhist">Histori tidak tersedia</div>';}}
function renderHistory(){const q=$("#historySearch").value.toLowerCase();const root=$("#history");root.innerHTML="";const filtered=sessions.filter(s=>(s.title||s.id||"").toLowerCase().includes(q));if(!filtered.length){root.innerHTML='<div class="emptyhist">Belum ada percakapan.</div>';return}
 filtered.forEach(s=>{const row=document.createElement("div");row.className="historyitem"+(s.id===activeSession?" active":"");const open=document.createElement("button");open.className="histopen";open.innerHTML='<span>▤</span><span class="histtitle"></span>';open.querySelector(".histtitle").textContent=s.title||s.id||"Untitled session";open.title=s.id;open.onclick=()=>openSession(s.id);const del=document.createElement("button");del.className="del";del.textContent="×";del.title="Hapus sesi";del.setAttribute("aria-label","Hapus sesi");del.onclick=e=>{e.stopPropagation();confirm("Hapus sesi ini?","Percakapan ini akan dihapus jika backend mendukung endpoint penghapusan.",()=>deleteSession(s.id))};row.append(open,del);root.append(row)})}
async function openSession(id){try{const r=await api("/api/session/load",{method:"POST",body:JSON.stringify({session_id:id})});const d=await r.json();if(!r.ok||d.error)throw Error(d.error||"Gagal membuka sesi");if(es){es.close();es=null}activeSession=id;$("#msgs").innerHTML="";(d.messages||[]).forEach(m=>{if(m.role==="user")addPlain("user","kamu",m.content||"");else if(m.role==="assistant"&&m.content){addAssistant();curBuf=m.content;curAssistant.innerHTML=md(curBuf)}});renderHistory();scroll()}catch(e){toast(e.message)}}
function confirm(title,desc,fn){$("#confirmTitle").textContent=title;$("#confirmText").textContent=desc;confirmAction=fn;$("#confirmModal").classList.add("open")}
async function deleteSession(id){try{const r=await api("/api/session/delete",{method:"POST",body:JSON.stringify({session_id:id})});const d=await r.json().catch(()=>({}));if(!r.ok||d.error)throw Error(d.error||"Endpoint penghapusan sesi belum tersedia di backend");sessions=sessions.filter(s=>s.id!==id);if(activeSession===id){activeSession=null;$("#msgs").innerHTML='<div class="welcome" id="welcome"><h1>Apa yang ingin kamu kerjakan?</h1><p>Pilih percakapan atau mulai yang baru.</p></div>'}renderHistory();toast("Sesi dihapus")}catch(e){toast(e.message)}}
async function clearAll(){try{const r=await api("/api/sessions/clear",{method:"POST",body:"{}"});const d=await r.json().catch(()=>({}));if(!r.ok||d.error)throw Error(d.error||"Endpoint hapus semua histori belum tersedia di backend");sessions=[];activeSession=null;renderHistory();$("#msgs").innerHTML='<div class="welcome" id="welcome"><h1>Apa yang ingin kamu kerjakan?</h1><p>Histori percakapan sudah dibersihkan.</p></div>';toast("Histori dihapus")}catch(e){toast(e.message)}}
async function changeModel(model){if(!model)return;try{const r=await api("/api/model",{method:"POST",body:JSON.stringify({model})});const d=await r.json();if(!r.ok||d.error)throw Error(d.error||"Gagal mengganti model");$("#settingModel").value=d.active_model;$("#modelButton").textContent=d.active_model+" ⌄";toast("Model aktif: "+d.active_model);updateState()}catch(e){toast(e.message)}}
async function updateMode(mode){try{const r=await api("/api/mode",{method:"POST",body:JSON.stringify({mode})});const d=await r.json();if(!r.ok||d.error)throw Error(d.error||"Gagal mengganti mode");toast("Permission mode: "+mode);updateState()}catch(e){toast(e.message)}}
async function updateState(){try{const r=await api("/api/state");const d=await r.json();$("#settingMode").value=d.permission_mode||"auto";if(d.active_model){$("#modelButton").textContent=d.active_model+" ⌄";$("#settingModel").value=d.active_model}}catch{}}
function resizeInput(){const t=$("#input");t.style.height="auto";t.style.height=Math.min(190,t.scrollHeight)+"px"}
function openSettings(){$("#settingsModal").classList.add("open")}
function setTheme(v){if(v==="system")document.documentElement.removeAttribute("data-theme");else document.documentElement.setAttribute("data-theme",v);try{localStorage.setItem("onno-theme",v)}catch{}}
async function init(){try{const r=await api("/api/state");if(!r.ok){document.body.innerHTML="<div style='padding:40px'>401 — token tidak valid. Buka URL lengkap dari terminal.</div>";return}const d=await r.json();models=d.models||[];const names=models.map(m=>m.name);if(d.active_model&&!names.includes(d.active_model))names.unshift(d.active_model);$("#settingModel").innerHTML="";names.forEach(n=>{const m=models.find(x=>x.name===n),o=document.createElement("option");o.value=n;o.textContent=n+(m?" ("+m.provider+")":"");$("#settingModel").append(o)});$("#settingModel").value=d.active_model||"";$("#modelButton").textContent=(d.active_model||"onno-x")+" ⌄";$("#settingMode").value=d.permission_mode||"auto";const saved=(()=>{try{return localStorage.getItem("onno-theme")||"dark"}catch{return"dark"}})();$("#settingTheme").value=saved;setTheme(saved);await loadSessions()}catch(e){toast(e.message)}}
$("#send").onclick=send;$("#stop").onclick=async()=>{try{await api("/api/stop",{method:"POST",body:"{}"})}finally{setBusy(false,"stopped");if(es){es.close();es=null}}};
$("#newChat").onclick=newChat;$("#newSearch").onclick=()=>{$("#input").value="Search: ";$("#input").focus();resizeInput()};$("#settingsNew").onclick=()=>{ $("#settingsModal").classList.remove("open");newChat() };
$("#menuBtn").onclick=()=>$("#sidebar").classList.add("open");$("#closeSide").onclick=()=>$("#sidebar").classList.remove("open");
$("#settingsBtn").onclick=openSettings;$("#topSettings").onclick=openSettings;
$("#refreshHistory").onclick=loadSessions;$("#historySearch").oninput=renderHistory;
$("#settingModel").onchange=e=>changeModel(e.target.value);$("#settingMode").onchange=e=>updateMode(e.target.value);$("#settingTheme").onchange=e=>setTheme(e.target.value);
$("#clearHistory").onclick=()=>confirm("Hapus seluruh histori?","Semua sesi tersimpan akan dihapus. Tindakan ini tidak dapat dibatalkan.",clearAll);
$("#confirmYes").onclick=()=>{const fn=confirmAction;confirmAction=null;$("#confirmModal").classList.remove("open");if(fn)fn()};
document.querySelectorAll("[data-close]").forEach(b=>b.onclick=()=>$("#"+b.dataset.close).classList.remove("open"));
$("#input").addEventListener("paste", e=>{
  const text=(e.clipboardData||e.originalEvent?.clipboardData||{}).getData("text/plain")||"";
  if(text){$("#input").value+=text;resizeInput()}
  e.preventDefault()
});
document.querySelectorAll(".overlay").forEach(o=>o.addEventListener("click",e=>{if(e.target===o)o.classList.remove("open")}));
$("#input").addEventListener("keydown",e=>{if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();send()}});
$("#input").addEventListener("input",resizeInput);
$("#msgs").addEventListener("click",e=>{const b=e.target.closest("[data-prompt]");if(b){$("#input").value=b.dataset.prompt;$("#input").focus();resizeInput()}});
$("#modelButton").onclick=()=>openSettings();
document.addEventListener("keydown",e=>{if(e.key==="Escape")document.querySelectorAll(".overlay.open").forEach(x=>x.classList.remove("open"))});
window.addEventListener("beforeunload",()=>{if(es)es.close()});
init();
</script>
</body></html>
"""
