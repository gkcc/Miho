const MODES=[['moc','混沌回忆'],['pf','虚构叙事'],['as','末日幻影'],['aa','异相仲裁']];
const VIEWS=[['trend','趋势'],['latest','排行'],['heatmap','热力']];
const ROLES=[['all','全部'],['main_dps','主C'],['sub_dps','副C'],['support','辅助'],['sustain','生存位'],['unknown','未分类']];
const TIERS=['T0','T0.5','T1','T1.5','T2','未分档'];
const TIER_RANK={'T0':0,'T0.5':0.5,'T1':1,'T1.5':1.5,'T2':2,'T3':3,'T4':4,'T5':5};
const CORE_ROLES=new Set(['main_dps','sub_dps']);
const BUILD_LEVELS=[0,20,40,50,60,70,75,80];
const BUILD_EIDOLONS=[['unset','未录入'],[0,'0魂'],[1,'1魂'],[2,'2魂'],[3,'3魂'],[4,'4魂'],[5,'5魂'],[6,'6魂']];
const BUILD_SIGNATURES=[['unset','未录入'],['no','无专武'],['yes','有专武']];
const BUILD_TRACES=[['unset','未录入',0],['low','低',0.32],['mid','中',0.58],['high','高',0.82],['max','满',1]];
const BUILD_RELICS=[['unset','未录入',0],['none','未刷',0.12],['ok','可用',0.58],['good','成型',0.82],['great','毕业',1]];
const ELEMENT_ORDER=['物理','火','冰','雷','风','量子','虚数'];
const PATH_ORDER=['毁灭','巡猎','智识','同谐','虚无','存护','丰饶','记忆','欢愉'];
const COLORS=['#2563eb','#dc2626','#16a34a','#9333ea','#ea580c','#0891b2','#be123c','#4f46e5','#65a30d','#a16207','#0f766e','#7c3aed','#db2777','#475569'];
const BOX_KEY='hsr_endgame_box_v1';
const REC_KEY='hsr_endgame_recommender_v1';
let DATA=null;
let state={page:'analysis',mode:'moc',view:'trend',role:'main_dps',tiers:new Set(TIERS),metric:'app_rate',limit:'12',search:'',avatars:true,focus:null,hover:null};
let box={owned:new Set(),builds:{},buildSlug:'',element:'all',path:'all',role:'all',rarity:'all',status:'all',search:'',saveStatus:'浏览器缓存'};
let rec={mode:'moc',scope:'',elements:{},gap:'1',riskMode:'warn',limit:'8',search:''};
let banner={phase:'current',search:''};
let boxSaveTimer=null;

