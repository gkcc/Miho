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
    ${hsr?'syncRecConstraintControls':'syncConstraintControls'}=()=>{};
    globalThis.contract={
      reset(data,settings={}){${hsr?'initializeVisualizerData':'installVisualizerData'}(data);rec={...rec,mode:'${hsr?'as':'sd'}',scope:'s1',strategy:'final',constraintScope:'local',buildMode:'ignore',constraints:{},locks:{},targetScopes:{},elements:{},teamCounts:{...DEFAULT_REC_TEAM_COUNTS},gap:'0',riskMode:'off',search:'',...settings};box.owned=new Set(DATA.rosterRows.map(row=>row.character_slug));box.builds={};},
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
