"""Self-contained visual effects for the offline report (plan G6).

Exports EFFECTS_CSS and EFFECTS_JS. The JS is one IIFE that defines only window.NHBEffects and
does nothing until NHBEffects.init() is called. Everything decorative is aria-hidden and
pointer-events:none; every animation or transition rule is keyed to html[data-motion="on"].
"""

from __future__ import annotations

EFFECTS_CSS = r"""
:where(:root){--fx-ease:cubic-bezier(.22,1,.36,1);--fx-ground:#08090d;--fx-dot-d:#dbe0eb;--fx-accent:#080a0d;--fx-blue:#7aa2ff;--fx-rule:rgba(219,224,235,.16);--fx-spot:rgba(219,224,235,.07)}
:where(:root[data-theme="light"]){--fx-ground:#fcfcfd;--fx-dot-d:rgba(22,25,31,.2);--fx-accent:#074ce0;--fx-blue:#074ce0;--fx-rule:rgba(22,25,31,.16);--fx-spot:rgba(7,76,224,.06)}
:where([data-fx-halftone]){position:relative}
[data-fx-halftone]{overflow:hidden;pointer-events:none}
.fx-halftone__canvas,.fx-halftone__fallback{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}
.fx-halftone__canvas{display:block;opacity:var(--fx-halftone-opacity,1)}
.fx-halftone__fallback{display:none;opacity:var(--fx-halftone-opacity,1);color:var(--fx-dot,var(--fx-ink,var(--fx-dot-d)));background-color:var(--fx-ground);border-color:var(--fx-accent);background-image:radial-gradient(circle,currentColor 0,currentColor 2.4px,transparent 3px);background-size:24px 24px;-webkit-mask-image:linear-gradient(160deg,#000,transparent 85%);mask-image:linear-gradient(160deg,#000,transparent 85%)}
[data-fx-state="fallback"]>.fx-halftone__fallback{display:block}
[data-fx-state="fallback"]>.fx-halftone__canvas{display:none}
html[data-motion="on"] .fx-halftone__canvas{animation:fx-fade .8s var(--fx-ease) both}
@keyframes fx-fade{from{opacity:0}}
:where([data-fx-journey]){position:absolute;inset:0;width:100%;height:100%}
[data-fx-journey]{overflow:visible;pointer-events:none}
.fx-journey__base,.fx-journey__ink{fill:none;stroke-linecap:round;stroke-linejoin:round;}
.fx-journey__base{stroke:var(--fx-rule);stroke-width:1.5}
.fx-journey__ink{stroke:var(--fx-blue);stroke-width:2}
.fx-journey__node{fill:var(--fx-node-bg,var(--bg,Canvas));stroke:var(--fx-rule);stroke-width:1.5;transform-box:fill-box;transform-origin:center}
.fx-journey__node.is-active{fill:var(--fx-blue);stroke:var(--fx-blue)}
html[data-motion="on"] .fx-journey__node{transition:fill .3s var(--fx-ease),stroke .3s var(--fx-ease),transform .5s var(--fx-ease)}
html[data-motion="on"] .fx-journey__node.is-active{transform:scale(1.25)}
[data-fx-count]{font-variant-numeric:tabular-nums}
.fx-sr{position:absolute;width:1px;height:1px;margin:-1px;padding:0;overflow:hidden;clip:rect(0 0 0 0);clip-path:inset(50%);white-space:nowrap;border:0}
.fx-pad{visibility:hidden}
html.js-fx[data-motion="on"] [data-fx-reveal]{opacity:0;translate:0 32px}
html.js-fx[data-motion="on"] [data-fx-reveal].fx-in{opacity:1;translate:none;transition:opacity .7s var(--fx-ease),translate .7s var(--fx-ease);transition-delay:var(--fx-delay,0ms)}
html.js-fx[data-motion="on"] [data-fx-reveal][data-fx-readable]{opacity:1}
:where([data-fx-spotlight]){position:relative}
[data-fx-spotlight]::after{content:"";position:absolute;inset:0;border-radius:inherit;pointer-events:none;opacity:0;background:radial-gradient(240px circle at var(--fx-x,50%) var(--fx-y,50%),var(--fx-spot),transparent 70%)}
html[data-motion="on"] [data-fx-spotlight]::after{transition:opacity .3s var(--fx-ease)}
html[data-motion="on"] [data-fx-spotlight]:hover::after{opacity:1}
html[data-motion="on"] [data-fx-magnetic]{translate:var(--fx-mx,0px) var(--fx-my,0px);transition:translate .5s var(--fx-ease),scale .3s var(--fx-ease)}
html[data-motion="on"] [data-fx-magnetic]:active{scale:.98}
html[data-motion="on"] .fx-tilt-html{transform:perspective(900px) rotateX(var(--fx-rx,0deg)) rotateY(var(--fx-ry,0deg));transition:transform .5s var(--fx-ease)}
html[data-motion="on"] .fx-tilt-svg{translate:var(--fx-tx,0px) var(--fx-ty,0px);transition:translate .5s var(--fx-ease)}
.fx-progress{display:none}
html[data-motion="on"] .fx-progress{display:block;position:fixed;inset:0 0 auto 0;height:2px;z-index:60;pointer-events:none;background:var(--fx-blue);transform-origin:0 50%;transform:scaleX(var(--fx-progress,0))}
:where([data-fx-nav]){position:relative}
.fx-nav-indicator{position:absolute;left:0;bottom:0;height:2px;width:1px;background:var(--fx-blue);transform-origin:0 50%;transform:translateX(var(--fx-nav-x,0px)) scaleX(var(--fx-nav-w,0));opacity:0;pointer-events:none}
.fx-nav-indicator.is-on{opacity:1}
html[data-motion="on"] .fx-nav-indicator{transition:transform .5s var(--fx-ease),opacity .3s var(--fx-ease)}
:where(details[data-fx-disclosure]>summary){display:flex;align-items:center;gap:.75rem;cursor:pointer;list-style:none}
:where(details[data-fx-disclosure]>summary)::-webkit-details-marker{display:none}
:where(details[data-fx-disclosure]>summary)::after{content:"+";content:"+" / "";margin-inline-start:auto;line-height:1;color:var(--fx-blue)}
details[data-fx-disclosure][open]>summary::after{rotate:45deg}
html[data-motion="on"] details[data-fx-disclosure]>summary::after{transition:rotate .5s var(--fx-ease)}
html[data-motion="on"]::view-transition-old(root),html[data-motion="on"]::view-transition-new(root){animation:none;mix-blend-mode:normal}
html[data-motion="on"]::view-transition-new(root){z-index:2}
html.js-fx[data-motion="on"] [data-fx-words] .fx-w{opacity:.3}
html.js-fx[data-motion="on"] [data-fx-words] .fx-w.is-lit{opacity:1;transition:opacity .5s var(--fx-ease)}
.fx-burger{position:relative;display:block;width:24px;height:24px;pointer-events:none}
.fx-burger i{position:absolute;left:4px;right:4px;top:11px;height:2px;border-radius:1px;background:currentColor;transform:translateY(-4px)}
.fx-burger i+i{transform:translateY(4px)}
[data-fx-pillnav].is-open .fx-burger i{transform:rotate(45deg)}
[data-fx-pillnav].is-open .fx-burger i+i{transform:rotate(-45deg)}
html[data-motion="on"] .fx-burger i{transition:transform .5s var(--fx-ease)}
html.fx-menu-open{overflow:hidden}
[data-fx-pillnav].fx-overlay:not(.is-open) [data-fx-pillnav-panel]{opacity:0;visibility:hidden;pointer-events:none}
html[data-motion="on"] .fx-ready.fx-overlay [data-fx-pillnav-panel]{transition:opacity .5s var(--fx-ease),visibility 0s step-end .5s}
html[data-motion="on"] .fx-ready.fx-overlay.is-open [data-fx-pillnav-panel]{transition:opacity .5s var(--fx-ease),visibility 0s}
html[data-motion="on"] .fx-overlay [data-fx-pillnav-panel] a{opacity:0;translate:0 24px}
html[data-motion="on"] .fx-ready.fx-overlay [data-fx-pillnav-panel] a{transition:opacity .4s var(--fx-ease),translate .4s var(--fx-ease)}
html[data-motion="on"] .fx-overlay.is-open [data-fx-pillnav-panel] a{opacity:1;translate:none;transition-delay:calc(var(--fx-i,0)*60ms)}
@media print{.fx-w{opacity:1!important}.fx-halftone__canvas,.fx-halftone__fallback,.fx-progress,[data-fx-journey]{display:none!important}[data-fx-reveal]{opacity:1!important;translate:none!important}}
"""

