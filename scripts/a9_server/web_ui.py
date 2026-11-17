# -*- coding: utf-8 -*-
VIEWER = b"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
html,body { margin:0; width:100%; height:100%; background:#000; overflow:hidden; }
canvas { display:block; width:100%; height:100%; object-fit:contain; }
#enable-audio { position:fixed; top:1rem; right:1rem; padding:0.6rem 1rem; }
</style>
<style id="ptz-pad-fix">
#ptz-pad { left: auto !important; right: 14px !important; bottom: 56px !important; }
#enable-audio { display: inline-flex !important; align-items: center;  position: static !important; margin: 0 !important; }
</style>
</head>
<body>
<img id="mjpg" src="/stream.mjpg" style="position:fixed;inset:0;width:100%;height:100%;object-fit:contain;background:#000;z-index:1;pointer-events:none;" />
<div id="osd-live-top" style="display:block;position:fixed;left:10px;top:245px;background:rgba(0,0,0,.62);color:#fff;padding:4px 9px;border-radius:6px;font:600 13px monospace;z-index:9500;pointer-events:none;border:1px solid rgba(255,255,255,.22);"></div>
<script>
(function(){
  var on = true;
  function p(n){return n<10?"0"+n:""+n;}
  function sync(){fetch("/state",{cache:"no-store"}).then(function(r){return r.json();}).then(function(s){if(typeof s.osd==="number")on=(s.osd===1);}).catch(function(){});}
  document.addEventListener("click",function(e){var b=e.target&&e.target.closest?e.target.closest("button"):e.target;if(b&&(b.getAttribute("onclick")||"").indexOf("osd")!==-1){on=(b.getAttribute("onclick").indexOf("1")!==-1);}},true);
  setInterval(function(){
    var el=document.getElementById("osd-live-top"), im=document.getElementById("mjpg");
    if(!el)return;
    if(!on){el.style.display="none";return;}
    var d=new Date();
    el.textContent=p(d.getDate())+"."+p(d.getMonth()+1)+"."+d.getFullYear()+" "+p(d.getHours())+":"+p(d.getMinutes())+":"+p(d.getSeconds());
    el.style.display="block";
    if(im&&im.clientWidth>100&&im.clientHeight>100){
      var nw=im.naturalWidth||640,nh=im.naturalHeight||480,sc=Math.min(im.clientWidth/nw,im.clientHeight/nh);
      el.style.left=Math.max(10,Math.round((im.clientWidth-nw*sc)/2)+10)+"px";
      el.style.top=Math.max(document.body.classList.contains("fs-active")?14:112,Math.round((im.clientHeight-nh*sc)/2)+10)+"px";
    }
  },300);
  sync();
})();
</script>

<canvas id="video" style="display:none;"></canvas>
<div style="position:relative;z-index:10010;pointer-events:auto;display:grid;grid-template-columns:repeat(3,1fr);gap:8px;padding:8px;max-width:480px;margin:0 auto;">
  <button style="cursor:pointer !important;pointer-events:auto !important;width:100%;padding:9px 6px;border-radius:9px;border:1px solid rgba(255,255,255,.28);background:rgba(15,23,42,.82);color:#fff;font-size:13px;font-weight:600;text-align:center;" id="enable-audio" type="button">&#128266; &#1047;&#1074;&#1091;&#1082;</button>
  <button style="cursor:pointer !important;pointer-events:auto !important;width:100%;padding:9px 6px;border-radius:9px;border:1px solid rgba(255,255,255,.28);background:rgba(15,23,42,.82);color:#fff;font-size:13px;font-weight:600;text-align:center;" id="btn-sd" type="button">&#128190; SD</button>
  <button style="cursor:pointer !important;pointer-events:auto !important;width:100%;padding:9px 6px;border-radius:9px;border:1px solid rgba(255,255,255,.28);background:rgba(15,23,42,.82);color:#fff;font-size:13px;font-weight:600;text-align:center;" id="btn-fs" type="button">&#9974; &#1042;&#1077;&#1089;&#1100; &#1101;&#1082;&#1088;&#1072;&#1085;</button>
  <button style="cursor:pointer !important;pointer-events:auto !important;width:100%;padding:9px 6px;border-radius:9px;border:1px solid rgba(255,255,255,.28);background:rgba(15,23,42,.82);color:#fff;font-size:13px;font-weight:600;text-align:center;" id="btn-nvr" type="button">&#127902; NVR</button>
  <button onclick="window.showModal('patrol-modal')" style="cursor:pointer !important;pointer-events:auto !important;width:100%;padding:9px 6px;border-radius:9px;border:1px solid rgba(255,255,255,.28);background:rgba(15,23,42,.82);color:#fff;font-size:13px;font-weight:600;text-align:center;" id="btn-patrol-menu" type="button">&#127919; &#1055;&#1072;&#1090;&#1088;&#1091;&#1083;&#1100;</button>
  <button onclick="window.showModal('cam-ext-modal')" style="cursor:pointer !important;pointer-events:auto !important;width:100%;padding:9px 6px;border-radius:9px;border:1px solid rgba(255,255,255,.28);background:rgba(15,23,42,.82);color:#fff;font-size:13px;font-weight:600;text-align:center;" id="btn-cam-ext" type="button">&#9881; &#1050;&#1072;&#1084;&#1077;&#1088;&#1072;</button>
</div>
<div id="ptz-pad" data-pos="1" style="position:fixed;bottom:20px;left:20px;display:grid;grid-template-columns:repeat(3,52px);grid-template-rows:repeat(3,52px);gap:6px;z-index:9999;touch-action:none;user-select:none;-webkit-user-select:none;">
  <div></div>
  <button data-dir="up" style="border-radius:12px;border:1px solid rgba(255,255,255,.35);background:rgba(0,0,0,.55);color:#fff;font-size:20px;">&#9650;</button>
  <div></div>
  <button data-dir="left" style="border-radius:12px;border:1px solid rgba(255,255,255,.35);background:rgba(0,0,0,.55);color:#fff;font-size:20px;">&#9664;</button>
  <button data-dir="stop" style="border-radius:12px;border:1px solid rgba(255,255,255,.35);background:rgba(180,40,40,.6);color:#fff;font-size:13px;">&#9632;</button>
  <button data-dir="right" style="border-radius:12px;border:1px solid rgba(255,255,255,.35);background:rgba(0,0,0,.55);color:#fff;font-size:20px;">&#9654;</button>
  <div></div>
  <button data-dir="down" style="border-radius:12px;border:1px solid rgba(255,255,255,.35);background:rgba(0,0,0,.55);color:#fff;font-size:20px;">&#9660;</button>
  <div></div>
</div>
<script>
(async () => {
  let audio = null, nextT = 0, aCtrl = null;
  const audioButton = document.getElementById("enable-audio");
  function playRawPCM(buf) {
    if (!audio || audio.state !== "running") return;
    const cnt = Math.floor(buf.byteLength / 2);
    if (!cnt) return;
    const ab = audio.createBuffer(1, cnt, 8000);
    const ch = ab.getChannelData(0);
    const i16 = new Int16Array(buf, 0, cnt);
    for (let i = 0; i < cnt; i++) ch.set([i16.at(i) / 32768], i);
    const src = audio.createBufferSource();
    src.buffer = ab;
    src.connect(audio.destination);
    const now = audio.currentTime;
    if (nextT < now || nextT > now + 0.4) nextT = now + 0.06;
    src.start(nextT);
    nextT += ab.duration;
  }
  async function runAudio() {
    aCtrl = new AbortController();
    try {
      const r = await fetch("/audio.pcm", {cache: "no-store", signal: aCtrl.signal});
      const rd = r.body.getReader();
      while (true) {
        const res = await rd.read();
        if (res.done) break;
        const v = res.value;
        playRawPCM(v.buffer.slice(v.byteOffset, v.byteOffset + v.byteLength));
      }
    } catch (e) {}
  }
  if (audioButton) {
    audioButton.onclick = async () => {
      try {
        if (!audio) var AC = window.AudioContext || window.webkitAudioContext; try { audio = new AC({sampleRate: 8000}); } catch(e) { audio = new AC(); }
        if (audio.state === "running") {
          if (aCtrl) { aCtrl.abort(); aCtrl = null; }
          await audio.suspend();
          nextT = 0;
          audioButton.style.background = "";
          audioButton.innerHTML = "&#128263; &#1047;&#1074;&#1091;&#1082;";
        } else {
          await audio.resume();
          nextT = 0;
          audioButton.style.background = "#16a34a";
          audioButton.innerHTML = "&#128266; &#1047;&#1074;&#1091;&#1082;";
          runAudio();
        }
      } catch (e) {}
    };
  }
})();

// &#1057;&#1090;&#1086;&#1088;&#1086;&#1078;&#1077;&#1074;&#1086;&#1081; &#1090;&#1072;&#1081;&#1084;&#1077;&#1088; &#1072;&#1085;&#1090;&#1080;-&#1092;&#1088;&#1080;&#1079;&#1072; &#1074;&#1080;&#1076;&#1077;&#1086;&#1087;&#1086;&#1090;&#1086;&#1082;&#1072; (#mjpg)
(function() {
  var lastSrvSeq = -1, lastMoveTs = Date.now(), lastResetTs = 0;
  var img = document.getElementById("mjpg");
  if (!img) return;
  img.onerror = function() {
    setTimeout(function() { img.src = "/stream.mjpg?r=" + Date.now(); }, 800);
  };
  setInterval(function() {
    if (document.hidden) return;
    fetch("/status", {cache: "no-store"}).then(function(r) { return r.json(); }).then(function(s) {
      if (typeof s.seq === "number" && s.seq !== lastSrvSeq) {
        lastSrvSeq = s.seq;
        lastMoveTs = Date.now();
      }
      var now = Date.now();
      // &#1045;&#1089;&#1083;&#1080; &#1082;&#1072;&#1084;&#1077;&#1088;&#1072; &#1078;&#1080;&#1074;&#1072; (age < 2s), &#1085;&#1086; &#1087;&#1086;&#1090;&#1086;&#1082; &#1074; &#1073;&#1088;&#1072;&#1091;&#1079;&#1077;&#1088;&#1077; &#1087;&#1086;&#1076;&#1074;&#1080;&#1089; > 2.5&#1089; &#8212; &#1084;&#1075;&#1085;&#1086;&#1074;&#1077;&#1085;&#1085;&#1086; &#1087;&#1077;&#1088;&#1077;&#1087;&#1086;&#1076;&#1082;&#1083;&#1102;&#1095;&#1072;&#1077;&#1084; src
      if (s.age !== null && s.age < 2.0 && (now - lastResetTs > 3500)) {
        if (!img.complete || img.naturalWidth === 0 || (now - lastMoveTs > 2500)) {
          lastResetTs = now;
          lastMoveTs = now;
          img.src = "/stream.mjpg?r=" + now;
        }
      }
    }).catch(function() {});
  }, 1500);
})();

(function(){
  fetch("/state", {cache:"no-store"}).then(function(r){return r.json();}).then(function(st){
    if(typeof st.osd === "number"){
      localStorage.setItem("a9_osd", st.osd ? "1" : "0");
      if(window.applyOsd) window.applyOsd(!!st.osd);
    }
    if(typeof st.flip === "number"){
      localStorage.setItem("a9_rot180", st.flip ? "1" : "0");
      var im = document.getElementById("mjpg");
      if(im) im.style.transform = st.flip ? "rotate(180deg)" : "";
    }
    var bIr = document.getElementById("btn-ir");
    if(bIr && typeof st.ir === "number"){
      var irNames = ["&#1048;&#1050;: &#1040;&#1074;&#1090;&#1086;", "&#1048;&#1050;: &#1042;&#1099;&#1082;&#1083;", "&#1048;&#1050;: &#1042;&#1082;&#1083;"];
      bIr.innerHTML = irNames[st.ir] || irNames[0];
    }
    var bRes = document.getElementById("btn-res");
    if(bRes && typeof st.qos === "number"){
      bRes.innerHTML = st.qos ? "&#128250; &#1050;&#1072;&#1095;&#1077;&#1089;&#1090;&#1074;&#1086;: HD" : "&#128250; &#1050;&#1072;&#1095;&#1077;&#1089;&#1090;&#1074;&#1086;: SD";
    }
  }).catch(function(){});
})();

window.toggleFs = function() {
  var el = document.documentElement;
  if (!document.fullscreenElement && !document.webkitFullscreenElement) {
    if (el.requestFullscreen) el.requestFullscreen();
    else if (el.webkitRequestFullscreen) el.webkitRequestFullscreen();
  } else {
    if (document.exitFullscreen) document.exitFullscreen();
    else if (document.webkitExitFullscreen) document.webkitExitFullscreen();
  }
};
</script>
<div id="sd-m" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.8);z-index:10000;align-items:center;justify-content:center;padding:16px;"><div style="background:#1c1e24;color:#fff;border:1px solid #444;border-radius:14px;padding:18px;width:100%;max-width:360px;font-family:sans-serif;"><div style="display:flex;justify-content:space-between;margin-bottom:10px;"><b>&#128190; SD-&#1082;&#1072;&#1088;&#1090;&#1072;</b><span id="sd-x" style="font-size:22px;cursor:pointer;">&times;</span></div><div id="sd-t" style="background:#262932;padding:10px;border-radius:8px;font-size:13px;line-height:1.5;margin-bottom:10px;">&#1054;&#1078;&#1080;&#1076;&#1072;&#1085;&#1080;&#1077;...</div><div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px;"><button id="sd-r" type="button" style="padding:9px;border-radius:8px;border:1px solid #4a90e2;background:#23466e;color:#fff;">&#128260; &#1048;&#1085;&#1092;&#1086;</button><button id="sd-d" type="button" style="padding:9px;border-radius:8px;border:1px solid #4a90e2;background:#23466e;color:#fff;">&#128197; &#1044;&#1085;&#1080;</button><button id="sd-o" type="button" style="padding:9px;border-radius:8px;border:1px solid #2ecc71;background:#1e5631;color:#fff;">&#9210; &#1047;&#1072;&#1087;&#1080;&#1089;&#1100; 30&#1089;</button><button id="sd-s" type="button" style="padding:9px;border-radius:8px;border:1px solid #888;background:#3a3f47;color:#fff;">&#9209; &#1057;&#1090;&#1086;&#1087;</button></div><button id="sd-f" type="button" style="width:100%;padding:9px;border-radius:8px;border:1px solid #e74c3c;background:#6e2323;color:#fff;">&#9888;&#65039; &#1060;&#1086;&#1088;&#1084;&#1072;&#1090;&#1080;&#1088;&#1086;&#1074;&#1072;&#1090;&#1100; SD</button></div></div><script>(()=>{const m=document.getElementById("sd-m"),t=document.getElementById("sd-t"),upd=(p)=>fetch("/sd/info?poll="+(p?1:0),{cache:"no-store"}).then(r=>r.json()).then(d=>{const tot=d.total_mb?(d.total_mb/1024).toFixed(2)+" GB":"-",u=d.used_mb?(d.used_mb/1024).toFixed(2)+" GB":"0 MB",fr=(d.total_mb&&d.total_mb>=d.used_mb)?((d.total_mb-d.used_mb)/1024).toFixed(2)+" GB":"-";t.innerHTML="<b>&#1057;&#1090;&#1072;&#1090;&#1091;&#1089;:</b> "+d.last_msg+"<br><b>&#1042;&#1089;&#1077;&#1075;&#1086;:</b> "+tot+"<br><b>&#1047;&#1072;&#1085;&#1103;&#1090;&#1086; / &#1057;&#1074;&#1086;&#1073;&#1086;&#1076;&#1085;&#1086;:</b> "+u+" / "+fr;});document.getElementById("btn-sd").onclick=()=>{m.style.display="flex";upd(1);setTimeout(()=>upd(0),1200);};document.getElementById("sd-x").onclick=()=>{m.style.display="none";};document.getElementById("sd-r").onclick=()=>{upd(1);setTimeout(()=>upd(0),1200);};document.getElementById("sd-d").onclick=()=>fetch("/sd/days").then(()=>setTimeout(()=>upd(0),1200));document.getElementById("sd-o").onclick=()=>fetch("/sd/record?dur=30").then(()=>setTimeout(()=>upd(0),1000));document.getElementById("sd-s").onclick=()=>fetch("/sd/record?dur=0").then(()=>setTimeout(()=>upd(0),1000));document.getElementById("sd-f").onclick=()=>{if(confirm("&#1060;&#1086;&#1088;&#1084;&#1072;&#1090;&#1080;&#1088;&#1086;&#1074;&#1072;&#1090;&#1100; SD?"))fetch("/sd/format").then(()=>setTimeout(()=>upd(0),1500));};})();</script>
<div id="nvr-m" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.84);z-index:99999;align-items:center;justify-content:center;padding:16px;">
  <div style="background:#1c1e24;color:#fff;border:1px solid #444;border-radius:14px;padding:18px;width:100%;max-width:400px;max-height:85vh;display:flex;flex-direction:column;font-family:sans-serif;">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
      <b>&#127902; NVR &#1040;&#1088;&#1093;&#1080;&#1074;</b>
      <span id="nvr-x" style="font-size:26px;cursor:pointer;padding:0 6px;">&times;</span>
    </div>
    <div style="background:#262932;padding:10px;border-radius:8px;margin-bottom:10px;font-size:12px;">
      <div style="margin-bottom:6px;">&#1055;&#1091;&#1090;&#1100; &#1087;&#1072;&#1087;&#1082;&#1080;: <input id="nvr-dir" style="width:100%;margin-top:3px;padding:6px;border-radius:6px;border:1px solid #555;background:#16181d;color:#fff;box-sizing:border-box;"></div>
      <div style="display:flex;gap:8px;margin-bottom:8px;">
        <div style="flex:1;">&#1056;&#1086;&#1083;&#1080;&#1082; (&#1084;&#1080;&#1085;): <input id="nvr-seg" type="number" style="width:100%;margin-top:3px;padding:6px;border-radius:6px;border:1px solid #555;background:#16181d;color:#fff;box-sizing:border-box;"></div>
        <div style="flex:1;">&#1051;&#1080;&#1084;&#1080;&#1090; (&#1052;&#1041;): <input id="nvr-max" type="number" style="width:100%;margin-top:3px;padding:6px;border-radius:6px;border:1px solid #555;background:#16181d;color:#fff;box-sizing:border-box;"></div>
      </div>
      <button id="nvr-sav" type="button" style="width:100%;padding:7px;border-radius:6px;border:1px solid #4a90e2;background:#23466e;color:#fff;cursor:pointer;">&#128190; &#1057;&#1086;&#1093;&#1088;&#1072;&#1085;&#1080;&#1090;&#1100; &#1074; .env</button>
    </div>
    <div style="display:flex;gap:8px;margin-bottom:10px;">
      <button id="nvr-tog" type="button" style="flex:1;padding:9px;border-radius:8px;border:1px solid #2ecc71;background:#1e5631;color:#fff;cursor:pointer;">REC</button>
      <button id="nvr-ref" type="button" style="padding:9px 14px;border-radius:8px;border:1px solid #4a90e2;background:#23466e;color:#fff;cursor:pointer;">&#128260;</button>
    </div>
    <div id="nvr-list" style="overflow-y:auto;flex:1;background:#262932;border-radius:8px;padding:8px;font-size:13px;"></div>
  </div>
