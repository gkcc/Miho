import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import test from 'node:test';
import vm from 'node:vm';

const ROOT=fileURLToPath(new URL('../',import.meta.url));
const ASSETS=path.join(ROOT,'crates/miho-core/assets/visualizer');
const plain=value=>JSON.parse(JSON.stringify(value));

function loadGame(game){
  const storage=new Map(),controls=new Map();
  const context=vm.createContext({console,performance,setTimeout,clearTimeout,URL,URLSearchParams,
    location:{hash:'',href:'http://localhost/',origin:'http://localhost',search:''},
    document:{body:{innerHTML:''},getElementById:id=>{if(!controls.has(id))controls.set(id,{value:'',textContent:''});return controls.get(id)},createElement:()=>({})},
    fetch:()=>new Promise(()=>{}),
    localStorage:{getItem:key=>storage.get(key)??null,setItem:(key,value)=>storage.set(key,String(value)),removeItem:key=>storage.delete(key)},
  });
  context.window=context;context.global=context;context.parent=context;
  const hsr=game==='hsr',sets=hsr?'recConstraintSets':'constraintSets',setter=hsr?'setRecConstraintSets':'setConstraintSets',save=hsr?'saveRecSettings':'saveRec',load=hsr?'loadRecSettings':'loadRec';
  const harness=`
    ${hsr?'renderRecommender':'renderRec'}=()=>{};
    ${hsr?'syncRecControls':'syncRec'}=()=>{};
    renderRecSlate=()=>{};
    ${hsr?'syncRecConstraintControls':'syncConstraintControls'}=()=>{};
    globalThis.contract={
      reset(data,settings={}){${hsr?'initializeVisualizerData':'installVisualizerData'}(data);rec={...rec,mode:'${hsr?'as':'sd'}',scope:'s1',strategy:'final',constraintScope:'local',buildMode:'ignore',constraints:{},locks:{},teamExclusions:{},targetScopes:{},elements:{},teamCounts:{...DEFAULT_REC_TEAM_COUNTS},gap:'0',riskMode:'off',search:'',...settings};box.owned=new Set(DATA.rosterRows.map(row=>row.character_slug));box.builds={};},
      state(){return {...rec}},
      patch(settings){Object.assign(rec,settings)},
      sets(scope,strategy=rec.strategy){const value=${sets}(rec.mode,scope,strategy);return {required:[...value.required],excluded:[...value.excluded]}},
      effective(scope){const value=recSlateScopeConstraints(rec.mode,scope);return {required:[...value.required],excluded:[...value.excluded]}},
      put(scope,required=[],excluded=[]){${setter}({required:new Set(required),excluded:new Set(excluded)},rec.mode,scope)},
      reload(){${save}();${load}();return {...rec}},
      clear(){${hsr?'clearRecConstraints':'clearConstraints'}()},
      add(kind,slug){$('recCharacterSelect').value=slug;${hsr?'addRecConstraint':'addConstraint'}(kind);return recConstraintMessage},
      editScope(){return recConstraintEditScope()},
      conflicts(){return recConstraintConflicts()},
      ranked(scope){return ${hsr?'rankedRecommendations':'rankedFor'}(rec.mode,scope).map(item=>item.template.id)},
      async rankedAsync(scope){return (await ${hsr?'rankedRecommendationsAsync':'rankedForAsync'}(rec.mode,scope)).map(item=>item.template.id)},
      async candidatesAsync(){return (await recSlateCandidateListsAsync(recPlanScopes())).map(items=>items.map(item=>item.template.id))},
      exclude(scope,chars){return excludeRecTeam({key:scope,label:scope},{template:{mode:rec.mode,chars}})},
      restore(scope,chars){restoreRecTeam(scope,chars)},
      excluded(scope){return recExcludedTeamRows(scope)},
      replaceData(data){${hsr?'initializeVisualizerData':'installVisualizerData'}(data)},
      prepare(){const scopeList=recPlanScopes();recSlateCurrentPrepared={fullCandidateLists:recSlateCandidateLists(scopeList)};return solveRecSlates(scopeList,{maxSolutions:3}).plans},
      select(plan){return selectRecPlan(recPlanScopes(),plan)},
      edit(scope){return openRecFineTune(recPlanScopes().find(entry=>entry.key===scope))},
      lock(scope,item){rec.locks[recLockKey(scope)]=item.${hsr?'variantKey':'slateKey'}},
      unlock(scope){return clearRecLock(scope)},
      detachPrepared(){recSlateCurrentPrepared=null},
      planScopes(){return recPlanScopes().map(scope=>scope.key)},
      completePlans(){return solveRecSlates(recPlanScopes(),{maxSolutions:3}).plans.filter(plan=>plan.picks.every(Boolean)).map(plan=>plan.picks.map(item=>[...item.finalChars]))},
    };`;
  new vm.Script(readFileSync(path.join(ASSETS,'solver.js'),'utf8')+'\n'+readFileSync(path.join(ASSETS,game,'app.js'),'utf8')+'\n'+harness).runInContext(context,{timeout:2000});
  return context.contract;
}

