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
const REC_STRATEGIES=[['final','末层实战'],['custom','按弱点配队']];
const REC_SORT_MODES=[['balanced','综合推荐'],['history','历史表现'],['box','Box 即战力']];
const DEFAULT_REC_TEAM_COUNTS={moc:'2',pf:'2',as:'2',aa:'2'};
const COLORS=['#2563eb','#dc2626','#16a34a','#9333ea','#ea580c','#0891b2','#be123c','#4f46e5','#65a30d','#a16207','#0f766e','#7c3aed','#db2777','#475569'];
const BOX_KEY='hsr_endgame_box_v1';
const BOX_UNDO_LIMIT=20;
const REC_KEY='hsr_endgame_recommender_v1';
const PAGES=new Set(['analysis','banner','box','recommender']);
const desktopMode=globalThis.__MIHO_DESKTOP__===true;
let DATA=null;
let state={page:PAGES.has(location.hash.slice(1))?location.hash.slice(1):'box',mode:'moc',view:'trend',role:'main_dps',tiers:new Set(TIERS),metric:'app_rate',limit:'12',search:'',avatars:true,focus:null,hover:null};
let box={owned:new Set(),builds:{},buildSlug:'',element:'all',path:'all',role:'all',rarity:'all',status:'all',search:'',saveStatus:'浏览器缓存',exportStatus:''};
let rec={mode:'moc',scope:'',strategy:'final',sortMode:'balanced',teamCounts:{...DEFAULT_REC_TEAM_COUNTS},targetScopes:{},elements:{},constraints:{},locks:{},gap:'1',riskMode:'warn',limit:'8',search:''};
const BANNER_PHASES=[['current','当期UP'],['next','后续卡池'],['recent','历史参考'],['all','全部含已结束']];
let banner={phase:'current',search:''};
let boxSaveTimer=null,boxSaveRevision=0,boxSaveChain=Promise.resolve(),boxPendingSave=null;
let boxUndoStack=[];
let recConstraintMessage='';
let recSlateNotice='';
let recSlateWorker=null,recSlateWorkerFailed=false,recSlateRequestId=0,recSlateCurrentPrepared=null;
const recSlatePending=new Map();