</div>
<div id="hud-stat" style="position:fixed;bottom:14px;left:14px;z-index:9998;pointer-events:none;background:rgba(0,0,0,.65);border:1px solid rgba(255,255,255,.22);border-radius:8px;padding:6px 10px;color:#fff;font-family:monospace;font-size:12px;line-height:1.4;">
  <span id="hud-sig">&#128994; &#1057;&#1080;&#1075;&#1085;&#1072;&#1083;: ...</span> | <span id="hud-fps">0.0 FPS</span> | <span id="hud-kbps">0 Kbit/s</span>
</div>
<script>
(() => {
  const sEl = document.getElementById("hud-sig");
  const fEl = document.getElementById("hud-fps");
  const kEl = document.getElementById("hud-kbps");
  const updHud = () => {
    const t0 = performance.now();
    fetch("/telemetry", {cache: "no-store"})
      .then(r => r.json())
      .then(d => {
        const ping = Math.round(performance.now() - t0);
        fEl.textContent = (d.fps || 0).toFixed(1) + " FPS";
        kEl.textContent = (d.kbps || 0) + " Kbit/s";
        if (!d.fps || d.fps <= 0) {
          sEl.innerHTML = "&#128308; &#1053;&#1077;&#1090; &#1087;&#1086;&#1090;&#1086;&#1082;&#1072;";
        } else if (ping < 90 && d.fps >= 1) {
          sEl.innerHTML = "&#128994; &#1054;&#1090;&#1083;&#1080;&#1095;&#1085;&#1099;&#1081; (" + ping + " ms)";
        } else if (ping < 250 && d.fps > 0) {
          sEl.innerHTML = "&#128993; &#1057;&#1088;&#1077;&#1076;&#1085;&#1080;&#1081; (" + ping + " ms)";
        } else {
          sEl.innerHTML = "&#128308; &#1057;&#1083;&#1072;&#1073;&#1099;&#1081; (" + ping + " ms)";
        }
      })
      .catch(() => { sEl.innerHTML = "&#128308; &#1054;&#1092;&#1092;&#1083;&#1072;&#1081;&#1085;"; });
  };
  setInterval(updHud, 2000);
  updHud();
})();
</script>
<div id="patrol-modal" onclick="if(event.target===this)this.style.setProperty('display','none','important')" style="display:none;pointer-events:auto !important;position:fixed;inset:0;background:rgba(0,0,0,.78);z-index:20000;align-items:center;justify-content:center;padding:12px;"><div style="pointer-events:auto !important;background:#1e293b;border:1px solid #334155;border-radius:14px;padding:14px;width:100%;max-width:420px;color:#f8fafc;"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;"><span style="font-size:16px;font-weight:bold;color:#38bdf8;">&#127919; &#1055;&#1072;&#1090;&#1088;&#1091;&#1083;&#1100;</span><button type="button" onclick="document.getElementById('patrol-modal').style.setProperty('display','none','important')" style="pointer-events:auto !important;cursor:pointer !important;background:none;border:none;color:#94a3b8;font-size:20px;">&#10005;</button></div><div style="background:#0f172a;border:1px solid #334155;border-radius:10px;padding:9px;margin-bottom:8px;"><div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:6px;"><button id="pat-on-btn" type="button" onclick="fetch('/cam/ext?act=patrol&on=1');setTimeout(window.syncUiState,250)" style="pointer-events:auto !important;cursor:pointer !important;padding:8px;border:none;border-radius:8px;background:#16a34a;color:#fff;font-weight:bold;">&#9654; &#1042;&#1082;&#1083;&#1102;&#1095;&#1080;&#1090;&#1100;</button><button id="pat-off-btn" type="button" onclick="fetch('/cam/ext?act=patrol&on=0');setTimeout(window.syncUiState,250)" style="pointer-events:auto !important;cursor:pointer !important;padding:8px;border:none;border-radius:8px;background:#dc2626;color:#fff;font-weight:bold;">&#9209; &#1054;&#1089;&#1090;&#1072;&#1085;&#1086;&#1074;&#1080;&#1090;&#1100;</button></div><div style="display:grid;grid-template-columns:repeat(4,1fr);gap:6px;"><button id="pat-sec-10" type="button" onclick="fetch('/cam/ext?act=patrol&on=1&sec=10');setTimeout(window.syncUiState,250)" style="pointer-events:auto !important;cursor:pointer !important;padding:6px;border:none;border-radius:7px;background:#334155;color:#fff;font-size:12px;">10&#1089;</button><button id="pat-sec-15" type="button" onclick="fetch('/cam/ext?act=patrol&on=1&sec=15');setTimeout(window.syncUiState,250)" style="pointer-events:auto !important;cursor:pointer !important;padding:6px;border:none;border-radius:7px;background:#334155;color:#fff;font-size:12px;">15&#1089;</button><button id="pat-sec-25" type="button" onclick="fetch('/cam/ext?act=patrol&on=1&sec=25');setTimeout(window.syncUiState,250)" style="pointer-events:auto !important;cursor:pointer !important;padding:6px;border:none;border-radius:7px;background:#334155;color:#fff;font-size:12px;">25&#1089;</button><button id="pat-sec-45" type="button" onclick="fetch('/cam/ext?act=patrol&on=1&sec=45');setTimeout(window.syncUiState,250)" style="pointer-events:auto !important;cursor:pointer !important;padding:6px;border:none;border-radius:7px;background:#334155;color:#fff;font-size:12px;">45&#1089;</button></div></div><div style="background:#0f172a;border:1px solid #334155;border-radius:10px;padding:9px;margin-bottom:8px;"><div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:6px;"><button type="button" onclick="fetch('/cam/ext?act=ptz_cal')" style="pointer-events:auto !important;cursor:pointer !important;padding:8px;border:none;border-radius:8px;background:#475569;color:#fff;font-size:12px;">&#127919; 1-&#1050;&#1072;&#1083;&#1080;&#1073;&#1088;&#1086;&#1074;&#1082;&#1072; (0,0)</button><button id="ptz-park-btn" type="button" onclick="fetch('/cam/ext?act=ptz_park');setTimeout(window.syncUiState,250)" style="pointer-events:auto !important;cursor:pointer !important;padding:8px;border:none;border-radius:8px;background:#0f766e;color:#fff;font-size:12px;">&#127968; &#1053;&#1072; &#1087;&#1072;&#1088;&#1082;&#1086;&#1074;&#1082;&#1091;</button></div><button type="button" onclick="fetch('/cam/ext?act=ptz_home_set');setTimeout(window.syncUiState,250)" style="pointer-events:auto !important;cursor:pointer !important;width:100%;padding:8px;border:none;border-radius:8px;background:#1e3a8a;color:#fff;font-size:12px;">&#128190; &#1047;&#1072;&#1087;&#1086;&#1084;&#1085;&#1080;&#1090;&#1100; &#1087;&#1072;&#1088;&#1082;&#1086;&#1074;&#1082;&#1091;</button></div><div style="background:#0f172a;border:1px solid #334155;border-radius:10px;padding:9px;display:grid;grid-template-columns:repeat(3,1fr);gap:6px;"><div style="display:flex;"><button id="ptz-t-1" type="button" onclick="fetch('/cam/ext?act=psp_call&id=1')" style="pointer-events:auto !important;cursor:pointer !important;flex:1;padding:7px;border:none;border-radius:7px 0 0 7px;background:#1d4ed8;color:#fff;font-weight:bold;">T1</button><button type="button" onclick="fetch('/cam/ext?act=psp_add&id=1');setTimeout(window.syncUiState,250)" style="pointer-events:auto !important;cursor:pointer !important;padding:7px 9px;border:none;border-radius:0 7px 7px 0;background:#334155;color:#fff;">&#128190;</button></div><div style="display:flex;"><button id="ptz-t-2" type="button" onclick="fetch('/cam/ext?act=psp_call&id=2')" style="pointer-events:auto !important;cursor:pointer !important;flex:1;padding:7px;border:none;border-radius:7px 0 0 7px;background:#1d4ed8;color:#fff;font-weight:bold;">T2</button><button type="button" onclick="fetch('/cam/ext?act=psp_add&id=2');setTimeout(window.syncUiState,250)" style="pointer-events:auto !important;cursor:pointer !important;padding:7px 9px;border:none;border-radius:0 7px 7px 0;background:#334155;color:#fff;">&#128190;</button></div><div style="display:flex;"><button id="ptz-t-3" type="button" onclick="fetch('/cam/ext?act=psp_call&id=3')" style="pointer-events:auto !important;cursor:pointer !important;flex:1;padding:7px;border:none;border-radius:7px 0 0 7px;background:#1d4ed8;color:#fff;font-weight:bold;">T3</button><button type="button" onclick="fetch('/cam/ext?act=psp_add&id=3');setTimeout(window.syncUiState,250)" style="pointer-events:auto !important;cursor:pointer !important;padding:7px 9px;border:none;border-radius:0 7px 7px 0;background:#334155;color:#fff;">&#128190;</button></div><div style="display:flex;"><button id="ptz-t-4" type="button" onclick="fetch('/cam/ext?act=psp_call&id=4')" style="pointer-events:auto !important;cursor:pointer !important;flex:1;padding:7px;border:none;border-radius:7px 0 0 7px;background:#1d4ed8;color:#fff;font-weight:bold;">T4</button><button type="button" onclick="fetch('/cam/ext?act=psp_add&id=4');setTimeout(window.syncUiState,250)" style="pointer-events:auto !important;cursor:pointer !important;padding:7px 9px;border:none;border-radius:0 7px 7px 0;background:#334155;color:#fff;">&#128190;</button></div><div style="display:flex;"><button id="ptz-t-5" type="button" onclick="fetch('/cam/ext?act=psp_call&id=5')" style="pointer-events:auto !important;cursor:pointer !important;flex:1;padding:7px;border:none;border-radius:7px 0 0 7px;background:#1d4ed8;color:#fff;font-weight:bold;">T5</button><button type="button" onclick="fetch('/cam/ext?act=psp_add&id=5');setTimeout(window.syncUiState,250)" style="pointer-events:auto !important;cursor:pointer !important;padding:7px 9px;border:none;border-radius:0 7px 7px 0;background:#334155;color:#fff;">&#128190;</button></div><div style="display:flex;"><button id="ptz-t-6" type="button" onclick="fetch('/cam/ext?act=psp_call&id=6')" style="pointer-events:auto !important;cursor:pointer !important;flex:1;padding:7px;border:none;border-radius:7px 0 0 7px;background:#1d4ed8;color:#fff;font-weight:bold;">T6</button><button type="button" onclick="fetch('/cam/ext?act=psp_add&id=6');setTimeout(window.syncUiState,250)" style="pointer-events:auto !important;cursor:pointer !important;padding:7px 9px;border:none;border-radius:0 7px 7px 0;background:#334155;color:#fff;">&#128190;</button></div></div></div></div>
<div id="cam-ext-modal"  style="display:none;pointer-events:auto !important;position:fixed;inset:0;background:rgba(0,0,0,.8);z-index:99999 !important;align-items:center;justify-content:center;padding:12px;">
<div id="cam-ext-box" style="pointer-events:auto !important;background:#1e293b;color:#fff;border:1px solid #475569;border-radius:12px;padding:14px;width:100%;max-width:360px;font-family:sans-serif;font-size:13px;">
<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;"><b>&#9881; &#1050;&#1072;&#1084;&#1077;&#1088;&#1072; <span id="ce-st" style="color:#4ade80;font-weight:normal;margin-left:6px;"></span></b><button type="button" onclick="document.getElementById('cam-ext-modal').style.display='none'" style="pointer-events:auto !important;background:none;border:none;color:#94a3b8;font-size:20px;cursor:pointer;">&#10005;</button></div>
<div style="margin-bottom:10px;padding:8px;background:#0f172a;border-radius:8px;">
  