function fixture(game,teams){
  const slugs=[...new Set(teams.flatMap(team=>team.chars))];
  return {rosterRows:slugs.map((slug,index)=>({character_slug:slug,character_name_cn:slug,alias_slugs:slug,element_cn:'火',path_cn:'毁灭',role_groups:'main_dps',role_group:'crit_dps',release_order:index+1,rarity:5})),
    teamTemplates:teams.map((team,index)=>({id:team.id,mode:game==='hsr'?'as':'sd',mode_cn:game,scope_key:team.scope,scope_label:team.scope,scope_order:team.scope==='s1'?1:2,chars:team.chars,names_cn:team.chars,rank:index+1,app_rate:20-index,collect_date:'2026-09-01',phase_ver:'test',phase_status:'current'})),tierRows:[],usageRows:[],trendRows:[],bannerRows:[]};
}

for(const game of ['hsr','zzz']){
  const size=game==='hsr'?4:3,first=Array.from({length:size},(_,i)=>`a${i}`),second=Array.from({length:size},(_,i)=>`b${i}`);
  const data=fixture(game,[{id:'first',scope:'s1',chars:first},{id:'second',scope:'s2',chars:second}]);
  test(`${game}: global constraints persist across reload, isolate strategies and modes, and preserve legacy final all`,()=>{
    const api=loadGame(game),mode=game==='hsr'?'as':'sd';api.reset(data,{constraints:{[`${mode}|all`]:{required:['a0'],excluded:['legacy-block']}}});
    assert.deepEqual(plain(api.sets('all')),{required:['a0'],excluded:['legacy-block']});
    api.patch({strategy:'custom',scope:'custom-1',constraintScope:'global',buildMode:'recorded'});
    assert.deepEqual(plain(api.sets('all')),{required:[],excluded:[]});
    api.put('all',[...first,...second],['custom-block']);api.reload();
    assert.equal(api.state().buildMode,'recorded');assert.equal(api.state().constraintScope,'global');
    assert.equal(api.sets('all').required.length,size*2,'global required must not be clipped to one team');
    api.patch({mode:game==='hsr'?'moc':'da'});assert.equal(api.sets('all').required.length,0);
    api.patch({mode,strategy:'final',scope:'s1'});assert.deepEqual(plain(api.sets('all')),{required:['a0'],excluded:['legacy-block']});
    api.clear();api.reload();assert.deepEqual(plain(api.sets('all')),{required:[],excluded:[]},'clearing migrated constraints must not resurrect legacy values');
  });

  test(`${game}: global required spans teams in both strategies; global exclusion filters every candidate pool`,()=>{
    const api=loadGame(game);api.reset(data);api.put('all',[first[0],second[0]]);
    assert.deepEqual(plain(api.effective('s1')).required,[],'global required is not a per-team requirement');
    assert.equal(api.completePlans().length,1);
    api.patch({strategy:'custom',scope:'custom-1'});api.put('all',[first[0],second[0]]);
    assert.ok(api.completePlans().length>0,'custom global required should be jointly satisfiable');
    api.put('all',[second[0]],[first[0]]);
    assert.deepEqual(plain(api.ranked('custom-1')),['second']);
    assert.deepEqual(plain(api.ranked('custom-2')),['second']);
    assert.equal(api.completePlans().length,0,'excluded global characters cannot be recovered by relaxed plans');
  });

  test(`${game}: stored conflicts survive reload, and UI editing never silently removes the opposite constraint`,()=>{
    const api=loadGame(game);api.reset(data,{constraintScope:'global'});api.put('all',['a0'],['a0']);api.reload();
    assert.deepEqual(plain(api.sets('all')),{required:['a0'],excluded:['a0']});
    assert.equal(api.completePlans().length,0);assert.ok(api.conflicts().length);
    api.put('all',[],['a0']);assert.match(api.add('required','a0'),/相反约束/);assert.deepEqual(plain(api.sets('all')),{required:[],excluded:['a0']});
    api.patch({constraintScope:'local'});api.put('s1',['a0']);assert.ok(api.conflicts().length);assert.equal(api.completePlans().length,0);
    api.patch({scope:'all'});assert.equal(api.editScope(),'all');
  });

  test(`${game}: hard constraint scope is an accessible visible product control`,()=>{
    const html=readFileSync(path.join(ASSETS,game,'index.html'),'utf8');
    assert.match(html,/<select id="recConstraintScopeSelect" aria-label="硬约束作用范围">/);
    assert.match(html,/<option value="global">全局（整套方案）<\/option>/);
    assert.match(html,/id="recGlobalConstraintSummary"/);
  });

  test(`${game}: stage team feedback filters warmed synchronous and async pools, keeps other stages, and restores`,async()=>{
    const api=loadGame(game),alt=Array.from({length:size},(_,i)=>`c${i}`);
    api.reset(fixture(game,[{id:'failed',scope:'s1',chars:first},{id:'alternative',scope:'s1',chars:alt},{id:'same-other-stage',scope:'s2',chars:first},{id:'second',scope:'s2',chars:second}]));
    await api.candidatesAsync();await api.rankedAsync('s1');const pending=api.rankedAsync('s1');
    assert.equal(api.exclude('s1',first),true);
    assert.ok(!plain(await pending).includes('failed'),'in-flight scoring must not resurrect a newly excluded team');
    assert.deepEqual(plain(api.ranked('s1')),['alternative']);
    assert.deepEqual(plain(await api.rankedAsync('s1')),['alternative']);
    const pools=plain(await api.candidatesAsync());assert.deepEqual(pools[0],['alternative']);assert.ok(pools[1].includes('same-other-stage'));
    assert.deepEqual(plain(api.sets('s1')),{required:[],excluded:[]},'team feedback must not exclude individual members');
    assert.ok(api.completePlans().length);api.restore('s1',first);assert.ok(plain(await api.rankedAsync('s1')).includes('failed'));assert.ok(plain(await api.candidatesAsync())[0].includes('failed'));
  });

  test(`${game}: excluded party survives reordered new evidence and reload, with mode and strategy isolation`,async()=>{
    const api=loadGame(game),mode=game==='hsr'?'as':'sd';api.reset(data);api.exclude('s1',first);api.reload();
    const refreshed=fixture(game,[{id:'first',scope:'s1',chars:first},{id:'second',scope:'s2',chars:second}]);refreshed.teamTemplates[0]={...refreshed.teamTemplates[0],id:'new-sample',chars:[...first].reverse(),rank:99,collect_date:'2026-10-02',bangboo:'different-bangboo'};api.replaceData(refreshed);
    assert.deepEqual(plain(await api.rankedAsync('s1')),[]);assert.equal(api.exclude('s1',[...first].reverse()),false,'same party order must not create a second exclusion');
    api.patch({strategy:'custom',scope:'custom-1'});assert.deepEqual(plain(api.excluded('custom-1')),[]);assert.ok(api.ranked('custom-1').includes('new-sample'));
    api.exclude('custom-1',first);assert.ok(!api.ranked('custom-1').includes('new-sample'));assert.ok(api.ranked('custom-2').includes('new-sample'));
    api.patch({strategy:'final',scope:'s1',mode:game==='hsr'?'moc':'da'});assert.deepEqual(plain(api.excluded('s1')),[]);api.patch({mode});assert.equal(api.excluded('s1').length,1);
  });

  test(`${game}: selecting a whole alternative plan pins it; excluding its failed stage clears only that lock`,()=>{
    const api=loadGame(game),alt=Array.from({length:size},(_,i)=>`c${i}`);
    api.reset(fixture(game,[{id:'first',scope:'s1',chars:first},{id:'alternative',scope:'s1',chars:alt},{id:'second',scope:'s2',chars:second}]));
    const plans=api.prepare();assert.ok(plans.length>=2);const chosen=plans[1];assert.equal(api.select(chosen),true);assert.equal(Object.keys(api.state().locks).length,2);
    const secondLock=Object.values(api.state().locks)[1];assert.equal(api.edit('s1'),true);assert.equal(api.state().scope,'s1');assert.equal(Object.keys(api.state().locks).length,2);
    api.detachPrepared();api.exclude('s1',chosen.picks[0].finalChars);assert.equal(Object.keys(api.state().locks).length,1,'feedback must identify an existing lock even while candidate preparation is pending');assert.equal(Object.values(api.state().locks)[0],secondLock);
    assert.equal(api.completePlans().length,1);assert.deepEqual(plain(api.completePlans()[0][1]),second);api.restore('s1',chosen.picks[0].finalChars);assert.equal(Object.keys(api.state().locks).length,1,'restore must not silently reinstate the failed-stage lock');
    api.prepare();assert.equal(api.select({...chosen,picks:[chosen.picks[0],null]}),false);
  });

  test(`${game}: excluding the only compatible team reports no complete plan without dropping other locks`,()=>{
    const api=loadGame(game);api.reset(data);const plan=api.prepare()[0];api.select(plan);api.exclude('s1',first);assert.equal(Object.keys(api.state().locks).length,1);assert.equal(api.completePlans().length,0);
  });
}