const $=id=>document.getElementById(id);
const ns='http://www.w3.org/2000/svg';
function number(v){const n=Number(v);return Number.isFinite(n)?n:null}
function pct(v){const n=number(v);return n==null?'':`${n.toFixed(2)}%`}
function fmtMetric(v){const n=number(v);if(n==null)return '';return state.metric==='app_rate'?`${n.toFixed(2)}%`:n.toFixed(2)}
function esc(v){return String(v??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}
function safeRelativeUrl(v,requirePath=false){const text=String(v??'').trim();if(!text||text.startsWith('/')||text.includes('\\')||/[\u0000-\u001f\u007f]/.test(text)||/^[a-z][a-z0-9+.-]*:/i.test(text)||text.startsWith('//'))return '';let path=text.split(/[?#]/,1)[0];try{for(let i=0;i<3;i++){const decoded=decodeURIComponent(path);if(decoded===path)break;path=decoded;}}catch{return '';}if(path.startsWith('/')||path.includes('\\')||path.split('/').includes('..')||(requirePath&&!path))return '';return text}
function safeLinkUrl(v){const text=String(v??'').trim();if(!text||text.includes('\\')||/[\u0000-\u001f\u007f]/.test(text))return '';if(/^[a-z][a-z0-9+.-]*:/i.test(text)){try{const url=new URL(text);return ['http:','https:'].includes(url.protocol)&&url.host?text:'';}catch{return '';}}return safeRelativeUrl(text,false)}
function safeAvatarUrl(v){return safeRelativeUrl(v,true)}

fetch(`./data.json?v=${Date.now()}`,{cache:'no-store'})
  .then(r=>r.json())
  .then(data=>{DATA=data;loadBox();loadRecSettings();init();render();syncBoxFromServer();})
  .catch(err=>{document.body.innerHTML=`<main class="app-shell"><h1>数据加载失败</h1><p>${esc(err.message)}</p></main>`;});

function init(){
  $('metaLine').textContent=`Prydwen T榜更新：${DATA.meta.tierUpdatedAt||DATA.meta.tierUpdatedDate||'未知'} · 本地数据生成：${DATA.meta.generatedAt||'未知'} · Box 自动保存`;
  makeButtons('appTabs',[['analysis','趋势分析'],['banner','卡池情报'],['box','我的Box'],['recommender','组队推荐']],state.page,v=>{state.page=v;render();});
  makeButtons('modeControl',MODES,state.mode,v=>{state.mode=v;state.focus=null;state.hover=null;render();});
  makeButtons('viewControl',VIEWS,state.view,v=>{state.view=v;state.focus=null;state.hover=null;render();});
  makeButtons('roleControl',ROLES,state.role,v=>{state.role=v;state.focus=null;state.hover=null;render();});
  const tierBox=$('tierControl');
  TIERS.forEach(t=>{const b=document.createElement('button');b.type='button';b.textContent=t;b.className='active';b.title=`显示或隐藏 ${t}`;b.onclick=()=>{state.tiers.has(t)?state.tiers.delete(t):state.tiers.add(t);b.classList.toggle('active',state.tiers.has(t));state.focus=null;state.hover=null;render();};tierBox.appendChild(b);});
  $('limitSelect').onchange=e=>{state.limit=e.target.value;render();};
  $('metricSelect').onchange=e=>{state.metric=e.target.value;render();};
  $('searchInput').oninput=e=>{state.search=e.target.value.trim().toLowerCase();state.focus=null;state.hover=null;render();};
  $('avatarToggle').onchange=e=>{state.avatars=e.target.checked;render();};
  $('resetBtn').onclick=resetCurrentPage;
  initBannerControls();
  initBoxControls();
  initRecommenderControls();
}

function initBannerControls(){
  makeButtons('bannerPhaseControl',[['current','当期UP'],['next','后续卡池'],['recent','历史参考'],['all','全部含已结束']],banner.phase,v=>{banner.phase=v;renderBanner();});
  $('bannerSearchInput').oninput=e=>{banner.search=e.target.value.trim().toLowerCase();renderBanner();};
}

function initBoxControls(){
  const elements=['all',...ELEMENT_ORDER.filter(x=>DATA.rosterRows.some(r=>r.element_cn===x))];
  const paths=['all',...PATH_ORDER.filter(x=>DATA.rosterRows.some(r=>r.path_cn===x))];
  makeButtons('boxElementControl',elements.map(x=>[x,x==='all'?'全部':x]),box.element,v=>{box.element=v;renderBox();});
  makeButtons('boxPathControl',paths.map(x=>[x,x==='all'?'全部':x]),box.path,v=>{box.path=v;renderBox();});
  makeButtons('boxRoleControl',ROLES.map(([v,l])=>[v,l]),box.role,v=>{box.role=v;renderBox();});
  $('boxRaritySelect').onchange=e=>{box.rarity=e.target.value;renderBox();};
  $('boxOwnedSelect').onchange=e=>{box.status=e.target.value;renderBox();};
  $('boxSearchInput').oninput=e=>{box.search=e.target.value.trim().toLowerCase();renderBox();};
  $('boxExportBtn').onclick=exportBox;
  $('boxImportBtn').onclick=()=>$('boxImportInput').click();
  $('boxImportInput').onchange=importBox;
  $('boxMarkVisibleBtn').onclick=()=>markVisible(true);
  $('boxClearVisibleBtn').onclick=()=>markVisible(false);
  $('boxBuildVisibleBtn').onclick=()=>setVisibleBuild('max');
  $('boxClearBuildVisibleBtn').onclick=()=>setVisibleBuild('clear');
  initBuildControls();
}

function initBuildControls(){
  $('buildLevelSelect').innerHTML=BUILD_LEVELS.map(v=>`<option value="${v}">${v?`${v}级`:'未录入'}</option>`).join('');
  $('buildLcSelect').innerHTML=BUILD_LEVELS.map(v=>`<option value="${v}">${v?`${v}级`:'未录入'}</option>`).join('');
  $('buildEidolonSelect').innerHTML=BUILD_EIDOLONS.map(([v,l])=>`<option value="${v}">${l}</option>`).join('');
  $('buildSignatureSelect').innerHTML=BUILD_SIGNATURES.map(([v,l])=>`<option value="${v}">${l}</option>`).join('');
  $('buildTraceSelect').innerHTML=BUILD_TRACES.map(([v,l])=>`<option value="${v}">${l}</option>`).join('');
  $('buildRelicSelect').innerHTML=BUILD_RELICS.map(([v,l])=>`<option value="${v}">${l}</option>`).join('');
  $('buildLevelSelect').onchange=e=>updateBuildField('level',Number(e.target.value)||0);
  $('buildLcSelect').onchange=e=>updateBuildField('lc',Number(e.target.value)||0);
  $('buildEidolonSelect').onchange=e=>updateBuildField('eidolon',e.target.value==='unset'?'unset':Number(e.target.value));
  $('buildSignatureSelect').onchange=e=>updateBuildField('signature',e.target.value);
  $('buildTraceSelect').onchange=e=>updateBuildField('traces',e.target.value);
  $('buildRelicSelect').onchange=e=>updateBuildField('relics',e.target.value);
  $('buildMaxBtn').onclick=()=>setBuildPreset('max');
  $('buildClearBtn').onclick=()=>setBuildPreset('clear');
}

function initRecommenderControls(){
  const modes=MODES.filter(([mode])=>DATA.teamTemplates?.some(t=>t.mode===mode));
  if(modes.length&&!modes.some(([mode])=>mode===rec.mode))rec.mode=modes[0][0];
  makeButtons('recModeControl',modes.length?modes:MODES,rec.mode,v=>{rec.mode=v;ensureRecScope();saveRecSettings();syncRecControls();renderRecommender();});
  $('recScopeSelect').onchange=e=>{rec.scope=e.target.value;saveRecSettings();syncRecControls();renderRecommender();};
  const elementBox=$('recElementControl');
  elementBox.innerHTML='';
  ELEMENT_ORDER.forEach(element=>{const b=document.createElement('button');b.type='button';b.textContent=element;b.title=`${element} 推荐属性`;b.onclick=()=>{const set=recElementSet();set.has(element)?set.delete(element):set.add(element);setRecElementSet(set);saveRecSettings();syncRecControls();renderRecommender();};elementBox.appendChild(b);});
  $('recGapSelect').onchange=e=>{rec.gap=e.target.value;saveRecSettings();renderRecommender();};
  $('recRiskSelect').onchange=e=>{rec.riskMode=e.target.value;saveRecSettings();renderRecommender();};
  $('recLimitSelect').onchange=e=>{rec.limit=e.target.value;saveRecSettings();renderRecommender();};
  $('recSearchInput').oninput=e=>{rec.search=e.target.value.trim().toLowerCase();saveRecSettings();renderRecommender();};
  ensureRecScope();
  syncRecControls();
}

function makeButtons(id,items,current,onClick){
  const boxEl=$(id);boxEl.innerHTML='';
  items.forEach(([value,label])=>{const b=document.createElement('button');b.type='button';b.textContent=label;b.dataset.value=value;b.className=value===current?'active':'';b.title=label;b.onclick=()=>{[...boxEl.children].forEach(x=>x.classList.remove('active'));b.classList.add('active');onClick(value);};boxEl.appendChild(b);});
}

function resetCurrentPage(){
  if(state.page==='banner'){
    banner={phase:'current',search:''};
    [...$('bannerPhaseControl').children].forEach(b=>b.classList.toggle('active',b.dataset.value===banner.phase));
    $('bannerSearchInput').value='';
    renderBanner();return;
  }
  if(state.page==='recommender'){
    rec={...rec,mode:'moc',scope:'',gap:'1',riskMode:'warn',limit:'8',search:''};
    ensureRecScope();saveRecSettings();syncRecControls();renderRecommender();return;
  }
  if(state.page==='box'){
    box={...box,buildSlug:'',element:'all',path:'all',role:'all',rarity:'all',status:'all',search:''};
    syncBoxControls();renderBox();return;
  }
  state={...state,mode:'moc',view:'trend',role:'main_dps',tiers:new Set(TIERS),metric:'app_rate',limit:'12',search:'',avatars:true,focus:null,hover:null};
  syncAnalysisControls();renderAnalysis();
}

function syncAnalysisControls(){
  [...$('modeControl').children].forEach(b=>b.classList.toggle('active',b.dataset.value===state.mode));
  [...$('viewControl').children].forEach(b=>b.classList.toggle('active',b.dataset.value===state.view));
  [...$('roleControl').children].forEach(b=>b.classList.toggle('active',b.dataset.value===state.role));
  [...$('tierControl').children].forEach(b=>b.classList.toggle('active',state.tiers.has(b.textContent)));
  $('limitSelect').value=state.limit;$('metricSelect').value=state.metric;$('searchInput').value=state.search;$('avatarToggle').checked=state.avatars;
}

function syncBoxControls(){
  [...$('boxElementControl').children].forEach(b=>b.classList.toggle('active',b.dataset.value===box.element));
  [...$('boxPathControl').children].forEach(b=>b.classList.toggle('active',b.dataset.value===box.path));
  [...$('boxRoleControl').children].forEach(b=>b.classList.toggle('active',b.dataset.value===box.role));
  $('boxRaritySelect').value=box.rarity;$('boxOwnedSelect').value=box.status;$('boxSearchInput').value=box.search;
}

function syncRecControls(){
  [...$('recModeControl').children].forEach(b=>b.classList.toggle('active',b.dataset.value===rec.mode));
  const options=recScopeOptions(rec.mode);
  const select=$('recScopeSelect');
  select.innerHTML=options.map(o=>`<option value="${esc(o.key)}">${esc(o.label)}</option>`).join('');
  if(!options.some(o=>o.key===rec.scope))rec.scope=options[0]?.key||'';
  select.value=rec.scope;
  const selected=recElementSet();
  [...$('recElementControl').children].forEach(b=>b.classList.toggle('active',selected.has(b.textContent)));
  $('recGapSelect').value=rec.gap;$('recRiskSelect').value=rec.riskMode||'warn';$('recLimitSelect').value=rec.limit;$('recSearchInput').value=rec.search;
}

function render(){
  $('analysisView').classList.toggle('hidden',state.page!=='analysis');
  $('bannerView').classList.toggle('hidden',state.page!=='banner');
  $('boxView').classList.toggle('hidden',state.page!=='box');
  $('recommenderView').classList.toggle('hidden',state.page!=='recommender');
  [...$('appTabs').children].forEach(b=>b.classList.toggle('active',b.dataset.value===state.page));
  if(state.page==='banner')renderBanner();else if(state.page==='box')renderBox();else if(state.page==='recommender')renderRecommender();else renderAnalysis();
}

function sourceRows(){
  return DATA.usageRows&&DATA.usageRows.length?DATA.usageRows:DATA.trendRows;
}

function filteredRows(){
  const q=state.search;
  const rows=sourceRows().filter(r=>
    r.tier_mode===state.mode &&
    (state.role==='all'||r.role_group===state.role) &&
    state.tiers.has(r.tier||'未分档') &&
    (!q || [r.character_name_cn,r.character_name_en,r.character_slug,r.tags,r.tier,r.element_cn,r.path_cn].some(x=>String(x||'').toLowerCase().includes(q)))
  );
  const seen=new Set();
  return rows.filter(r=>{
    const key=`${r.tier_mode}|${r.collect_date}|${r.character_slug}`;
    if(state.role==='all'&&seen.has(key))return false;
    seen.add(key);return true;
  });
}

function groupSeries(rows){
  const map=new Map();
  rows.forEach(r=>{if(!map.has(r.character_slug))map.set(r.character_slug,[]);map.get(r.character_slug).push(r);});
  const list=[...map.entries()].map(([slug,points])=>{
    points.sort((a,b)=>String(a.collect_date).localeCompare(String(b.collect_date)));
    const latest=points[points.length-1];
    return{slug,points,latest,max:Math.max(...points.map(p=>number(p[state.metric])||0),0)};
  });
  list.sort((a,b)=>(number(b.latest.app_rate)||0)-(number(a.latest.app_rate)||0)||(number(b.latest.rating)||0)-(number(a.latest.rating)||0)||a.slug.localeCompare(b.slug));
  return list;
}

function limitSeries(series){return state.limit==='all'?series:series.slice(0,Number(state.limit)||12)}

function renderAnalysis(){
  hideTooltip();
  const rows=filteredRows();
  const allSeries=groupSeries(rows);
  const series=limitSeries(allSeries);
  const modeLabel=MODES.find(x=>x[0]===state.mode)?.[1]||state.mode;
  const roleLabel=ROLES.find(x=>x[0]===state.role)?.[1]||state.role;
  const viewLabel=VIEWS.find(x=>x[0]===state.view)?.[1]||state.view;
  $('chartTitle').textContent=`${modeLabel} · ${roleLabel} · ${viewLabel}`;
  const aaNote=state.mode==='aa'?' · AA 为全 Boss / 未拆分本地数据':'';
  $('chartSubtitle').textContent=`展示 ${series.length}/${allSeries.length} 个角色，${rows.length} 个采样点${aaNote}`;
  $('summaryBadges').innerHTML=[`${[...state.tiers].join(' / ')||'未选T档'}`,state.metric==='app_rate'?'出场率':'平均值',state.limit==='all'?'全量':`Top ${state.limit}`].map(x=>`<span>${esc(x)}</span>`).join('');
  if(state.view==='latest')renderLatest(series);else if(state.view==='heatmap')renderHeatmap(series);else renderTrend(series,rows);
  renderCharacters(series);
  renderChangelog(series.length?series:allSeries);
}

function chartBox(){const svg=$('chart');svg.innerHTML='';const rect=svg.getBoundingClientRect();const width=Math.max(760,Math.round(rect.width||1000));const height=Math.max(560,Math.round(rect.height||620));svg.setAttribute('viewBox',`0 0 ${width} ${height}`);return{svg,width,height}}
function add(svg,tag,attrs,parent=svg){const el=document.createElementNS(ns,tag);Object.entries(attrs).forEach(([k,v])=>el.setAttribute(k,v));parent.appendChild(el);return el}
function renderEmpty(svg,width,height){add(svg,'text',{x:width/2,y:height/2,'text-anchor':'middle',class:'empty-state'}).textContent='当前筛选没有数据'}

function renderTrend(series,rows){
  const {svg,width,height}=chartBox();if(!series.length){renderEmpty(svg,width,height);return;}
  const margin={l:62,r:28,t:34,b:54};const cw=width-margin.l-margin.r,ch=height-margin.t-margin.b;
  const dates=[...new Set(rows.map(r=>r.collect_date))].sort();const metric=state.metric;
  const values=rows.map(r=>number(r[metric])).filter(v=>v!=null&&v>=0&&(metric!=='avg_round'||v<99));const max=Math.max(10,...values)*1.14;
  const x=d=>margin.l+(dates.length<=1?cw/2:cw*dates.indexOf(d)/(dates.length-1));const y=v=>margin.t+ch-ch*(Math.min(v,max))/max;
  drawAxes(svg,margin,cw,ch,max,dates,x,y,metric);const defs=add(svg,'defs',{});
  series.forEach((s,idx)=>{const color=COLORS[idx%COLORS.length];const pts=s.points.map(p=>[x(p.collect_date),y(number(p[metric])||0),p]).filter(p=>Number.isFinite(p[1]));if(!pts.length)return;const path=pts.map((p,i)=>`${i?'L':'M'}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(' ');const line=add(svg,'path',{d:path,stroke:color,class:`series-line ${dimClass(s.slug)}`});line.dataset.slug=s.slug;const hit=add(svg,'path',{d:path,class:'series-hit'});hit.dataset.slug=s.slug;bindHover(hit,s.latest,s.slug);pts.forEach(([xx,yy,p],pi)=>drawPoint(svg,defs,xx,yy,p,s.slug,color,idx,pi,11));});
}

function drawAxes(svg,margin,cw,ch,max,dates,x,y,metric){
  const label=metric==='app_rate'?'出场率 %':'平均值';
  for(let i=0;i<=5;i++){const val=max*i/5,yy=y(val);add(svg,'line',{x1:margin.l,y1:yy,x2:margin.l+cw,y2:yy,class:'grid'});add(svg,'text',{x:margin.l-10,y:yy+4,'text-anchor':'end',class:'axis-label'}).textContent=val.toFixed(0);}
  add(svg,'line',{x1:margin.l,y1:margin.t,x2:margin.l,y2:margin.t+ch,class:'axis-line'});add(svg,'line',{x1:margin.l,y1:margin.t+ch,x2:margin.l+cw,y2:margin.t+ch,class:'axis-line'});add(svg,'text',{x:margin.l,y:22,class:'axis-label'}).textContent=label;
  dates.forEach((d,i)=>{if(dates.length>14&&i%2===1)return;add(svg,'text',{x:x(d),y:margin.t+ch+24,'text-anchor':'middle',class:'axis-label'}).textContent=String(d).slice(5);});
}

function drawPoint(svg,defs,x,y,row,slug,color,seriesIndex,pointIndex,radius){
  const icon=safeAvatarUrl(row.icon_url);if(state.avatars&&icon){const clipId=`clip-${seriesIndex}-${pointIndex}-${Math.round(x)}-${Math.round(y)}`;const clip=add(svg,'clipPath',{id:clipId},defs);add(svg,'circle',{cx:x,cy:y,r:radius},clip);const img=add(svg,'image',{href:icon,x:x-radius,y:y-radius,width:radius*2,height:radius*2,'clip-path':`url(#${clipId})`,class:`avatar-node ${dimClass(slug)}`});img.dataset.slug=slug;add(svg,'circle',{cx:x,cy:y,r:radius,fill:'none',stroke:color,class:`avatar-ring ${dimClass(slug)}`});bindHover(img,row,slug);img.addEventListener('click',()=>toggleFocus(slug));}
  else{const c=add(svg,'circle',{cx:x,cy:y,r:4.6,fill:color,class:`point-node ${dimClass(slug)}`});c.dataset.slug=slug;bindHover(c,row,slug);c.addEventListener('click',()=>toggleFocus(slug));}
}

function renderLatest(series){
  const {svg,width,height}=chartBox();if(!series.length){renderEmpty(svg,width,height);return;}
  const margin={l:158,r:48,t:36,b:38};const rowH=Math.max(34,Math.min(48,(height-margin.t-margin.b)/Math.max(series.length,1)));const chartH=rowH*series.length;const metric=state.metric;
  const values=series.map(s=>number(s.latest[metric])).filter(v=>v!=null&&v>=0&&(metric!=='avg_round'||v<99));const max=Math.max(10,...values)*1.12;const x=v=>margin.l+(width-margin.l-margin.r)*Math.min(v,max)/max;
  add(svg,'text',{x:margin.l,y:22,class:'axis-label'}).textContent=metric==='app_rate'?'最近一期出场率 %':'最近一期平均值';
  for(let i=0;i<=4;i++){const val=max*i/4,xx=x(val);add(svg,'line',{x1:xx,y1:margin.t-10,x2:xx,y2:margin.t+chartH,class:'grid'});add(svg,'text',{x:xx,y:margin.t+chartH+22,'text-anchor':'middle',class:'axis-label'}).textContent=val.toFixed(0);}
  const defs=add(svg,'defs',{});series.forEach((s,idx)=>{const row=s.latest;const color=COLORS[idx%COLORS.length];const yy=margin.t+idx*rowH+rowH/2;const val=number(row[metric])||0;const xx=x(val);add(svg,'text',{x:18,y:yy-2,class:`rank-label ${dimClass(s.slug)}`}).textContent=`${idx+1}. ${row.character_name_cn||row.character_name_en||s.slug}`;add(svg,'text',{x:18,y:yy+14,class:`muted-label ${dimClass(s.slug)}`}).textContent=`${row.tier} · ${row.tags||row.path_cn||row.character_name_en||''}`;const bar=add(svg,'line',{x1:margin.l,y1:yy,x2:xx,y2:yy,stroke:color,'stroke-width':8,'stroke-linecap':'round',class:`bar-line ${dimClass(s.slug)}`});bar.dataset.slug=s.slug;bindHover(bar,row,s.slug);drawPoint(svg,defs,xx,yy,row,s.slug,color,idx,0,14);add(svg,'text',{x:Math.min(width-42,xx+18),y:yy+4,class:'axis-label'}).textContent=fmtMetric(val);});
}

function renderHeatmap(series){
  const {svg,width,height}=chartBox();if(!series.length){renderEmpty(svg,width,height);return;}
  const rows=series.flatMap(s=>s.points);const dates=[...new Set(rows.map(r=>r.collect_date))].sort();const metric=state.metric;const margin={l:156,r:24,t:42,b:36};const cellGap=4;const cw=(width-margin.l-margin.r-(dates.length-1)*cellGap)/Math.max(dates.length,1);const rowH=Math.max(28,Math.min(42,(height-margin.t-margin.b)/Math.max(series.length,1)));const values=rows.map(r=>number(r[metric])).filter(v=>v!=null&&v>=0&&(metric!=='avg_round'||v<99));const max=Math.max(10,...values);const defs=add(svg,'defs',{});
  dates.forEach((d,i)=>add(svg,'text',{x:margin.l+i*(cw+cellGap)+cw/2,y:24,'text-anchor':'middle',class:'heat-head'}).textContent=String(d).slice(5));
  series.forEach((s,idx)=>{const rowY=margin.t+idx*rowH;const latest=s.latest;add(svg,'text',{x:48,y:rowY+rowH/2+4,class:`heat-name ${dimClass(s.slug)}`}).textContent=latest.character_name_cn||latest.character_name_en||s.slug;drawMiniAvatar(svg,defs,24,rowY+rowH/2,latest,s.slug,idx);const byDate=new Map(s.points.map(p=>[p.collect_date,p]));dates.forEach((d,j)=>{const p=byDate.get(d);const val=number(p?.[metric])||0;const intensity=Math.max(.08,Math.min(1,val/max));const fill=metric==='app_rate'?`rgba(23,76,90,${intensity})`:`rgba(37,99,235,${intensity})`;const rect=add(svg,'rect',{x:margin.l+j*(cw+cellGap),y:rowY+5,width:Math.max(10,cw),height:rowH-10,fill,class:`heat-cell ${dimClass(s.slug)}`});rect.dataset.slug=s.slug;if(p)bindHover(rect,p,s.slug);rect.addEventListener('click',()=>toggleFocus(s.slug));});});
}

function drawMiniAvatar(svg,defs,x,y,row,slug,index){const icon=safeAvatarUrl(row.icon_url);if(!icon)return;const clipId=`mini-${index}-${slug}`;const clip=add(svg,'clipPath',{id:clipId},defs);add(svg,'circle',{cx:x,cy:y,r:14},clip);const img=add(svg,'image',{href:icon,x:x-14,y:y-14,width:28,height:28,'clip-path':`url(#${clipId})`,class:`avatar-node ${dimClass(slug)}`});img.dataset.slug=slug;bindHover(img,row,slug);img.addEventListener('click',()=>toggleFocus(slug));}
function activeSlug(){return state.focus||state.hover}
function dimClass(slug){const active=activeSlug();return active&&active!==slug?'dim':state.focus===slug?'focused':''}
function toggleFocus(slug){state.focus=state.focus===slug?null:slug;state.hover=null;renderAnalysis();}
function setHover(slug){state.hover=slug;updateFocusClasses();}
function clearHover(){state.hover=null;updateFocusClasses();hideTooltip();}
function updateFocusClasses(){const active=activeSlug();document.querySelectorAll('[data-slug]').forEach(el=>{const slug=el.dataset.slug;el.classList.toggle('dim',Boolean(active&&active!==slug));el.classList.toggle('focused',Boolean(state.focus&&state.focus===slug));});document.querySelectorAll('.character-card').forEach(el=>{const slug=el.dataset.slug;el.classList.toggle('dim',Boolean(active&&active!==slug));el.classList.toggle('active',Boolean(state.focus&&state.focus===slug));});}
function bindHover(el,row,slug){el.addEventListener('mouseenter',evt=>{setHover(slug);showTooltip(evt,row);});el.addEventListener('mousemove',moveTooltip);el.addEventListener('mouseleave',clearHover);}

function showTooltip(evt,row){
  const tt=$('tooltip');tt.hidden=false;
  tt.innerHTML=`<div class="tooltip-head"><img src="${esc(row.icon_url)}" alt=""><div><strong>${esc(row.character_name_cn||row.character_name_en||row.character_slug)}</strong><span>${esc(row.character_name_en)} · ${esc(row.character_slug)}</span></div></div><div class="tooltip-grid"><b>模式</b><div>${esc(row.tier_mode_cn)}${row.sub_mode_cn?` · ${esc(row.sub_mode_cn)}`:''}</div><b>职能/T档</b><div>${esc(row.role_group_cn)} · ${esc(row.tier)}${row.rating?` (${esc(row.rating)})`:''}</div><b>属性/命途</b><div>${esc(row.element_cn||'')} ${esc(row.path_cn||'')}</div><b>日期/期数</b><div>${esc(row.collect_date)} · ${esc(row.phase_ver)}</div><b>出场率</b><div>${pct(row.app_rate)}</div><b>平均值</b><div>${esc(row.avg_round??'')}</div><b>标签</b><div>${esc(row.tags||'')}</div><b>质量标记</b><div>${esc(row.quality_flag||'')}</div></div>`;
  moveTooltip(evt);
}
function moveTooltip(evt){const target=evt.currentTarget;const tt=target?.closest?.('.box-card')?$('boxTooltip'):(target?.closest?.('.rec-card')||target?.closest?.('.rec-slate-card'))?$('recTooltip'):$('tooltip');const pad=14;let x=evt.clientX+16,y=evt.clientY+16;const rect=tt.getBoundingClientRect();if(x+rect.width+pad>window.innerWidth)x=evt.clientX-rect.width-16;if(y+rect.height+pad>window.innerHeight)y=evt.clientY-rect.height-16;tt.style.left=`${Math.max(pad,x)}px`;tt.style.top=`${Math.max(pad,y)}px`;}
function hideTooltip(){$('tooltip').hidden=true;}

function renderCharacters(series){
  const boxEl=$('characterList');boxEl.innerHTML='';
  series.forEach((s,idx)=>{const r=s.latest;const card=document.createElement('button');card.type='button';card.dataset.slug=s.slug;card.className=`character-card ${state.focus===s.slug?'active':''} ${activeSlug()&&activeSlug()!==s.slug?'dim':''}`;card.onclick=()=>toggleFocus(s.slug);card.onmouseenter=e=>{setHover(s.slug);showTooltip(e,r);};card.onmousemove=moveTooltip;card.onmouseleave=clearHover;card.innerHTML=`<img src="${esc(r.icon_url)}" alt=""><div><div class="name">${idx+1}. ${esc(r.character_name_cn||r.character_name_en||s.slug)}</div><div class="meta">${esc(r.character_name_en)} · ${esc(r.tier)} · ${esc(r.element_cn||'')} ${esc(r.path_cn||r.tags||'')}</div></div><div><span class="pill">${esc(r.tier)}</span><div class="rate">${pct(r.app_rate)}</div></div>`;boxEl.appendChild(card);});
}

function renderChangelog(series){const slugs=new Set(series.map(s=>s.slug));const boxEl=$('changelogList');boxEl.innerHTML='';const related=DATA.changelogRows.filter(r=>String(r.character_slugs||'').split(';').some(s=>slugs.has(s)));const rows=(related.length?related:DATA.changelogRows).slice(0,8);rows.forEach(r=>{const item=document.createElement('div');item.className='changelog-item';const text=String(r.text||'');item.innerHTML=`<time>${esc(r.changelog_date)}</time><p>${esc(text).slice(0,420)}${text.length>420?'...':''}</p>`;boxEl.appendChild(item);});}

function bannerRows(){const q=banner.search;return (DATA.bannerRows||[]).filter(r=>(banner.phase==='all'||r.phase_status===banner.phase)&&(!q||[r.character_slug,r.character_name_cn,r.character_name_en,r.banner_role,r.element_cn,r.path_cn,r.role_group_cns,...(r.analysis_tags||[])].some(x=>String(x||'').toLowerCase().includes(q))));}
function renderBanner(){const rows=bannerRows();$('bannerTitle').textContent='卡池情报';$('bannerSubtitle').textContent='这里只做数据提炼：复刻看历史趋势和组队占用，新角色/联动角色只做公开信息与 Box 关系识别。';$('bannerBadges').innerHTML=[`角色 ${rows.length}`,`Box ${box.owned.size}`,'趋势仅供参考'].map(x=>`<span>${esc(x)}</span>`).join('');const grid=$('bannerGrid');grid.innerHTML='';if(!rows.length){grid.innerHTML='<div class="rec-empty">暂无卡池情报；可更新 configs/hsr_banner_plan.json</div>';return;}const phases=[...new Map(rows.map(r=>[r.phase_id,{id:r.phase_id,title:r.phase_title,subtitle:r.phase_subtitle,date:r.date_range,source:r.source_label,url:r.source_url,status:r.phase_status}])).values()];phases.forEach(phase=>{const section=document.createElement('section');section.className='banner-section';section.innerHTML=`<div class="banner-section-head"><div><h3>${esc(phase.title||'卡池')}</h3><p>${esc(phase.subtitle||'')} · ${esc(phase.date||'时间待确认')}</p></div>${phase.url?`<a href="${esc(phase.url)}" target="_blank" rel="noreferrer">${esc(phase.source||'来源')}</a>`:''}</div><div class="banner-card-grid"></div>`;const inner=section.querySelector('.banner-card-grid');rows.filter(r=>r.phase_id===phase.id).forEach(row=>inner.appendChild(bannerCard(row)));grid.appendChild(section);});}
function bannerCard(row){const slug=row.character_slug,info={...charInfo(slug),...row},ins=bannerInsight(row);const card=document.createElement('article');card.className=`banner-card ${box.owned.has(slug)?'owned':''} ${row.phase_status}`;const tags=(row.analysis_tags||[]).slice(0,5).map(t=>`<span>${esc(t)}</span>`).join('');const name=info.character_name_cn||info.character_name_en||slug;const roleText=info.role_group_cns||roleCn(info)||'未分类';card.innerHTML=`<div class="banner-art">${info.icon_url?`<img src="${esc(info.icon_url)}" alt="" loading="lazy" decoding="async">`:`<div class="avatar-fallback">${esc(name.slice(0,2))}</div>`}<button class="mini-owned" type="button">${box.owned.has(slug)?'已拥有':'加入Box'}</button></div><div class="banner-body"><div class="banner-kicker">${esc(row.banner_role||row.phase_subtitle||'卡池角色')}</div><h3>${esc(name)}</h3><p class="banner-meta">${esc(info.rarity?`${info.rarity}星`:'-')} · ${esc(info.element_cn||'属性未知')} · ${esc(info.path_cn||'命途未知')} · ${esc(roleText)} · ${esc(ins.tierText)}</p><svg class="spark" viewBox="0 0 220 54">${sparkline(ins.points)}</svg><div class="rec-tags">${tags}</div><div class="banner-facts">${ins.lines.slice(0,4).map(x=>`<p>${esc(x)}</p>`).join('')}</div><div class="banner-relations">${ins.relations.slice(0,6).map(x=>`<span class="${x.owned?'owned':''}">${esc(x.name)}${x.count?` ×${x.count}`:''}</span>`).join('')||'<span>暂无历史组合</span>'}</div></div>`;card.querySelector('.mini-owned').onclick=e=>{e.stopPropagation();box.owned.has(slug)?box.owned.delete(slug):box.owned.add(slug);box.buildSlug=slug;saveBox();renderBanner();};card.addEventListener('mouseenter',e=>showBannerTooltip(e,row,ins));card.addEventListener('mousemove',moveBannerTooltip);card.addEventListener('mouseleave',()=>{$('bannerTooltip').hidden=true;});return card;}
function bannerInsight(row){const slug=row.character_slug,info={...charInfo(slug),...row};const grouped=new Map();(DATA.usageRows||DATA.trendRows||[]).filter(r=>r.character_slug===slug&&(r.sub_mode==='all'||r.sub_mode==='all_bosses'||!r.sub_mode)).forEach(r=>{const key=`${r.tier_mode||r.mode}|${r.collect_date||r.tier_updated_date||''}`;const current=grouped.get(key);if(!current||Number(r.app_rate||0)>Number(current.app_rate||0))grouped.set(key,r);});const usage=[...grouped.values()].sort((a,b)=>String(a.collect_date||a.tier_updated_date).localeCompare(String(b.collect_date||b.tier_updated_date)));const points=usage.map(r=>({date:r.collect_date||r.tier_updated_date,value:number(r.app_rate)||0,mode:r.tier_mode_cn||r.mode_cn||r.tier_mode||r.mode}));const tierText=tierSummaryFor(slug),tierDetails=tierDetailsFor(slug);const teams=(DATA.teamTemplates||[]).filter(t=>(t.chars||[]).includes(slug));const relations=relationRows(slug,teams);const ownedRelation=relations.filter(r=>r.owned).slice(0,4).map(r=>r.name).join('、');const lines=[`T档：Prydwen 按模式分档，${tierText}。`];if(points.length){const latest=points[points.length-1],recent=points.slice(-3),avg=recent.reduce((s,p)=>s+p.value,0)/recent.length,delta=points.length>1?latest.value-points[0].value:0;lines.push(`历史：${points.length} 个样本点，最新 ${latest.value.toFixed(2)}%，近三期均值 ${avg.toFixed(2)}%，首尾变化 ${delta.toFixed(2)}%。`);}else lines.push('历史：本地高难暂无完整样本，不能用趋势替代实测。');if(teams.length){const bestRank=Math.min(...teams.map(t=>number(t.rank)||9999));lines.push(`组队：历史模板 ${teams.length} 条，最好 Rank ${bestRank}，常见队友见下方关系。`);}else lines.push('组队：暂无可回溯历史队伍，等待实测或人工分析。');if(ownedRelation)lines.push(`Box关系：你已有角色中，历史上相关度较高的是 ${ownedRelation}。`);else lines.push('Box关系：暂未发现与你已有 Box 的直接历史组合；需要看属性、命途与队友缺口。');if(row.phase_status==='next'||!points.length)lines.push('未知项：技能组、倍率、光锥价值、实战轴和环境适配仍需外部分析确认。');if(row.focus)lines.push(`关注点：${row.focus}`);return{points,relations,lines,tierText,tierDetails};}
function tierRowsFor(slug){const resolved=canonicalSlug(slug);return (DATA.tierRows||[]).filter(r=>canonicalSlug(r.character_slug)===resolved);}
function bestTierInMode(slug,mode){return tierRowsFor(slug).filter(r=>r.tier_mode===mode).sort((a,b)=>(TIER_RANK[a.tier]??9)-(TIER_RANK[b.tier]??9))[0]||null;}
function tierSummaryFor(slug){const modes=[['moc','混沌'],['pf','虚构'],['as','末日']];const rows=tierRowsFor(slug);if(!rows.length)return '未分档';return modes.map(([mode,label])=>{const row=bestTierInMode(slug,mode);return `${label} ${row?.tier||'未分档'}`;}).join(' / ');}
function tierDetailsFor(slug){const modes=[['moc','混沌回忆'],['pf','虚构叙事'],['as','末日幻影']];const rows=tierRowsFor(slug);if(!rows.length)return 'Prydwen 当前未收录 T 档';return modes.map(([mode,label])=>{const row=bestTierInMode(slug,mode);return `${label}：${row?`${row.role_group_cn||row.role_group||''} ${row.tier}`:'未分档'}`;}).join('；');}
function relationRows(slug,teams){const map=new Map();teams.forEach(t=>(t.chars||[]).forEach(c=>{if(c===slug)return;const item=map.get(c)||{slug:c,name:charName(c),count:0,owned:box.owned.has(c)};item.count++;item.owned=box.owned.has(c);map.set(c,item);}));return [...map.values()].sort((a,b)=>Number(b.owned)-Number(a.owned)||b.count-a.count||a.name.localeCompare(b.name));}
function sparkline(points){if(!points.length)return '<text x="10" y="31" class="spark-empty">暂无趋势</text>';const max=Math.max(1,...points.map(p=>p.value)),xs=points.map((p,i)=>8+i*(204/Math.max(1,points.length-1))),ys=points.map(p=>46-(p.value/max)*36),d=xs.map((x,i)=>`${i?'L':'M'}${x.toFixed(1)} ${ys[i].toFixed(1)}`).join(' ');return `<path d="${d}" class="spark-line"/><path d="M8 47H212" class="spark-axis"/>${xs.map((x,i)=>`<circle cx="${x.toFixed(1)}" cy="${ys[i].toFixed(1)}" r="3.2" class="spark-dot"/>`).join('')}`;}
function showBannerTooltip(evt,row,ins){const tt=$('bannerTooltip');tt.innerHTML=`<div class="tooltip-grid"><b>角色</b><span>${esc(row.character_name_cn||row.character_name_en||row.character_slug)}</span><b>阶段</b><span>${esc(row.phase_title||'-')}</span><b>定位</b><span>${esc([row.element_cn,row.path_cn,row.role_group_cns].filter(Boolean).join(' · ')||'未知')}</span><b>模式T档</b><span>${esc(ins.tierDetails||ins.tierText||'未分档')}</span><b>分析输入</b><span>${esc(ins.lines.join('；'))}</span></div>`;tt.hidden=false;moveBannerTooltip(evt);}
function moveBannerTooltip(evt){const tt=$('bannerTooltip');let x=evt.clientX+16,y=evt.clientY+16;const rect=tt.getBoundingClientRect();if(x+rect.width+12>innerWidth)x=evt.clientX-rect.width-16;if(y+rect.height+12>innerHeight)y=evt.clientY-rect.height-16;tt.style.left=`${Math.max(12,x)}px`;tt.style.top=`${Math.max(12,y)}px`;}

function loadRecSettings(){try{const raw=JSON.parse(localStorage.getItem(REC_KEY)||'{}');rec={...rec,...raw,elements:raw.elements||{},riskMode:raw.riskMode||'warn'};}catch{rec={...rec,elements:{},riskMode:'warn'};}ensureRecScope();}
function saveRecSettings(){localStorage.setItem(REC_KEY,JSON.stringify({updatedAt:new Date().toISOString(),mode:rec.mode,scope:rec.scope,gap:rec.gap,riskMode:rec.riskMode||'warn',limit:rec.limit,search:rec.search,elements:rec.elements}));}
function recSettingKey(mode=rec.mode,scope=rec.scope){return `${mode}|${scope||''}`}
function recElementSet(mode=rec.mode,scope=rec.scope){return new Set(rec.elements[recSettingKey(mode,scope)]||[])}
function setRecElementSet(set,mode=rec.mode,scope=rec.scope){rec.elements[recSettingKey(mode,scope)]=[...set].sort((a,b)=>ELEMENT_ORDER.indexOf(a)-ELEMENT_ORDER.indexOf(b));}
function recScopeOptions(mode){
  const map=new Map();
  (DATA.teamTemplates||[]).filter(t=>t.mode===mode).forEach(t=>{if(!map.has(t.scope_key))map.set(t.scope_key,{key:t.scope_key,label:t.scope_label||t.scope_key,order:Number(t.scope_order)||90});});
  return [...map.values()].sort((a,b)=>a.order-b.order||a.label.localeCompare(b.label));
}
function ensureRecScope(){const options=recScopeOptions(rec.mode);if(options.length&&!options.some(o=>o.key===rec.scope))rec.scope=options[0].key;}

function boxAliasMap(){const aliases=new Map();(DATA.rosterRows||[]).forEach(r=>String(r.alias_slugs||r.character_slug||'').split(';').forEach(s=>{if(s)aliases.set(s,r.character_slug);}));return aliases;}
function normalizeEidolon(value){const n=Number(value);return Number.isInteger(n)&&n>=0&&n<=6?n:'unset'}
function normalizeSignature(value){const text=String(value).toLowerCase();if(value===true||['yes','owned','signature','s1','专武'].includes(text))return 'yes';if(value===false||['no','none','s0','无专武'].includes(text))return 'no';return 'unset'}
function normalizeBuild(raw={}){const level=BUILD_LEVELS.includes(Number(raw.level))?Number(raw.level):0;const lc=BUILD_LEVELS.includes(Number(raw.lc??raw.lightConeLevel))?Number(raw.lc??raw.lightConeLevel):0;const traceValues=new Set(BUILD_TRACES.map(x=>x[0]));const relicValues=new Set(BUILD_RELICS.map(x=>x[0]));const eidolon=normalizeEidolon(raw.eidolon??raw.eidolons??raw.cons??raw.constellation);const signature=normalizeSignature(raw.signature??raw.signatureWeapon??raw.hasSignature??raw.s);return{level,lc,eidolon,signature,traces:traceValues.has(raw.traces)?raw.traces:'unset',relics:relicValues.has(raw.relics)?raw.relics:'unset'};}
function buildOptionScore(options,value){return options.find(x=>x[0]===value)?.[2]??0}
function buildCoreRecorded(build){return Boolean(build.level||build.lc||build.traces!=='unset'||build.relics!=='unset')}
function buildConfigRecorded(build){return build.eidolon!=='unset'||build.signature!=='unset'}
function buildRecorded(build){return buildCoreRecorded(build)||buildConfigRecorded(build)}
function buildConfigLabel(build){const b=normalizeBuild(build);const e=b.eidolon==='unset'?'E?':`E${b.eidolon}`;const s=b.signature==='yes'?'S1':b.signature==='no'?'S0':'S?';return `${e}${s}`}
function signatureText(value){return BUILD_SIGNATURES.find(x=>x[0]===value)?.[1]||'未录入'}
function buildState(build){const b=normalizeBuild(build);const traceScore=buildOptionScore(BUILD_TRACES,b.traces);const relicScore=buildOptionScore(BUILD_RELICS,b.relics);const baseScore=(b.level/80)*.25+(b.lc/80)*.2+traceScore*.25+relicScore*.3;const configBonus=(b.eidolon==='unset'?0:Number(b.eidolon)*.008)+(b.signature==='yes'?.035:0);const score=Math.min(1,baseScore+configBonus);const recorded=buildRecorded(b);const coreRecorded=buildCoreRecorded(b);const ready=coreRecorded&&baseScore>=.86&&b.level>=75&&b.lc>=70&&traceScore>=.82&&relicScore>=.82;let label='练度未录入';if(ready)label='已成型';else if(coreRecorded&&baseScore>=.72)label='可用';else if(coreRecorded)label='待练';else if(buildConfigRecorded(b))label='仅配置';return{...b,baseScore,score,basePercent:Math.round(baseScore*100),percent:Math.round(score*100),recorded,coreRecorded,ready,label,configLabel:buildConfigLabel(b)};}
function buildFor(slug){return normalizeBuild(box.builds?.[canonicalSlug(slug)]||{})}
function buildShortLabel(slug){const s=buildState(buildFor(slug));return `${s.label}${s.coreRecorded?` ${s.basePercent}%`:''} · ${s.configLabel}`}
function readBoxRaw(){try{return JSON.parse(localStorage.getItem(BOX_KEY)||'{}');}catch{return{};}}
function rawOwnedList(raw){const rows=Array.isArray(raw.owned)?raw.owned:Object.keys(raw.owned||{}).filter(k=>raw.owned[k]);return rows.filter(slug=>slug&&slug!=='__codex_test__');}
function readableBoxRaw(raw={}){if(!raw||typeof raw!=='object'||Array.isArray(raw))return{};const version=raw.version==null?1:Number(raw.version);return [1,2,3].includes(version)?raw:{}}
function applyBoxRaw(raw){raw=readableBoxRaw(raw);const aliases=boxAliasMap();const owned=rawOwnedList(raw);box.owned=new Set(owned.map(s=>aliases.get(s)||s).filter(Boolean));box.builds={};Object.entries(raw.builds||{}).forEach(([slug,build])=>{const resolved=aliases.get(slug)||slug;if(resolved)box.builds[resolved]=normalizeBuild(build);});box.buildSlug=aliases.get(raw.buildSlug)||raw.buildSlug||'';if(box.buildSlug&&!box.owned.has(box.buildSlug))box.buildSlug='';box.saveStatus=raw.fromServer?'本机自动保存':'浏览器缓存';}
function loadBox(){try{applyBoxRaw(readBoxRaw());}catch{box.owned=new Set();box.builds={};box.buildSlug='';box.saveStatus='浏览器缓存';}}
function boxPayload(){const builds={};Object.entries(box.builds||{}).forEach(([slug,build])=>{const normalized=normalizeBuild(build);if(buildRecorded(normalized))builds[slug]=normalized;});return{version:2,updatedAt:new Date().toISOString(),owned:[...box.owned].sort(),buildSlug:box.buildSlug||'',builds};}
function saveBox(){const payload=boxPayload();localStorage.setItem(BOX_KEY,JSON.stringify(payload));box.saveStatus='已保存到浏览器';clearTimeout(boxSaveTimer);boxSaveTimer=setTimeout(()=>saveBoxToServer(payload),180);if(state.page==='box'||state.page==='banner')requestAnimationFrame(()=>{if(state.page==='box')renderBox();else renderBanner();});}
function hasBoxData(raw){return Boolean(rawOwnedList(raw).length||Object.keys(raw.builds||{}).length);}
function boxTime(raw){const t=Date.parse(raw.updatedAt||raw.exportedAt||'');return Number.isFinite(t)?t:0;}
function syncBoxFromServer(){fetch('/api/hsr/box',{cache:'no-store'}).then(r=>r.ok?r.json():Promise.reject(new Error('no api'))).then(server=>{const local=readBoxRaw();server.fromServer=true;const serverWins=Boolean(server.updatedAt)&&boxTime(server)>=boxTime(local);if(serverWins||(hasBoxData(server)&&(!hasBoxData(local)||boxTime(server)>=boxTime(local)))){applyBoxRaw(server);localStorage.setItem(BOX_KEY,JSON.stringify(server));box.saveStatus='本机自动保存';render();}else if(hasBoxData(local)){saveBoxToServer(boxPayload());}else{box.saveStatus='本机自动保存';render();}}).catch(()=>{box.saveStatus='浏览器缓存';if(state.page==='box'||state.page==='banner')render();});}
function saveBoxToServer(payload){fetch('/api/hsr/box',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}).then(r=>r.ok?r.json():Promise.reject(new Error('save failed'))).then(()=>{box.saveStatus='本机自动保存';if(state.page==='box'||state.page==='banner')render();}).catch(()=>{box.saveStatus='浏览器缓存';if(state.page==='box'||state.page==='banner')render();});}
function releaseOrder(row){const n=Number(row.release_order);return Number.isFinite(n)?n:99999}
function matchesBoxStatus(row){if(box.status==='all')return true;if(box.status==='owned')return box.owned.has(row.character_slug);if(box.status==='missing')return !box.owned.has(row.character_slug);if(box.status.startsWith('banner_'))return String(row.banner_statuses||'').split(';').includes(box.status.replace('banner_',''));return true}
function boxStatusLabel(){return{all:'全部状态',owned:'已拥有',missing:'未拥有',banner_current:'当期UP',banner_next:'后续卡池',banner_recent:'历史参考'}[box.status]||box.status}
function boxStatusText(status){return{current:'当期UP',next:'后续卡池',recent:'历史参考',previous:'已结束'}[status]||status}
function filteredRoster(){const q=box.search;return DATA.rosterRows.filter(r=>(box.element==='all'||r.element_cn===box.element)&&(box.path==='all'||r.path_cn===box.path)&&(box.role==='all'||String(r.role_groups||'').split(';').includes(box.role))&&(box.rarity==='all'||String(r.rarity)===box.rarity)&&matchesBoxStatus(r)&&(!q||[r.character_name_cn,r.character_name_en,r.character_slug,r.element_cn,r.path_cn,r.role_group_cns,r.banner_phase_titles].some(x=>String(x||'').toLowerCase().includes(q)))).sort((a,b)=>releaseOrder(a)-releaseOrder(b)||String(a.character_name_en).localeCompare(String(b.character_name_en)));}
function toggleOwned(slug){const resolved=canonicalSlug(slug);if(box.owned.has(resolved)){box.owned.delete(resolved);if(box.buildSlug===resolved)box.buildSlug='';}else{box.owned.add(resolved);box.buildSlug=resolved;}saveBox();renderBox();}
function renderBox(){const rows=filteredRoster();const total=DATA.rosterRows.length;const owned=DATA.rosterRows.filter(r=>box.owned.has(r.character_slug)).length;const built=DATA.rosterRows.filter(r=>box.owned.has(r.character_slug)&&buildState(buildFor(r.character_slug)).ready).length;renderBuildEditor();$('boxSubtitle').textContent=`展示 ${rows.length}/${total} 个角色，已拥有 ${owned} 个，已成型 ${built} 个。点击卡片切换拥有，点「练度」维护等级/光锥/星魂/专武/行迹/遗器。`;$('boxBadges').innerHTML=[box.saveStatus||'浏览器缓存',box.element==='all'?'全部属性':box.element,box.path==='all'?'全部命途':box.path,boxStatusLabel(),`成型 ${built}/${owned||0}`].map(x=>`<span>${esc(x)}</span>`).join('');const grid=$('boxGrid');grid.innerHTML='';rows.forEach(row=>{const owned=box.owned.has(row.character_slug);const buildText=owned?buildShortLabel(row.character_slug):'未拥有';const bannerTag=String(row.banner_statuses||'').split(';').filter(Boolean)[0];const card=document.createElement('article');card.tabIndex=0;card.setAttribute('role','button');card.className=`box-card ${owned?'owned':'missing'} ${box.buildSlug===row.character_slug?'selected':''}`;card.dataset.slug=row.character_slug;card.onclick=()=>toggleOwned(row.character_slug);card.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();toggleOwned(row.character_slug);}};card.onmouseenter=e=>showBoxTooltip(e,row);card.onmousemove=moveTooltip;card.onmouseleave=()=>{$('boxTooltip').hidden=true;};card.innerHTML=`<button class="build-button" type="button">练度</button><span class="owned-dot"></span><img src="${esc(row.icon_url)}" alt="" loading="lazy" decoding="async"><div class="box-name">${esc(row.character_name_cn||row.character_name_en||row.character_slug)}</div><div class="box-meta">${esc(row.element_cn||'')} · ${esc(row.path_cn||'')}${bannerTag?` · ${esc(boxStatusText(bannerTag))}`:''}</div><div class="box-meta">${esc(row.role_group_cns||'未分类')}</div><div class="box-meta box-build">${esc(buildText)}</div>`;card.querySelector('.build-button').onclick=e=>{e.stopPropagation();selectBuild(row.character_slug);};grid.appendChild(card);});}
function selectBuild(slug){const resolved=canonicalSlug(slug);box.owned.add(resolved);box.buildSlug=resolved;saveBox();renderBox();}
function renderBuildEditor(){const panel=$('buildEditor');if(!box.buildSlug||!box.owned.has(box.buildSlug)){panel.classList.add('hidden');return;}const row=charInfo(box.buildSlug);const state=buildState(buildFor(box.buildSlug));panel.classList.remove('hidden');$('buildEditorIcon').src=row.icon_url||'';$('buildEditorTitle').textContent=`${charName(box.buildSlug)} · 练度`;$('buildEditorSubtitle').textContent=`${row.element_cn||'未知'} · ${row.path_cn||'未知'} · ${roleCn(row)}`;$('buildLevelSelect').value=String(state.level);$('buildLcSelect').value=String(state.lc);$('buildEidolonSelect').value=String(state.eidolon);$('buildSignatureSelect').value=state.signature;$('buildTraceSelect').value=state.traces;$('buildRelicSelect').value=state.relics;$('buildScoreText').textContent=`${state.label} · ${state.coreRecorded?state.basePercent:0}% · ${state.configLabel}`;}
function updateBuildField(field,value){if(!box.buildSlug)return;const build=buildFor(box.buildSlug);build[field]=value;box.builds[box.buildSlug]=normalizeBuild(build);box.owned.add(box.buildSlug);saveBox();renderBox();}
function fullBuild(prev={}){const b=normalizeBuild(prev);return{...b,level:80,lc:80,traces:'max',relics:'great'}}
function setBuildPreset(kind){if(!box.buildSlug)return;if(kind==='clear')delete box.builds[box.buildSlug];else box.builds[box.buildSlug]=fullBuild(box.builds[box.buildSlug]||{});box.owned.add(box.buildSlug);saveBox();renderBox();}
function setVisibleBuild(kind){filteredRoster().forEach(r=>{if(kind==='clear')delete box.builds[r.character_slug];else{box.owned.add(r.character_slug);box.builds[r.character_slug]=fullBuild(box.builds[r.character_slug]||{});}});saveBox();renderBox();}
function showBoxTooltip(evt,row){const tt=$('boxTooltip');const owned=box.owned.has(row.character_slug);const state=buildState(buildFor(row.character_slug));const eidolonText=state.eidolon==='unset'?'未录入':`${state.eidolon}魂`;tt.hidden=false;tt.innerHTML=`<div class="tooltip-head"><img src="${esc(row.icon_url)}" alt=""><div><strong>${esc(row.character_name_cn||row.character_name_en)}</strong><span>${esc(row.character_name_en)} · ${esc(row.character_slug)}</span></div></div><div class="tooltip-grid"><b>收集状态</b><div>${owned?'已拥有':'未拥有'}</div><b>练度</b><div>${owned?`${esc(state.label)} · ${state.coreRecorded?state.basePercent:0}%`:'未拥有'}</div><b>星魂/专武</b><div>${owned?`${esc(eidolonText)} · ${esc(signatureText(state.signature))}`:'未拥有'}</div><b>属性/命途</b><div>${esc(row.element_cn||'未知')} · ${esc(row.path_cn||'未知')}</div><b>星级</b><div>${esc(row.rarity||'未知')}</div><b>职能</b><div>${esc(row.role_group_cns||'未分类')}</div><b>排序</b><div>新旧序 #${esc(row.release_order)}</div><b>来源</b><div>${esc(row.source||'')}</div></div>`;moveTooltip(evt);}
function markVisible(value){filteredRoster().forEach(r=>{if(value)box.owned.add(r.character_slug);else{box.owned.delete(r.character_slug);if(box.buildSlug===r.character_slug)box.buildSlug='';}});saveBox();renderBox();}
function exportBox(){const blob=new Blob([JSON.stringify({...boxPayload(),exportedAt:new Date().toISOString()},null,2)],{type:'application/json'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='hsr_box_state.json';a.click();URL.revokeObjectURL(a.href);}
function importBox(evt){const file=evt.target.files?.[0];if(!file)return;const reader=new FileReader();reader.onload=()=>{try{const data=JSON.parse(String(reader.result||'{}'));applyBoxRaw(data);box.buildSlug='';saveBox();renderBox();}catch(err){alert(`导入失败：${err.message}`);}finally{evt.target.value='';}};reader.readAsText(file);}

function rosterBySlug(){if(!DATA._rosterBySlug){DATA._rosterBySlug=new Map();(DATA.rosterRows||[]).forEach(r=>{DATA._rosterBySlug.set(r.character_slug,r);String(r.alias_slugs||'').split(';').forEach(s=>{if(s)DATA._rosterBySlug.set(s,r);});});}return DATA._rosterBySlug;}
function charInfo(slug){return rosterBySlug().get(slug)||{character_slug:slug,character_name_cn:'',character_name_en:slug,element_cn:'',path_cn:'',role_groups:'unknown',role_group_cns:'未分类',icon_url:''};}
function charName(slug){const r=charInfo(slug);return r.character_name_cn||r.character_name_en||slug}
function phaseName(row){return row?.phase_name_cn||(row?.phase_name?'中文期名待维护':'')}
function phaseLabel(row){const ver=row?.phase_ver||'';const name=phaseName(row);return `${ver} ${name}`.trim()}
function roleList(row){return String(row.role_groups||'unknown').split(';').filter(Boolean)}
function roleCn(row){return row.role_group_cns||roleList(row).join('/')}
function phaseStatusLabel(status){return status==='expired'?'已过期':status==='future'?'未开始':status==='current'?'当前周期':'日期未知'}
function templateRecencyKey(t){return `${String(t.collect_date||'')}|${String(t.phase_ver||'')}|${String(t.snapshot_id||'')}`}
function currentModeTemplates(mode){const rows=(DATA.teamTemplates||[]).filter(t=>t.mode===mode);const usable=rows.filter(t=>!['expired','future'].includes(t.phase_status));const pool=usable.length?usable:rows;const latest=pool.reduce((m,t)=>templateRecencyKey(t)>m?templateRecencyKey(t):m,'');return pool.filter(t=>templateRecencyKey(t)===latest);}
function scopeTemplates(mode,scope){return currentModeTemplates(mode).filter(t=>t.scope_key===scope);}
function num(v){const n=Number(v);return Number.isFinite(n)?n:null}
function canonicalSlug(slug){return charInfo(slug).character_slug||slug}
function isCoreMember(info){return roleList(info).some(role=>CORE_ROLES.has(role))}
function tierMetaFor(slug,mode){
  if(!DATA._tierRiskMeta){
    DATA._tierRiskMeta=new Map();
    (DATA.tierRows||[]).forEach(row=>{
      const resolved=canonicalSlug(row.character_slug);
      const key=`${row.tier_mode}|${resolved}`;
      const rank=TIER_RANK[row.tier];
      if(rank==null)return;
      const current=DATA._tierRiskMeta.get(key);
      if(!current||rank<current.rank)DATA._tierRiskMeta.set(key,{tier:row.tier,rank,role:row.role_group_cn||row.role_group||'',rating:num(row.rating)});
    });
  }
  return DATA._tierRiskMeta.get(`${mode}|${canonicalSlug(slug)}`)||null;
}
function usageTrendFor(slug,mode){
  if(!DATA._usageTrendMeta){
    DATA._usageTrendMeta=new Map();
    const grouped=new Map();
    (DATA.usageRows||DATA.trendRows||[]).forEach(row=>{
      const rowMode=row.tier_mode||row.mode;
      const resolved=canonicalSlug(row.character_slug);
      if(!rowMode||!resolved||!row.collect_date)return;
      const key=`${rowMode}|${resolved}|${row.collect_date}`;
      const current=grouped.get(key);
      const rate=num(row.app_rate);
      if(rate==null)return;
      if(!current||rate>current.app_rate)grouped.set(key,{mode:rowMode,slug:resolved,date:row.collect_date,app_rate:rate});
    });
    const byChar=new Map();
    grouped.forEach(point=>{const key=`${point.mode}|${point.slug}`;if(!byChar.has(key))byChar.set(key,[]);byChar.get(key).push(point);});
    byChar.forEach((points,key)=>{
      points.sort((a,b)=>String(a.date).localeCompare(String(b.date)));
      const recent=points.slice(-4);
      if(recent.length<3){DATA._usageTrendMeta.set(key,{risk:false,points:recent});return;}
      const first=recent[0].app_rate,last=recent[recent.length-1].app_rate,prev=recent[recent.length-2].app_rate;
      const drops=recent.slice(1).filter((p,i)=>p.app_rate<recent[i].app_rate).length;
      const absoluteDrop=first-last;
      const relativeDrop=first>0?absoluteDrop/first:0;
      const risk=first>=3&&last<prev&&((drops>=2&&absoluteDrop>=3)||(relativeDrop>=0.45&&absoluteDrop>=2.2));
      DATA._usageTrendMeta.set(key,{risk,points:recent,first,last,drop:absoluteDrop});
    });
  }
  return DATA._usageTrendMeta.get(`${mode}|${canonicalSlug(slug)}`)||{risk:false,points:[]};
}
function memberRisk(member,mode){
  const reasons=[];const tier=tierMetaFor(member.slug,mode);const core=isCoreMember(member.info);const build=member.buildState||buildState(buildFor(member.slug));const built=member.owned&&build.ready;
  if(member.owned){
    if(!build.coreRecorded)reasons.push({type:'build-missing',text:'练度未录入',penalty:core?44:24});
    else if(build.baseScore<.68)reasons.push({type:'build-low',text:`练度待补 ${build.basePercent}%`,penalty:core?70:38,severe:core});
    else if(build.baseScore<.86)reasons.push({type:'build-mid',text:`练度未成型 ${build.basePercent}%`,penalty:core?32:16});
  }
  if(tier){
    if(tier.rank>=5)reasons.push({type:'tier-forgotten',text:`${tier.tier}不建议投入${built?'（已练，降权）':''}`,penalty:built?(core?55:30):(core?120:70),severe:true});
    else if(tier.rank>=3)reasons.push({type:'tier-offmeta',text:`${tier.tier}非主流低档${built?'（已练，降权）':''}`,penalty:built?(core?42:24):(core?85:45),severe:true});
    else if(tier.rank>=1&&!built)reasons.push({type:'tier-caution',text:`${tier.tier}投入谨慎`,penalty:core?34:18});
  }
  const trend=usageTrendFor(member.slug,mode);
  if(trend.risk)reasons.push({type:'trend',text:`近${trend.points.length}期走弱 ${trend.first?.toFixed?.(1)}%→${trend.last?.toFixed?.(1)}%`,penalty:core?55:25});
  return reasons;
}
function teamRisk(members,selectedElements){
  const risks=[];const core=members.filter(m=>isCoreMember(m.info));
  if(selectedElements.size&&core.length){
    const coreHits=core.filter(m=>selectedElements.has(m.info.element_cn)).length;
    const expected=Math.min(2,core.length,selectedElements.size);
    if(coreHits===0)risks.push({type:'core-none',text:'主C/副C均未命中推荐属性',penalty:180,severe:true});
    else if(coreHits<expected)risks.push({type:'core-low',text:`核心属性不足 ${coreHits}/${expected}`,penalty:85,severe:true});
  }
  return risks;
}

function rankedRecommendations(mode=rec.mode,scope=rec.scope,used=new Set(),options={}){
  const selected=recElementSet(mode,scope);
  const maxGap=Number(options.maxGap??rec.gap);
  const q=options.ignoreSearch?'':rec.search;
  return scopeTemplates(mode,scope).map(t=>scoreTemplate(t,selected,used)).filter(item=>{
    if(Number.isFinite(maxGap)&&item.missingCount>maxGap)return false;
    const riskMode=options.riskMode||rec.riskMode||'warn';
    if(riskMode==='filter'&&item.risks.length)return false;
    if(q&&!item.searchText.includes(q))return false;
    return true;
  }).sort((a,b)=>b.score-a.score||a.missingCount-b.missingCount||(num(a.template.rank)||9999)-(num(b.template.rank)||9999));
}

function scoreTemplate(template,selectedElements,used){
  const chars=template.chars||[];
  const members=chars.map(slug=>{const info=charInfo(slug);const build=buildFor(slug);const buildMeta=buildState(build);return{slug,info,build,buildState:buildMeta,owned:box.owned.has(slug),selected:selectedElements.has(info.element_cn),used:used.has(slug),core:isCoreMember(info)}});
  const ownedCount=members.filter(m=>m.owned).length;
  const buildReadyCount=members.filter(m=>m.owned&&m.buildState.ready).length;
  const ownedBuildScore=members.filter(m=>m.owned).reduce((sum,m)=>sum+m.buildState.score,0);
  const missing=members.filter(m=>!m.owned);
  const conflictCount=members.filter(m=>m.owned&&m.used).length;
  const elementHits=members.filter(m=>m.selected).length;
  const coreMembers=members.filter(m=>m.core);
  const coreElementHits=coreMembers.filter(m=>m.selected).length;
  members.forEach(m=>{m.risks=memberRisk(m,template.mode);});
  const reserved=new Set([...chars,...used]);
  const substitutions=missing.map(m=>({missing:m,candidates:substituteCandidates(m.slug,selectedElements,reserved)}));
  const fillCount=substitutions.filter(s=>s.candidates.length).length;
  const memberRisks=members.flatMap(m=>m.risks.map(r=>({...r,slug:m.slug,name:charName(m.slug)})));
  const attributeRisks=teamRisk(members,selectedElements);
  const risks=[...memberRisks,...attributeRisks];
  const riskPenalty=(rec.riskMode==='off'?0:risks.reduce((sum,r)=>sum+(r.penalty||0),0));
  const app=num(template.app_rate)||0;
  const rank=num(template.rank);
  const avg=num(template.avg_round);
  let score=ownedCount*45+ownedBuildScore*90-missing.length*66-conflictCount*180+elementHits*8+coreElementHits*48+fillCount*34+Math.min(app,35)*2.2-riskPenalty;
  if(rank!=null)score+=Math.max(0,160-rank)*0.34;
  if(avg!=null&&avg<99)score-=avg*1.2;
  if(missing.length===0)score+=95;
  if(selectedElements.size&&elementHits===0)score-=40;
  const finalChars=members.map(m=>m.owned?m.slug:(substitutions.find(s=>s.missing.slug===m.slug)?.candidates[0]?.character_slug||m.slug));
  const searchText=[template.phase_name_cn,template.phase_name,template.source_kind,template.scope_label,...chars, ...chars.map(charName),...risks.map(r=>r.text)].join(' ').toLowerCase();
  return{template,members,missingCount:missing.length,ownedCount,buildReadyCount,conflictCount,elementHits,coreElementHits,substitutions,risks,score,finalChars,searchText};
}

function substituteCandidates(missingSlug,selectedElements,reserved){
  const missing=charInfo(missingSlug);
  const missingRoles=new Set(roleList(missing));
  return (DATA.rosterRows||[]).filter(r=>box.owned.has(r.character_slug)&&!reserved.has(r.character_slug)).map(r=>{
    const roles=roleList(r);
    const roleOverlap=roles.some(role=>missingRoles.has(role));
    let score=0;
    if(roleOverlap)score+=58;
    if(r.path_cn&&r.path_cn===missing.path_cn)score+=18;
    if(r.element_cn&&r.element_cn===missing.element_cn)score+=18;
    if(selectedElements.has(r.element_cn))score+=24;
    if(String(r.rarity)==='5')score+=4;
    if(missingRoles.has('sustain')&&roles.includes('sustain'))score+=24;
    if((missingRoles.has('support')||missingRoles.has('sub_dps'))&&(roles.includes('support')||roles.includes('sub_dps')))score+=12;
    return{...r,subScore:score};
  }).filter(r=>r.subScore>0).sort((a,b)=>b.subScore-a.subScore||releaseOrder(a)-releaseOrder(b)).slice(0,3);
}

function renderRecommender(){
  ensureRecScope();syncRecControls();$('recTooltip').hidden=true;
  const modeLabel=MODES.find(x=>x[0]===rec.mode)?.[1]||rec.mode;
  const scope=recScopeOptions(rec.mode).find(o=>o.key===rec.scope);
  const templates=scopeTemplates(rec.mode,rec.scope);
  const ranked=rankedRecommendations().slice(0,Number(rec.limit)||8);
  const latest=templates[0]||{};
  const selected=[...recElementSet()];
  renderPhaseMechanics(latest);
  $('recTitle').textContent=`${modeLabel} · ${scope?.label||rec.scope}`;
  const status=latest.phase_status||phaseInfoFor(latest).phase_status||'unknown';
  const templateLabel=status==='expired'?'历史模板（源滞后）':'当前同模式同关卡模板';
  $('recSubtitle').textContent=`${phaseLabel(latest)} · ${latest.collect_date||''} · ${phaseStatusLabel(status)} · ${templateLabel} ${templates.length} 队`;
  const riskLabel=rec.riskMode==='filter'?'过滤风险':rec.riskMode==='off'?'忽略风险':'仅提醒';
  const tierRiskLabel=rec.riskMode==='off'?'当前模式T档不提醒':'当前模式T1及以下提醒';
  $('recBadges').innerHTML=[selected.length?selected.join(' / '):'未选属性',`缺口 ≤ ${rec.gap}`,riskLabel,tierRiskLabel,`Box ${box.owned.size}`].map(x=>`<span>${esc(x)}</span>`).join('');
  const list=$('recList');list.innerHTML='';
  if(!ranked.length){list.innerHTML='<div class="rec-empty">当前筛选没有可展示队伍</div>';renderRecSlate();return;}
  ranked.forEach((item,index)=>list.appendChild(recCard(item,index+1)));
  renderRecSlate();
}

function phaseInfoFor(template){
  const rows=DATA.phaseInfoRows||[];
  const exact=rows.find(r=>r.mode===rec.mode&&r.phase_ver===template.phase_ver&&r.phase_name===template.phase_name);
  if(exact)return exact;
  const modeRows=rows.filter(r=>r.mode===rec.mode).sort((a,b)=>String(b.collect_date).localeCompare(String(a.collect_date)));
  return modeRows[0]||template||{};
}

function renderPhaseMechanics(template){
  const info=phaseInfoFor(template||{});
  const modeLabel=MODES.find(x=>x[0]===rec.mode)?.[1]||rec.mode;
  const phaseTitle=phaseLabel(info)||phaseLabel(template);
  $('phaseMechanicsTitle').textContent=`${modeLabel} · ${phaseTitle||'未识别期名'}`;
  const status=info.phase_status||template.phase_status||'unknown';
  const dates=[phaseStatusLabel(status),info.start_date&&`开始 ${info.start_date}`,info.end_date&&`结束 ${info.end_date}`,info.collect_date&&`采样 ${info.collect_date}`].filter(Boolean).join(' · ');
  $('phaseMechanicsSubtitle').textContent=dates||'期名来自本地 phase_index';
  const expiredText=status==='expired'?`本地最新 ${modeLabel} 数据已于 ${info.end_date||'上一周期'} 结束；上游尚未提供新周期队伍数据。请和我对话手动更新至少活动范围，再把当前推荐当作正式参考。`:'';
  const mechanicName=expiredText?'源滞后 / 历史模板':(info.mechanic_name||'机制效果待维护');
  const mechanicText=expiredText||info.mechanic_text||'当前本地数据只识别到了期名和采样日期，尚未维护这一期的环境效果。这个状态会明确显示，避免把未知效果误当成已匹配。';
  $('phaseMechanicsText').textContent=`${mechanicName}：${mechanicText}`;
  const source=$('phaseMechanicsSource');
  if(info.mechanic_url){source.href=info.mechanic_url;source.textContent=info.mechanic_source||'机制来源';source.classList.remove('hidden-link');}
  else{source.href='#';source.textContent='';source.classList.add('hidden-link');}
}

function recCard(item,index){
  const t=item.template;
  const card=document.createElement('article');
  card.className=`rec-card ${item.risks.length&&rec.riskMode!=='off'?'risky':''}`;
  card.onmouseenter=e=>showRecTooltip(e,item);
  card.onmousemove=moveTooltip;
  card.onmouseleave=()=>{$('recTooltip').hidden=true;};
  const missingNames=item.members.filter(m=>!m.owned).map(m=>charName(m.slug));
  card.innerHTML=`<div class="rec-card-head"><div><h3>${index}. ${esc((t.names_cn||[]).filter(Boolean).join(' / ')||t.chars.map(charName).join(' / '))}</h3><div class="rec-meta">${esc(t.scope_label)} · Rank ${esc(t.rank??'-')} · ${t.app_rate==null?'-':pct(t.app_rate)} · ${t.avg_round==null?'-':Number(t.avg_round).toFixed(2)}</div></div><div class="rec-score"><strong>${Math.round(item.score)}</strong><span>${item.ownedCount}/4</span></div></div><div class="rec-team">${item.members.map(m=>recMemberHtml(m,item)).join('')}</div><div class="rec-tags">${recTags(item).map(tag=>`<span class="${tag.danger?'danger':tag.warn?'warn':''}">${esc(tag.text)}</span>`).join('')}</div>${riskNoteHtml(item)}${substitutionHtml(item)}${missingNames.length?`<div class="rec-note">缺：${esc(missingNames.join('、'))}</div>`:''}`;
  return card;
}

function recMemberHtml(member,item){
  const r=member.info;
  const riskText=(member.risks||[]).map(x=>x.text).join('；');
  const coreRisk=item?.risks?.some(risk=>(risk.type==='core-none'||risk.type==='core-low')&&member.core&&!member.selected);
  const buildText=member.owned?` · ${member.buildState.label} · ${member.buildState.configLabel}`:'';
  return `<div class="rec-member ${member.owned?'owned':'missing'} ${(riskText||coreRisk)&&rec.riskMode!=='off'?'risky':''}" title="${esc([member.owned?'已拥有':'未拥有',member.owned?`练度 ${member.buildState.label} ${member.buildState.basePercent}% · ${member.buildState.configLabel}`:'',riskText,coreRisk?'核心属性未命中':''].filter(Boolean).join('；'))}"><img src="${esc(r.icon_url)}" alt="" loading="lazy" decoding="async"><div class="name">${esc(r.character_name_cn||r.character_name_en||member.slug)}</div><div class="meta">${esc(r.element_cn||'')} · ${esc(roleCn(r))}${esc(buildText)}</div></div>`;
}

function recTags(item){
  const t=item.template;
  const tags=[{text:item.missingCount?`缺 ${item.missingCount}`:'可成队',warn:item.missingCount>0},{text:`属性命中 ${item.elementHits}`,warn:false},{text:t.source_kind||'source',warn:false}];
  if(item.ownedCount)tags.push({text:`练度 ${item.buildReadyCount}/${item.ownedCount}`,warn:item.buildReadyCount<item.ownedCount});
  if(item.coreElementHits||recElementSet(t.mode,t.scope_key).size)tags.push({text:`核心命中 ${item.coreElementHits}`,warn:item.coreElementHits===0});
  if(item.risks.length&&rec.riskMode!=='off')tags.push({text:`风险 ${item.risks.length}`,danger:item.risks.some(r=>r.severe),warn:true});
  if(item.conflictCount)tags.push({text:`冲突 ${item.conflictCount}`,warn:true});
  return tags;
}

function riskNoteHtml(item){
  if(!item.risks.length||rec.riskMode==='off')return '';
  const text=item.risks.slice(0,4).map(r=>r.name?`${r.name}：${r.text}`:r.text).join('；');
  return `<div class="rec-risk-note">${esc(text)}${item.risks.length>4?'；...':''}</div>`;
}

function substitutionHtml(item){
  const rows=item.substitutions.filter(s=>s.candidates.length);
  if(!rows.length)return '';
  return `<div class="rec-subs">${rows.map(s=>`<div class="rec-subline"><b>${esc(charName(s.missing.slug))}</b>${s.candidates.map(c=>`<span class="rec-mini"><img src="${esc(c.icon_url)}" alt="">${esc(c.character_name_cn||c.character_name_en)}</span>`).join('')}</div>`).join('')}</div>`;
}

function renderRecSlate(){
  const scopes=recScopeOptions(rec.mode).filter(o=>o.key!=='all');
  const used=new Set();
  const chosen=[];
  scopes.forEach(scope=>{
    const best=rankedRecommendations(rec.mode,scope.key,used,{ignoreSearch:true,maxGap:Number(rec.gap)}).find(item=>item.conflictCount===0);
    if(best){chosen.push({scope,item:best});best.finalChars.forEach(slug=>{if(box.owned.has(slug))used.add(slug);});}
    else chosen.push({scope,item:null});
  });
  $('recSlateSubtitle').textContent=`${chosen.filter(x=>x.item).length}/${scopes.length} 队 · 不复用已拥有角色`;
  const boxEl=$('recSlateList');boxEl.innerHTML='';
  if(!chosen.length){boxEl.innerHTML='<div class="rec-empty">暂无当前模式关卡模板</div>';return;}
  chosen.forEach(({scope,item})=>{const card=document.createElement('div');card.className=`rec-slate-card ${item?.risks?.length&&rec.riskMode!=='off'?'risky':''}`;if(!item){card.innerHTML=`<h3>${esc(scope.label)}</h3><div class="rec-note">没有符合缺口限制的队伍</div>`;}else{card.onmouseenter=e=>showRecTooltip(e,item);card.onmousemove=moveTooltip;card.onmouseleave=()=>{$('recTooltip').hidden=true;};card.innerHTML=`<h3>${esc(scope.label)} · ${Math.round(item.score)} · ${item.ownedCount}/4</h3><div class="rec-slate-team">${item.finalChars.map(slug=>{const r=charInfo(slug);const owned=box.owned.has(slug);const member=item.members.find(m=>m.slug===slug);const risky=rec.riskMode!=='off'&&Boolean(member?.risks?.length);return`<img class="${owned?'':'missing'} ${risky?'risky':''}" src="${esc(r.icon_url)}" title="${esc(charName(slug))}" alt="">`;}).join('')}</div>${riskNoteHtml(item)}`;}boxEl.appendChild(card);});
}

function showRecTooltip(evt,item){
  const tt=$('recTooltip');const t=item.template;const selected=[...recElementSet(t.mode,t.scope_key)].join(' / ')||'未选';
  const riskText=item.risks.length&&rec.riskMode!=='off'?item.risks.map(r=>r.name?`${r.name}：${r.text}`:r.text).join('；'):'无';
  const riskMode=rec.riskMode==='filter'?'过滤风险':rec.riskMode==='off'?'忽略风险':'仅提醒';
  tt.hidden=false;
  tt.innerHTML=`<div class="tooltip-head"><div><strong>${esc(t.mode_cn)} · ${esc(t.scope_label)}</strong><span>${esc(phaseLabel(t))} · ${esc(t.collect_date)}</span></div></div><div class="tooltip-grid"><b>当前约束</b><div>同模式 / 同关卡 / 最新采样</div><b>推荐属性</b><div>${esc(selected)}</div><b>风险模式</b><div>${esc(riskMode)}</div><b>模板表现</b><div>Rank ${esc(t.rank??'-')} · ${t.app_rate==null?'-':pct(t.app_rate)} · ${t.avg_round==null?'-':esc(Number(t.avg_round).toFixed(2))}</div><b>Box命中</b><div>${item.ownedCount}/4，成型 ${item.buildReadyCount}/${item.ownedCount}，缺 ${item.missingCount}</div><b>属性命中</b><div>全队 ${item.elementHits} · 核心 ${item.coreElementHits}</div><b>风险</b><div>${esc(riskText)}</div><b>分数</b><div>${Math.round(item.score)}</div><b>来源</b><div>${esc(t.source_kind||'')} · ${esc(t.source_file||'')}</div></div>`;
  moveTooltip(evt);
}