</div>
<div style="margin-bottom:8px;padding:8px;background:#0f172a;border-radius:8px;display:flex;justify-content:space-between;align-items:center;">
  <span>&#9889; &#1040;&#1085;&#1090;&#1080;&#1084;&#1077;&#1088;&#1094;&#1072;&#1085;&#1080;&#1077;:</span>
  <div>
    <button type="button" style="pointer-events:auto !important;padding:7px 10px;border:none;border-radius:7px;color:#fff;font-size:13px;cursor:pointer;background:#0284c7;" onclick="camExt('freq',{hz:50})">50 &#1043;&#1094;</button>
    <button type="button" style="pointer-events:auto !important;padding:7px 10px;border:none;border-radius:7px;color:#fff;font-size:13px;cursor:pointer;background:#334155;" onclick="camExt('freq',{hz:60})">60 &#1043;&#1094;</button>
  </div>
</div>
<div style="margin-bottom:8px;padding:8px;background:#0f172a;border-radius:8px;display:flex;justify-content:space-between;align-items:center;">
  <span>&#128338; &#1042;&#1088;&#1077;&#1084;&#1103; OSD:</span>
  <div>
    <button type="button" style="pointer-events:auto !important;padding:7px 10px;border:none;border-radius:7px;color:#fff;font-size:13px;cursor:pointer;background:#16a34a;" onclick="camExt('osd',{enable:1})">&#1042;&#1082;&#1083;</button>
    <button type="button" style="pointer-events:auto !important;padding:7px 10px;border:none;border-radius:7px;color:#fff;font-size:13px;cursor:pointer;background:#475569;" onclick="camExt('osd',{enable:0})">&#1042;&#1099;&#1082;&#1083;</button>
  </div>