test('HSR global required and excluded target the selected form while cross-team deployment conflicts still share a group',()=>{
  const api=loadGame('hsr'),harmony='trailblazer-harmony',preservation='trailblazer-preservation';
  const second=['b0','b1','b2','b3'];
  api.reset(fixture('hsr',[{id:'preservation-only',scope:'s1',chars:[preservation,'a1','a2','a3']},{id:'second',scope:'s2',chars:second}]));
  api.put('all',[harmony]);assert.equal(api.completePlans().length,0,'another Trailblazer form cannot satisfy required harmony');
  api.put('all',[],[harmony]);assert.equal(api.completePlans().length,1,'excluding harmony does not exclude preservation');
  api.reset(fixture('hsr',[{id:'harmony',scope:'s1',chars:[harmony,'a1','a2','a3']},{id:'preservation',scope:'s2',chars:[preservation,'b1','b2','b3']}]));
  api.put('all',[harmony]);assert.equal(api.completePlans().length,0,'different Trailblazer forms still cannot deploy in two teams');
});

test('HSR team exclusion distinguishes forms, and fine tuning keeps the selected arbitration division',()=>{
  const api=loadGame('hsr'),harmony=['trailblazer-harmony','a1','a2','a3'],preservation=['trailblazer-preservation','a1','a2','a3'];
  api.reset(fixture('hsr',[{id:'harmony',scope:'s1',chars:harmony},{id:'preservation',scope:'s1',chars:preservation},{id:'second',scope:'s2',chars:['b0','b1','b2','b3']} ]));
  api.exclude('s1',harmony);assert.deepEqual(plain(api.ranked('s1')),['preservation']);
  const arbitration=fixture('hsr',['1-1','1-2','1-3','2-1'].map((scope,index)=>({id:scope,scope,chars:Array.from({length:4},(_,i)=>`party${index}-${i}`)})));
  arbitration.teamTemplates.forEach(template=>{template.mode='aa'});api.reset(arbitration,{mode:'aa',scope:'1-1'});
  const plan=api.prepare()[0];assert.equal(api.select(plan),true);api.edit('1-2');assert.deepEqual(plain(api.planScopes()),['1-1','1-2','1-3']);assert.equal(Object.keys(api.state().locks).length,3);
});