const $=id=>document.getElementById(id);
const ns='http://www.w3.org/2000/svg';
function number(v){const n=Number(v);return Number.isFinite(n)?n:null}
function pct(v){const n=number(v);return n==null?'':`${n.toFixed(2)}%`}
function analysisMetricPolicy(mode=state.mode,metric=state.metric){
  if(metric==='app_rate')return{key:'app_rate',label:'出场率 %',summary:'出场率',higherBetter:true,sortable:true,valid:value=>value!=null&&value>=0,format:value=>`${value.toFixed(2)}%`};
  const scoreMode=mode==='pf'||mode==='as';
  const label=mode==='moc'?'平均回合':mode==='pf'?'虚构得分':mode==='as'?'末日得分':'表现原值';
  return{key:'avg_round',label,summary:label,higherBetter:scoreMode?true:mode==='moc'?false:null,sortable:mode!=='aa',valid:value=>value!=null&&value>0&&Math.abs(value-99.99)>.001,format:value=>Number.isInteger(value)?String(value):value.toFixed(2)};
}
function analysisMetricValue(row,mode=state.mode,metric=state.metric){const policy=analysisMetricPolicy(mode,metric),raw=row?.[policy.key];if(raw==null||raw==='')return null;const value=number(raw);return policy.valid(value)?value:null}
function fmtMetric(v){const policy=analysisMetricPolicy(),value=number(v);return value!=null&&policy.valid(value)?policy.format(value):'缺失'}
function esc(v){return String(v??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}
function safeRelativeUrl(v,requirePath=false){const text=String(v??'').trim();if(!text||text.startsWith('/')||text.includes('\\')||/[\u0000-\u001f\u007f]/.test(text)||/^[a-z][a-z0-9+.-]*:/i.test(text)||text.startsWith('//'))return '';let path=text.split(/[?#]/,1)[0];try{for(let i=0;i<3;i++){const decoded=decodeURIComponent(path);if(decoded===path)break;path=decoded;}}catch{return '';}if(path.startsWith('/')||path.includes('\\')||path.split('/').includes('..')||(requirePath&&!path))return '';return text}
function safeLinkUrl(v){const text=String(v??'').trim();if(!text||text.includes('\\')||/[\u0000-\u001f\u007f]/.test(text))return '';if(/^[a-z][a-z0-9+.-]*:/i.test(text)){try{const url=new URL(text);return url.protocol==='https:'&&url.host&&!url.username&&!url.password?text:'';}catch{return '';}}return safeRelativeUrl(text,false)}
function safeAvatarUrl(v){return safeRelativeUrl(v,true)}
function installExternalLinkBridge(){
  if(!desktopMode||globalThis.parent===globalThis)return;
  document.addEventListener('click',event=>{const link=event.target?.closest?.('a[href]');if(!link)return;const raw=String(link.getAttribute('href')||'').trim();if(!/^https:\/\//i.test(raw))return;const safe=safeLinkUrl(raw);if(!safe)return;let url;try{url=new URL(safe);}catch{return;}if(url.protocol!=='https:'||!url.host||url.username||url.password)return;event.preventDefault();globalThis.parent.postMessage({schema_version:'miho-visualizer-external-link-v1',url:url.href},'*');},true);
}

function installBoxFlushBridge(){
  const parentWindow=globalThis.parent;
  if(typeof globalThis.addEventListener!=='function'||!parentWindow||parentWindow===globalThis)return;
  globalThis.addEventListener('message',event=>{
    const message=event?.data;
    if(event.source!==parentWindow||!message||typeof message!=='object'||Array.isArray(message)||message.schema_version!=='miho-visualizer-box-flush-request-v1'||typeof message.request_id!=='string'||!message.request_id||message.request_id.length>128)return;
    Promise.resolve(flushBoxSave()).then(()=>parentWindow.postMessage({schema_version:'miho-visualizer-box-flush-result-v1',request_id:message.request_id,ok:true},'*')).catch(()=>parentWindow.postMessage({schema_version:'miho-visualizer-box-flush-result-v1',request_id:message.request_id,ok:false,error:'Box 保存失败，请重试。'},'*'));
  });
}

installBoxFlushBridge();

fetch(`./data.json?v=${Date.now()}`,{cache:'no-store'})
  .then(r=>r.ok?r.json():Promise.reject(new Error(`数据请求失败（${r.status}）`)))
  .then(async data=>{DATA=data;loadRecSettings();if(desktopMode)await syncBoxFromServer();else loadBox();init();render();})
  .catch(err=>{const guard=desktopMode?'为保护你的 Box，本次没有启用编辑；请重启应用后再试。':'';document.body.innerHTML=`<main class="app-shell"><h1>应用启动失败</h1><p>${esc(err.message)}</p><p>${esc(guard)}</p></main>`;});

function init(){
  installExternalLinkBridge();
  $('metaLine').textContent=`Prydwen T榜更新：${DATA.meta.tierUpdatedAt||DATA.meta.tierUpdatedDate||'未知'} · 本地数据生成：${DATA.meta.generatedAt||'未知'} · Box 自动保存`;
  makeButtons('appTabs',[['box','我的 Box'],['analysis','终局分析'],['banner','卡池'],['recommender','组队推荐']],state.page,v=>{state.page=v;history.replaceState(null,'',`#${v}`);render();});
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
  syncFreshnessNavigation();
}

function initBannerControls(){
  ensureBannerPhase();
  makeButtons('bannerPhaseControl',BANNER_PHASES,banner.phase,v=>{banner.phase=v;renderBanner();});
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
  $('boxUndoBtn').onclick=undoBoxChange;
  $('boxMarkVisibleBtn').onclick=()=>markVisible(true);
  $('boxClearVisibleBtn').onclick=()=>markVisible(false);
  $('boxBuildVisibleBtn').onclick=()=>setVisibleBuild('max');
  $('boxClearBuildVisibleBtn').onclick=()=>setVisibleBuild('clear');
  $('boxClearAllBtn').onclick=clearEntireBox;
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
  makeButtons('recModeControl',modes.length?modes:MODES,rec.mode,v=>{rec.mode=v;recConstraintMessage='';ensureRecScope();saveRecSettings();syncRecControls();renderRecommender();});
  makeButtons('recStrategyControl',REC_STRATEGIES,rec.strategy,v=>{rec.strategy=v;rec.scope='';recConstraintMessage='';ensureRecScope();saveRecSettings();syncRecControls();renderRecommender();});
  $('recTeamCountSelect').onchange=e=>{const previous=recPlanScopes();rec.teamCounts[rec.mode]=e.target.value==='3'?'3':'2';recConstraintMessage='';ensureRecScope();const active=new Set(recPlanScopes().map(scope=>recLockKey(scope.key)));const removed=previous.filter(scope=>!active.has(recLockKey(scope.key))&&clearRecLock(scope.key));if(removed.length)recSlateNotice=`已取消 ${removed.map(scope=>scope.label).join('、')} 的锁定阵容。`;saveRecSettings();syncRecControls();renderRecommender();};
  $('recScopeSelect').onchange=e=>{rec.scope=e.target.value;recConstraintMessage='';saveRecSettings();syncRecControls();renderRecommender();};
  $('recSortSelect').onchange=e=>{rec.sortMode=normalizeRecSortMode(e.target.value);saveRecSettings();renderRecommender();};
  const elementBox=$('recElementControl');
  elementBox.innerHTML='';
  ELEMENT_ORDER.forEach(element=>{const b=document.createElement('button');b.type='button';b.textContent=element;b.title=`${element} 推荐属性`;b.onclick=()=>{const set=recElementSet();set.has(element)?set.delete(element):set.add(element);setRecElementSet(set);saveRecSettings();syncRecControls();renderRecommender();};elementBox.appendChild(b);});
  $('recGapSelect').onchange=e=>{rec.gap=e.target.value;saveRecSettings();renderRecommender();};
  $('recRiskSelect').onchange=e=>{rec.riskMode=e.target.value;saveRecSettings();renderRecommender();};
  $('recLimitSelect').onchange=e=>{rec.limit=e.target.value;saveRecSettings();renderRecommender();};
  $('recSearchInput').oninput=e=>{rec.search=e.target.value.trim().toLowerCase();saveRecSettings();renderRecommender({recomputeSlate:false});};
  $('recRequireBtn').onclick=()=>addRecConstraint('required');
  $('recExcludeBtn').onclick=()=>addRecConstraint('excluded');
  $('recConstraintClearBtn').onclick=clearRecConstraints;
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
    ensureBannerPhase();
    [...$('bannerPhaseControl').children].forEach(b=>b.classList.toggle('active',b.dataset.value===banner.phase));
    $('bannerSearchInput').value='';
    renderBanner();return;
  }
  if(state.page==='recommender'){
    rec={mode:'moc',scope:'',strategy:'final',sortMode:'balanced',teamCounts:{...DEFAULT_REC_TEAM_COUNTS},targetScopes:{},elements:rec.elements||{},constraints:rec.constraints||{},locks:{},gap:'1',riskMode:'warn',limit:'8',search:''};
    recConstraintMessage='';
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
  [...$('recStrategyControl').children].forEach(b=>b.classList.toggle('active',b.dataset.value===rec.strategy));
  const custom=rec.strategy==='custom';
  $('recPlanControls').classList.toggle('custom',custom);
  $('recTeamCountSelect').value=String(recTeamCount());
  $('recTeamCountControl').classList.toggle('hidden',!custom);
  $('recTargetScopeControl').classList.toggle('hidden',custom);
  $('recScopeLabel').textContent=custom?'目标队伍':'实战节点';
  $('recElementLabel').textContent=custom?'敌方弱点（用于选队）':'敌方弱点（默认仅标注）';
  $('recScopeSelect').title=custom?'每一队独立保存弱点与角色硬约束':'使用当前模式最新采样期的同节点真实队伍模板';
  $('recElementControl').title=custom?'从当前模式全部实战阵容池中，优先寻找核心输出命中任一弱点的队伍':'同节点真实队伍排序优先；弱点只标注适配，选择“过滤风险”后才会硬筛选';
  $('recStrategyHint').textContent=custom?'适合普通层或自定义敌人：默认 2 队，每队按弱点从当前模式完整实战阵容池找队。':'选择实际准备挑战的关卡；联合优化只在已选关卡之间分配 Box，未选关卡不会预留角色。弱点默认不改榜，“过滤风险”时才参与硬筛选。';
  renderRecTargetScopeControls();
  const options=recScopeOptions(rec.mode);
  const select=$('recScopeSelect');
  select.innerHTML=options.map(o=>`<option value="${esc(o.key)}">${esc(o.label)}</option>`).join('');
  if(!options.some(o=>o.key===rec.scope))rec.scope=options[0]?.key||'';
  select.value=rec.scope;
  const selected=recElementSet();
  [...$('recElementControl').children].forEach(b=>b.classList.toggle('active',selected.has(b.textContent)));
  $('recSortSelect').value=normalizeRecSortMode(rec.sortMode);$('recGapSelect').value=rec.gap;$('recRiskSelect').value=rec.riskMode||'warn';$('recLimitSelect').value=rec.limit;$('recSearchInput').value=rec.search;
  syncRecConstraintControls();
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
    return{slug,points,latest,max:Math.max(...points.map(p=>analysisMetricValue(p)??0),0)};
  });
  const policy=analysisMetricPolicy();
  if(policy.sortable)list.sort((a,b)=>{const av=analysisMetricValue(a.latest),bv=analysisMetricValue(b.latest);if(av==null||bv==null){if(av==null&&bv==null)return a.slug.localeCompare(b.slug);return av==null?1:-1;}const diff=policy.higherBetter?bv-av:av-bv;return diff||(number(b.latest.rating)||0)-(number(a.latest.rating)||0)||a.slug.localeCompare(b.slug);});
  return list;
}

function limitSeries(series){return state.limit==='all'?series:series.slice(0,Number(state.limit)||12)}

function latestSampleMeta(rows,mode){
  const dated=rows.filter(r=>r.collect_date).slice().sort((a,b)=>String(a.collect_date).localeCompare(String(b.collect_date)));
  const latest=dated[dated.length-1]||{};
  const date=latest.collect_date||'';
  const phases=(DATA.phaseInfoRows||[]).filter(r=>r.mode===mode);
  const info=phases.find(r=>r.collect_date===date&&(!latest.phase_ver||r.phase_ver===latest.phase_ver))||phases.find(r=>r.phase_ver===latest.phase_ver)||{};
  const status=info.phase_status||latest.phase_status||'unknown';
  return{date:date||'未知',label:status==='current'?'当前周期':status==='expired'?'历史样本':'周期未知'};
}

function renderAnalysis(){
  hideTooltip();
  const rows=filteredRows();
  const allSeries=groupSeries(rows);
  const series=limitSeries(allSeries);
  const modeLabel=MODES.find(x=>x[0]===state.mode)?.[1]||state.mode;
  const roleLabel=ROLES.find(x=>x[0]===state.role)?.[1]||state.role;
  const viewLabel=VIEWS.find(x=>x[0]===state.view)?.[1]||state.view;
  const modeRows=sourceRows().filter(r=>r.tier_mode===state.mode);
  const sample=latestSampleMeta(modeRows,state.mode);
  $('chartTitle').textContent=`${modeLabel} · ${roleLabel} · ${viewLabel}`;
  const metricPolicy=analysisMetricPolicy();
  const aaNote=state.mode==='aa'?' · AA 为全 Boss / 未拆分本地数据，表现原值仅展示不排序':'';
  const emptyNote=rows.length?'':modeRows.length?' · 当前筛选无匹配':' · 该模式数据未生成';
  $('chartSubtitle').textContent=`展示 ${series.length}/${allSeries.length} 个角色，${rows.length} 个采样点 · 最新采样 ${sample.date} · ${sample.label}${emptyNote}${aaNote}`;
  $('summaryBadges').innerHTML=[`${[...state.tiers].join(' / ')||'未选T档'}`,metricPolicy.summary,state.limit==='all'?'全量':`Top ${state.limit}`].map(x=>`<span>${esc(x)}</span>`).join('');
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
  const dates=[...new Set(rows.map(r=>r.collect_date))].sort();const metric=state.metric,policy=analysisMetricPolicy();
  const values=rows.map(r=>analysisMetricValue(r));const max=Math.max(10,...values.filter(v=>v!=null))*1.14;
  const x=d=>margin.l+(dates.length<=1?cw/2:cw*dates.indexOf(d)/(dates.length-1));const y=v=>margin.t+ch-ch*(Math.min(v,max))/max;
  drawAxes(svg,margin,cw,ch,max,dates,x,y,policy.label);const defs=add(svg,'defs',{});
  series.forEach((s,idx)=>{const color=COLORS[idx%COLORS.length];const points=s.points.map(p=>{const value=analysisMetricValue(p);return value==null?null:[x(p.collect_date),y(value),p];});const segments=[];let segment=[];points.forEach(point=>{if(point)segment.push(point);else if(segment.length){segments.push(segment);segment=[];}});if(segment.length)segments.push(segment);if(!segments.length)return;segments.forEach(pts=>{const path=pts.map((p,i)=>`${i?'L':'M'}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(' ');const line=add(svg,'path',{d:path,stroke:color,class:`series-line ${dimClass(s.slug)}`});line.dataset.slug=s.slug;const hit=add(svg,'path',{d:path,class:'series-hit'});hit.dataset.slug=s.slug;bindHover(hit,pts[pts.length-1][2],s.slug);});points.filter(Boolean).forEach(([xx,yy,p],pi)=>drawPoint(svg,defs,xx,yy,p,s.slug,color,idx,pi,11));});
}

function drawAxes(svg,margin,cw,ch,max,dates,x,y,label){
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
  const margin={l:158,r:48,t:36,b:38};const rowH=Math.max(34,Math.min(48,(height-margin.t-margin.b)/Math.max(series.length,1)));const chartH=rowH*series.length;const policy=analysisMetricPolicy();
  const values=series.map(s=>analysisMetricValue(s.latest)).filter(v=>v!=null);const max=Math.max(10,...values)*1.12;const x=v=>margin.l+(width-margin.l-margin.r)*Math.min(v,max)/max;
  add(svg,'text',{x:margin.l,y:22,class:'axis-label'}).textContent=`最近一期${policy.label}`;
  for(let i=0;i<=4;i++){const val=max*i/4,xx=x(val);add(svg,'line',{x1:xx,y1:margin.t-10,x2:xx,y2:margin.t+chartH,class:'grid'});add(svg,'text',{x:xx,y:margin.t+chartH+22,'text-anchor':'middle',class:'axis-label'}).textContent=val.toFixed(0);}
  const defs=add(svg,'defs',{});series.forEach((s,idx)=>{const row=s.latest;const color=COLORS[idx%COLORS.length];const yy=margin.t+idx*rowH+rowH/2;const val=analysisMetricValue(row);add(svg,'text',{x:18,y:yy-2,class:`rank-label ${dimClass(s.slug)}`}).textContent=`${idx+1}. ${row.character_name_cn||row.character_name_en||s.slug}`;add(svg,'text',{x:18,y:yy+14,class:`muted-label ${dimClass(s.slug)}`}).textContent=`${row.tier} · ${row.tags||row.path_cn||row.character_name_en||''}`;if(val==null){add(svg,'text',{x:margin.l+8,y:yy+4,class:'axis-label'}).textContent='缺失';return;}const xx=x(val);const bar=add(svg,'line',{x1:margin.l,y1:yy,x2:xx,y2:yy,stroke:color,'stroke-width':8,'stroke-linecap':'round',class:`bar-line ${dimClass(s.slug)}`});bar.dataset.slug=s.slug;bindHover(bar,row,s.slug);drawPoint(svg,defs,xx,yy,row,s.slug,color,idx,0,14);add(svg,'text',{x:Math.min(width-42,xx+18),y:yy+4,class:'axis-label'}).textContent=fmtMetric(val);});
}

function renderHeatmap(series){
  const {svg,width,height}=chartBox();if(!series.length){renderEmpty(svg,width,height);return;}
  const rows=series.flatMap(s=>s.points);const dates=[...new Set(rows.map(r=>r.collect_date))].sort();const metric=state.metric;const margin={l:156,r:24,t:42,b:36};const cellGap=4;const cw=(width-margin.l-margin.r-(dates.length-1)*cellGap)/Math.max(dates.length,1);const rowH=Math.max(28,Math.min(42,(height-margin.t-margin.b)/Math.max(series.length,1)));const values=rows.map(r=>analysisMetricValue(r)).filter(v=>v!=null);const max=Math.max(10,...values);const defs=add(svg,'defs',{});
  dates.forEach((d,i)=>add(svg,'text',{x:margin.l+i*(cw+cellGap)+cw/2,y:24,'text-anchor':'middle',class:'heat-head'}).textContent=String(d).slice(5));
  series.forEach((s,idx)=>{const rowY=margin.t+idx*rowH;const latest=s.latest;add(svg,'text',{x:48,y:rowY+rowH/2+4,class:`heat-name ${dimClass(s.slug)}`}).textContent=latest.character_name_cn||latest.character_name_en||s.slug;drawMiniAvatar(svg,defs,24,rowY+rowH/2,latest,s.slug,idx);const byDate=new Map(s.points.map(p=>[p.collect_date,p]));dates.forEach((d,j)=>{const p=byDate.get(d);const val=analysisMetricValue(p);const intensity=val==null?0:Math.max(.08,Math.min(1,val/max));const fill=val==null?'transparent':metric==='app_rate'?`rgba(23,76,90,${intensity})`:`rgba(37,99,235,${intensity})`;const rect=add(svg,'rect',{x:margin.l+j*(cw+cellGap),y:rowY+5,width:Math.max(10,cw),height:rowH-10,fill,class:`heat-cell ${val==null?'missing ':''}${dimClass(s.slug)}`});rect.dataset.slug=s.slug;if(p)bindHover(rect,p,s.slug);rect.addEventListener('click',()=>toggleFocus(s.slug));});});
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
  const policy=analysisMetricPolicy(row.tier_mode||state.mode,'avg_round'),rawValue=number(row.avg_round),metricText=rawValue!=null&&policy.valid(rawValue)?policy.format(rawValue):'缺失';
  tt.innerHTML=`<div class="tooltip-head"><img src="${esc(row.icon_url)}" alt=""><div><strong>${esc(row.character_name_cn||row.character_name_en||row.character_slug)}</strong><span>${esc(row.character_name_en)} · ${esc(row.character_slug)}</span></div></div><div class="tooltip-grid"><b>模式</b><div>${esc(row.tier_mode_cn)}${row.sub_mode_cn?` · ${esc(row.sub_mode_cn)}`:''}</div><b>职能/T档</b><div>${esc(row.role_group_cn)} · ${esc(row.tier)}${row.rating?` (${esc(row.rating)})`:''}</div><b>属性/命途</b><div>${esc(row.element_cn||'')} ${esc(row.path_cn||'')}</div><b>日期/期数</b><div>${esc(row.collect_date)} · ${esc(row.phase_ver)}</div><b>出场率</b><div>${pct(row.app_rate)}</div><b>${esc(policy.label)}</b><div>${esc(metricText)}${policy.higherBetter==null&&metricText!=='缺失'?' · 仅展示':''}</div><b>标签</b><div>${esc(row.tags||'')}</div><b>质量标记</b><div>${esc(row.quality_flag||'')}</div></div>`;
  moveTooltip(evt);
}
function moveTooltip(evt){const target=evt.currentTarget;const tt=target?.closest?.('.box-card')?$('boxTooltip'):(target?.closest?.('.rec-card')||target?.closest?.('.rec-slate-card'))?$('recTooltip'):$('tooltip');const pad=14;let x=evt.clientX+16,y=evt.clientY+16;const rect=tt.getBoundingClientRect();if(x+rect.width+pad>window.innerWidth)x=evt.clientX-rect.width-16;if(y+rect.height+pad>window.innerHeight)y=evt.clientY-rect.height-16;tt.style.left=`${Math.max(pad,x)}px`;tt.style.top=`${Math.max(pad,y)}px`;}
function hideTooltip(){$('tooltip').hidden=true;}

function renderCharacters(series){
  const boxEl=$('characterList');boxEl.innerHTML='';
  series.forEach((s,idx)=>{const r=s.latest;const card=document.createElement('button');card.type='button';card.dataset.slug=s.slug;card.className=`character-card ${state.focus===s.slug?'active':''} ${activeSlug()&&activeSlug()!==s.slug?'dim':''}`;card.onclick=()=>toggleFocus(s.slug);card.onmouseenter=e=>{setHover(s.slug);showTooltip(e,r);};card.onmousemove=moveTooltip;card.onmouseleave=clearHover;card.innerHTML=`<img src="${esc(r.icon_url)}" alt=""><div><div class="name">${idx+1}. ${esc(r.character_name_cn||r.character_name_en||s.slug)}</div><div class="meta">${esc(r.character_name_en)} · ${esc(r.tier)} · ${esc(r.element_cn||'')} ${esc(r.path_cn||r.tags||'')}</div></div><div><span class="pill">${esc(r.tier)}</span><div class="rate">${pct(r.app_rate)}</div></div>`;boxEl.appendChild(card);});
}

function renderChangelog(series){const slugs=new Set(series.map(s=>s.slug));const boxEl=$('changelogList');boxEl.innerHTML='';const related=DATA.changelogRows.filter(r=>String(r.character_slugs||'').split(';').some(s=>slugs.has(s)));const rows=(related.length?related:DATA.changelogRows).slice(0,8);rows.forEach(r=>{const item=document.createElement('div');item.className='changelog-item';const text=String(r.text||'');item.innerHTML=`<time>${esc(r.changelog_date)}</time><p>${esc(text).slice(0,420)}${text.length>420?'...':''}</p>`;boxEl.appendChild(item);});}

function bannerPhaseMatches(status,phase){return phase==='all'||(phase==='recent'?status==='recent'||status==='previous':status===phase)}
function ensureBannerPhase(){const rows=DATA.bannerRows||[];if(!rows.length)return;if(!rows.some(r=>bannerPhaseMatches(r.phase_status,banner.phase)))banner.phase=BANNER_PHASES.map(([value])=>value).find(value=>value!=='all'&&rows.some(r=>bannerPhaseMatches(r.phase_status,value)))||'all';}
function bannerRows(){const q=banner.search;return (DATA.bannerRows||[]).filter(r=>bannerPhaseMatches(r.phase_status,banner.phase)&&(!q||[r.character_slug,r.character_name_cn,r.character_name_en,r.banner_role,r.element_cn,r.path_cn,r.role_group_cns,...(r.analysis_tags||[])].some(x=>String(x||'').toLowerCase().includes(q))));}
function renderBanner(){const allRows=DATA.bannerRows||[],rows=bannerRows();$('bannerTitle').textContent='卡池情报';$('bannerSubtitle').textContent='这里只做数据提炼：复刻看历史趋势和组队占用，新角色/联动角色只做公开信息与 Box 关系识别。';$('bannerBadges').innerHTML=[`角色 ${rows.length}`,`Box ${box.owned.size}`,'趋势仅供参考'].map(x=>`<span>${esc(x)}</span>`).join('');const grid=$('bannerGrid');grid.innerHTML='';if(!allRows.length){grid.innerHTML='<div class="rec-empty">卡池数据未生成或为空；终局统计与 Box 数据不受影响</div>';return;}if(!rows.length){const phaseLabel=BANNER_PHASES.find(([value])=>value===banner.phase)?.[1]||'当前阶段';grid.innerHTML=`<div class="rec-empty">${banner.search?'当前搜索与阶段没有匹配角色':`${esc(phaseLabel)}暂无记录`}；卡池数据已载入 ${allRows.length} 条</div>`;return;}const phases=[...new Map(rows.map(r=>[r.phase_id,{id:r.phase_id,title:r.phase_title,subtitle:r.phase_subtitle,date:r.date_range,source:r.source_label,url:r.source_url,status:r.phase_status}])).values()];phases.forEach(phase=>{const section=document.createElement('section'),phaseUrl=safeLinkUrl(phase.url);section.className='banner-section';section.innerHTML=`<div class="banner-section-head"><div><h3>${esc(phase.title||'卡池')}</h3><p>${esc(phase.subtitle||'')} · ${esc(phase.date||'时间待确认')}</p></div>${phaseUrl?`<a href="${esc(phaseUrl)}" target="_blank" rel="noopener noreferrer">${esc(phase.source||'来源')}</a>`:''}</div><div class="banner-card-grid"></div>`;const inner=section.querySelector('.banner-card-grid');rows.filter(r=>r.phase_id===phase.id).forEach(row=>inner.appendChild(bannerCard(row)));grid.appendChild(section);});}
function bannerCard(row){const slug=row.character_slug,info={...charInfo(slug),...row},ins=bannerInsight(row);const card=document.createElement('article');card.className=`banner-card ${box.owned.has(slug)?'owned':''} ${row.phase_status}`;const tags=(row.analysis_tags||[]).slice(0,5).map(t=>`<span>${esc(t)}</span>`).join('');const name=info.character_name_cn||info.character_name_en||slug;const roleText=info.role_group_cns||roleCn(info)||'未分类';card.innerHTML=`<div class="banner-art">${info.icon_url?`<img src="${esc(info.icon_url)}" alt="" loading="lazy" decoding="async">`:`<div class="avatar-fallback">${esc(name.slice(0,2))}</div>`}<button class="mini-owned" type="button">${box.owned.has(slug)?'已拥有':'加入Box'}</button></div><div class="banner-body"><div class="banner-kicker">${esc(row.banner_role||row.phase_subtitle||'卡池角色')}</div><h3>${esc(name)}</h3><p class="banner-meta">${esc(info.rarity?`${info.rarity}星`:'-')} · ${esc(info.element_cn||'属性未知')} · ${esc(info.path_cn||'命途未知')} · ${esc(roleText)} · ${esc(ins.tierText)}</p><svg class="spark" viewBox="0 0 220 54">${sparkline(ins.points)}</svg><div class="rec-tags">${tags}</div><div class="banner-facts">${ins.lines.slice(0,4).map(x=>`<p>${esc(x)}</p>`).join('')}</div><div class="banner-relations">${ins.relations.slice(0,6).map(x=>`<span class="${x.owned?'owned':''}">${esc(x.name)}${x.count?` ×${x.count}`:''}</span>`).join('')||'<span>暂无历史组合</span>'}</div></div>`;card.querySelector('.mini-owned').onclick=e=>{e.stopPropagation();commitBoxChange(()=>{box.owned.has(slug)?box.owned.delete(slug):box.owned.add(slug);box.buildSlug=slug;},renderBanner);};card.addEventListener('mouseenter',e=>showBannerTooltip(e,row,ins));card.addEventListener('mousemove',moveBannerTooltip);card.addEventListener('mouseleave',()=>{$('bannerTooltip').hidden=true;});return card;}
function bannerInsight(row){const slug=row.character_slug,info={...charInfo(slug),...row};const grouped=new Map();(DATA.usageRows||DATA.trendRows||[]).filter(r=>r.character_slug===slug&&(r.sub_mode==='all'||r.sub_mode==='all_bosses'||!r.sub_mode)).forEach(r=>{const key=`${r.tier_mode||r.mode}|${r.collect_date||r.tier_updated_date||''}`;const current=grouped.get(key);if(!current||Number(r.app_rate||0)>Number(current.app_rate||0))grouped.set(key,r);});const usage=[...grouped.values()].sort((a,b)=>String(a.collect_date||a.tier_updated_date).localeCompare(String(b.collect_date||b.tier_updated_date)));const points=usage.map(r=>({date:r.collect_date||r.tier_updated_date,value:number(r.app_rate)||0,mode:r.tier_mode_cn||r.mode_cn||r.tier_mode||r.mode}));const tierText=tierSummaryFor(slug),tierDetails=tierDetailsFor(slug);const teams=(DATA.teamTemplates||[]).filter(t=>(t.chars||[]).includes(slug));const relations=relationRows(slug,teams);const ownedRelation=relations.filter(r=>r.owned).slice(0,4).map(r=>r.name).join('、');const lines=[`T档：Prydwen 按模式分档，${tierText}。`];if(points.length){const latest=points[points.length-1],recent=points.slice(-3),avg=recent.reduce((s,p)=>s+p.value,0)/recent.length,delta=points.length>1?latest.value-points[0].value:0;lines.push(`历史：${points.length} 个样本点，最新 ${latest.value.toFixed(2)}%，近三期均值 ${avg.toFixed(2)}%，首尾变化 ${delta.toFixed(2)}%。`);}else lines.push('历史：本地高难暂无完整样本，不能用趋势替代实测。');if(teams.length){const bestRank=Math.min(...teams.map(t=>number(t.rank)||9999));lines.push(`组队：历史模板 ${teams.length} 条，最好 Rank ${bestRank}，常见队友见下方关系。`);}else lines.push('组队：暂无可回溯历史队伍，等待实测或人工分析。');if(ownedRelation)lines.push(`Box关系：你已有角色中，历史上相关度较高的是 ${ownedRelation}。`);else lines.push('Box关系：暂未发现与你已有 Box 的直接历史组合；需要看属性、命途与队友缺口。');if(row.phase_status==='next'||!points.length)lines.push('未知项：技能组、倍率、光锥价值、实战轴和环境适配仍需外部分析确认。');if(row.focus)lines.push(`关注点：${row.focus}`);return{points,relations,lines,tierText,tierDetails};}
function tierRowsFor(slug){const resolved=canonicalSlug(slug);return (DATA.tierRows||[]).filter(r=>canonicalSlug(r.character_slug)===resolved);}
function bestTierInMode(slug,mode){return tierRowsFor(slug).filter(r=>r.tier_mode===mode).sort((a,b)=>(TIER_RANK[a.tier]??9)-(TIER_RANK[b.tier]??9))[0]||null;}
function tierSummaryFor(slug){const modes=[['moc','混沌'],['pf','虚构'],['as','末日']];const rows=tierRowsFor(slug);if(!rows.length)return '未分档';return modes.map(([mode,label])=>{const row=bestTierInMode(slug,mode);return `${label} ${row?.tier||'未分档'}`;}).join(' / ');}
function tierDetailsFor(slug){const modes=[['moc','混沌回忆'],['pf','虚构叙事'],['as','末日幻影']];const rows=tierRowsFor(slug);if(!rows.length)return 'Prydwen 当前未收录 T 档';return modes.map(([mode,label])=>{const row=bestTierInMode(slug,mode);return `${label}：${row?`${row.role_group_cn||row.role_group||''} ${row.tier}`:'未分档'}`;}).join('；');}
function relationRows(slug,teams){const map=new Map();teams.forEach(t=>(t.chars||[]).forEach(c=>{if(c===slug)return;const item=map.get(c)||{slug:c,name:charName(c),count:0,owned:box.owned.has(c)};item.count++;item.owned=box.owned.has(c);map.set(c,item);}));return [...map.values()].sort((a,b)=>Number(b.owned)-Number(a.owned)||b.count-a.count||a.name.localeCompare(b.name));}
function sparkline(points){if(!points.length)return '<text x="10" y="31" class="spark-empty">暂无趋势</text>';const max=Math.max(1,...points.map(p=>p.value)),xs=points.map((p,i)=>8+i*(204/Math.max(1,points.length-1))),ys=points.map(p=>46-(p.value/max)*36),d=xs.map((x,i)=>`${i?'L':'M'}${x.toFixed(1)} ${ys[i].toFixed(1)}`).join(' ');return `<path d="${d}" class="spark-line"/><path d="M8 47H212" class="spark-axis"/>${xs.map((x,i)=>`<circle cx="${x.toFixed(1)}" cy="${ys[i].toFixed(1)}" r="3.2" class="spark-dot"/>`).join('')}`;}
function showBannerTooltip(evt,row,ins){const tt=$('bannerTooltip');tt.innerHTML=`<div class="tooltip-grid"><b>角色</b><span>${esc(row.character_name_cn||row.character_name_en||row.character_slug)}</span><b>阶段</b><span>${esc(row.phase_title||'-')}</span><b>定位</b><span>${esc([row.element_cn,row.path_cn,row.role_group_cns].filter(Boolean).join(' · ')||'未知')}</span><b>模式T档</b><span>${esc(ins.tierDetails||ins.tierText||'未分档')}</span><b>分析输入</b><span>${esc(ins.lines.join('；'))}</span></div>`;tt.hidden=false;moveBannerTooltip(evt);}
function moveBannerTooltip(evt){const tt=$('bannerTooltip');let x=evt.clientX+16,y=evt.clientY+16;const rect=tt.getBoundingClientRect();if(x+rect.width+12>innerWidth)x=evt.clientX-rect.width-16;if(y+rect.height+12>innerHeight)y=evt.clientY-rect.height-16;tt.style.left=`${Math.max(12,x)}px`;tt.style.top=`${Math.max(12,y)}px`;}

function normalizeRecTeamCounts(raw){const input=raw&&typeof raw==='object'&&!Array.isArray(raw)?raw:{};return Object.fromEntries(Object.entries(DEFAULT_REC_TEAM_COUNTS).map(([mode,fallback])=>[mode,String(input[mode])==='3'?'3':String(input[mode])==='2'?'2':fallback]));}
function normalizeRecTargetScopes(raw){if(!raw||typeof raw!=='object'||Array.isArray(raw))return{};return Object.fromEntries(Object.entries(raw).filter(([,values])=>Array.isArray(values)).map(([key,values])=>[key,[...new Set(values.map(value=>String(value||'').trim()).filter(Boolean))]]));}
function normalizeRecLocks(raw){if(!raw||typeof raw!=='object'||Array.isArray(raw))return{};return Object.fromEntries(Object.entries(raw).map(([key,value])=>[String(key||'').trim(),String(value||'').trim()]).filter(([key,value])=>key&&value));}
function normalizeRecSortMode(value){return REC_SORT_MODES.some(([mode])=>mode===value)?value:'balanced'}
function recSortMeta(mode=rec.sortMode){const key=normalizeRecSortMode(mode);return{
  balanced:{key,label:'综合推荐',scoreLabel:'综合分',description:'当前 Box 适配为主，并按模式轻量参考 Rank、占比和有效表现。'},
  history:{key,label:'历史表现',scoreLabel:'历史参考分',description:'只比较同模式候选池内的 Rank、占比和有效表现，不代表当前 Box 可立即成队。'},
  box:{key,label:'Box 即战力',scoreLabel:'Box 分',description:'只比较拥有、练度、缺口、可替补和跨队冲突，不采用历史 Rank、占比或表现。'},
}[key];}
function loadRecSettings(){try{const raw=JSON.parse(localStorage.getItem(REC_KEY)||'{}');rec={...rec,...raw,strategy:raw.strategy==='custom'?'custom':'final',sortMode:normalizeRecSortMode(raw.sortMode),teamCounts:normalizeRecTeamCounts(raw.teamCounts),targetScopes:normalizeRecTargetScopes(raw.targetScopes),elements:raw.elements&&typeof raw.elements==='object'&&!Array.isArray(raw.elements)?raw.elements:{},constraints:raw.constraints&&typeof raw.constraints==='object'&&!Array.isArray(raw.constraints)?raw.constraints:{},locks:normalizeRecLocks(raw.locks),riskMode:raw.riskMode||'warn'};}catch{rec={...rec,strategy:'final',sortMode:'balanced',teamCounts:{...DEFAULT_REC_TEAM_COUNTS},targetScopes:{},elements:{},constraints:{},locks:{},riskMode:'warn'};}ensureRecScope();}
function saveRecSettings(){localStorage.setItem(REC_KEY,JSON.stringify({updatedAt:new Date().toISOString(),mode:rec.mode,scope:rec.scope,strategy:rec.strategy,sortMode:normalizeRecSortMode(rec.sortMode),teamCounts:rec.teamCounts,targetScopes:rec.targetScopes,gap:rec.gap,riskMode:rec.riskMode||'warn',limit:rec.limit,search:rec.search,elements:rec.elements,constraints:rec.constraints,locks:normalizeRecLocks(rec.locks)}));}
function recTeamCount(mode=rec.mode){return String(rec.teamCounts?.[mode])==='3'?3:2}
function isCustomScope(scope){return /^custom-[123]$/.test(String(scope||''))}
function recSettingKey(mode=rec.mode,scope=rec.scope){return `${mode}|${scope||''}`}
function recLockKey(scope,mode=rec.mode,strategy=rec.strategy){return `${mode}|${strategy==='custom'?'custom':'final'}|${scope||''}`}
function recLockedVariantKey(scope,mode=rec.mode,strategy=rec.strategy){return normalizeRecLocks(rec.locks)[recLockKey(scope,mode,strategy)]||''}
function clearRecLock(scope,mode=rec.mode,strategy=rec.strategy){const key=recLockKey(scope,mode,strategy);if(!rec.locks||!Object.prototype.hasOwnProperty.call(rec.locks,key))return false;delete rec.locks[key];return true}
function recElementSet(mode=rec.mode,scope=rec.scope){return new Set(rec.elements[recSettingKey(mode,scope)]||[])}
function setRecElementSet(set,mode=rec.mode,scope=rec.scope){rec.elements[recSettingKey(mode,scope)]=[...set].sort((a,b)=>ELEMENT_ORDER.indexOf(a)-ELEMENT_ORDER.indexOf(b));}
function recConstraintSets(mode=rec.mode,scope=rec.scope){const raw=rec.constraints?.[recSettingKey(mode,scope)]||{};const normalize=(values,limit)=>new Set((Array.isArray(values)?values:[]).map(canonicalSlug).filter(Boolean).slice(0,limit));const required=normalize(raw.required,4),excluded=normalize(raw.excluded,160);required.forEach(slug=>excluded.delete(slug));return{required,excluded};}
function setRecConstraintSets(sets,mode=rec.mode,scope=rec.scope){const order=(a,b)=>releaseOrder(charInfo(a))-releaseOrder(charInfo(b))||charName(a).localeCompare(charName(b));rec.constraints[recSettingKey(mode,scope)]={required:[...sets.required].sort(order),excluded:[...sets.excluded].sort(order)};}
function constraintRosterRows(){const current=new Set(scopeTemplates(rec.mode,rec.scope).flatMap(t=>(t.chars||[]).map(canonicalSlug)));return (DATA.rosterRows||[]).slice().sort((a,b)=>Number(box.owned.has(b.character_slug))-Number(box.owned.has(a.character_slug))||Number(current.has(b.character_slug))-Number(current.has(a.character_slug))||releaseOrder(a)-releaseOrder(b)||charName(a.character_slug).localeCompare(charName(b.character_slug)));}
function syncRecConstraintControls(){const select=$('recCharacterSelect'),previous=select.value;select.innerHTML='<option value="">选择角色…</option>'+constraintRosterRows().map(row=>`<option value="${esc(row.character_slug)}">${box.owned.has(row.character_slug)?'已拥有 · ':'未拥有 · '}${esc(charName(row.character_slug))}</option>`).join('');if([...select.options].some(option=>option.value===previous))select.value=previous;const sets=recConstraintSets();renderConstraintChips('recRequiredList',sets.required,'required');renderConstraintChips('recExcludedList',sets.excluded,'excluded');$('recConstraintMessage').textContent=recConstraintMessage;}
function renderConstraintChips(id,values,kind){const root=$(id);root.innerHTML='';values.forEach(slug=>{const button=document.createElement('button');button.type='button';button.className='constraint-chip';button.textContent=charName(slug);button.title=`移除${kind==='required'?'必须上场':'排除'}：${charName(slug)}`;button.onclick=()=>removeRecConstraint(kind,slug);root.appendChild(button);});}
function addRecConstraint(kind){const slug=canonicalSlug($('recCharacterSelect').value);if(!slug){recConstraintMessage='请先选择角色。';syncRecConstraintControls();return;}const sets=recConstraintSets(),target=sets[kind],other=sets[kind==='required'?'excluded':'required'];if(kind==='required'&&!target.has(slug)&&target.size>=4){recConstraintMessage='一队最多 4 人；请先移除一个必须上场角色。';syncRecConstraintControls();return;}other.delete(slug);target.add(slug);setRecConstraintSets(sets);recConstraintMessage=`${charName(slug)}已设为${kind==='required'?'必须上场':'排除'}。`;saveRecSettings();renderRecommender();}
function removeRecConstraint(kind,slug){const sets=recConstraintSets();sets[kind].delete(canonicalSlug(slug));setRecConstraintSets(sets);recConstraintMessage='已更新当前关卡约束。';saveRecSettings();renderRecommender();}
function clearRecConstraints(){delete rec.constraints[recSettingKey()];recConstraintMessage='已清空当前关卡的角色约束。';saveRecSettings();renderRecommender();}
function recScopeDisplayLabel(mode,key,fallback){if(key==='all')return '综合队伍池';if((mode==='pf'||mode==='as')&&/^4-[123]$/.test(key)){const node=key.slice(-1);return `${key} / 第${node}战斗侧${node==='3'?'（星芒）':''}`;}if(mode==='moc'&&key==='12-3')return '12-3 / 第3战斗侧（星芒）';if(mode==='aa'&&/^1-[123]$/.test(key))return `${key} / 骑士 ${key.slice(-1)}`;if(mode==='aa'&&key==='2-1')return '2-1 / 王棋';return fallback||key;}
function realRecScopeOptions(mode){
  const map=new Map();
  currentModeTemplates(mode).forEach(t=>{if(!map.has(t.scope_key))map.set(t.scope_key,{key:t.scope_key,label:recScopeDisplayLabel(mode,t.scope_key,t.scope_label),order:Number(t.scope_order)||90});});
  return [...map.values()].sort((a,b)=>a.order-b.order||a.label.localeCompare(b.label));
}
function recScopeOptions(mode){return rec.strategy==='custom'?Array.from({length:recTeamCount(mode)},(_,index)=>({key:`custom-${index+1}`,label:`第 ${index+1} 队`,order:index+1})):realRecScopeOptions(mode);}
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
function isPlainBoxObject(value){return Boolean(value)&&typeof value==='object'&&!Array.isArray(value)}
function readBoxRaw(){try{return JSON.parse(localStorage.getItem(BOX_KEY)||'{}');}catch{return{};}}
function rawOwnedList(raw){const rows=Array.isArray(raw.owned)?raw.owned:Object.keys(raw.owned||{}).filter(k=>raw.owned[k]);return rows.filter(slug=>slug&&slug!=='__codex_test__');}
function readableBoxRaw(raw={}){if(!raw||typeof raw!=='object'||Array.isArray(raw))return{};const version=raw.version==null?1:Number(raw.version);return [1,2,3].includes(version)?raw:{}}
function applyBoxRaw(raw){raw=readableBoxRaw(raw);const aliases=boxAliasMap();const owned=rawOwnedList(raw);box.owned=new Set(owned.map(s=>aliases.get(s)||s).filter(Boolean));box.builds={};Object.entries(raw.builds||{}).forEach(([slug,build])=>{const resolved=aliases.get(slug)||slug;if(resolved)box.builds[resolved]=normalizeBuild(build);});box.buildSlug=aliases.get(raw.buildSlug)||raw.buildSlug||'';if(box.buildSlug&&!box.owned.has(box.buildSlug))box.buildSlug='';box.saveStatus=raw.fromServer?'本机自动保存':'浏览器缓存';}
function loadBox(){try{applyBoxRaw(readBoxRaw());}catch{box.owned=new Set();box.builds={};box.buildSlug='';box.saveStatus='浏览器缓存';}boxUndoStack=[];}
function boxPayload(){const builds={};Object.entries(box.builds||{}).forEach(([slug,build])=>{const normalized=normalizeBuild(build);if(buildRecorded(normalized))builds[slug]=normalized;});return{version:2,updatedAt:new Date().toISOString(),owned:[...box.owned].sort(),buildSlug:box.buildSlug||'',builds};}
function boxSnapshot(){const payload=boxPayload(),builds=Object.fromEntries(Object.entries(payload.builds).sort(([left],[right])=>left.localeCompare(right)));return{version:payload.version,owned:[...payload.owned],buildSlug:payload.buildSlug,builds};}
function boxSnapshotKey(snapshot){return JSON.stringify(snapshot)}
function rememberBoxUndo(snapshot=boxSnapshot()){boxUndoStack.push(snapshot);if(boxUndoStack.length>BOX_UNDO_LIMIT)boxUndoStack.splice(0,boxUndoStack.length-BOX_UNDO_LIMIT);}
function syncBoxUndoControl(){const undo=$('boxUndoBtn'),clear=$('boxClearAllBtn');if(undo){undo.disabled=!boxUndoStack.length;undo.textContent=boxUndoStack.length?`撤销 (${boxUndoStack.length})`:'撤销';undo.title=boxUndoStack.length?'恢复上一步 Box 修改':'暂无可撤销修改';}if(clear)clear.disabled=!box.owned.size&&!Object.keys(boxSnapshot().builds).length;}
function commitBoxChange(mutator,renderer=renderBox){const before=boxSnapshot(),beforeKey=boxSnapshotKey(before);mutator();const after=boxSnapshot();if(beforeKey===boxSnapshotKey(after)){if(typeof renderer==='function')renderer();return false;}rememberBoxUndo(before);saveBox();if(typeof renderer==='function')renderer();return true;}
function undoBoxChange(){const previous=boxUndoStack.pop();if(!previous)return;applyBoxRaw(previous);saveBox();renderBox();}
function parseBoxImportDocument(raw){if(!isPlainBoxObject(raw))throw new Error('导入文件必须是 Box JSON 对象');const version=raw.version==null?1:Number(raw.version);if(![1,2,3].includes(version))throw new Error('不支持该 Box 文件版本');const hasOwned=Object.prototype.hasOwnProperty.call(raw,'owned'),hasBuilds=Object.prototype.hasOwnProperty.call(raw,'builds');if(!hasOwned&&!hasBuilds)throw new Error('文件没有 Box 角色或练度字段，未执行导入');if(!hasOwned||(version>1&&!hasBuilds))throw new Error('Box 文件缺少完整的拥有与练度字段，未执行导入');if(hasOwned&&!Array.isArray(raw.owned)&&!isPlainBoxObject(raw.owned))throw new Error('Box 拥有列表格式无效');if(hasBuilds&&!isPlainBoxObject(raw.builds))throw new Error('Box 练度记录格式无效');const aliases=boxAliasMap(),owned=[...new Set(rawOwnedList(raw).map(slug=>aliases.get(slug)||String(slug||'').trim()).filter(Boolean))].sort(),builds={};Object.entries(raw.builds||{}).forEach(([slug,build])=>{const resolved=aliases.get(slug)||String(slug||'').trim(),normalized=normalizeBuild(isPlainBoxObject(build)?build:{});if(resolved&&buildRecorded(normalized))builds[resolved]=normalized;});const normalizedBuilds=Object.fromEntries(Object.entries(builds).sort(([left],[right])=>left.localeCompare(right)));if(!owned.length&&!Object.keys(normalizedBuilds).length)throw new Error('导入文件没有角色或练度记录；如需清空请使用“清空整个 Box”');return{version:2,owned,buildSlug:'',builds:normalizedBuilds};}
function boxImportPreview(raw){const next=parseBoxImportDocument(raw),current=boxSnapshot(),currentOwned=new Set(current.owned),nextOwned=new Set(next.owned),currentBuilds=current.builds,nextBuilds=next.builds;return{next,ownedAdded:[...nextOwned].filter(slug=>!currentOwned.has(slug)).length,ownedRemoved:[...currentOwned].filter(slug=>!nextOwned.has(slug)).length,buildAdded:Object.keys(nextBuilds).filter(slug=>!Object.prototype.hasOwnProperty.call(currentBuilds,slug)).length,buildChanged:Object.keys(nextBuilds).filter(slug=>Object.prototype.hasOwnProperty.call(currentBuilds,slug)&&JSON.stringify(nextBuilds[slug])!==JSON.stringify(currentBuilds[slug])).length,buildCleared:Object.keys(currentBuilds).filter(slug=>!Object.prototype.hasOwnProperty.call(nextBuilds,slug)).length};}
function formatBoxImportPreview(preview){return`导入预览（将替换当前 Box）：\n拥有：新增 ${preview.ownedAdded}，移除 ${preview.ownedRemoved}\n练度：新增 ${preview.buildAdded}，变化 ${preview.buildChanged}，清除 ${preview.buildCleared}\n\n确认导入？此操作之后可以撤销。`;}
function clearEntireBox(){const snapshot=boxSnapshot(),buildCount=Object.keys(snapshot.builds).length;if(!snapshot.owned.length&&!buildCount){box.exportStatus='Box 已为空';renderBox();return;}if(!globalThis.confirm(`确认清空整个 Box？\n将移除 ${snapshot.owned.length} 个已拥有角色和 ${buildCount} 条练度记录。\n\n清空后仍可使用“撤销”恢复。`))return;commitBoxChange(()=>{box.owned.clear();box.builds={};box.buildSlug='';});}
function enqueueBoxServerSave(pending){if(boxPendingSave===pending)boxPendingSave=null;const operation=boxSaveChain.catch(()=>undefined).then(()=>pending.revision===boxSaveRevision?saveBoxToServer(pending.payload,pending.revision):undefined);boxSaveChain=operation;operation.catch(()=>{});return operation;}
function saveBox(){const payload=boxPayload();box.exportStatus='';const exportButton=$('boxExportBtn');if(exportButton&&!exportButton.disabled){exportButton.textContent='导出Box';exportButton.title='';}clearTimeout(boxSaveTimer);boxSaveTimer=null;if(!desktopMode){localStorage.setItem(BOX_KEY,JSON.stringify(payload));boxPendingSave=null;box.saveStatus='已保存到浏览器';}else{const pending={payload,revision:++boxSaveRevision};boxPendingSave=pending;box.saveStatus='正在保存到本机';boxSaveTimer=setTimeout(()=>{boxSaveTimer=null;if(boxPendingSave===pending)boxPendingSave=null;enqueueBoxServerSave(pending).catch(()=>{});},180);}if(state.page==='box'||state.page==='banner')requestAnimationFrame(()=>{if(state.page==='box')renderBox();else renderBanner();});}
async function flushBoxSave(){if(!desktopMode)return;clearTimeout(boxSaveTimer);boxSaveTimer=null;const pending=boxPendingSave;boxPendingSave=null;if(pending)await enqueueBoxServerSave(pending);else await boxSaveChain;}
globalThis.flushBoxSave=flushBoxSave;
function syncBoxFromServer(){return fetch('/api/hsr/box',{cache:'no-store'}).then(r=>r.ok?r.json():Promise.reject(new Error(`Box 读取失败（${r.status}）`))).then(server=>{server.fromServer=true;applyBoxRaw(server);boxUndoStack=[];localStorage.setItem(BOX_KEY,JSON.stringify(server));box.saveStatus='本机自动保存';});}
function saveBoxToServer(payload,revision){return fetch('/api/hsr/box',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}).then(r=>r.ok?r.json():Promise.reject(new Error('Box 保存失败'))).then(saved=>{if(revision!==boxSaveRevision)return;localStorage.setItem(BOX_KEY,JSON.stringify(saved));box.saveStatus='本机自动保存';if(state.page==='box'||state.page==='banner')render();}).catch(()=>{if(revision===boxSaveRevision){box.saveStatus='保存失败，请重试';if(state.page==='box'||state.page==='banner')render();}throw new Error('Box 保存失败，请重试。');});}
function releaseOrder(row){const n=Number(row.release_order);return Number.isFinite(n)?n:99999}
function matchesBoxStatus(row){if(box.status==='all')return true;if(box.status==='owned')return box.owned.has(row.character_slug);if(box.status==='missing')return !box.owned.has(row.character_slug);if(box.status.startsWith('banner_'))return String(row.banner_statuses||'').split(';').includes(box.status.replace('banner_',''));return true}
function boxStatusLabel(){return{all:'全部状态',owned:'已拥有',missing:'未拥有',banner_current:'当期UP',banner_next:'后续卡池',banner_recent:'历史参考'}[box.status]||box.status}
function boxStatusText(status){return{current:'当期UP',next:'后续卡池',recent:'历史参考',previous:'已结束'}[status]||status}
function filteredRoster(){const q=box.search;return DATA.rosterRows.filter(r=>(box.element==='all'||r.element_cn===box.element)&&(box.path==='all'||r.path_cn===box.path)&&(box.role==='all'||String(r.role_groups||'').split(';').includes(box.role))&&(box.rarity==='all'||String(r.rarity)===box.rarity)&&matchesBoxStatus(r)&&(!q||[r.character_name_cn,r.character_name_en,r.character_slug,r.element_cn,r.path_cn,r.role_group_cns,r.banner_phase_titles].some(x=>String(x||'').toLowerCase().includes(q)))).sort((a,b)=>releaseOrder(a)-releaseOrder(b)||String(a.character_name_en).localeCompare(String(b.character_name_en)));}
function toggleOwned(slug){const resolved=canonicalSlug(slug);commitBoxChange(()=>{if(box.owned.has(resolved)){box.owned.delete(resolved);if(box.buildSlug===resolved)box.buildSlug='';}else{box.owned.add(resolved);box.buildSlug=resolved;}});}
function renderBox(){const rows=filteredRoster();const total=DATA.rosterRows.length;const owned=DATA.rosterRows.filter(r=>box.owned.has(r.character_slug)).length;const built=DATA.rosterRows.filter(r=>box.owned.has(r.character_slug)&&buildState(buildFor(r.character_slug)).ready).length;syncBoxUndoControl();renderBuildEditor();$('boxSubtitle').textContent=`展示 ${rows.length}/${total} 个角色，已拥有 ${owned} 个，已成型 ${built} 个。点击卡片切换拥有，点「练度」维护等级/光锥/星魂/专武/行迹/遗器。`;$('boxBadges').innerHTML=[box.exportStatus||box.saveStatus||'浏览器缓存',box.element==='all'?'全部属性':box.element,box.path==='all'?'全部命途':box.path,boxStatusLabel(),`成型 ${built}/${owned||0}`].map(x=>`<span>${esc(x)}</span>`).join('');const grid=$('boxGrid');grid.innerHTML='';rows.forEach(row=>{const owned=box.owned.has(row.character_slug);const buildText=owned?buildShortLabel(row.character_slug):'未拥有';const bannerTag=String(row.banner_statuses||'').split(';').filter(Boolean)[0];const card=document.createElement('article');card.tabIndex=0;card.setAttribute('role','button');card.className=`box-card ${owned?'owned':'missing'} ${box.buildSlug===row.character_slug?'selected':''}`;card.dataset.slug=row.character_slug;card.onclick=()=>toggleOwned(row.character_slug);card.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();toggleOwned(row.character_slug);}};card.onmouseenter=e=>showBoxTooltip(e,row);card.onmousemove=moveTooltip;card.onmouseleave=()=>{$('boxTooltip').hidden=true;};card.innerHTML=`<button class="build-button" type="button">练度</button><span class="owned-dot"></span><img src="${esc(row.icon_url)}" alt="" loading="lazy" decoding="async"><div class="box-name">${esc(row.character_name_cn||row.character_name_en||row.character_slug)}</div><div class="box-meta">${esc(row.element_cn||'')} · ${esc(row.path_cn||'')}${bannerTag?` · ${esc(boxStatusText(bannerTag))}`:''}</div><div class="box-meta">${esc(row.role_group_cns||'未分类')}</div><div class="box-meta box-build">${esc(buildText)}</div>`;card.querySelector('.build-button').onclick=e=>{e.stopPropagation();selectBuild(row.character_slug);};grid.appendChild(card);});}
function selectBuild(slug){const resolved=canonicalSlug(slug);commitBoxChange(()=>{box.owned.add(resolved);box.buildSlug=resolved;});}
function renderBuildEditor(){const panel=$('buildEditor');if(!box.buildSlug||!box.owned.has(box.buildSlug)){panel.classList.add('hidden');return;}const row=charInfo(box.buildSlug);const state=buildState(buildFor(box.buildSlug));panel.classList.remove('hidden');$('buildEditorIcon').src=row.icon_url||'';$('buildEditorTitle').textContent=`${charName(box.buildSlug)} · 练度`;$('buildEditorSubtitle').textContent=`${row.element_cn||'未知'} · ${row.path_cn||'未知'} · ${roleCn(row)}`;$('buildLevelSelect').value=String(state.level);$('buildLcSelect').value=String(state.lc);$('buildEidolonSelect').value=String(state.eidolon);$('buildSignatureSelect').value=state.signature;$('buildTraceSelect').value=state.traces;$('buildRelicSelect').value=state.relics;$('buildScoreText').textContent=`${state.label} · ${state.coreRecorded?state.basePercent:0}% · ${state.configLabel}`;}
function updateBuildField(field,value){if(!box.buildSlug)return;commitBoxChange(()=>{const build=buildFor(box.buildSlug);build[field]=value;box.builds[box.buildSlug]=normalizeBuild(build);box.owned.add(box.buildSlug);});}
function fullBuild(prev={}){const b=normalizeBuild(prev);return{...b,level:80,lc:80,traces:'max',relics:'great'}}
function setBuildPreset(kind){if(!box.buildSlug)return;commitBoxChange(()=>{if(kind==='clear')delete box.builds[box.buildSlug];else box.builds[box.buildSlug]=fullBuild(box.builds[box.buildSlug]||{});box.owned.add(box.buildSlug);});}
function setVisibleBuild(kind){commitBoxChange(()=>{filteredRoster().forEach(r=>{if(kind==='clear')delete box.builds[r.character_slug];else{box.owned.add(r.character_slug);box.builds[r.character_slug]=fullBuild(box.builds[r.character_slug]||{});}});});}
function showBoxTooltip(evt,row){const tt=$('boxTooltip');const owned=box.owned.has(row.character_slug);const state=buildState(buildFor(row.character_slug));const eidolonText=state.eidolon==='unset'?'未录入':`${state.eidolon}魂`;tt.hidden=false;tt.innerHTML=`<div class="tooltip-head"><img src="${esc(row.icon_url)}" alt=""><div><strong>${esc(row.character_name_cn||row.character_name_en)}</strong><span>${esc(row.character_name_en)} · ${esc(row.character_slug)}</span></div></div><div class="tooltip-grid"><b>收集状态</b><div>${owned?'已拥有':'未拥有'}</div><b>练度</b><div>${owned?`${esc(state.label)} · ${state.coreRecorded?state.basePercent:0}%`:'未拥有'}</div><b>星魂/专武</b><div>${owned?`${esc(eidolonText)} · ${esc(signatureText(state.signature))}`:'未拥有'}</div><b>属性/命途</b><div>${esc(row.element_cn||'未知')} · ${esc(row.path_cn||'未知')}</div><b>星级</b><div>${esc(row.rarity||'未知')}</div><b>职能</b><div>${esc(row.role_group_cns||'未分类')}</div><b>排序</b><div>新旧序 #${esc(row.release_order)}</div><b>来源</b><div>${esc(row.source||'')}</div></div>`;moveTooltip(evt);}
function markVisible(value){const rows=filteredRoster(),targets=new Set(rows.map(row=>row.character_slug));if(!value&&box.owned.size&&[...box.owned].every(slug=>targets.has(slug))){alert('该批量操作会清空整个 Box。请使用“清空整个 Box”并确认后执行。');return;}commitBoxChange(()=>{rows.forEach(r=>{if(value)box.owned.add(r.character_slug);else{box.owned.delete(r.character_slug);if(box.buildSlug===r.character_slug)box.buildSlug='';}});});}
async function exportBox(){const payload={...boxPayload(),exportedAt:new Date().toISOString()};const button=$('boxExportBtn');if(desktopMode){if(button.disabled)return;button.disabled=true;button.textContent='正在导出…';button.title='';box.exportStatus='正在导出 Box…';renderBox();try{const response=await fetch('/api/hsr/box/export',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});if(!response.ok)throw new Error(`本机导出失败（${response.status}）`);const receipt=await response.json();if(receipt?.schema_version!=='miho-box-export-receipt-v1'||typeof receipt.file_name!=='string'||!receipt.file_name.startsWith('hsr_box_state')||!Number.isSafeInteger(receipt.bytes)||receipt.bytes<=0)throw new Error('本机导出回执无效');button.textContent='已导出到下载文件夹';button.title=receipt.file_name;box.exportStatus=`已导出到下载文件夹：${receipt.file_name}`;}catch(error){button.textContent='导出失败';button.title='';box.exportStatus=`导出失败：${error instanceof Error?error.message:'未知错误'}`;}finally{button.disabled=false;renderBox();}return;}const blob=new Blob([JSON.stringify(payload,null,2)],{type:'application/json'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='hsr_box_state.json';document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function importBox(evt){const file=evt.target.files?.[0];if(!file)return;const reader=new FileReader();reader.onload=()=>{try{const preview=boxImportPreview(JSON.parse(String(reader.result||'{}')));if(!globalThis.confirm(formatBoxImportPreview(preview)))return;commitBoxChange(()=>applyBoxRaw(preview.next));}catch(err){alert(`导入失败：${err instanceof Error?err.message:'文件格式无效'}`);}finally{evt.target.value='';}};reader.readAsText(file);}

function rosterBySlug(){if(!DATA._rosterBySlug){DATA._rosterBySlug=new Map();(DATA.rosterRows||[]).forEach(r=>{DATA._rosterBySlug.set(r.character_slug,r);String(r.alias_slugs||'').split(';').forEach(s=>{if(s)DATA._rosterBySlug.set(s,r);});});}return DATA._rosterBySlug;}
function charInfo(slug){return rosterBySlug().get(slug)||{character_slug:slug,character_name_cn:'',character_name_en:slug,element_cn:'',path_cn:'',role_groups:'unknown',role_group_cns:'未分类',icon_url:''};}
function charName(slug){const r=charInfo(slug);return r.character_name_cn||r.character_name_en||slug}
function phaseName(row){return row?.phase_name_cn||(row?.phase_name?'中文期名待维护':'')}
function phaseLabel(row){const ver=row?.phase_ver||'';const name=phaseName(row);return `${ver} ${name}`.trim()}
function roleList(row){return String(row.role_groups||'unknown').split(';').filter(Boolean)}
function roleCn(row){return row.role_group_cns||roleList(row).join('/')}
function phaseStatusLabel(status){return status==='expired'?'已过期':status==='future'?'未开始':status==='current'?'当前周期':'日期未知'}
function freshnessStatusLabel(status){return status==='active'?'当前周期':status==='future'?'未来周期':status==='stale'?'历史样本':'周期未知'}
function modeFreshness(mode=rec.mode,fallback={}){
  const raw=DATA?.freshness?.[mode]||DATA?.data_quality?.modes?.[mode]?.freshness||DATA?.dataQuality?.modes?.[mode]?.freshness;
  const fallbackStatus=fallback.phase_status==='expired'?'stale':fallback.phase_status==='future'?'future':fallback.phase_status==='current'?'active':'unknown';
  const status=['active','future','stale','unknown'].includes(raw?.status)?raw.status:fallbackStatus;
  return{status,sampleDate:raw?.sample_date||fallback.collect_date||'',startDate:raw?.start_date||fallback.start_date||'',endDate:raw?.end_date||fallback.end_date||'',source:raw?.source||fallback.source||fallback.source_path||''};
}
function freshnessPeriodText(freshness){return`${freshness.startDate||'未知'} 至 ${freshness.endDate||'未知'}`}
function freshnessBadgeHtml(freshness){return freshness.status==='active'?'':`<span class="data-${esc(freshness.status)}">${esc(freshnessStatusLabel(freshness.status))}</span>`}
function freshnessTemplateLabel(status,currentLabel){return status==='stale'?'历史模板（源滞后）':status==='future'?'未来周期样本（尚未开始）':status==='unknown'?'周期状态未知的样本':currentLabel}
function syncFreshnessNavigation(mode=rec.mode){const root=$('appTabs');if(!root)return;const button=[...root.children].find(item=>item.dataset.value==='recommender');if(!button)return;const freshness=modeFreshness(mode),suffix=freshness.status==='active'?'':` · ${freshnessStatusLabel(freshness.status)}`;button.textContent=`组队推荐${suffix}`;button.classList.remove('freshness-stale','freshness-future','freshness-unknown');if(freshness.status!=='active')button.classList.add(`freshness-${freshness.status}`);button.title=`${MODES.find(([value])=>value===mode)?.[1]||mode}：${freshnessStatusLabel(freshness.status)}，不阻止浏览`;}
function templateRecencyKey(t){return `${String(t.collect_date||'')}|${String(t.phase_ver||'')}|${String(t.snapshot_id||'')}`}
function currentModeTemplates(mode){const rows=(DATA.teamTemplates||[]).filter(t=>t.mode===mode);const usable=rows.filter(t=>!['expired','future'].includes(t.phase_status));const pool=usable.length?usable:rows;const latest=pool.reduce((m,t)=>templateRecencyKey(t)>m?templateRecencyKey(t):m,'');return pool.filter(t=>templateRecencyKey(t)===latest);}
function templatePoolKey(template){return (template.chars||[]).map(canonicalSlug).sort().join('|')}
function compareTemplatePerformance(candidate,current){const candidateEvidence=performanceEvidence(candidate),currentEvidence=performanceEvidence(current);if(candidateEvidence.valid!==currentEvidence.valid)return candidateEvidence.valid?-1:1;if(!candidateEvidence.valid||candidateEvidence.higherBetter==null)return 0;return candidateEvidence.higherBetter?currentEvidence.value-candidateEvidence.value:candidateEvidence.value-currentEvidence.value}
function preferPoolTemplate(candidate,current){const candidateRank=rankSortValue(candidate.rank),currentRank=rankSortValue(current.rank);if(candidateRank!==currentRank)return candidateRank<currentRank;const candidateRate=num(candidate.app_rate)??-1,currentRate=num(current.app_rate)??-1;if(candidateRate!==currentRate)return candidateRate>currentRate;const performanceDiff=compareTemplatePerformance(candidate,current);if(performanceDiff)return performanceDiff<0;return Number(candidate.scope_order||99)<Number(current.scope_order||99);}
function customPoolTemplates(mode){
  if(!DATA._customTeamPools)DATA._customTeamPools=new Map();
  if(DATA._customTeamPools.has(mode))return DATA._customTeamPools.get(mode);
  const groups=new Map();
  currentModeTemplates(mode).filter(t=>t.scope_key!=='all').forEach(template=>{const key=templatePoolKey(template);if(!key)return;const group=groups.get(key)||{best:template,scopes:new Set()};group.scopes.add(template.scope_key);if(preferPoolTemplate(template,group.best))group.best=template;groups.set(key,group);});
  const pool=[...groups.values()].map(group=>({...group.best,evidenceScopes:[...group.scopes].sort(),evidenceScopeCount:group.scopes.size})).sort((a,b)=>rankSortValue(a.rank)-rankSortValue(b.rank)||(num(b.app_rate)??-1)-(num(a.app_rate)??-1)||templatePoolKey(a).localeCompare(templatePoolKey(b)));
  DATA._customTeamPools.set(mode,pool);
  return pool;
}
function scopeTemplates(mode,scope){return isCustomScope(scope)?customPoolTemplates(mode):currentModeTemplates(mode).filter(t=>t.scope_key===scope);}
function num(v){const n=Number(v);return Number.isFinite(n)?n:null}
function metricNumber(v){return v==null||v===''?null:num(v)}
function rankSortValue(v){const value=metricNumber(v);return value!=null&&value>0?value:Number.POSITIVE_INFINITY}
function rankDisplayText(v){const value=metricNumber(v);return value!=null&&value>0?metricValueText(value):'缺失'}
function canonicalSlug(slug){return charInfo(slug).character_slug||slug}
function deploymentGroup(slug){const raw=String(slug||''),info=DATA?charInfo(raw):{},resolved=info.character_slug||raw,declared=info.deployment_group;if(declared)return declared;if(/^trailblazer(?:-|$)/.test(resolved))return'trailblazer';if(['march-7th','march-7th-swordmaster','march-7th-the-hunt'].includes(resolved))return'march-7th';return resolved}
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
    if(build.coreRecorded&&build.baseScore<.68)reasons.push({type:'build-low',text:`练度待补 ${build.basePercent}%`,penalty:core?70:38,severe:core});
    else if(build.coreRecorded&&build.baseScore<.86)reasons.push({type:'build-mid',text:`练度未成型 ${build.basePercent}%`,penalty:core?32:16});
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
    if(coreHits===0)risks.push({type:'core-none',text:'核心输出未命中敌方弱点',penalty:180,severe:true});
  }
  return risks;
}

function scorePart(key,label,value,detail='',available=true){return{key,label,value:metricNumber(value)??0,detail,available:Boolean(available)}}
function scorePartsTotal(parts){return parts.reduce((sum,part)=>sum+(part.available?part.value:0),0)}
function metricValueText(value){if(value==null)return'缺失';return Number.isInteger(value)?String(value):value.toFixed(2)}
function performanceEvidence(template){
  const mode=template.mode,value=metricNumber(template.avg_round);
  if(mode==='moc'){
    const valid=value!=null&&value>0&&Math.abs(value-99.99)>.001;
    return{mode,value,valid,higherBetter:false,label:'平均回合',display:valid?`${metricValueText(value)} 回合`:'缺失',note:valid?'越低越好':'0 / 99.99 视为缺失'};
  }
  if(mode==='pf'||mode==='as'){
    const valid=value!=null&&value>0&&Math.abs(value-99.99)>.001,label=mode==='pf'?'虚构得分':'末日得分';
    return{mode,value,valid,higherBetter:true,label,display:valid?metricValueText(value):'缺失',note:valid?'越高越好':'0 / 99.99 视为缺失'};
  }
  const sentinel=value==null||value<=0||Math.abs(value-99.99)<=.001;
  return{mode,value,valid:false,higherBetter:null,label:'表现值',display:sentinel?'缺失':metricValueText(value),note:sentinel?'0 / 99.99 视为缺失':'方向未确认，仅展示'};
}
function balancedPerformanceScore(evidence){
  if(!evidence.valid)return 0;
  if(evidence.mode==='moc')return-evidence.value*1.2;
  if(evidence.mode==='pf')return Math.min(evidence.value/1000,45);
  if(evidence.mode==='as')return Math.min(evidence.value/100,45);
  return 0;
}
function balancedPerformanceDetail(evidence){
  const base=`${evidence.display} · ${evidence.note}`;
  if(!evidence.valid)return base;
  if(evidence.mode==='moc')return`${base} · 平均回合 × -1.2`;
  if(evidence.mode==='pf')return`${base} · 得分 ÷ 1000，上限 +45`;
  if(evidence.mode==='as')return`${base} · 得分 ÷ 100，上限 +45`;
  return base;
}
function relativeQuality(value,values,higherBetter){
  if(value==null||!values.length)return 0;
  const low=Math.min(...values),high=Math.max(...values);
  if(Math.abs(high-low)<1e-9)return 1;
  const ratio=(value-low)/(high-low);
  return higherBetter?ratio:1-ratio;
}
function finalizeRecommendationScores(items,sortMode=rec.sortMode){
  const validRanks=items.map(item=>metricNumber(item.template.rank)).filter(value=>value!=null&&value>0);
  const validRates=items.map(item=>metricNumber(item.template.app_rate)).filter(value=>value!=null&&value>0);
  const validPerformance=items.map(item=>item.performance).filter(evidence=>evidence.valid).map(evidence=>evidence.value);
  const activeMode=normalizeRecSortMode(sortMode);
  items.forEach(item=>{
    const rank=metricNumber(item.template.rank),rankValid=rank!=null&&rank>0,rankQuality=rankValid?relativeQuality(rank,validRanks,false):0;
    const rate=metricNumber(item.template.app_rate),rateValid=rate!=null&&rate>0,rateQuality=rateValid?relativeQuality(rate,validRates,true):0;
    const evidence=item.performance,performanceQuality=evidence.valid?relativeQuality(evidence.value,validPerformance,evidence.higherBetter):0;
    item.scoreParts.history=[
      scorePart('rank','Rank',rankQuality*45,rankValid?`Rank ${metricValueText(rank)} · 同候选相对 ${(rankQuality*100).toFixed(0)}% · 上限 45`:'Rank 缺失',rankValid),
      scorePart('app_rate','占比',rateQuality*30,rateValid?`占比 ${rate.toFixed(2)}% · 同候选相对 ${(rateQuality*100).toFixed(0)}% · 上限 30`:'占比缺失或为 0',rateValid),
      scorePart('performance',evidence.label,performanceQuality*25,`${evidence.display} · ${evidence.note}${evidence.valid?` · 同候选相对 ${(performanceQuality*100).toFixed(0)}% · 上限 25`:''}`,evidence.valid),
    ];
    item.scores.history=scorePartsTotal(item.scoreParts.history);
    item.scoreMode=activeMode;
    item.score=item.scores[activeMode];
  });
  return items;
}
function compareHistoryEvidence(a,b){
  const aRank=metricNumber(a.template.rank),bRank=metricNumber(b.template.rank),rankDiff=(aRank!=null&&aRank>0?aRank:Number.POSITIVE_INFINITY)-(bRank!=null&&bRank>0?bRank:Number.POSITIVE_INFINITY);
  if(rankDiff)return rankDiff;
  const aRate=metricNumber(a.template.app_rate),bRate=metricNumber(b.template.app_rate),rateDiff=(bRate!=null&&bRate>0?bRate:-1)-(aRate!=null&&aRate>0?aRate:-1);
  if(rateDiff)return rateDiff;
  if(a.performance.valid!==b.performance.valid)return Number(b.performance.valid)-Number(a.performance.valid);
  if(a.performance.valid&&b.performance.valid){const diff=b.performance.value-a.performance.value;return a.performance.higherBetter?diff:-diff;}
  return 0;
}
function compareRecommendations(a,b,weaknessDriven,selected,sortMode){
  if(weaknessDriven&&selected.size){const weaknessDiff=Number(b.weaknessMatched)-Number(a.weaknessMatched);if(weaknessDiff)return weaknessDiff;}
  const scoreDiff=b.score-a.score;if(scoreDiff)return scoreDiff;
  if(sortMode==='history'){const historyDiff=compareHistoryEvidence(a,b);return historyDiff||templatePoolKey(a.template).localeCompare(templatePoolKey(b.template));}
  if(sortMode==='box')return a.missingCount-b.missingCount||templatePoolKey(a.template).localeCompare(templatePoolKey(b.template));
  return a.missingCount-b.missingCount||rankSortValue(a.template.rank)-rankSortValue(b.template.rank)||templatePoolKey(a.template).localeCompare(templatePoolKey(b.template));
}

function rankedRecommendations(mode=rec.mode,scope=rec.scope,used=new Set(),options={}){
  const selected=recElementSet(mode,scope);
  const constraints=recConstraintSets(mode,scope);
  const reserved=new Set([...(options.reserved||[])].map(deploymentGroup));
  const weaknessDriven=isCustomScope(scope);
  const maxGap=Number(options.maxGap??rec.gap);
  const q=options.ignoreSearch?'':rec.search;
  const sortMode=normalizeRecSortMode(options.sortMode??rec.sortMode);
  const scored=finalizeRecommendationScores(scopeTemplates(mode,scope).filter(t=>templateMatchesConstraints(t,constraints)&&templateHasUniqueDeployments(t)).map(t=>scoreTemplate(t,selected,used,constraints,reserved,{targetScope:scope,weaknessDriven})),sortMode);
  return scored.filter(item=>{
    if(Number.isFinite(maxGap)&&item.missingCount>maxGap)return false;
    const riskMode=options.riskMode||rec.riskMode||'warn';
    if(riskMode==='filter'&&item.risks.length)return false;
    if(reserved.size&&item.finalChars.some(slug=>reserved.has(deploymentGroup(slug))))return false;
    if(q&&!item.searchText.includes(q))return false;
    return true;
  }).sort((a,b)=>compareRecommendations(a,b,weaknessDriven,selected,sortMode));
}

function templateMatchesConstraints(template,constraints){const chars=new Set((template.chars||[]).map(canonicalSlug));return [...constraints.required].every(slug=>chars.has(slug))&&[...constraints.excluded].every(slug=>!chars.has(slug));}
function templateHasUniqueDeployments(template){const groups=(template.chars||[]).map(deploymentGroup);return new Set(groups).size===groups.length}

function scoreTemplate(template,selectedElements,used,constraints=recConstraintSets(template.mode,template.scope_key),externalReserved=new Set(),options={}){
  const chars=template.chars||[];
  const usedGroups=new Set([...used].map(deploymentGroup));
  const members=chars.map(slug=>{const info=charInfo(slug);const resolved=canonicalSlug(slug);const build=buildFor(resolved);const buildMeta=buildState(build);return{slug,info,build,buildState:buildMeta,owned:box.owned.has(resolved),selected:selectedElements.has(info.element_cn),used:usedGroups.has(deploymentGroup(resolved)),core:isCoreMember(info)}});
  const ownedCount=members.filter(m=>m.owned).length;
  const buildRecordedCount=members.filter(m=>m.owned&&m.buildState.recorded).length;
  const buildReadyCount=members.filter(m=>m.owned&&m.buildState.ready).length;
  const ownedBuildScore=members.filter(m=>m.owned).reduce((sum,m)=>sum+m.buildState.score,0);
  const missing=members.filter(m=>!m.owned);
  const conflictCount=members.filter(m=>m.used).length;
  const elementHits=members.filter(m=>m.selected).length;
  const coreMembers=members.filter(m=>m.core);
  const coreElementHits=coreMembers.filter(m=>m.selected).length;
  members.forEach(m=>{m.risks=memberRisk(m,template.mode);});
  const reserved=new Set([...chars,...used,...constraints.excluded,...externalReserved].map(deploymentGroup));
  const substitutions=[];
  missing.forEach(member=>{const candidates=constraints.required.has(canonicalSlug(member.slug))?[]:substituteCandidates(member.slug,reserved);substitutions.push({missing:member,candidates});});
  const defaultSubstitutions=new Map(),defaultReserved=new Set(reserved);
  substitutions.forEach(substitution=>{const candidate=substitution.candidates.find(row=>!defaultReserved.has(deploymentGroup(row.character_slug)));if(candidate){defaultSubstitutions.set(canonicalSlug(substitution.missing.slug),candidate);defaultReserved.add(deploymentGroup(candidate.character_slug));}});
  substitutions.forEach(substitution=>{const preferred=defaultSubstitutions.get(canonicalSlug(substitution.missing.slug));if(!preferred)return;substitution.candidates=[preferred,...substitution.candidates.filter(candidate=>candidate.character_slug!==preferred.character_slug)];});
  const fillCount=substitutions.filter(s=>s.candidates.length).length;
  const memberRisks=members.flatMap(m=>m.risks.map(r=>({...r,slug:m.slug,name:charName(m.slug)})));
  const attributeRisks=teamRisk(members,selectedElements);
  const risks=[...memberRisks,...attributeRisks];
  const weaknessConfigured=selectedElements.size>0;
  const weaknessMatched=weaknessConfigured&&coreElementHits>0;
  const weaknessScore=options.weaknessDriven&&weaknessConfigured?(weaknessMatched?140:-220):0;
  const app=metricNumber(template.app_rate),rank=metricNumber(template.rank),performance=performanceEvidence(template);
  const baseParts=[
    scorePart('owned','拥有',ownedCount*45,`${ownedCount}/4，每人 +45`),
    scorePart('build','练度',ownedBuildScore*90,`已拥有角色练度合计 ${ownedBuildScore.toFixed(3)} × 90`),
    scorePart('missing','缺口',-missing.length*66,`${missing.length} 人，每人 -66`),
    scorePart('conflict','跨队冲突',-conflictCount*180,`${conflictCount} 人，每人 -180`),
    scorePart('substitute','可替补',fillCount*34,`${fillCount} 个缺口找到替补，每个 +34`),
    scorePart('complete','满员',missing.length===0?95:0,missing.length===0?'原队 4 人全部拥有 +95':'未满员'),
  ];
  const boxParts=baseParts.map(part=>({...part}));
  const balancedParts=[...baseParts.map(part=>({...part})),
    scorePart('rank','Rank',rank!=null&&rank>0?Math.max(0,160-rank)*0.34:0,rank!=null&&rank>0?`Rank ${metricValueText(rank)} · max(0, 160 - Rank) × 0.34${rank>=160?' · 超出加分区间':''}`:'Rank 缺失',rank!=null&&rank>0),
    scorePart('app_rate','占比',app!=null&&app>0?Math.min(app,35)*2.2:0,app!=null&&app>0?`占比 ${app.toFixed(2)}% · min(占比, 35) × 2.2`:'占比缺失或为 0',app!=null&&app>0),
    scorePart('performance',performance.label,balancedPerformanceScore(performance),balancedPerformanceDetail(performance),performance.valid),
    scorePart('weakness','弱点',weaknessScore,weaknessConfigured?(weaknessMatched?'核心输出命中自定义弱点':'核心输出未命中自定义弱点'):'未配置自定义弱点'),
  ];
  const scoreParts={balanced:balancedParts,history:[],box:boxParts};
  const scores={balanced:scorePartsTotal(balancedParts),history:0,box:scorePartsTotal(boxParts)};
  const finalChars=members.map(m=>m.owned||constraints.required.has(canonicalSlug(m.slug))?m.slug:(defaultSubstitutions.get(canonicalSlug(m.slug))?.character_slug||m.slug));
  const searchText=[template.phase_name_cn,template.phase_name,template.source_kind,template.scope_label,...(template.evidenceScopes||[]),...chars, ...chars.map(charName),...risks.map(r=>r.text)].join(' ').toLowerCase();
  const scoreMode=normalizeRecSortMode(rec.sortMode);
  return{template,targetScope:options.targetScope||template.scope_key,weaknessDriven:Boolean(options.weaknessDriven),weaknessConfigured,weaknessMatched,members,missingCount:missing.length,ownedCount,buildRecordedCount,buildReadyCount,conflictCount,elementHits,coreElementHits,substitutions,risks,performance,scoreParts,scores,scoreMode,score:scores[scoreMode],finalChars,searchText};
}

function substituteCandidates(missingSlug,reserved){
  const missing=charInfo(missingSlug);
  const missingRoles=new Set(roleList(missing));
  return (DATA.rosterRows||[]).filter(r=>box.owned.has(r.character_slug)&&!reserved.has(deploymentGroup(r.character_slug))).map(r=>{
    const roles=roleList(r);
    const roleOverlap=roles.some(role=>missingRoles.has(role));
    let score=0;
    if(roleOverlap)score+=58;
    if(r.path_cn&&r.path_cn===missing.path_cn)score+=18;
    if(r.element_cn&&r.element_cn===missing.element_cn)score+=18;
    if(String(r.rarity)==='5')score+=4;
    if(missingRoles.has('sustain')&&roles.includes('sustain'))score+=24;
    if((missingRoles.has('support')||missingRoles.has('sub_dps'))&&(roles.includes('support')||roles.includes('sub_dps')))score+=12;
    return{...r,subScore:score};
  }).filter(r=>r.subScore>0).sort((a,b)=>b.subScore-a.subScore||releaseOrder(a)-releaseOrder(b)).slice(0,3);
}

function renderRecommender(options={}){
  ensureRecScope();syncRecControls();syncFreshnessNavigation();$('recTooltip').hidden=true;
  const modeLabel=MODES.find(x=>x[0]===rec.mode)?.[1]||rec.mode;
  const scope=recScopeOptions(rec.mode).find(o=>o.key===rec.scope);
  const custom=rec.strategy==='custom';
  const templates=scopeTemplates(rec.mode,rec.scope);
  const ranked=rankedRecommendations().slice(0,Number(rec.limit)||8);
  const latest=templates[0]||{};
  const selected=[...recElementSet()];
  const constraints=recConstraintSets();
  const plannedScopes=recPlanScopes();
  const constraintMatchedCount=templates.filter(template=>templateMatchesConstraints(template,constraints)).length;
  renderPhaseMechanics(latest);
  $('recTitle').textContent=`${modeLabel} · ${scope?.label||rec.scope}`;
  const phaseInfo=phaseInfoFor(latest),status=latest.phase_status||phaseInfo.phase_status||'unknown',freshness=modeFreshness(rec.mode,phaseInfo);
  const templateLabel=freshnessTemplateLabel(freshness.status,custom?'当前模式完整实战阵容池':'当前同节点实战模板');
  const sortMeta=recSortMeta();
  const strategyNote=custom?'跨全部具体战斗侧去重；核心输出命中任一弱点优先':`${plannedScopes.length}队联合优化；同节点实战排序优先；弱点默认仅标注，不参与加减分；选择“过滤风险”时才硬筛选`;
  $('recSubtitle').textContent=`${phaseLabel(latest)} · ${latest.collect_date||''} · ${phaseStatusLabel(status)} · ${templateLabel} ${templates.length} 队 · ${sortMeta.description} · ${strategyNote}${rec.search?' · 搜索只筛选左侧候选，不会改动右侧联合方案':''}`;
  const riskLabel=rec.riskMode==='filter'?'过滤风险':rec.riskMode==='off'?'忽略风险':'仅提醒';
  const tierRiskLabel=rec.riskMode==='off'?'当前模式T档不提醒':'当前模式T1及以下提醒';
  const freshnessBadge=freshnessBadgeHtml(freshness);
  $('recBadges').innerHTML=freshnessBadge+[`排序 ${sortMeta.label}`,custom?'自定义弱点池':'末层实战',`${plannedScopes.length} 队模型`,selected.length?`弱点 ${selected.join(' / ')}`:'未标弱点',constraints.required.size?`必上 ${constraints.required.size}`:'未设必上',constraints.excluded.size?`排除 ${constraints.excluded.size}`:'未设排除',`缺口 ≤ ${rec.gap}`,riskLabel,tierRiskLabel,`Box ${box.owned.size}`].map(x=>`<span>${esc(x)}</span>`).join('');
  const list=$('recList');list.innerHTML='';
  if(!ranked.length){const constrained=constraints.required.size||constraints.excluded.size;const message=constrained&&!constraintMatchedCount?'当前角色硬约束没有匹配的真实队伍模板':constrained?'命中角色约束的模板被当前缺口、风险或搜索条件筛掉':'当前筛选没有可展示队伍';list.innerHTML=`<div class="rec-empty">${message}</div>`;if(options.recomputeSlate!==false)renderRecSlate();return;}
  ranked.forEach((item,index)=>list.appendChild(recCard(item,index+1)));
  if(options.recomputeSlate!==false)renderRecSlate();
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
  const status=info.phase_status||template.phase_status||'unknown',freshness=modeFreshness(rec.mode,{...template,...info});
  $('phaseMechanicsSubtitle').textContent=`${freshnessStatusLabel(freshness.status)} · 采样 ${freshness.sampleDate||'未知'} · 周期 ${freshnessPeriodText(freshness)} · 来源 ${freshness.source||'未知'}`;
  const expiredText=freshness.status==='stale'||status==='expired'?`本地最新 ${modeLabel} 数据周期已于 ${freshness.endDate||info.end_date||'上一周期'} 结束；当前数据包尚未包含新周期统计，以下队伍仅作历史参考。`:'';
  const mechanicName=expiredText?'源滞后 / 历史模板':(info.mechanic_name||'机制效果待维护');
  const mechanicText=expiredText||info.mechanic_text||'当前本地数据只识别到了期名和采样日期，尚未维护这一期的环境效果。这个状态会明确显示，避免把未知效果误当成已匹配。';
  $('phaseMechanicsText').textContent=`${mechanicName}：${mechanicText}`;
  const source=$('phaseMechanicsSource');
  const mechanicUrl=safeLinkUrl(info.mechanic_url);
  if(mechanicUrl){source.href=mechanicUrl;source.textContent=info.mechanic_source||'机制来源';source.classList.remove('hidden-link');}
  else{source.href='#';source.textContent='';source.classList.add('hidden-link');}
}

function scoreValueText(value){const numberValue=metricNumber(value)??0;return Math.abs(numberValue)<.05?'0.0':numberValue.toFixed(1)}
function signedScoreValue(value){const numberValue=metricNumber(value)??0;return`${numberValue>0?'+':''}${scoreValueText(numberValue)}`}
function performanceSummary(evidence){return`${evidence.label} ${evidence.display}（${evidence.note}）`}
function activeScoreParts(item){const mode=normalizeRecSortMode(item.scoreMode);return(item.scoreParts[mode]||[]).filter(part=>mode==='history'||(part.available&&(Math.abs(part.value)>=.005||(mode==='balanced'&&['rank','app_rate','performance'].includes(part.key)))))}
function scoreBreakdownText(item){const parts=activeScoreParts(item);return parts.length?parts.map(part=>`${part.label} ${part.available?signedScoreValue(part.value):'未计'}${part.detail?`（${part.detail}）`:''}`).join('；'):'当前口径没有可计分项'}
function scoreBreakdownHtml(item){const meta=recSortMeta(item.scoreMode),parts=activeScoreParts(item);return`<div class="rec-score-breakdown"><strong>${esc(meta.label)}拆分</strong>${parts.map(part=>`<span class="rec-score-part ${part.value<0?'negative':''} ${part.available?'':'unavailable'}" title="${esc(part.detail)}"><b>${esc(part.label)}</b> ${part.available?esc(signedScoreValue(part.value)):'未计'}</span>`).join('')||'<span class="rec-score-part unavailable">暂无可计分项</span>'}</div>`}
function scoreReferencesHtml(item){const active=normalizeRecSortMode(item.scoreMode);return`<div class="rec-score-refs" title="三种分值量纲不同，只用于各自口径内排序">${REC_SORT_MODES.map(([mode,label])=>`<span class="${mode===active?'active':''}">${esc(label)} <b>${esc(scoreValueText(item.scores[mode]))}</b></span>`).join('')}<small>分值仅在同一口径内比较</small></div>`}

function recCard(item,index){
  const t=item.template;
  const scoreMeta=recSortMeta(item.scoreMode);
  const card=document.createElement('article');
  card.className=`rec-card ${item.risks.length&&rec.riskMode!=='off'?'risky':''}`;
  card.onmouseenter=e=>showRecTooltip(e,item);
  card.onmousemove=moveTooltip;
  card.onmouseleave=()=>{$('recTooltip').hidden=true;};
  const missingNames=item.members.filter(m=>!m.owned).map(m=>charName(m.slug));
  const sourceScope=recScopeDisplayLabel(t.mode,t.scope_key,t.scope_label);
  card.innerHTML=`<div class="rec-card-head"><div><h3>${index}. ${esc((t.names_cn||[]).filter(Boolean).join(' / ')||t.chars.map(charName).join(' / '))}</h3><div class="rec-meta">${esc(item.weaknessDriven?`来源 ${sourceScope}`:sourceScope)} · Rank ${esc(rankDisplayText(t.rank))} · ${t.app_rate==null?'-':pct(t.app_rate)} · ${esc(performanceSummary(item.performance))}</div></div><div class="rec-score"><strong>${Math.round(item.score)}</strong><span>${esc(scoreMeta.scoreLabel)}</span><span>${item.ownedCount}/4 已拥有</span><span>练度已录入 ${item.buildRecordedCount}/${item.ownedCount}</span></div></div>${scoreReferencesHtml(item)}${scoreBreakdownHtml(item)}<div class="rec-team">${item.members.map(m=>recMemberHtml(m,item)).join('')}</div><div class="rec-tags">${recTags(item).map(tag=>`<span class="${tag.danger?'danger':tag.warn?'warn':''}">${esc(tag.text)}</span>`).join('')}</div>${riskNoteHtml(item)}${substitutionHtml(item)}${missingNames.length?`<div class="rec-note">缺：${esc(missingNames.join('、'))}</div>`:''}`;
  return card;
}

function recMemberHtml(member,item){
  const r=member.info;
  const riskText=(member.risks||[]).map(x=>x.text).join('；');
  const coreRisk=item?.risks?.some(risk=>(risk.type==='core-none'||risk.type==='core-low')&&member.core&&!member.selected);
  const buildText=member.owned?` · ${member.buildState.label} · ${member.buildState.configLabel}`:'';
  return `<div class="rec-member ${member.owned?'owned':'missing'} ${(riskText||coreRisk)&&rec.riskMode!=='off'?'risky':''}" title="${esc([member.owned?'已拥有':'未拥有',member.owned?`练度 ${member.buildState.label} ${member.buildState.basePercent}% · ${member.buildState.configLabel}`:'',riskText,coreRisk?'核心属性未命中':''].filter(Boolean).join('；'))}"><img src="${esc(r.icon_url)}" alt="" loading="lazy" decoding="async"><div class="name">${esc(r.character_name_cn||r.character_name_en||member.slug)}</div><div class="meta">${esc(r.element_cn||'')} · ${esc(roleCn(r))}${esc(buildText)}</div></div>`;
}

function templateEvidenceGrade(template){const grade=String(template?.evidence_grade||'B').toUpperCase();return grade==='A'?'A':'B'}
function templateEvidenceCount(template){const count=Math.trunc(Number(template?.duplicate_count));return Number.isFinite(count)&&count>0?count:1}
function templateEvidenceSummary(template){return`证据 ${templateEvidenceGrade(template)} · 记录 ${templateEvidenceCount(template)} 条${template?.quality_flag?` · 质量 ${template.quality_flag}`:''}`}
function recTags(item){
  const t=item.template;
  const grade=templateEvidenceGrade(t),tags=[{text:item.missingCount?`缺 ${item.missingCount}`:'可成队',warn:item.missingCount>0},{text:`证据 ${grade}`,warn:grade!=='A'},{text:`记录 ${templateEvidenceCount(t)} 条`,warn:false},{text:t.source_kind||'source',warn:false}];
  if(item.ownedCount)tags.push({text:`练度已录入 ${item.buildRecordedCount}/${item.ownedCount}`,warn:false});
  if(item.buildRecordedCount)tags.push({text:`成型 ${item.buildReadyCount}/${item.buildRecordedCount}`,warn:item.buildReadyCount<item.buildRecordedCount});
  if(recElementSet(t.mode,item.targetScope).size)tags.push({text:`弱点核心命中 ${item.coreElementHits}`,warn:item.coreElementHits===0});
  if(item.weaknessDriven&&item.template.evidenceScopeCount)tags.push({text:`实战侧覆盖 ${item.template.evidenceScopeCount}`,warn:false});
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
  return `<div class="rec-subs">${rows.map(s=>`<div class="rec-subline"><b>${esc(charName(s.missing.slug))}</b>${s.candidates.map(c=>`<span class="rec-mini"><img src="${esc(c.icon_url)}" alt="">${esc(c.character_name_cn||c.character_name_en)}</span>`).join('')}</div>`).join('')}<div class="rec-sub-evidence">替补属于理论推演，证据最高 C；Rank、占比与表现仍来自原始实证模板。</div></div>`;
}

function finalRecScopes(mode=rec.mode,scope=rec.scope){
  const concrete=realRecScopeOptions(mode).filter(scope=>scope.key!=='all');
  if(mode==='aa'){
    if(scope==='2-1')return concrete.filter(scope=>scope.key==='2-1');
    return concrete.filter(scope=>scope.key.startsWith('1-'));
  }
  return concrete;
}
function recTargetScopeKey(mode=rec.mode,scope=rec.scope){return mode==='aa'?scope==='2-1'?'aa|king':'aa|knights':mode}
function selectedFinalRecScopes(mode=rec.mode,scope=rec.scope){
  const available=finalRecScopes(mode,scope);
  const saved=rec.targetScopes?.[recTargetScopeKey(mode,scope)];
  if(!Array.isArray(saved))return available;
  const selected=new Set(saved);
  const filtered=available.filter(item=>selected.has(item.key));
  return filtered.length?filtered:available;
}
function toggleRecTargetScope(scopeKey){
  const available=finalRecScopes(),selected=new Set(selectedFinalRecScopes().map(scope=>scope.key));
  if(selected.has(scopeKey)){if(selected.size===1)return;selected.delete(scopeKey);if(clearRecLock(scopeKey))recSlateNotice=`${available.find(scope=>scope.key===scopeKey)?.label||scopeKey} 已取消参战，原锁定阵容已解锁。`;}else selected.add(scopeKey);
  rec.targetScopes[recTargetScopeKey()]=available.filter(scope=>selected.has(scope.key)).map(scope=>scope.key);
  if(!selected.has(rec.scope))rec.scope=available.find(scope=>selected.has(scope.key))?.key||rec.scope;
  recConstraintMessage='';saveRecSettings();syncRecControls();renderRecommender();
}
function renderRecTargetScopeControls(){
  const root=$('recTargetScopeButtons');if(!root)return;root.innerHTML='';
  const selected=new Set(selectedFinalRecScopes().map(scope=>scope.key));
  finalRecScopes().forEach(scope=>{const button=document.createElement('button');button.type='button';button.dataset.value=scope.key;button.textContent=scope.label;button.classList.toggle('active',selected.has(scope.key));button.setAttribute('aria-pressed',String(selected.has(scope.key)));button.title=selected.has(scope.key)&&selected.size===1?'至少保留一个参战关卡':`${selected.has(scope.key)?'取消':'加入'}联合优化：${scope.label}`;button.onclick=()=>toggleRecTargetScope(scope.key);root.appendChild(button);});
}
function recPlanScopes(){
  if(rec.strategy==='custom')return recScopeOptions(rec.mode);
  return selectedFinalRecScopes(rec.mode,rec.scope);
}

function slateItemSlugs(item){return new Set(item.finalChars.map(deploymentGroup))}
function compareSlateStates(a,b){return b.filled-a.filled||b.weaknessMatches-a.weaknessMatches||b.totalScore-a.totalScore||a.key.localeCompare(b.key)}
function slateVariantMember(slug,mode,targetScope){const info=charInfo(slug),build=buildFor(slug),buildMeta=buildState(build),member={slug,info,build,buildState:buildMeta,owned:box.owned.has(canonicalSlug(slug)),selected:recElementSet(mode,targetScope).has(info.element_cn),used:false,core:isCoreMember(info)};member.risks=memberRisk(member,mode);return member}
function slateVariantScoreModel(item,finalMembers){const owned=finalMembers.filter(member=>member.owned),missing=finalMembers.length-owned.length,ownedBuildScore=owned.reduce((sum,member)=>sum+member.buildState.score,0),boxParts=[scorePart('owned','拥有',owned.length*45,`${owned.length}/4，每人 +45`),scorePart('build','练度',ownedBuildScore*90,`最终阵容已拥有角色练度合计 ${ownedBuildScore.toFixed(3)} × 90`),scorePart('missing','缺口',-missing*66,`${missing} 人，每人 -66`),scorePart('conflict','跨队冲突',0,'联合求解已将跨队复用作为硬约束'),scorePart('substitute','可替补',0,'替补已纳入最终阵容，不额外加分'),scorePart('complete','满员',missing===0?95:0,missing===0?'最终阵容 4 人全部拥有 +95':'最终阵容未满员')],replacement=new Map(boxParts.map(part=>[part.key,part])),balancedParts=item.scoreParts.balanced.map(part=>replacement.has(part.key)?{...replacement.get(part.key)}:{...part}),historyParts=item.scoreParts.history.map(part=>({...part})),scoreParts={balanced:balancedParts,history:historyParts,box:boxParts},scores=Object.fromEntries(Object.entries(scoreParts).map(([mode,parts])=>[mode,scorePartsTotal(parts)])),scoreMode=normalizeRecSortMode(item.scoreMode);return{scoreParts,scores,scoreMode,score:scores[scoreMode],owned,missing};}
function expandSlateItemVariants(item){
  const substitutions=item.substitutions||[],choices=substitutions.map(substitution=>[...substitution.candidates.slice(0,3).map((candidate,index)=>({candidate,index})),{candidate:null,index:3}]);
  const fixedGroups=new Set(item.members.filter(member=>member.owned).map(member=>deploymentGroup(member.slug)));
  const variants=[],seen=new Set();
  const walk=(index,assignments,usedGroups)=>{
    if(index<substitutions.length){const substitution=substitutions[index];choices[index].forEach(choice=>{const group=choice.candidate?deploymentGroup(choice.candidate.character_slug):deploymentGroup(substitution.missing.slug);if(usedGroups.has(group))return;const nextGroups=new Set(usedGroups);nextGroups.add(group);const nextAssignments=new Map(assignments);if(choice.candidate)nextAssignments.set(canonicalSlug(substitution.missing.slug),{missing:substitution.missing.slug,replacement:choice.candidate.character_slug,candidate:choice.candidate,optionIndex:choice.index});walk(index+1,nextAssignments,nextGroups);});return;}
    const required=recConstraintSets(item.template.mode,item.targetScope).required;
    const finalChars=item.members.map(member=>member.owned||required.has(canonicalSlug(member.slug))?member.slug:(assignments.get(canonicalSlug(member.slug))?.replacement||member.slug));
    const groups=finalChars.map(deploymentGroup);if(new Set(groups).size!==groups.length)return;
    const assignmentRows=[...assignments.values()].sort((left,right)=>canonicalSlug(left.missing).localeCompare(canonicalSlug(right.missing)));
    const variantKey=`${item.template.mode}|${item.targetScope}|${templatePoolKey(item.template)}|${assignmentRows.length?assignmentRows.map(row=>`${canonicalSlug(row.missing)}>${canonicalSlug(row.replacement)}`).join(','):'real'}`;
    if(seen.has(variantKey))return;seen.add(variantKey);
    const finalMembers=finalChars.map(slug=>item.members.find(member=>canonicalSlug(member.slug)===canonicalSlug(slug))||slateVariantMember(slug,item.template.mode,item.targetScope));
    const replacementRisks=finalMembers.filter(member=>!item.members.includes(member)).flatMap(member=>member.risks.map(risk=>({...risk,slug:member.slug,name:charName(member.slug)})));
    if((rec.riskMode||'warn')==='filter'&&replacementRisks.length)return;
    const model=slateVariantScoreModel(item,finalMembers),finalOwned=model.owned,preference=assignmentRows.reduce((sum,row)=>sum+(3-row.optionIndex)*.00001,0);
    variants.push({...item,...model,finalChars,finalMembers,risks:[...item.risks,...replacementRisks],variantKey,slateScore:model.score+preference,substitutionAssignments:assignmentRows,isSubstituted:assignmentRows.length>0,evidenceConfidence:assignmentRows.length?'C':templateEvidenceGrade(item.template),finalOwnedCount:finalOwned.length,finalMissingCount:model.missing,finalBuildRecordedCount:finalOwned.filter(member=>member.buildState.recorded).length,finalBuildReadyCount:finalOwned.filter(member=>member.buildState.ready).length});
  };
  walk(0,new Map(),fixedGroups);
  return variants;
}
function recSlateCandidateLists(scopes,limit=Number.MAX_SAFE_INTEGER){
  return scopes.map((scope,index)=>{const reserved=new Set(scopes.slice(index+1).flatMap(other=>[...recConstraintSets(rec.mode,other.key).required]));const variants=rankedRecommendations(rec.mode,scope.key,new Set(),{ignoreSearch:true,maxGap:Number(rec.gap),reserved}).flatMap(expandSlateItemVariants).sort((left,right)=>right.slateScore-left.slateScore||left.variantKey.localeCompare(right.variantKey));return Number.isFinite(limit)?variants.slice(0,limit):variants;});
}
function searchRecSlate(candidateLists,beamWidth){
  let states=[{picks:[],used:new Set(),filled:0,weaknessMatches:0,totalScore:0,key:''}];
  candidateLists.forEach(candidates=>{
    const next=[];
    states.forEach(state=>{
      next.push({...state,picks:[...state.picks,null],key:`${state.key}|~`});
      candidates.forEach(item=>{const slugs=slateItemSlugs(item);if([...slugs].some(slug=>state.used.has(slug)))return;const used=new Set([...state.used,...slugs]);next.push({picks:[...state.picks,item],used,filled:state.filled+1,weaknessMatches:state.weaknessMatches+Number(item.weaknessDriven&&item.weaknessConfigured&&item.weaknessMatched),totalScore:state.totalScore+item.score,key:`${state.key}|${templatePoolKey(item.template)}`});});
    });
    states=next.sort(compareSlateStates).slice(0,beamWidth);
  });
  return states.sort(compareSlateStates)[0]||{picks:candidateLists.map(()=>null),used:new Set(),filled:0,weaknessMatches:0,totalScore:0,key:''};
}
function prepareRecSlateSolve(scopes,{maxSolutions=3}={}){
  const rawCandidateCounts=scopes.map(scope=>scopeTemplates(rec.mode,scope.key).length),fullCandidateLists=recSlateCandidateLists(scopes,Number.MAX_SAFE_INTEGER),eligibleCandidateCounts=fullCandidateLists.map(list=>list.length),lockedUsed=new Set(),messages=[];
  let settingsChanged=false;
  const lockedCandidateLists=fullCandidateLists.map((list,index)=>{const scope=scopes[index],lockedKey=recLockedVariantKey(scope.key);if(!lockedKey)return list;const match=list.find(item=>item.variantKey===lockedKey);if(!match){clearRecLock(scope.key);settingsChanged=true;messages.push(`${scope.label} 的锁定阵容已因当前 Box、缺口或角色约束失效，已自动解锁。`);return list;}const groups=slateItemSlugs(match);if([...groups].some(group=>lockedUsed.has(group))){clearRecLock(scope.key);settingsChanged=true;messages.push(`${scope.label} 的锁定阵容与前序锁队冲突，已自动解锁。`);return list;}groups.forEach(group=>lockedUsed.add(group));return[match];});
  if(settingsChanged)saveRecSettings();
  if(messages.length)recSlateNotice=[recSlateNotice,...messages].filter(Boolean).join(' ');
  const hardLockedLists=lockedCandidateLists.map((list,index)=>recLockedVariantKey(scopes[index].key)?list:list.filter(item=>![...slateItemSlugs(item)].some(group=>lockedUsed.has(group))));
  const beam=scopes.length>2,candidateLists=hardLockedLists.map((list,index)=>beam&&!recLockedVariantKey(scopes[index].key)?list.slice(0,240):list);
  const input={candidateLists:candidateLists.map(list=>list.map(item=>({key:item.variantKey,teamKey:templatePoolKey(item.template),score:item.slateScore,weaknessMatches:Number(normalizeRecSortMode(rec.sortMode)==='balanced'&&item.weaknessDriven&&item.weaknessConfigured&&item.weaknessMatched),members:[...slateItemSlugs(item)]}))),rawCandidateCounts,eligibleCandidateCounts,originalCandidateCounts:rawCandidateCounts,maxSolutions,beamWidth:720,branchLimit:240};
  return{scopes,fullCandidateLists,candidateLists,input};
}
function runSharedSlateSolver(input){if(!globalThis.MihoSlateSolver||typeof globalThis.MihoSlateSolver.solve!=='function')throw new Error('联合推荐求解器未加载');return globalThis.MihoSlateSolver.solve(input)}
function hydrateRecSlateResult(prepared,result,execution='sync'){
  const plans=(result?.solutions||[]).map(solution=>{const picks=solution.picks.map((pick,index)=>pick==null?null:(prepared.candidateLists[index]?.[pick]||null));return{...solution,candidateIndexes:[...solution.picks],picks,displayScore:picks.reduce((sum,item)=>sum+(item?.score||0),0)};});
  return{plans,solutions:plans,solver_meta:{...(result?.solver_meta||{}),execution},scopes:prepared.scopes,candidateLists:prepared.candidateLists,fullCandidateLists:prepared.fullCandidateLists};
}
function solveRecSlates(scopes,{maxSolutions=3}={}){const prepared=prepareRecSlateSolve(scopes,{maxSolutions});return hydrateRecSlateResult(prepared,runSharedSlateSolver(prepared.input));}
function bestExactTwoScopePlan(scopes){return solveRecSlates(scopes,{maxSolutions:1}).plans[0]?.picks||scopes.map(()=>null)}
function bestRecSlatePlan(scopes){return solveRecSlates(scopes,{maxSolutions:1}).plans[0]?.picks||scopes.map(()=>null)}
function ensureRecSlateWorker(){
  if(recSlateWorker||recSlateWorkerFailed||typeof Worker!=='function')return recSlateWorker;
  try{recSlateWorker=new Worker(`./solver.js${typeof location==='object'&&location.search?location.search:''}`);recSlateWorker.onmessage=event=>{const message=event?.data||{},pending=recSlatePending.get(message.requestId);if(!pending)return;recSlatePending.delete(message.requestId);if(message.ok)pending.resolve({result:message.result,execution:'worker'});else{try{pending.resolve({result:runSharedSlateSolver(pending.input),execution:'sync-fallback'});}catch(error){pending.reject(error);}}};recSlateWorker.onerror=()=>{recSlateWorkerFailed=true;recSlateWorker?.terminate();recSlateWorker=null;for(const [requestId,pending] of recSlatePending){recSlatePending.delete(requestId);try{pending.resolve({result:runSharedSlateSolver(pending.input),execution:'sync-fallback'});}catch(error){pending.reject(error);}}};}catch{recSlateWorkerFailed=true;recSlateWorker=null;}
  return recSlateWorker;
}
function solveRecSlateAsync(input,requestId){const worker=ensureRecSlateWorker();if(!worker)return Promise.resolve({result:runSharedSlateSolver(input),execution:'sync'});return new Promise((resolve,reject)=>{recSlatePending.set(requestId,{resolve,reject,input});try{worker.postMessage({requestId,input});}catch{recSlatePending.delete(requestId);try{resolve({result:runSharedSlateSolver(input),execution:'sync-fallback'});}catch(error){reject(error);}}});}
function toggleRecSlateLock(scope,item){
  const current=recLockedVariantKey(scope.key);if(current===item.variantKey){clearRecLock(scope.key);recSlateNotice=`${scope.label} 已解锁。`;saveRecSettings();renderRecSlate();return;}
  const selectedScopes=recPlanScopes(),groups=slateItemSlugs(item),prepared=recSlateCurrentPrepared;
  for(let index=0;index<selectedScopes.length;index++){const otherScope=selectedScopes[index];if(otherScope.key===scope.key)continue;const otherKey=recLockedVariantKey(otherScope.key);if(!otherKey)continue;const other=prepared?.fullCandidateLists?.[index]?.find(candidate=>candidate.variantKey===otherKey);if(other&&[...slateItemSlugs(other)].some(group=>groups.has(group))){recSlateNotice=`无法锁定 ${scope.label}：与 ${otherScope.label} 的已锁阵容复用角色。`;renderRecSlateResult(recSlateCurrentPrepared?.result||{plans:[],solver_meta:{},scopes:selectedScopes});return;}}
  if(!rec.locks||typeof rec.locks!=='object')rec.locks={};rec.locks[recLockKey(scope.key)]=item.variantKey;recSlateNotice=`已锁定 ${scope.label} 的当前最终阵容，其余关卡已重新优化。`;saveRecSettings();renderRecSlate();
}
function recSlateSearchMeta(meta){if(!meta||!meta.search_type)return'';const type=meta.search_type==='exact'?'精确搜索':'有界近似搜索',limits=meta.search_type==='beam'?` · beam ${meta.beam_width} / 分支 ${meta.branch_limit}`:'',execution=meta.execution==='worker'?'后台线程':meta.execution==='sync-fallback'?'同步回退':'同步计算',raw=Array.isArray(meta.raw_candidate_counts)?meta.raw_candidate_counts.join(' / '):'-',eligible=Array.isArray(meta.eligible_candidate_counts)?meta.eligible_candidate_counts.join(' / '):raw,searched=Array.isArray(meta.searched_candidate_counts)?meta.searched_candidate_counts.join(' / '):eligible,elapsed=Number.isFinite(Number(meta.elapsed_ms))?` · ${Number(meta.elapsed_ms).toFixed(1)} ms`:'';return`${meta.scope_count||0} 关${type}${limits} · ${execution}${elapsed} · 原始模板 ${raw} → 合格阵容 ${eligible} → 搜索 ${searched}`}
function renderRecSlateTeamCard(scope,item,scoreMeta){
  const card=document.createElement('div');card.className=`rec-slate-card ${item?.risks?.length&&rec.riskMode!=='off'?'risky':''}`;
  if(!item){card.innerHTML=`<h3>${esc(scope.label)}</h3><div class="rec-note">没有同时满足缺口、角色约束与不复用要求的队伍</div>`;return card;}
  card.onmouseenter=e=>showRecTooltip(e,item);card.onmousemove=moveTooltip;card.onmouseleave=()=>{$('recTooltip').hidden=true;};
  const locked=recLockedVariantKey(scope.key)===item.variantKey,subText=item.isSubstituted?`<div class="rec-slate-evidence"><b>替补推演 · 证据最高 C</b>：${item.substitutionAssignments.map(row=>`${esc(charName(row.missing))} → ${esc(charName(row.replacement))}`).join('；')}。历史指标仍来自原模板「${esc((item.template.names_cn||[]).filter(Boolean).join(' / '))}」。</div>`:`<div class="rec-slate-evidence real">原始实证队伍 · ${esc(templateEvidenceSummary(item.template))}。${esc(item.template.evidence_comment||'')}</div>`;
  card.innerHTML=`<div class="rec-slate-card-head"><h3>${esc(scope.label)} · ${esc(scoreMeta.scoreLabel)} ${Math.round(item.score)} · 缺口 ${item.finalMissingCount}</h3><button type="button" class="rec-lock-button ${locked?'active':''}">${locked?'已锁定':'锁定本关'}</button></div><div class="rec-slate-team">${item.finalMembers.map(member=>`<img class="${member.owned?'':'missing'} ${member.risks.length&&rec.riskMode!=='off'?'risky':''}" src="${esc(member.info.icon_url)}" title="${esc(charName(member.slug))}" alt="">`).join('')}</div><div class="rec-slate-coverage">最终阵容 ${item.finalOwnedCount}/4 已拥有 · 练度已录入 ${item.finalBuildRecordedCount}/${item.finalOwnedCount} · 成型 ${item.finalBuildReadyCount}/${item.finalBuildRecordedCount}</div>${subText}${riskNoteHtml(item)}`;
  card.querySelector('.rec-lock-button').onclick=event=>{event.stopPropagation();toggleRecSlateLock(scope,item);};return card;
}
function recSlatePlanStats(plan){const items=plan.picks.filter(Boolean),members=new Set(items.flatMap(item=>item.finalMembers.map(member=>canonicalSlug(member.slug))));return{score:plan.displayScore,missing:items.reduce((sum,item)=>sum+item.finalMissingCount,0),owned:items.reduce((sum,item)=>sum+item.finalOwnedCount,0),recorded:items.reduce((sum,item)=>sum+item.finalBuildRecordedCount,0),ready:items.reduce((sum,item)=>sum+item.finalBuildReadyCount,0),members};}
function signedSlateDelta(value,digits=0){const rounded=digits?Number(value).toFixed(digits):String(Math.round(value));return`${value>0?'+':''}${rounded}`}
function recSlateRoleDiff(plan,best){const current=recSlatePlanStats(plan).members,baseline=recSlatePlanStats(best).members,added=[...current].filter(slug=>!baseline.has(slug)).sort((a,b)=>charName(a).localeCompare(charName(b))),removed=[...baseline].filter(slug=>!current.has(slug)).sort((a,b)=>charName(a).localeCompare(charName(b)));if(!added.length&&!removed.length)return'变化角色：无';return`变化角色：${[added.length&&`新增 ${added.map(charName).join('、')}`,removed.length&&`移出 ${removed.map(charName).join('、')}`].filter(Boolean).join('；')}`;}
function renderRecSlateResult(result){
  const scopes=result.scopes||recPlanScopes(),plans=result.plans||[],scoreMeta=recSortMeta(),meta=result.solver_meta||{},strategyLabel=rec.strategy==='custom'?'跨节点阵容池联合选队':'已选实战节点联合选队（未选关卡不预留角色）',freshness=modeFreshness(rec.mode),historical=freshness.status==='stale';
  $('recSlateSubtitle').textContent=`${historical?'历史样本 · ':''}${plans[0]?.filled||0}/${scopes.length} 队 · 目标：${scoreMeta.label} · ${strategyLabel} · 最多 3 套 · 搜索只筛左侧，不触发重算`;
  const status=$('recSlateStatus');if(status)status.textContent=[recSlateNotice,recSlateSearchMeta(meta)].filter(Boolean).join(' ');
  const boxEl=$('recSlateList');boxEl.innerHTML='';if(!plans.length){boxEl.innerHTML='<div class="rec-empty">暂无满足当前条件的完整方案</div>';return;}
  const best=plans[0],bestStats=recSlatePlanStats(best);plans.slice(0,3).forEach((plan,index)=>{const stats=recSlatePlanStats(plan),changes=index?plan.picks.filter((item,scopeIndex)=>(item?.variantKey||'')!==(best.picks[scopeIndex]?.variantKey||'')).length:0,hasSubstitution=plan.picks.some(item=>item?.isSubstituted),diff=index?`较首选：分差 ${signedSlateDelta(stats.score-bestStats.score,1)} · 变化 ${changes} 关 · 缺口 ${signedSlateDelta(stats.missing-bestStats.missing)} · 练度录入 ${signedSlateDelta(stats.recorded-bestStats.recorded)} · 成型 ${signedSlateDelta(stats.ready-bestStats.ready)}`:'当前口径联合最优',roles=index?recSlateRoleDiff(plan,best):'变化角色：基准方案';const section=document.createElement('section');section.className=`rec-slate-solution ${historical?'historical':''}`;section.innerHTML=`<div class="rec-slate-solution-head"><div><strong>方案 ${index+1}${index?'':' · 首选'}</strong><span>${esc(diff)}</span></div><div class="rec-slate-summary">${historical?'<span class="history">历史样本</span>':''}<span>总缺口 ${stats.missing}</span><span>练度 ${stats.recorded}/${stats.owned}</span><span>成型 ${stats.ready}/${stats.recorded}</span>${hasSubstitution?'<span class="theory">含 C 级替补推演</span>':'<span>全为原始实证队</span>'}</div></div><div class="rec-slate-diff">${esc(roles)}</div>`;plan.picks.forEach((item,scopeIndex)=>section.appendChild(renderRecSlateTeamCard(scopes[scopeIndex],item,scoreMeta)));boxEl.appendChild(section);});
  recSlateNotice='';
}
function renderRecSlate(){
  const scopes=recPlanScopes(),prepared=prepareRecSlateSolve(scopes,{maxSolutions:3}),requestId=++recSlateRequestId;recSlateCurrentPrepared=prepared;const status=$('recSlateStatus');if(status)status.textContent='正在联合优化完整候选池…';const list=$('recSlateList');if(list)list.innerHTML='<div class="rec-empty">正在生成最多 3 套不复用角色的完整方案…</div>';
  solveRecSlateAsync(prepared.input,requestId).then(({result,execution})=>{if(requestId!==recSlateRequestId)return;const hydrated=hydrateRecSlateResult(prepared,result,execution);prepared.result=hydrated;recSlateCurrentPrepared=prepared;renderRecSlateResult(hydrated);}).catch(error=>{if(requestId!==recSlateRequestId)return;if(status)status.textContent=`联合推荐失败：${error?.message||error}`;if(list)list.innerHTML='<div class="rec-empty">联合推荐暂不可用，请重新载入页面。</div>';});
}

function showRecTooltip(evt,item){
  const tt=$('recTooltip');const t=item.template;const selected=[...recElementSet(t.mode,item.targetScope)].join(' / ')||'未选';
  const scoreMeta=recSortMeta(item.scoreMode);
  const constraints=recConstraintSets(t.mode,item.targetScope);const constraintText=[constraints.required.size&&`必上 ${[...constraints.required].map(charName).join('、')}`,constraints.excluded.size&&`排除 ${[...constraints.excluded].map(charName).join('、')}`].filter(Boolean).join('；')||'无';
  const riskText=item.risks.length&&rec.riskMode!=='off'?item.risks.map(r=>r.name?`${r.name}：${r.text}`:r.text).join('；'):'无';
  const riskMode=rec.riskMode==='filter'?'过滤风险':rec.riskMode==='off'?'忽略风险':'仅提醒';
  tt.hidden=false;
  const dataRange=item.weaknessDriven?`当前模式全部具体战斗侧去重池${t.evidenceScopes?.length?`（${t.evidenceScopes.join(' / ')}）`:''}`:'同模式 / 同战斗侧 / 最新采样';
  const weaknessUse=item.weaknessDriven?'用于匹配核心输出':rec.riskMode==='filter'?'默认仅标注；当前“过滤风险”会硬筛':'仅标注，不参与加减分';
  const variantText=item.isSubstituted?`C 级理论替补：${item.substitutionAssignments.map(row=>`${charName(row.missing)} → ${charName(row.replacement)}`).join('；')}；历史表现仍来自原模板`:`原始实证队伍；${templateEvidenceSummary(t)}；${t.evidence_comment||''}`;
  const ownedCount=item.finalOwnedCount??item.ownedCount,recordedCount=item.finalBuildRecordedCount??item.buildRecordedCount,readyCount=item.finalBuildReadyCount??item.buildReadyCount,missingCount=item.finalMissingCount??item.missingCount;
  tt.innerHTML=`<div class="tooltip-head"><div><strong>${esc(t.mode_cn)} · ${esc(recScopeDisplayLabel(t.mode,t.scope_key,t.scope_label))}</strong><span>${esc(phaseLabel(t))} · ${esc(t.collect_date)}</span></div></div><div class="tooltip-grid"><b>数据范围</b><div>${esc(dataRange)}</div><b>阵容证据</b><div>${esc(variantText)}</div><b>排序参考</b><div>${esc(scoreMeta.label)}：${esc(scoreMeta.description)}</div><b>角色硬约束</b><div>${esc(constraintText)}</div><b>敌方弱点</b><div>${esc(selected)}（${esc(weaknessUse)}）</div><b>风险模式</b><div>${esc(riskMode)}</div><b>原模板表现</b><div>Rank ${esc(rankDisplayText(t.rank))} · ${t.app_rate==null?'-':pct(t.app_rate)} · ${esc(performanceSummary(item.performance))}</div><b>最终阵容</b><div>${ownedCount}/4，练度已录入 ${recordedCount}/${ownedCount}，成型 ${readyCount}/${recordedCount}，缺 ${missingCount}</div><b>弱点命中</b><div>全队 ${item.elementHits} · 核心 ${item.coreElementHits}</div><b>风险</b><div>${esc(riskText)}</div><b>评分拆分</b><div>${esc(scoreBreakdownText(item))}</div><b>三套参考</b><div>综合 ${esc(scoreValueText(item.scores.balanced))} · 历史 ${esc(scoreValueText(item.scores.history))} · Box ${esc(scoreValueText(item.scores.box))}（量纲不同）</div><b>${esc(scoreMeta.scoreLabel)}</b><div>${Math.round(item.score)}</div><b>来源</b><div>${esc(t.source_kind||'')} · ${esc(t.source_file||'')}</div></div>`;
  moveTooltip(evt);
}