</div>
<div style="margin:8px 0;padding:10px;background:#0f172a;border:1px solid #334155;border-radius:10px;">
  <div style="margin:8px 0;padding:10px;background:#0f172a;border:1px solid #334155;border-radius:10px;"><div style="font-size:13px;font-weight:bold;color:#38bdf8;margin-bottom:8px;">&#9881; &#1053;&#1072;&#1089;&#1090;&#1088;&#1086;&#1081;&#1082;&#1080; &#1080;&#1079;&#1086;&#1073;&#1088;&#1072;&#1078;&#1077;&#1085;&#1080;&#1103; &#1080; &#1076;&#1072;&#1090;&#1095;&#1080;&#1082;&#1086;&#1074;</div><div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;"><button id="btn-ir" type="button" onclick="uiIr(this)" style="pointer-events:auto;padding:8px 12px;border-radius:8px;border:1px solid rgba(255,255,255,.3);background:rgba(0,0,0,.6);color:#fff;font-size:14px;">&#127769; &#1048;&#1050;: &#1040;&#1074;&#1090;&#1086;</button><button id="btn-res" type="button" onclick="uiRes(this)" style="pointer-events:auto;padding:8px 12px;border-radius:8px;border:1px solid rgba(255,255,255,.3);background:rgba(0,0,0,.6);color:#fff;font-size:14px;">&#128250; &#1050;&#1072;&#1095;&#1077;&#1089;&#1090;&#1074;&#1086;: SD</button><button id="btn-flip" type="button" onclick="uiFlip(this)" style="pointer-events:auto;padding:8px 12px;border-radius:8px;border:1px solid rgba(255,255,255,.3);background:rgba(0,0,0,.6);color:#fff;font-size:14px;">&#128260; &#1053;&#1086;&#1088;&#1084;&#1072;&#1083;&#1100;&#1085;&#1099;&#1081;</button>