test('ZZZ Deadly Assault legacy scope merges into one Adversity division without consuming ordinary parties',()=>{
  const data=fixture('zzz',['1-1','1-2','1-3','2-1','4'].map((scope,index)=>({id:scope,scope,chars:[`party${index}-a`,`party${index}-b`,`party${index}-c`]})));
  data.teamTemplates.forEach(template=>{template.mode='da'});
  const api=loadGame('zzz');api.reset(data,{mode:'da',scope:'4',targetScopes:{da:['1-1','1-2','1-3']}});api.reload();
  assert.equal(api.state().scope,'2-1');assert.deepEqual(plain(api.planScopes()),['2-1']);
  assert.equal(api.completePlans().length,2,'both old source records remain available in the single canonical stage');
  assert.ok(api.completePlans().every(plan=>plan.length===1));
  api.patch({scope:'1-1'});assert.deepEqual(plain(api.planScopes()),['1-1','1-2','1-3']);
  assert.ok(api.completePlans().every(plan=>plan.length===3));
});

test('ZZZ unified Adversity reload preserves exclusions, contradictory constraints, and conflicting locks',()=>{
  const data=fixture('zzz',[{id:'adversity',scope:'4',chars:['a0','a1','a2']}]);data.teamTemplates[0].mode='da';
  const api=loadGame('zzz');api.reset(data,{mode:'da',scope:'4',targetScopes:{da:['4','2-1']},
    constraints:{'da|4':{required:['a0'],excluded:['a1']},'da|final|2-1':{required:['a1'],excluded:['a2']}},
    elements:{'da|4':['火'],'da|2-1':['冰']},
    teamExclusions:{'da|final|4':[['a0','a1','a2']],'da|final|2-1':[['b0','b1','b2']]},
    locks:{'da|final|4':'da|4|legacy|a0+a1+a2|2026-09-01|1','da|final|2-1':'da|2-1|other|b0+b1+b2|2026-09-01|2'}});
  api.reload();api.reload();
  assert.deepEqual(plain(api.state().targetScopes.da),['2-1']);
  assert.deepEqual(plain(api.sets('2-1')),{required:['a1','a0'],excluded:['a2','a1']});
  assert.deepEqual(plain(api.state().elements['da|2-1']),['火','冰']);
  assert.equal(api.excluded('2-1').length,2);assert.equal(api.state().scopeLockConflicts['da|final|2-1'].length,2);
  assert.equal(api.completePlans().length,0,'conflicting saved settings must never be silently loosened');
  assert.ok(api.conflicts().some(message=>message.includes('a1')));
  api.patch({constraints:{},teamExclusions:{}});assert.equal(api.completePlans().length,0,'saved conflicting locks alone must block the unified stage');
  assert.equal(api.unlock('2-1'),true);api.reload();assert.equal(api.completePlans().length,1,'explicit unlock resolves the retained lock conflict');
  assert.deepEqual(plain(api.state().scopeLockConflicts),{});
});