EFFECTS_JS = r"""
(function(){"use strict";
var D=document,W=window,H=D.documentElement,MAXH=3,T0=7.3,S=null,PRE=null,BASE="cubic-bezier(.22,1,.36,1)";
var VS="attribute vec2 p;void main(){gl_Position=vec4(p,0.,1.);}";
var FS=["#ifdef GL_FRAGMENT_PRECISION_HIGH","precision highp float;","#else","precision mediump float;","#endif",
"uniform vec2 uRes,uPointer;uniform float uTime,uIntensity;uniform vec3 uGround,uDot,uAccent;",
"float hash11(float p){p=fract(p*.1031);p*=p+33.33;p*=p+p;return fract(p);}",
"float hash21(vec2 p){vec3 q=fract(vec3(p.xyx)*.1031);q+=dot(q,q.yzx+33.33);return fract((q.x+q.y)*q.z);}",
"float vnoise(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);",
"return mix(mix(hash21(i),hash21(i+vec2(1.,0.)),f.x),mix(hash21(i+vec2(0.,1.)),hash21(i+vec2(1.,1.)),f.x),f.y);}",
"float fbm(vec2 p){float a=.5,s=0.;for(int i=0;i<6;i++){s+=a*vnoise(p);p=p*2.02+vec2(17.1,9.2);a*=.5;}return s;}",
"vec2 warp(vec2 p,float t){return p+.8*vec2(fbm(p+vec2(0.,t)),fbm(p+vec2(5.2,1.3)-t));}",
"vec2 warp2(vec2 p,float t){return warp(warp(p,t),t*1.37+3.1);}",
"const float CELLS=34.0;",
"float pointerFalloff(vec2 c){vec2 d=c-uPointer;return exp(-dot(d,d)*7.);}",
"void main(){",
"float m=min(uRes.x,uRes.y);vec2 uv=gl_FragCoord.xy/m;",
"vec2 cell=floor(uv*CELLS);vec2 centre=(cell+.5)/CELLS;",
"float t=uTime*.16;",
"float v=fbm(warp2(centre*2.2,t)+vec2(t*.6,-t*.35));",
"float r=mix(.07,.4,smoothstep(.3,.72,v))*(1.+uIntensity*.5*pointerFalloff(centre));r=min(r,.49);",
"float aa=CELLS/m;float d=distance(fract(uv*CELLS),vec2(.5));",
"float dotm=1.-smoothstep(r-aa,r+aa,d);",
"float rim=dotm*smoothstep(r-3.*aa,r-aa,d);",
"vec3 col=mix(mix(uGround,uDot,dotm),uAccent,rim*.8);",
"gl_FragColor=vec4(col,1.);}"].join("\n");

function qa(root,sel){try{return Array.prototype.slice.call(root.querySelectorAll(sel))}catch(e){return[]}}
function clamp(v,a,b){return v<a?a:v>b?b:v}
function mq(q){try{return W.matchMedia(q)}catch(e){return null}}
function mk(tag,cls){var e=D.createElement(tag);if(cls)e.className=cls;return e}
function on(t,type,fn,opt){t.addEventListener(type,fn,opt);S.off.push(function(){t.removeEventListener(type,fn,opt)})}
function obs(C,cb,opt){if(typeof C!=="function")return null;var o=new C(cb,opt);S.off.push(function(){o.disconnect()});return o}
function safe(fn){try{fn()}catch(e){/* decorative layer: one failing effect must not break the page */}}
function fresh(kind,el){var s=S.seen[kind]||(S.seen[kind]=new WeakSet());if(s.has(el))return false;s.add(el);return true}
function fine(){var m=mq("(hover: hover) and (pointer: fine)");return !!(m&&m.matches)}

/* ---------- halftone ---------- */
function rgba(v){var n=(String(v).match(/-?[\d.]+/g)||[]).map(Number);if(n.length<3||n.some(isNaN))return null;
var k=/^color\(/.test(v)?1:1/255;return[n[0]*k,n[1]*k,n[2]*k,n.length>3?n[3]:1]}
function palette(h){var cs=W.getComputedStyle(h.fb);
var g=rgba(cs.backgroundColor)||[8/255,9/255,13/255,1];
function over(c,d){c=c||d;return[0,1,2].map(function(i){return c[i]*c[3]+g[i]*(1-c[3])})}
h.pal=[g.slice(0,3),over(rgba(cs.color),[219/255,224/255,235/255,1]),over(rgba(cs.borderTopColor),[8/255,10/255,13/255,1])]}
function sd(o,t,st,dt){var w=2/st,x=w*dt,e=1/(1+x+.48*x*x+.235*x*x*x),c=o.x-t,q=(o.v+w*c)*dt;o.v=(o.v-w*q)*e;o.x=t+(c+q)*e}
function shader(g,type,src){var s=g.createShader(type);g.shaderSource(s,src);g.compileShader(s);return g.getShaderParameter(s,g.COMPILE_STATUS)?s:null}
function glInit(h){
var o={alpha:false,antialias:false,depth:false,stencil:false,preserveDrawingBuffer:true,powerPreference:"low-power"},g;
try{g=h.canvas.getContext("webgl",o)||h.canvas.getContext("experimental-webgl",o)}catch(e){g=null}
if(!g||(g.isContextLost&&g.isContextLost()))return false;
var v=shader(g,g.VERTEX_SHADER,VS),f=shader(g,g.FRAGMENT_SHADER,FS);if(!v||!f)return false;
var p=g.createProgram();g.attachShader(p,v);g.attachShader(p,f);g.linkProgram(p);
if(!g.getProgramParameter(p,g.LINK_STATUS))return false;
g.useProgram(p);var b=g.createBuffer();g.bindBuffer(g.ARRAY_BUFFER,b);
g.bufferData(g.ARRAY_BUFFER,new Float32Array([-1,-1,3,-1,-1,3]),g.STATIC_DRAW);
var a=g.getAttribLocation(p,"p");g.enableVertexAttribArray(a);g.vertexAttribPointer(a,2,g.FLOAT,false,0,0);
var n=["uRes","uTime","uIntensity","uPointer","uGround","uDot","uAccent"];h.u={};
n.forEach(function(k){h.u[k]=g.getUniformLocation(p,k)});h.gl=g;return true}
function draw(h,t){var g=h.gl,u=h.u;if(!g||h.lost||!h.cw)return;
g.viewport(0,0,h.cw,h.ch);g.uniform2f(u.uRes,h.cw,h.ch);g.uniform1f(u.uTime,t);g.uniform1f(u.uIntensity,h.i.x);
g.uniform2f(u.uPointer,h.px.x,h.py.x);g.uniform3fv(u.uGround,h.pal[0]);g.uniform3fv(u.uDot,h.pal[1]);g.uniform3fv(u.uAccent,h.pal[2]);
g.drawArrays(g.TRIANGLES,0,3)}
function fit(h){var w=h.host.clientWidth,e=h.host.clientHeight;if(!w||!e||!h.gl)return;
var s=Math.min(W.devicePixelRatio||1,1.5)*h.q,px=w*e*s*s;if(px>1.6e6)s*=Math.sqrt(1.6e6/px);
var cw=Math.max(1,Math.round(w*s)),ch=Math.max(1,Math.round(e*s));
if(cw!==h.cw||ch!==h.ch){h.cw=cw;h.ch=ch;h.canvas.width=cw;h.canvas.height=ch}draw(h,h.time)}
function live(h){return S.motion&&h.state==="gl"&&h.vis&&!D.hidden&&!h.lost}
function stop(h){if(h.raf){W.cancelAnimationFrame(h.raf);h.raf=0}}
function start(h){if(live(h)&&!h.raf){h.last=0;h.raf=W.requestAnimationFrame(h.cb)}}
function tick(h,now){h.raf=0;if(!live(h))return;h.raf=W.requestAnimationFrame(h.cb);
if(now-h.last<30)return;var raw=h.last?(now-h.last)/1000:.016,dt=Math.min(raw,.1);h.last=now;
if(raw>.075){if(++h.slow>=10&&h.q>.4){h.q*=.75;h.slow=0;fit(h)}}else h.slow=0;
sd(h.i,h.tgt,.22,dt);sd(h.px,h.tx,.12,dt);sd(h.py,h.ty,.12,dt);h.time+=dt;draw(h,h.time)}
function setState(h,s){h.state=s;h.host.setAttribute("data-fx-state",s)}
function sync(h){if(h.state!=="gl")return;stop(h);
if(!S.motion){h.i.x=h.i.v=0;h.tgt=0;h.time=T0;draw(h,T0);return}
draw(h,h.time);start(h)}
function halftone(host,idx){
var h={host:host,state:"fallback",vis:true,lost:false,raf:0,last:0,time:T0,tgt:0,tx:.5,ty:.5,q:1,slow:0,cw:0,ch:0,gl:null,u:null,pal:null,
i:{x:0,v:0},px:{x:.5,v:0},py:{x:.5,v:0}};
h.cb=function(n){tick(h,n)};
host.setAttribute("aria-hidden","true");
h.fb=mk("div","fx-halftone__fallback");h.fb.setAttribute("aria-hidden","true");
h.canvas=mk("canvas","fx-halftone__canvas");h.canvas.setAttribute("aria-hidden","true");
host.insertBefore(h.canvas,host.firstChild);host.insertBefore(h.fb,host.firstChild);
host.setAttribute("data-fx-state","fallback");palette(h);
h.canvas.addEventListener("webglcontextlost",function(e){e.preventDefault();if(h.dead)return;h.lost=true;stop(h);setState(h,"fallback")});
h.canvas.addEventListener("webglcontextrestored",function(){if(h.dead)return;h.lost=false;h.gl=null;h.cw=h.ch=0;
if(glInit(h)){setState(h,"gl");fit(h);sync(h)}});
if(idx<MAXH&&glInit(h)){setState(h,"gl");fit(h);sync(h)}
return h}
function dropHost(h){h.dead=true;stop(h);var x=h.gl&&h.gl.getExtension&&h.gl.getExtension("WEBGL_lose_context");
if(x)safe(function(){x.loseContext()});
[h.canvas,h.fb].forEach(function(e){if(e.parentNode)e.parentNode.removeChild(e)});
if(S.ro)S.ro.unobserve(h.host);if(S.hio)S.hio.unobserve(h.host);S.byEl.delete(h.host);
h.host.removeAttribute("data-fx-state");h.host.removeAttribute("aria-hidden")}
function hostMove(e){var x=e.clientX,y=e.clientY;S.hosts.forEach(function(h){
if(h.state!=="gl"||!h.vis)return;var r=h.host.getBoundingClientRect(),m=Math.min(r.width,r.height);
if(m>0&&x>=r.left&&x<=r.right&&y>=r.top&&y<=r.bottom){
h.tx=(x-r.left)/m;h.ty=(r.bottom-y)/m;if(!h.tgt&&h.i.x<.02){h.px.x=h.tx;h.py.x=h.ty;h.px.v=h.py.v=0}h.tgt=1}else h.tgt=0})}
function hostsLeave(){S.hosts.forEach(function(h){h.tgt=0})}

/* ---------- scroll journey ---------- */
function journey(svg){
var box=svg.parentElement;if(!box)return null;
var j={svg:svg,box:box,len:0,marks:[],nodes:[],p:-1,ns:svg.namespaceURI};
function el(tag,cls){var e=D.createElementNS(j.ns,tag);e.setAttribute("class",cls);return e}
j.base=el("path","fx-journey__base");j.ink=el("path","fx-journey__ink");j.g=el("g","fx-journey__nodes");
svg.appendChild(j.base);svg.appendChild(j.ink);svg.appendChild(j.g);
if(W.getComputedStyle(box).position==="static")box.style.position="relative";
j.build=function(){
var stops=qa(box,"[data-fx-stop]"),cr=svg.getBoundingClientRect(),w=cr.width,hh=cr.height;
while(j.g.firstChild)j.g.removeChild(j.g.firstChild);j.nodes=[];j.marks=[];j.p=-1;
if(!stops.length||hh<2||w<2){j.base.removeAttribute("d");j.ink.removeAttribute("d");j.len=0;return}
svg.setAttribute("viewBox","0 0 "+w.toFixed(1)+" "+hh.toFixed(1));svg.setAttribute("preserveAspectRatio","none");
var wide=W.innerWidth>=1050,pts=stops.map(function(s){var r=s.getBoundingClientRect();
return{x:r.left-cr.left,y:r.top-cr.top+Math.min(r.height/2,16)}});
var minX=Math.min.apply(null,pts.map(function(q){return q.x})),sx=wide?clamp(minX-48,6,Math.max(6,w-32)):5,nx=wide?sx+24:sx,d="M"+sx+" 0",pre=[];
pts.forEach(function(q,i){var y=q.y,g=Math.min(32,(y-(i?pts[i-1].y:0))/2.4,((i<pts.length-1?pts[i+1].y:y+80)-y)/2.4);g=Math.max(2,g);
var a=sx+" "+(y-g);d+=" L"+a;
if(wide)d+=" C"+sx+" "+(y-g/2)+" "+nx+" "+(y-g/2)+" "+nx+" "+y;else d+=" L"+sx+" "+y;
pre.push(d);
if(wide)d+=" C"+nx+" "+(y+g/2)+" "+sx+" "+(y+g/2)+" "+sx+" "+(y+g);
j.nodes.push(function(){var c=el("circle","fx-journey__node");c.setAttribute("cx",nx.toFixed(1));c.setAttribute("cy",y.toFixed(1));c.setAttribute("r","4");return c}())});
d+=" L"+sx+" "+hh.toFixed(1);
try{pre.forEach(function(s){j.ink.setAttribute("d",s);j.marks.push(j.ink.getTotalLength())});
j.base.setAttribute("d",d);j.ink.setAttribute("d",d);j.len=j.ink.getTotalLength()}catch(e){j.len=hh;j.marks=pts.map(function(q){return q.y})}
j.nodes.forEach(function(c){j.g.appendChild(c)});
j.ink.setAttribute("stroke-dasharray",j.len.toFixed(2)+" "+j.len.toFixed(2))};
j.update=function(){if(!j.len)return;var p=1;
if(S.motion){var r=box.getBoundingClientRect(),vh=W.innerHeight;p=clamp((vh*.55-r.top)/Math.max(1,r.height),0,1);
if(W.scrollY+vh>=H.scrollHeight-2&&r.bottom<=vh+1)p=1}
if(p===j.p)return;j.p=p;j.ink.setAttribute("stroke-dashoffset",(j.len*(1-p)).toFixed(2));
j.nodes.forEach(function(c,i){c.classList.toggle("is-active",j.marks[i]<=j.len*p+.5)})};
j.build();j.update();return j}

/* ---------- disclosure ---------- */
function toggle(d,s){
var run=S.anim.get(d),cur=d.offsetHeight,closing,cs=W.getComputedStyle(d);
var ex=["paddingTop","paddingBottom","borderTopWidth","borderBottomWidth"].reduce(function(a,k){return a+(parseFloat(cs[k])||0)},0);
var adj=cs.boxSizing==="border-box"?0:ex;
if(run){run.a.onfinish=null;run.a.cancel();closing=run.opening}else closing=d.open;
var from,to,shut=s.offsetHeight+ex;
if(closing){from=cur;to=shut}else{if(!d.open)d.open=true;to=d.offsetHeight;from=run?cur:shut}
d.style.overflow="hidden";
var a=d.animate({height:[Math.max(0,from-adj)+"px",Math.max(0,to-adj)+"px"]},{duration:500,easing:BASE});
S.anim.set(d,{a:a,opening:!closing});
a.onfinish=function(){S.anim.delete(d);d.style.removeProperty("overflow");if(closing)d.open=false}}
function onClick(e){var t=e.target;if(!S.motion||!t||!t.closest||e.defaultPrevented)return;
var s=t.closest("summary"),d=s&&s.parentNode;
if(!d||d.tagName!=="DETAILS"||!d.hasAttribute("data-fx-disclosure")||typeof d.animate!=="function")return;
var i=t.closest("a[href],button,input,select,textarea");if(i&&s.contains(i))return;
e.preventDefault();safe(function(){toggle(d,s)})}

/* ---------- count, draw, reveal ---------- */
function easeOut(p){return 1-Math.pow(1-p,3)}
function countUp(el){
var m=/^\s*(\d{1,12})\s*$/.exec(el.textContent);if(!m||!S.motion)return;
var to=+m[1],n=m[1].length,kids=Array.prototype.slice.call(el.childNodes),
sr=mk("span","fx-sr"),cl=mk("span"),a=mk("span"),b=mk("span","fx-pad"),t0=0,job={raf:0};
var right=/right|end/.test(W.getComputedStyle(el).textAlign);
cl.setAttribute("aria-hidden","true");
kids.forEach(function(k){sr.appendChild(k)});
cl.appendChild(right?b:a);cl.appendChild(right?a:b);el.appendChild(sr);el.appendChild(cl);
function show(v){var s=String(v);a.textContent=s;b.textContent=s.length<n?new Array(n-s.length+1).join("0"):""}
job.fin=function(){if(job.raf)W.cancelAnimationFrame(job.raf);job.raf=0;S.counts.delete(job);
if(!sr.parentNode)return;kids.forEach(function(k){el.insertBefore(k,sr)});el.removeChild(sr);if(cl.parentNode)el.removeChild(cl)};
function step(now){if(!t0)t0=now;var p=Math.min(1,(now-t0)/900);show(Math.round(to*easeOut(p)));
if(p<1)job.raf=W.requestAnimationFrame(step);else job.fin()}
show(0);S.counts.add(job);job.raf=W.requestAnimationFrame(step)}
function drawPrep(el){if(!S.motion||S.dp.has(el))return;var len;
try{len=el.getTotalLength();if(W.getComputedStyle(el).vectorEffect==="non-scaling-stroke"){var cm=el.getScreenCTM();if(cm)len*=Math.sqrt(Math.abs(cm.a*cm.d-cm.b*cm.c))}var r=el.getBoundingClientRect(),vh=W.innerHeight,vis=Math.min(r.bottom,vh)-Math.max(r.top,0);
if(!(len>0)||(r.height>0&&vis>=r.height*.6))return}catch(e){return}
el.style.strokeDasharray=String(len);el.style.strokeDashoffset=String(len);S.dp.set(el,len)}
function drawClear(el){S.dp.delete(el);el.style.removeProperty("stroke-dasharray");el.style.removeProperty("stroke-dashoffset")}
function drawGo(el){var len=S.dp.get(el);if(!len)return;
if(!S.motion||typeof el.animate!=="function"){drawClear(el);return}
el.style.strokeDashoffset="0";S.dp.delete(el);
var a=el.animate([{strokeDashoffset:len},{strokeDashoffset:0}],{duration:700,easing:BASE});
S.dr.add(a);a.onfinish=a.oncancel=function(){S.dr.delete(a);drawClear(el)}}
function reveal(el){var d=parseInt(el.getAttribute("data-fx-delay"),10);
if(d>0&&S.motion){el.style.setProperty("--fx-delay",Math.min(d,2000)+"ms");
el.addEventListener("transitionend",function f(ev){if(ev.target===el){el.style.removeProperty("--fx-delay");el.removeEventListener("transitionend",f)}})}
el.classList.add("fx-in")}

/* ---------- pointer micro-interactions ---------- */
function rel(e,el){var r=el.getBoundingClientRect();return{r:r,x:e.clientX-r.left,y:e.clientY-r.top}}
function unhot(k){var el=S.hot[k];if(!el)return;S.hot[k]=null;
if(k==="mag"){el.style.removeProperty("--fx-mx");el.style.removeProperty("--fx-my")}
else["--fx-rx","--fx-ry","--fx-tx","--fx-ty"].forEach(function(p){el.style.removeProperty(p)})}
function onMove(e){if(!S.motion||e.pointerType==="touch")return;var t=e.target;if(!t||!t.closest)return;
hostMove(e);
var sp=t.closest("[data-fx-spotlight]");
if(sp){var q=rel(e,sp);sp.style.setProperty("--fx-x",q.x.toFixed(1)+"px");sp.style.setProperty("--fx-y",q.y.toFixed(1)+"px")}
var mg=fine()?t.closest("[data-fx-magnetic]"):null,tl=fine()?t.closest("[data-fx-tilt]"):null;
if(S.hot.mag&&S.hot.mag!==mg)unhot("mag");if(S.hot.tilt&&S.hot.tilt!==tl)unhot("tilt");
if(mg){S.hot.mag=mg;var m=rel(e,mg),pr=e.buttons?0:4;
mg.style.setProperty("--fx-mx",(clamp((m.x-m.r.width/2)/(m.r.width/2),-1,1)*pr).toFixed(2)+"px");
mg.style.setProperty("--fx-my",(clamp((m.y-m.r.height/2)/(m.r.height/2),-1,1)*pr).toFixed(2)+"px")}
if(tl){S.hot.tilt=tl;var c=rel(e,tl),nx=clamp((c.x-c.r.width/2)/(c.r.width/2),-1,1),ny=clamp((c.y-c.r.height/2)/(c.r.height/2),-1,1);
if(tl instanceof W.SVGElement){tl.style.setProperty("--fx-tx",(nx*3).toFixed(2)+"px");tl.style.setProperty("--fx-ty",(ny*3).toFixed(2)+"px")}
else{tl.style.setProperty("--fx-ry",(nx*3).toFixed(2)+"deg");tl.style.setProperty("--fx-rx",(-ny*3).toFixed(2)+"deg")}}}
function onDown(e){var t=e.target,m=t&&t.closest&&t.closest("[data-fx-magnetic]");
if(m){m.style.setProperty("--fx-mx","0px");m.style.setProperty("--fx-my","0px")}}
function onLeave(){hostsLeave();unhot("mag");unhot("tilt")}

/* ---------- nav scrollspy ---------- */
function nav(root){
var n={root:root,cur:-1,links:[],secs:[]};
n.ind=mk("span","fx-nav-indicator");n.ind.setAttribute("aria-hidden","true");root.appendChild(n.ind);
n.collect=function(){n.links=[];n.secs=[];qa(root,'a[href^="#"]').forEach(function(a){var id=a.getAttribute("href").slice(1),s;
try{s=D.getElementById(decodeURIComponent(id))}catch(e){s=null}
if(s){n.links.push(a);n.secs.push(s)}})};
n.place=function(){var a=n.links[n.cur];if(!a){n.ind.classList.remove("is-on");return}
var was=n.ind.classList.contains("is-on"),nr=root.getBoundingClientRect(),ar=a.getBoundingClientRect();
if(!was)n.ind.style.setProperty("transition","none");
n.ind.style.setProperty("--fx-nav-x",(ar.left-nr.left+root.scrollLeft-root.clientLeft).toFixed(1)+"px");
n.ind.style.setProperty("--fx-nav-w",ar.width.toFixed(1));n.ind.classList.add("is-on");
if(!was){void n.ind.offsetWidth;n.ind.style.removeProperty("transition")}};
n.set=function(i){if(i===n.cur){if(i>=0)n.place();return}n.cur=i;
n.links.forEach(function(a,k){if(k===i)a.setAttribute("aria-current","true");else a.removeAttribute("aria-current")});n.place()};
n.spy=function(){var vh=W.innerHeight,lim=W.scrollY+vh>=H.scrollHeight-2?vh-8:vh*.3,best=-1,bt=-1e9;
n.secs.forEach(function(s,i){var r=s.getBoundingClientRect();if(!r.width&&!r.height)return;if(r.top<=lim&&r.top>bt){bt=r.top;best=i}});n.set(best)};
n.collect();
qa(root,'a[href^="#"]').forEach(function(a){a.addEventListener("click",function(){var i=n.links.indexOf(a);if(i>=0)n.set(i)})});
return n}

/* ---------- per-word reveal ---------- */
function words(c){var tw=D.createTreeWalker(c,4),ns=[],n;while((n=tw.nextNode()))ns.push(n);
ns.forEach(function(t){if(t.parentNode.classList&&t.parentNode.classList.contains("fx-w"))return;
var f=D.createDocumentFragment();t.nodeValue.split(/(\s+)/).forEach(function(p){if(!p)return;
if(/^\s+$/.test(p)){f.appendChild(D.createTextNode(p));return}
var w=mk("span","fx-w");w.textContent=p;f.appendChild(w);if(S.wio)S.wio.observe(w);else w.classList.add("is-lit")});
t.parentNode.replaceChild(f,t)})}
function unwords(r){qa(r,".fx-w").forEach(function(w){w.parentNode.replaceChild(D.createTextNode(w.textContent),w)});qa(r,"[data-fx-words]").forEach(function(c){c.normalize()})}

/* ---------- floating pill nav (mobile full-height menu) ---------- */
var FOCUS='a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';
function pill(root){var tg=root.querySelector("[data-fx-pillnav-toggle]"),pn=root.querySelector("[data-fx-pillnav-panel]");if(!tg||!pn)return null;
var p={root:root,tg:tg,pn:pn,open:false,burger:null};
if(!tg.querySelector(".fx-burger")){p.burger=mk("span","fx-burger");p.burger.setAttribute("aria-hidden","true");p.burger.appendChild(mk("i"));p.burger.appendChild(mk("i"));tg.appendChild(p.burger)}
tg.setAttribute("aria-expanded","false");
p.set=function(v,focus){root.classList.add("fx-ready");p.open=v;root.classList.toggle("is-open",v);tg.setAttribute("aria-expanded",v?"true":"false");H.classList.toggle("fx-menu-open",v);
if(v){var l=qa(pn,"a[href]");l.forEach(function(a,i){a.style.setProperty("--fx-i",String(Math.min(i,6)))});if(l[0])l[0].focus()}else if(focus)tg.focus()};
p.sync=function(){var ov=W.getComputedStyle(pn).position==="fixed";root.classList.toggle("fx-overlay",ov);if(!ov&&p.open)p.set(false,false)};
tg.addEventListener("click",function(){p.set(!p.open,true)});
pn.addEventListener("click",function(e){if(p.open&&e.target.closest&&e.target.closest("a[href]"))p.set(false,false)});
p.sync();return p}
function onKey(e){S.pills.forEach(function(p){if(!p.open)return;
if(e.key==="Escape"){e.preventDefault();p.set(false,true);return}
if(e.key!=="Tab")return;
var l=qa(p.root,FOCUS).filter(function(x){return x.getClientRects().length>0&&W.getComputedStyle(x).visibility!=="hidden"});if(!l.length)return;
var i=l.indexOf(D.activeElement);e.preventDefault();
l[i<0?(e.shiftKey?l.length-1:0):(i+(e.shiftKey?l.length-1:1))%l.length].focus()})}

/* ---------- orchestration ---------- */
function progress(){
if(S&&S.bar&&S.motion){var m=H.scrollHeight-W.innerHeight;S.bar.style.setProperty("--fx-progress",(m>0?clamp(W.scrollY/m,0,1):0).toFixed(4))}}
function onScroll(){progress();sched()}
function frame(){
progress();
S.journeys.forEach(function(j){j.update()});S.navs.forEach(function(n){n.spy()});S.pills.forEach(function(p){p.sync()})}
function sched(){if(S.tick)return;S.tick=true;W.requestAnimationFrame(function(){S.tick=false;if(S)frame()})}
function scan(){var r=S.root;
S.hosts=S.hosts.filter(function(h){if(h.host.isConnected)return true;dropHost(h);return false});
S.journeys=S.journeys.filter(function(j){if(j.box.isConnected)return true;if(S.jro)S.jro.unobserve(j.box);return false});
S.pills=S.pills.filter(function(p){if(p.root.isConnected)return true;if(p.open)p.set(false,false);return false});
S.navs=S.navs.filter(function(n){if(n.root.isConnected)return true;if(S.nro)S.nro.unobserve(n.root);return false});
qa(r,"[data-fx-tilt]").forEach(function(e){if(fresh("tl",e))e.classList.add(e instanceof W.SVGElement?"fx-tilt-svg":"fx-tilt-html")});
qa(r,"[data-fx-halftone]").forEach(function(e){if(fresh("ht",e)){var h=halftone(e,S.hosts.length);S.hosts.push(h);S.byEl.set(e,h);
if(S.ro)S.ro.observe(e);if(S.hio)S.hio.observe(e)}});
qa(r,"svg[data-fx-journey]").forEach(function(e){if(fresh("jr",e)){var j=journey(e);if(j){S.journeys.push(j);if(S.jro)S.jro.observe(j.box)}}});
qa(r,"[data-fx-nav]").forEach(function(e){if(fresh("nv",e)){var n=nav(e);S.navs.push(n);if(S.nro)S.nro.observe(e)}});
qa(r,"[data-fx-pillnav]").forEach(function(e){if(fresh("pn",e)){var p=pill(e);if(p)S.pills.push(p)}});
qa(r,"[data-fx-words]").forEach(function(e){if(fresh("wd",e))words(e)});
qa(r,"[data-fx-count]").forEach(function(e){if(fresh("ct",e)&&S.cio)S.cio.observe(e)});
qa(r,"[data-fx-draw]").forEach(function(e){if(fresh("dw",e)){drawPrep(e);if(S.dio)S.dio.observe(e)}});
qa(r,"[data-fx-reveal]").forEach(function(e){if(fresh("rv",e)){if(S.rio)S.rio.observe(e);else e.classList.add("fx-in")}})}
function motionChanged(){
S.hosts.forEach(sync);
S.journeys.forEach(function(j){j.p=-1;j.update()});
if(!S.motion){S.counts.forEach(function(c){c.fin()});
qa(S.root,"[data-fx-draw]").forEach(function(e){if(S.dp.has(e))drawClear(e)});
S.dr.forEach(function(a){a.cancel()});
S.anim.forEach(function(v,d){v.a.finish()});onLeave()}
else qa(S.root,"[data-fx-draw]").forEach(drawPrep);
sched();frame()}
function setMotion(v){v=!!v;H.setAttribute("data-motion",v?"on":"off");
if(!S)return;if(S.motion===v)return;S.motion=v;safe(motionChanged)}
function init(root,opts){
if(S){safe(refresh);return}
var want=opts&&typeof opts.motion==="boolean"?opts.motion:(PRE!==null?PRE:null),rm=mq("(prefers-reduced-motion: reduce)");
S={root:root&&root.querySelectorAll?root:D,motion:false,off:[],seen:{},hosts:[],byEl:new Map(),journeys:[],navs:[],pills:[],counts:new Set(),
dp:new Map(),dr:new Set(),anim:new Map(),hot:{mag:null,tilt:null},tick:false,bar:null};
S.motion=want===null?!(rm&&rm.matches):want;H.setAttribute("data-motion",S.motion?"on":"off");
if(want===null&&rm&&rm.addEventListener){var f=function(e){setMotion(!e.matches)};rm.addEventListener("change",f);S.off.push(function(){rm.removeEventListener("change",f)})}
safe(function(){S.ro=obs(W.ResizeObserver,function(es){es.forEach(function(e){var h=S.byEl.get(e.target);if(h)fit(h)})})});
safe(function(){S.hio=obs(W.IntersectionObserver,function(es){es.forEach(function(e){var h=S.byEl.get(e.target);if(!h)return;h.vis=e.isIntersecting;
if(h.vis)start(h);else stop(h)})},{rootMargin:"100px"})});
safe(function(){S.jro=obs(W.ResizeObserver,function(){S.journeys.forEach(function(j){j.build();j.update()})})});
safe(function(){S.nro=obs(W.ResizeObserver,function(){S.navs.forEach(function(n){n.place()})})});
safe(function(){S.wio=obs(W.IntersectionObserver,function(es){es.forEach(function(e){var rb=e.rootBounds;
if(e.isIntersecting||(rb&&e.boundingClientRect.bottom<=rb.top)){S.wio.unobserve(e.target);e.target.classList.add("is-lit")}})},{rootMargin:"0px 0px -35% 0px"})});
safe(function(){S.rio=obs(W.IntersectionObserver,function(es){es.forEach(function(e){if(e.isIntersecting){S.rio.unobserve(e.target);reveal(e.target)}})},{threshold:.15})});
safe(function(){S.cio=obs(W.IntersectionObserver,function(es){es.forEach(function(e){if(e.isIntersecting){S.cio.unobserve(e.target);safe(function(){countUp(e.target)})}})},{threshold:.4})});
safe(function(){S.dio=obs(W.IntersectionObserver,function(es){es.forEach(function(e){if(!e.isIntersecting)return;
var vh=(e.rootBounds&&e.rootBounds.height)||W.innerHeight;
if(e.intersectionRatio>=.6||e.intersectionRect.height>=vh*.5){S.dio.unobserve(e.target);drawGo(e.target)}})},{threshold:[0,.6]})});
safe(function(){var m=obs(W.MutationObserver,function(){S.hosts.forEach(function(h){palette(h);sync(h)})});if(m)m.observe(H,{attributes:true,attributeFilter:["data-theme"]})});
if(D.body){S.bar=mk("div","fx-progress");S.bar.setAttribute("aria-hidden","true");D.body.appendChild(S.bar);S.off.push(function(){if(S.bar.parentNode)S.bar.parentNode.removeChild(S.bar)})}
on(W,"scroll",onScroll,{passive:true});on(W,"resize",sched,{passive:true});
on(D,"visibilitychange",function(){S.hosts.forEach(function(h){if(live(h))start(h);else stop(h)})});
on(W,"pointermove",onMove,{passive:true});on(W,"pointerdown",onDown,{passive:true});
on(D,"keydown",onKey);on(H,"pointerleave",onLeave);on(H,"mouseleave",onLeave);on(W,"blur",onLeave);on(D,"click",onClick);
var ok=true;try{scan()}catch(e){ok=false}safe(frame);
if(ok&&!H.classList.contains("js-fx")){S.addedJs=true;H.classList.add("js-fx")}}
function refresh(){if(!S)return;
safe(scan);S.hosts.forEach(function(h){safe(function(){palette(h);fit(h)})});
S.journeys.forEach(function(j){safe(function(){j.build();j.update()})});
S.navs.forEach(function(n){safe(function(){n.collect();n.cur=-1;n.spy()})});safe(frame)}
function transitionTheme(fn,origin){
var done=false;function run(){if(!done){done=true;fn()}}
if(!S||!S.motion||typeof D.startViewTransition!=="function"){run();return}
try{var r=origin&&origin.getBoundingClientRect?origin.getBoundingClientRect():{left:W.innerWidth/2,top:0,width:0,height:0},
x=r.left+r.width/2,y=r.top+r.height/2,rad=Math.hypot(Math.max(x,W.innerWidth-x),Math.max(y,W.innerHeight-y));
var t=D.startViewTransition(run);
t.ready.then(function(){H.animate({clipPath:["circle(0px at "+x+"px "+y+"px)","circle("+rad+"px at "+x+"px "+y+"px)"]},
{duration:500,easing:BASE,pseudoElement:"::view-transition-new(root)"})},function(){});
if(t.finished&&t.finished.catch)t.finished.catch(function(){})}catch(e){run()}}
function destroy(){if(!S)return;var s=S;
s.hosts.forEach(dropHost);qa(s.root,".fx-tilt-html,.fx-tilt-svg").forEach(function(e){e.classList.remove("fx-tilt-html","fx-tilt-svg")});
if(s.addedJs)H.classList.remove("js-fx");
s.journeys.forEach(function(j){[j.base,j.ink,j.g].forEach(function(e){if(e.parentNode)e.parentNode.removeChild(e)})});
s.navs.forEach(function(n){if(n.ind.parentNode)n.ind.parentNode.removeChild(n.ind);n.links.forEach(function(a){a.removeAttribute("aria-current")})});
s.counts.forEach(function(c){c.fin()});
s.pills.forEach(function(p){if(p.open)p.set(false,false);p.root.classList.remove("fx-overlay","is-open","fx-ready");if(p.burger&&p.burger.parentNode)p.burger.parentNode.removeChild(p.burger);
p.tg.removeAttribute("aria-expanded");qa(p.pn,"a").forEach(function(a){a.style.removeProperty("--fx-i")})});
unwords(s.root);
qa(s.root,"[data-fx-draw]").forEach(function(e){if(s.dp.has(e))drawClear(e)});
s.dr.forEach(function(a){a.cancel()});s.anim.forEach(function(v,d){v.a.finish()});
qa(s.root,"[data-fx-reveal]").forEach(function(e){e.classList.remove("fx-in");e.style.removeProperty("--fx-delay")});
onLeave();s.off.forEach(function(f){safe(f)});S=null;H.removeAttribute("data-motion")}
W.NHBEffects={init:function(r,o){safe(function(){init(r,o)})},refresh:function(){safe(refresh)},
setMotion:function(v){safe(function(){if(!S)PRE=!!v;setMotion(v)})},
motionEnabled:function(){return H.getAttribute("data-motion")==="on"},
transitionTheme:function(fn,o){try{transitionTheme(fn,o)}catch(e){if(typeof fn==="function")fn()}},destroy:function(){safe(destroy)}};
})();
"""