<button id="btn-mot" type="button" style="pointer-events:auto;padding:8px 12px;border-radius:8px;border:1px solid rgba(255,255,255,.3);background:rgba(0,0,0,.6);color:#fff;font-size:14px;">&#128680; &#1044;&#1074;&#1080;&#1078;&#1077;&#1085;&#1080;&#1077;: &#1042;&#1099;&#1082;&#1083;</button></div></div>
<div id="wifi-scan-box" style="margin-bottom:10px;padding:10px;background:#0f172a;border:1px solid #334155;border-radius:8px;">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
    <b style="font-size:13px;color:#38bdf8;">&#128246; Wi-Fi &#1082;&#1072;&#1084;&#1077;&#1088;&#1099;</b>
    <button id="btn-wscan" type="button" style="pointer-events:auto !important;padding:5px 10px;border:none;border-radius:6px;background:#0284c7;color:#fff;font-size:12px;font-weight:bold;cursor:pointer;" onclick="scanCamWifi()">&#128260; &#1057;&#1082;&#1072;&#1085;&#1080;&#1088;&#1086;&#1074;&#1072;&#1090;&#1100;</button>
  </div>
  <div id="wscan-cur" style="font-size:12px;color:#cbd5e1;margin-bottom:6px;">&#1058;&#1077;&#1082;&#1091;&#1097;&#1072;&#1103; &#1089;&#1077;&#1090;&#1100;: <b>&mdash;</b></div>
  <div id="wscan-list" style="pointer-events:auto !important;max-height:130px;overflow-y:auto;background:#1e293b;border-radius:6px;padding:4px;font-size:12px;color:#cbd5e1;">&#1053;&#1072;&#1078;&#1084;&#1080;&#1090;&#1077; &laquo;&#1057;&#1082;&#1072;&#1085;&#1080;&#1088;&#1086;&#1074;&#1072;&#1090;&#1100;&raquo;</div>
</div>
<script>
window.renderCamWifi = function(d) {
  var cur = document.getElementById("wscan-cur");
  var lst = document.getElementById("wscan-list");
  if (cur && d) cur.innerHTML = "&#1058;&#1077;&#1082;&#1091;&#1097;&#1072;&#1103; &#1089;&#1077;&#1090;&#1100;: <b style='color:#4ade80;'>" + (d.cur || "&mdash;") + "</b>";
  if (!lst || !d) return;
  if (!d.aps || !d.aps.length) {
    lst.innerHTML = "<div style='color:#94a3b8;padding:6px;'>&#1057;&#1077;&#1090;&#1080; &#1085;&#1077; &#1085;&#1072;&#1081;&#1076;&#1077;&#1085;&#1099;</div>";
    return;
  }
  lst.innerHTML = d.aps.map(function(a) {
    var s = String(a.ssid || "").replace(/</g, "&lt;");
    return "<div style='padding:6px 8px;border-bottom:1px solid #0f172a;display:flex;justify-content:space-between;'><span>&#128246; " + s + "</span><span style='color:#38bdf8;'>" + (a.sig ? a.sig + "%" : "") + "</span></div>";
  }).join("");
};
window.scanCamWifi = function() {
  var lst = document.getElementById("wscan-list");
  if (lst) lst.innerHTML = "<div style='color:#38bdf8;padding:6px;'>&#1057;&#1082;&#1072;&#1085;&#1080;&#1088;&#1086;&#1074;&#1072;&#1085;&#1080;&#1077; &#1101;&#1092;&#1080;&#1088;&#1072;...</div>";
  fetch("/wifi/scan?poll=1", {cache: "no-store"}).then(function(r){ return r.json(); }).then(window.renderCamWifi).catch(function(){});
  setTimeout(function() {
    fetch("/wifi/scan?poll=0", {cache: "no-store"}).then(function(r){ return r.json(); }).then(window.renderCamWifi).catch(function(){});
  }, 1500);
  setTimeout(function() {
    fetch("/wifi/scan?poll=0", {cache: "no-store"}).then(function(r){ return r.json(); }).then(window.renderCamWifi).catch(function(){});
  }, 3200);
};
setTimeout(function() {
  fetch("/wifi/scan?poll=0", {cache: "no-store"}).then(function(r){ return r.json(); }).then(window.renderCamWifi).catch(function(){});
}, 1200);
</script>
<button type="button" style="pointer-events:auto !important;padding:7px 10px;border:none;border-radius:7px;color:#fff;font-size:13px;cursor:pointer;width:100%;padding:9px;background:#dc2626;font-weight:bold;" onclick="if(confirm('&#1055;&#1077;&#1088;&#1077;&#1079;&#1072;&#1075;&#1088;&#1091;&#1079;&#1080;&#1090;&#1100; &#1082;&#1072;&#1084;&#1077;&#1088;&#1091;?'))camExt('reboot',{})">&#128260; &#1055;&#1077;&#1088;&#1077;&#1079;&#1072;&#1075;&#1088;&#1091;&#1079;&#1080;&#1090;&#1100; &#1082;&#1072;&#1084;&#1077;&#1088;&#1091;</button></div></div><script>
window.applyOsd = function(on) {
  var oc = document.getElementById("osd-clk");
  if (!oc) return;
  oc.style.display = on ? "block" : "none";
  if (on) {
    var tick = function() {
      var d = new Date();
      oc.textContent = d.toLocaleDateString("ru-RU") + " " + d.toLocaleTimeString("ru-RU");
    };
    tick();
    if (!window._ot) window._ot = setInterval(tick, 1000);
  } else if (window._ot) {
    clearInterval(window._ot);
    window._ot = null;
  }
};
window.addEventListener("DOMContentLoaded", function(){ window.applyOsd(localStorage.getItem("a9_osd") === "1"); });
setTimeout(function(){ window.applyOsd(localStorage.getItem("a9_osd") === "1"); }, 100);
window._unusedOsd = function(on) {
  var oc = document.getElementById("osd-clk");
  if (!oc) return;
  oc.style.display = on ? "block" : "none";
  if (on) {
    oc.textContent = new Date().toLocaleString("ru-RU");
    if (!window._ot) window._ot = setInterval(function() { oc.textContent = new Date().toLocaleString("ru-RU"); }, 1000);
  }
};
window.applyOsd(localStorage.getItem("a9_osd") === "1");
window.camExt = function(a, e) {
  var q = new URLSearchParams(Object.assign({act: a}, e || {})).toString();
  var st = document.getElementById("ce-st"); if (st) st.textContent = "...";
  fetch("/cam/ext?" + q, {cache: "no-store"}).then(function(r) { return r.json(); }).then(function() {
    if (st) st.textContent = "OK: " + a;
    if (a === "osd") { var _on = Boolean(e && Number(e.enable)); localStorage.setItem("a9_osd", _on ? "1" : "0"); if (window.applyOsd) window.applyOsd(_on);
      localStorage.setItem("a9_osd", e && e.enable ? "1" : "0");
      window.applyOsd(!!(e && e.enable));
    }
    if (a === "reboot" || a === "wifi") document.getElementById("cam-ext-modal").style.display = "none";
  }).catch(function() { if (st) st.textContent = "Err"; });
};

(function() {
  window._sndOn = false; window._audio = null; window._aCtrl = null; window._nextT = 0;
  var abtn = document.getElementById("enable-audio");
  function playPCM(buf) {
    if (!window._sndOn || !window._audio) return;
    var cnt = Math.floor(buf.byteLength / 2); if (!cnt) return;
    var ab = window._audio.createBuffer(1, cnt, 8000);
    ab.copyToChannel(Float32Array.from(new Int16Array(buf, 0, cnt), function(v) { return v / 32768; }), 0);
    var src = window._audio.createBufferSource(); src.buffer = ab; src.connect(window._audio.destination);
    var now = window._audio.currentTime; if (window._nextT < now || window._nextT > now + 0.35) window._nextT = now + 0.05;
    src.start(window._nextT); window._nextT += ab.duration;
  }
  async function startAudio() {
    window._aCtrl = new AbortController();
    try {
      var r = await fetch("/audio.pcm", {cache: "no-store", signal: window._aCtrl.signal});
      var rd = r.body.getReader();
      while (window._sndOn) { var res = await rd.read(); if (res.done || !window._sndOn) break; playPCM(res.value.buffer.slice(res.value.byteOffset, res.value.byteOffset + res.value.byteLength)); }
    } catch (e) {}
  }
  if (abtn) {
    abtn.innerHTML = "&#128263; &#1047;&#1074;&#1091;&#1082;";
    abtn.onclick = async function(e) {
      e.stopPropagation();
      if (window._sndOn) {
        window._sndOn = false;
        if (window._aCtrl) { try { window._aCtrl.abort(); } catch(_) {} window._aCtrl = null; }
        if (window._audio) { try { await window._audio.close(); } catch(_) {} window._audio = null; }
        abtn.style.background = "rgba(0,0,0,.6)"; abtn.innerHTML = "&#128263; &#1047;&#1074;&#1091;&#1082;";
      } else {
        var AC = window.AudioContext || window.webkitAudioContext;
        try { window._audio = new AC({sampleRate: 8000}); } catch(_) { window._audio = new AC(); }
        await window._audio.resume(); window._sndOn = true; window._nextT = 0;
        abtn.style.background = "#16a34a"; abtn.innerHTML = "&#128266; &#1047;&#1074;&#1091;&#1082;";
        startAudio();
      }
    };
  }
})();
</script>
<script>
window._irI = 0; window._irL = Array.of("&#127769; &#1048;&#1050;: &#1040;&#1074;&#1090;&#1086;", "&#9728;&#65039; &#1048;&#1050;: &#1042;&#1099;&#1082;&#1083;", "&#127761; &#1048;&#1050;: &#1042;&#1082;&#1083;");
window.uiIr = function(b) { window._irI = (window._irI + 1) % 3; b.innerHTML = window._irL.at(window._irI); fetch("/ctrl?act=ir&val=" + window._irI, {cache: "no-store"}).catch(function(){}); };
window._hd = false;
window.uiRes = function(b) { window._hd = !window._hd; b.innerHTML = window._hd ? "&#128250; &#1050;&#1072;&#1095;&#1077;&#1089;&#1090;&#1074;&#1086;: HD" : "&#128250; &#1050;&#1072;&#1095;&#1077;&#1089;&#1090;&#1074;&#1086;: SD"; fetch("/ctrl?act=res&val=" + (window._hd ? 1 : 0), {cache: "no-store"}).catch(function(){}); };
window._flI = parseInt(localStorage.getItem("a9_flip") || "0", 10) || 0;
window._flL = Array.of("&#128260; &#1053;&#1086;&#1088;&#1084;&#1072;&#1083;&#1100;&#1085;&#1099;&#1081;", "&#128260; &#1055;&#1086;&#1074;&#1086;&#1088;&#1086;&#1090; 180&#176;", "&#8596; &#1047;&#1077;&#1088;&#1082;&#1072;&#1083;&#1086; &#1043;", "&#8597; &#1047;&#1077;&#1088;&#1082;&#1072;&#1083;&#1086; &#1042;");
window._flT = Array.of("none", "rotate(180deg)", "scaleX(-1)", "scaleY(-1)");
window.applyFlip = function(idx) { var im = document.getElementById("mjpg"), b = document.getElementById("btn-flip"); if (im) im.style.transform = window._flT.at(idx) || "none"; if (b) b.innerHTML = window._flL.at(idx); };
window.uiFlip = function(b) { window._flI = (window._flI + 1) % 4; localStorage.setItem("a9_flip", String(window._flI)); window.applyFlip(window._flI); };
window.applyFlip(window._flI);

(function() {
  var mm = Array.of({l:"&#128680; &#1044;&#1074;&#1080;&#1078;&#1077;&#1085;&#1080;&#1077;: &#1042;&#1099;&#1082;&#1083;",v:0,bg:"rgba(0,0,0,.6)"},{l:"&#128680; &#1044;&#1074;&#1080;&#1078;: &#1053;&#1080;&#1079;&#1082;",v:1,bg:"rgba(210,160,20,.85)"},{l:"&#128680; &#1044;&#1074;&#1080;&#1078;: &#1057;&#1088;&#1077;&#1076;",v:2,bg:"rgba(230,110,20,.85)"},{l:"&#128680; &#1044;&#1074;&#1080;&#1078;: &#1042;&#1099;&#1089;&#1086;&#1082;",v:3,bg:"rgba(210,40,40,.85)"});
  var mi = 0, bm = document.getElementById("btn-mot");
  if (bm) bm.onclick = function() { mi = (mi + 1) % mm.length; var cur = mm.at(mi); fetch("/ctrl?act=motion&val=" + cur.v, {cache: "no-store"}).catch(function(){}); bm.innerHTML = cur.l; bm.style.background = cur.bg; };

  var nm = document.getElementById("nvr-m"), bNvr = 
document.getElementById("btn-nvr"), xNvr = document.getElementById("nvr-x"), dIn = document.getElementById("nvr-dir"), sIn = document.getElementById("nvr-seg"), mIn = document.getElementById("nvr-max"), lst = document.getElementById("nvr-list"), tog = document.getElementById("nvr-tog"), sav = document.getElementById("nvr-sav"), ref = document.getElementById("nvr-ref");
  var ldNvr = function() {
    fetch("/nvr/list", {cache: "no-store"}).then(function(r) { return r.json(); }).then(function(d) {
      if (dIn) dIn.value = d.dir || ""; if (sIn) sIn.value = d.seg || 10; if (mIn) mIn.value = d.max || 5120;
      if (tog) { tog.textContent = d.enabled ? "REC: ON (Stop)" : "REC: OFF (Start)"; tog.style.background = d.enabled ? "#1e5631" : "#6e2323"; }
      if (lst) lst.innerHTML = (d.files && d.files.length) ? d.files.map(function(f) { return "<div style='display:flex;justify-content:space-between;padding:6px;border-bottom:1px solid #333'><span>" + (f.active ? "&#128308; " : "") + (f.dt ? ((f.name && f.name.indexOf("motion_") === 0 ? "&#128680; " : "&#127909; ") + f.dt) : f.name) + " (" + f.size_mb + " MB)</span><a href='/nvr/file?name=" + encodeURIComponent(f.name) + "' style='color:#4da3ff;text-decoration:none;font-weight:bold'>&#11015; AVI</a></div>"; }).join("") : "<div style='color:#888;padding:8px'>&#1047;&#1072;&#1087;&#1080;&#1089;&#1077;&#1081; &#1087;&#1086;&#1082;&#1072; &#1085;&#1077;&#1090;</div>";
    }).catch(function(){});
  };
  if (bNvr && nm) bNvr.onclick = function() { nm.style.display = "flex"; ldNvr(); };
  if (xNvr && nm) xNvr.onclick = function() { nm.style.display = "none"; };
  if (tog) tog.onclick = function() { fetch("/nvr/toggle", {cache: "no-store"}).then(ldNvr).catch(function(){}); };
  if (ref) ref.onclick = ldNvr;
  if (sav) sav.onclick = function() { fetch("/nvr/save?dir=" + encodeURIComponent(dIn.value) + "&seg=" + encodeURIComponent(sIn.value) + "&max=" + encodeURIComponent(mIn.value), {cache: "no-store"}).then(ldNvr).catch(function(){}); };

  var pad = document.getElementById("ptz-pad");
  if (pad) {
    var activeDir = null, sendPtz = function(dir) { fetch("/ctrl?act=" + dir, {cache: "no-store"}).catch(function(){}); };
    pad.querySelectorAll("button[data-dir]").forEach(function(btn) {
      var dir = btn.getAttribute("data-dir");
      var start = function(e) { if (e.cancelable) e.preventDefault(); if (dir === "stop") { activeDir = null; sendPtz("stop"); return; } if (activeDir === dir) return; activeDir = dir; sendPtz(dir); };
      var stop = function(e) { if (e && e.cancelable) e.preventDefault(); if (activeDir && dir !== "stop") { activeDir = null; sendPtz("stop"); } };
      btn.addEventListener("pointerdown", start); btn.addEventListener("pointerup", stop); btn.addEventListener("pointercancel", stop);
      btn.addEventListener("touchstart", start, {passive: false}); btn.addEventListener("touchend", stop);
    });
  }

  setInterval(function() {
    var t0 = performance.now();
    fetch("/telemetry", {cache: "no-store"}).then(function(r) { return r.json(); }).then(function(d) {
      var ms = Math.round(performance.now() - t0);
      var q = ms < 60 ? "&#1054;&#1090;&#1083;&#1080;&#1095;&#1085;&#1099;&#1081;" : (ms < 180 ? "&#1057;&#1088;&#1077;&#1076;&#1085;&#1080;&#1081;" : "&#1057;&#1083;&#1072;&#1073;&#1099;&#1081;");
      var dot = ms < 60 ? "#4ade80" : (ms < 180 ? "#facc15" : "#f87171");
      var st = document.getElementById("hud-stat");
      if (st) st.innerHTML = '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:' + dot + ';margin-right:6px;"></span>' + q + ' (' + ms + ' ms) | ' + (d.fps || 0) + ' FPS | ' + (d.kbps || 0) + ' Kbit/s';
      var rb = document.getElementById("rec-badge");
      if (rb) rb.style.display = d.rec ? "flex" : "none";
    }).catch(function(){});
  }, 1000);
})();
</script>
<div id="rec-badge" style="display:none;position:fixed;top:14px;right:14px;z-index:9999;background:rgba(15,23,42,0.82);color:#fca5a5;border:1px solid rgba(239,68,68,0.65);padding:4px 10px;border-radius:7px;font:700 12px/1.2 system-ui,sans-serif;letter-spacing:0.6px;pointer-events:none;align-items:center;"><span style="display:inline-block;width:9px;height:9px;border-radius:50%;background:#ef4444;margin-right:6px;box-shadow:0 0 8px #ef4444;"></span>REC</div>
<div id="osd-clk" style="display:none;position:fixed;bottom:52px;left:14px;z-index:9998;color:#fff;background:rgba(0,0,0,.65);border:1px solid rgba(255,255,255,.25);padding:4px 9px;border-radius:6px;font-family:monospace;font-size:13px;font-weight:bold;pointer-events:none;"></div>

<style>
body.fs-active { overflow: hidden !important; background: #000 !important; }
body.fs-active #mjpg {
  position: fixed !important; inset: 0 !important; width: 100vw !important; height: 100vh !important;
  max-height: 100vh !important; object-fit: contain !important; background: #000 !important; z-index: 9990 !important;
}
#fs-exit-btn {
  display: none; position: fixed; top: 14px; right: 14px; z-index: 9999;
  background: rgba(15,23,42,.82); color: #fff; border: 1px solid #475569;
  border-radius: 10px; padding: 8px 14px; font-size: 14px; font-weight: bold;
}
body.fs-active #fs-exit-btn { display: block !important; }
</style>
<button type="button" id="fs-exit-btn" onclick="toggleFs()">&#10005; &#1042;&#1099;&#1093;&#1086;&#1076;</button>









<script>
(function() {
  function openOnly(id) {
    var ids = ["patrol-modal", "cam-ext-modal", "nvr-modal", "sd-modal"];
    for (var i = 0; i < ids.length; i++) {
      var el = document.getElementById(ids[i]);
      if (el) el.style.setProperty("display", ids[i] === id ? "flex" : "none", "important");
    }
  }
  window.showModal = openOnly;
  window.pExt = function(act, obj) {
    var q = ["act=" + encodeURIComponent(act)];
    if (obj) {
      for (var k in obj) {
        if (Object.prototype.hasOwnProperty.call(obj, k)) {
          q.push(encodeURIComponent(k) + "=" + encodeURIComponent(obj[k]));
        }
      }
    }
    fetch("/cam/ext?" + q.join("&"), {cache: "no-store"}).catch(function(){});
  };
  var bPat = document.getElementById("btn-patrol-menu");
  if (bPat) bPat.onclick = function() { openOnly("patrol-modal"); };
  var bCam = document.getElementById("btn-cam-ext");
  if (bCam) bCam.onclick = function() { openOnly("cam-ext-modal"); };
  var bFs = document.getElementById("btn-fs");
  var bFsX = document.getElementById("fs-exit-btn");
  var togFs = function() {
    var on = !document.body.classList.contains("fs-active");
    document.body.classList.toggle("fs-active", on);
    var el = document.documentElement;
    try {
      if (on && el.requestFullscreen) el.requestFullscreen().catch(function(){});
      else if (!on && document.fullscreenElement && document.exitFullscreen) document.exitFullscreen().catch(function(){});
    } catch(e) {}
  };
  if (bFs) bFs.onclick = togFs;
  if (bFsX) bFsX.onclick = togFs;
})();
</script>




<script>
(function() {
  var stCache = {osd: 1, freq: 50, flip: 0, patrol: 0, patrol_sec: 15, pts: ""};
  function p2(n) { return n < 10 ? "0" + n : "" + n; }
  function fmtNow() { var d = new Date(); return p2(d.getDate())+"."+p2(d.getMonth()+1)+"."+d.getFullYear()+" "+p2(d.getHours())+":"+p2(d.getMinutes())+":"+p2(d.getSeconds()); }
  

  setInterval(function() {
    var b = document.getElementById("live-osd-badge");
    if (!b) return;
    if (stCache.osd === 0) { b.style.setProperty("display", "none", "important"); return; }
    var d = new Date();
    b.textContent = p2(d.getDate()) + "." + p2(d.getMonth() + 1) + "." + d.getFullYear() + " " +
                    p2(d.getHours()) + ":" + p2(d.getMinutes()) + ":" + p2(d.getSeconds());
    var im = document.getElementById("mjpg");
    var isFs = document.body.classList.contains("fs-active");
    var vx = 10, vy = isFs ? 14 : 245;
    if (im && im.clientWidth > 100 && im.clientHeight > 100) {
      var nw = im.naturalWidth || 640, nh = im.naturalHeight || 480;
      var sc = Math.min(im.clientWidth / nw, im.clientHeight / nh);
      var vw = nw * sc, vh = nh * sc;
      vx = Math.max(10, Math.round((im.clientWidth - vw) / 2) + 10);
      vy = Math.max(isFs ? 14 : 112, Math.round((im.clientHeight - vh) / 2) + 10);
    }
    b.style.setProperty("display", "block", "important");
    b.style.left = vx + "px";
    b.style.top = vy + "px";
    b.style.zIndex = "9500";
  }, 300);

  var mapSt = {
    "OK: osd": "&#10003; &#1042;&#1088;&#1077;&#1084;&#1103; OSD &#1086;&#1073;&#1085;&#1086;&#1074;&#1083;&#1077;&#1085;&#1086;",
    "OK: freq": "&#10003; &#1040;&#1085;&#1090;&#1080;&#1084;&#1077;&#1088;&#1094;&#1072;&#1085;&#1080;&#1077; (50/60 &#1043;&#1094;) &#1087;&#1088;&#1080;&#1084;&#1077;&#1085;&#1077;&#1085;&#1086;",
    "OK: flip": "&#10003; &#1055;&#1086;&#1074;&#1086;&#1088;&#1086;&#1090; 180&#176; &#1087;&#1088;&#1080;&#1084;&#1077;&#1085;&#1105;&#1085;",
    "OK: ir": "&#10003; &#1056;&#1077;&#1078;&#1080;&#1084; &#1048;&#1050; &#1080;&#1079;&#1084;&#1077;&#1085;&#1105;&#1085;",
    "OK: res": "&#10003; &#1050;&#1072;&#1095;&#1077;&#1089;&#1090;&#1074;&#1086; &#1087;&#1077;&#1088;&#1077;&#1082;&#1083;&#1102;&#1095;&#1077;&#1085;&#1086;",
    "OK: motion": "&#10003; &#1044;&#1072;&#1090;&#1095;&#1080;&#1082; &#1076;&#1074;&#1080;&#1078;&#1077;&#1085;&#1080;&#1103; &#1086;&#1073;&#1085;&#1086;&#1074;&#1083;&#1105;&#1085;"
  };

  setInterval(function() {
    var m = document.getElementById("cam-ext-modal");
    if (!m || m.style.display === "none") return;
    var spans = m.querySelectorAll("span, div, b");
    for (var i = 0; i < spans.length; i++) {
      var tx = spans[i].textContent.trim();
      if (mapSt[tx]) spans[i].innerHTML = mapSt[tx];
    }
  }, 150);

  window.syncUiState = function() {
    fetch("/state", {cache: "no-store"}).then(function(r) { return r.json(); }).then(function(st) {
      if (typeof st.osd === "number") stCache.osd = st.osd;
      stCache.freq = st.freq || 50;
      stCache.flip = st.flip ? 1 : 0;
      stCache.patrol = st.patrol ? 1 : 0;
      stCache.patrol_sec = st.patrol_sec || 15;
      var ptsStr = "," + (st.pts || []).join(",") + ",";

      var m = document.getElementById("cam-ext-modal");
      if (m) {
        var btns = m.querySelectorAll("button");
        for (var i = 0; i < btns.length; i++) {
          var b = btns[i], tx = b.textContent.trim(), oc = b.getAttribute("onclick") || "";
          if (tx.indexOf("180") !== -1) {
            b.innerHTML = st.flip ? "&#128260; &#1055;&#1086;&#1074;&#1086;&#1088;&#1086;&#1090; 180&#176;: &#1042;&#1050;&#1051;" : "&#128260; &#1055;&#1086;&#1074;&#1086;&#1088;&#1086;&#1090; 180&#176;: &#1042;&#1067;&#1050;&#1051;";
            b.style.setProperty("background", st.flip ? "#0284c7" : "#1e293b", "important");
          } else if (tx.indexOf("50") === 0 && tx.indexOf("60") === -1) {
            var a50 = stCache.freq == 50;
            b.style.setProperty("background", a50 ? "#0284c7" : "#1e293b", "important");
            b.style.opacity = a50 ? "1" : "0.5";
          } else if (tx.indexOf("60") === 0) {
            var a60 = stCache.freq == 60;
            b.style.setProperty("background", a60 ? "#0284c7" : "#1e293b", "important");
            b.style.opacity = a60 ? "1" : "0.5";
          } else if (oc.indexOf("osd") !== -1 && oc.indexOf("1") !== -1) {
            b.style.setProperty("background", st.osd ? "#16a34a" : "#1e293b", "important");
            b.style.opacity = st.osd ? "1" : "0.5";
          } else if (oc.indexOf("osd") !== -1 && oc.indexOf("0") !== -1) {
            b.style.setProperty("background", !st.osd ? "#475569" : "#1e293b", "important");
            b.style.opacity = !st.osd ? "1" : "0.5";
          }
        }
      }
      var bOn = document.getElementById("pat-on-btn"), bOff = document.getElementById("pat-off-btn");
      if (bOn && bOff) {
        bOn.style.opacity = st.patrol ? "1" : "0.45";
        bOff.style.opacity = !st.patrol ? "1" : "0.45";
      }
      var sArr = "10,15,25,45".split(",");
      for (var j = 0; j < sArr.length; j++) {
        var bs = document.getElementById("pat-sec-" + sArr[j]);
        if (bs) {
          var actS = String(stCache.patrol_sec) === sArr[j];
          bs.style.setProperty("background", actS ? "#0284c7" : "#1e293b", "important");
          bs.style.opacity = actS ? "1" : "0.5";
        }
      }
      for (var k = 1; k <= 6; k++) {
        var bt = document.getElementById("ptz-t-" + k);
        if (bt) bt.style.setProperty("background", ptsStr.indexOf("," + k + ",") !== -1 ? "#1d4ed8" : "#334155", "important");
      }
      var bPk = document.getElementById("ptz-park-btn");
      if (bPk) bPk.style.setProperty("background", ptsStr.indexOf(",home,") !== -1 ? "#0f766e" : "#334155", "important");
    }).catch(function() {});
  };

  document.addEventListener("click", function(ev) {
    var t = ev.target && ev.target.closest ? ev.target.closest("button") : ev.target;
    if (!t) return;
    var oc = t.getAttribute("onclick") || "";
    if (oc.indexOf("osd") !== -1) stCache.osd = (oc.indexOf("1") !== -1) ? 1 : 0;
    if (t.id === "btn-patrol-menu" || t.id === "btn-cam-ext" || (t.closest && (t.closest("#cam-ext-modal") || t.closest("#patrol-modal")))) {
      setTimeout(window.syncUiState, 220);
    }
  }, true);

  setTimeout(window.syncUiState, 300);
})();
</script>
<script>
(function(){
  var stopAllPtz = function() {
    fetch("/ctrl?act=stop", {cache:"no-store"}).catch(function(){});
  };
  window.addEventListener("pointerup", stopAllPtz, true);
  window.addEventListener("pointercancel", stopAllPtz, true);
  window.addEventListener("touchend", stopAllPtz, true);
  window.addEventListener("touchcancel", stopAllPtz, true);
  window.addEventListener("blur", stopAllPtz, true);
})();
</script>
<script>
(function() {
  var liteOn = localStorage.getItem("cam_lite_mode") === "1";
  var nextTimer = null;
  var wdTimer = null;

  function clearTimers() {
    if (nextTimer) { clearTimeout(nextTimer); nextTimer = null; }
    if (wdTimer) { clearTimeout(wdTimer); wdTimer = null; }
  }

  function updateBtn() {
    var b = document.getElementById("btn-lite-toggle");
    if (!b) return;
    if (liteOn) {
      b.innerHTML = "&#9889; &#1051;&#1072;&#1081;&#1090;: &#1042;&#1050;&#1051;";
      b.style.setProperty("background", "#0284c7", "important");
      b.style.setProperty("border-color", "#38bdf8", "important");
    } else {
      b.innerHTML = "&#9889; &#1051;&#1072;&#1081;&#1090;: &#1042;&#1067;&#1050;&#1051;";
      b.style.setProperty("background", "#1e293b", "important");
      b.style.setProperty("border-color", "#334155", "important");
    }
  }

  function runLiteLoop() {
    clearTimers();
    var im = document.getElementById("mjpg");
    if (!im || !liteOn) return;

    var pump = function() {
      if (!liteOn) return;
      clearTimers();
      var done = false;
      var finish = function(delay) {
        if (done || !liteOn) return;
        done = true;
        clearTimers();
        nextTimer = setTimeout(pump, delay);
      };
      im.onload = function() { finish(70); };
      im.onerror = function() { finish(350); };
      wdTimer = setTimeout(function() { finish(150); }, 2500);
      im.src = "/snapshot.jpg?t=" + Date.now();
    };
    pump();
  }

  function applyLiteState(switchQuality) {
    updateBtn();
    var im = document.getElementById("mjpg");
    if (!im) return;
    if (liteOn) {
      if (switchQuality) {
        fetch("/ctrl?act=res&val=0", {cache: "no-store"}).catch(function(){});
      }
      runLiteLoop();
    } else {
      clearTimers();
      im.onload = null;
      im.onerror = null;
      if (switchQuality) {
        fetch("/ctrl?act=res&val=1", {cache: "no-store"}).catch(function(){});
      }
      im.src = "/stream.mjpg?t=" + Date.now();
    }
  }

  window.toggleLiteMode = function() {
    liteOn = !liteOn;
    localStorage.setItem("cam_lite_mode", liteOn ? "1" : "0");
    applyLiteState(true);
  };

  function mountLiteButton() {
    var camBtn = document.getElementById("btn-cam-ext");
    if (camBtn && !document.getElementById("btn-lite-toggle")) {
      var b = document.createElement("button");
      b.id = "btn-lite-toggle";
      b.type = "button";
      b.onclick = window.toggleLiteMode;
      b.style.cssText = camBtn.style.cssText + ";grid-column:1 / -1;margin-top:4px;font-weight:bold;";
      camBtn.parentNode.appendChild(b);
    }
    applyLiteState(false);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mountLiteButton);
  } else {
    mountLiteButton();
  }
})();
</script>
<script>
(function() {
  var ledOn = localStorage.getItem("cam_led") !== "0";
  function updLedBtn() {
    var b = document.getElementById("btn-cam-led");
    if (!b) return;
    b.innerHTML = ledOn ? "&#128161; &#1048;&#1085;&#1076;&#1080;&#1082;&#1072;&#1090;&#1086;&#1088;: &#1042;&#1050;&#1051;" : "&#128161; &#1048;&#1085;&#1076;&#1080;&#1082;&#1072;&#1090;&#1086;&#1088;: &#1042;&#1067;&#1050;&#1051;";
    b.style.background = ledOn ? "#1e293b" : "#0f172a";
  }
  window.toggleCamLed = function() {
    ledOn = !ledOn;
    localStorage.setItem("cam_led", ledOn ? "1" : "0");
    updLedBtn();
    fetch("/cam/ext?act=led&val=" + (ledOn ? 1 : 0), {cache: "no-store"}).catch(function(){});
  };
  setInterval(function() {
    var btns = document.querySelectorAll("button");
    for (var i = 0; i < btns.length; i++) {
      var tx = btns[i].textContent || "";
      if ((tx.indexOf("50") !== -1 && tx.indexOf("60") !== -1) || tx.indexOf("180") !== -1) {
        var box = btns[i].parentNode;
        if (box && !document.getElementById("btn-cam-led")) {
          var nb = document.createElement("button");
          nb.id = "btn-cam-led";
          nb.type = "button";
          nb.onclick = window.toggleCamLed;
          nb.style.cssText = btns[i].style.cssText + ";width:100%;margin-top:6px;";
          box.appendChild(nb);
          updLedBtn();
        }
        break;
      }
    }
  }, 600);
})();
</script>
<script>
(function() {
  function ensureRecBadge() {
    var box = document.getElementById("mjpg") ? document.getElementById("mjpg").parentNode : document.body;
    if (!box || document.getElementById("osd-rec-badge")) return;
    if (getComputedStyle(box).position === "static") box.style.position = "relative";
    var el = document.createElement("div");
    el.id = "osd-rec-badge";
    el.innerHTML = "<span style='display:inline-block;width:9px;height:9px;border-radius:50%;background:#ef4444;margin-right:6px;box-shadow:0 0 8px #ef4444;'></span>REC";
    el.style.cssText = "display:none;position:absolute;top:12px;right:12px;z-index:9999;background:rgba(15,23,42,0.78);color:#fca5a5;border:1px solid rgba(239,68,68,0.6);padding:3px 9px;border-radius:6px;font:700 12px/1.2 system-ui,sans-serif;letter-spacing:0.6px;pointer-events:none;align-items:center;";
    box.appendChild(el);
  }
  function pollRec() {
    ensureRecBadge();
    fetch("/nvr/status", {cache: "no-store"}).then(function(r) {
      return r.ok ? r.json() : null;
    }).then(function(d) {
      var el = document.getElementById("osd-rec-badge");
      if (!el || !d) return;
      var active = Boolean(d.recording || d.enabled || d.on || (d.nvr && (d.nvr.enabled || d.nvr.recording)));
      el.style.display = active ? "flex" : "none";
    }).catch(function(){});
  }
  setInterval(pollRec, 2000);
  setTimeout(pollRec, 600);
})();
</script>
</body>
</html>
"""
