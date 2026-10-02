#!/usr/bin/env node
// A focused, reversible probe of the real desktop Visualizer and its current Box.
import assert from 'node:assert/strict';
import {writeFileSync} from 'node:fs';

const args=new Map();for(let i=2;i<process.argv.length;i+=2)args.set(process.argv[i].replace(/^--/,''),process.argv[i+1]);
const endpoint=new URL(args.get('ws-url'));if(endpoint.hostname==='localhost')endpoint.hostname='127.0.0.1';
const socket=new WebSocket(endpoint),pending=new Map(),contexts=new Map(),attached=new Map();let nextId=1;
socket.addEventListener('message',event=>{const message=JSON.parse(String(event.data));if(message.id){const call=pending.get(message.id);if(call){pending.delete(message.id);clearTimeout(call.timer);message.error?call.reject(new Error(message.error.message)):call.resolve(message.result||{});}}else if(message.method==='Runtime.executionContextCreated')contexts.set(message.params.context.id,message.params.context);else if(message.method==='Runtime.executionContextDestroyed')contexts.delete(message.params.executionContextId);});
await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});
function command(method,params={},sessionId){return new Promise((resolve,reject)=>{const id=nextId++,timer=setTimeout(()=>{pending.delete(id);reject(new Error(`CDP timeout: ${method}`));},45000);pending.set(id,{resolve,reject,timer});socket.send(JSON.stringify({id,method,params,...(sessionId?{sessionId}:{})}));});}
async function evaluate(context,expression){const result=await command('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true,...(context?.id?{contextId:context.id}:{})},context?.sessionId);if(result.exceptionDetails)throw new Error(result.exceptionDetails.exception?.description||result.exceptionDetails.text);return result.result?.value;}
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function wait(label,probe){const until=Date.now()+45000;let last;while(Date.now()<until){try{const result=await probe();if(result)return result;}catch(error){last=error;}await delay(100);}throw new Error(`Timed out: ${label}${last?`; ${last.message}`:''}`);}
function frames(node){return[node.frame,...(node.childFrames||[]).flatMap(frames)];}
async function frameContext(game){return wait(`${game} frame context`,async()=>{
  const tree=await command('Page.getFrameTree'),frame=frames(tree.frameTree).find(frame=>frame.url.includes(`miho-visualizer.localhost/${game}/index.html`));
  const context=frame&&[...contexts.values()].find(context=>context.auxData?.isDefault&&context.auxData?.frameId===frame.id);if(context)return context;
  const info=(await command('Target.getTargets')).targetInfos.find(target=>target.type==='iframe'&&target.url.includes(`miho-visualizer.localhost/${game}/index.html`));if(!info)return null;
  if(!attached.has(info.targetId)){const response=await command('Target.attachToTarget',{targetId:info.targetId,flatten:true});attached.set(info.targetId,response.sessionId);await command('Runtime.enable',{},response.sessionId);}return{sessionId:attached.get(info.targetId)};
});}
async function click(context,selector){assert.equal(await evaluate(context,`(()=>{const button=document.querySelector(${JSON.stringify(selector)});if(!button||button.disabled) return false;button.click();return true})()`),true,`Unable to click ${selector}`);}
const receipt={schema:'miho-multi-team-workflow-probe-v1',games:[]};
try{
  await command('Runtime.enable');await command('Page.enable');await command('Target.setDiscoverTargets',{discover:true});
  const tree=await command('Page.getFrameTree'),top=await wait('desktop context',()=>[...contexts.values()].find(context=>context.auxData?.isDefault&&context.auxData?.frameId===tree.frameTree.frame.id));
  for(const game of ['hsr','zzz']){
    assert.equal(await evaluate(top,`(()=>{const button=[...document.querySelectorAll('.game-button')].find(button=>button.textContent.trim()===${JSON.stringify(game==='hsr'?'崩坏：星穹铁道':'绝区零')});button?.click();return !!button})()`),true);
    let context=await frameContext(game);await wait(`${game} loaded`,()=>evaluate(context,`typeof DATA==='object'&&!!DATA&&typeof rec==='object'`));
    const key=game==='hsr'?'hsr_endgame_recommender_v1':'zzz_endgame_rec_v1';
    const saved=await evaluate(context,`({raw:localStorage.getItem(${JSON.stringify(key)}),rec:JSON.parse(JSON.stringify(rec)),page:state.page,hash:location.hash,open:document.querySelector('#recFineTune').open})`);
    const read=expression=>evaluate(context,expression);
    const snapshot=()=>read(`(()=>{const plans=[...document.querySelectorAll('#recSlateList .rec-slate-solution,#recSlateList .rec-solution')];return {scope:rec.scope,locks:rec.locks,exclusions:rec.teamExclusions,scopes:recPlanScopes().map(scope=>scope.key),plans:plans.map(plan=>({selected:plan.classList.contains('selected'),chars:[...plan.querySelectorAll('.rec-slate-card')].map(card=>[...card.querySelectorAll('.rec-slate-team img')].map(img=>img.title).sort())})),ready:!!recSlateCurrentPrepared?.fullCandidateLists}})()`);
    try{
      await read(`(()=>{rec.constraints={};rec.locks={};rec.teamExclusions={};rec.targetScopes={};rec.elements={};rec.search='';state.page='recommender';location.hash='#recommender';render();document.querySelector('#recFineTune').open=false;return true})()`);
      await click(context,`#recModeControl button[data-value="${game==='hsr'?'as':'sd'}"]`);
      await click(context,'#recStrategyControl button[data-value="custom"]');
      await read(`(()=>{for(const [id,value] of [['recTeamCountSelect','2'],['recGapSelect','0'],['recRiskSelect','off'],['recSortSelect','box']]){const select=document.getElementById(id);select.value=value;select.dispatchEvent(new Event('change',{bubbles:true}));}return true})()`);
      const initial=await wait(`${game} complete alternatives`,async()=>{const value=await snapshot();return value.ready&&value.plans.length>=2&&value.scopes.length===2?value:null;});
      const layout=await read(`(()=>{const main=document.querySelector('.rec-primary-slate'),fine=document.querySelector('#recFineTune');return {primaryBeforeFine:!!(main.compareDocumentPosition(fine)&Node.DOCUMENT_POSITION_FOLLOWING),fineClosed:!fine.open,width:innerWidth,scrollWidth:document.documentElement.scrollWidth}})()`);
      assert.equal(layout.primaryBeforeFine,true);assert.equal(layout.fineClosed,true);assert.ok(layout.scrollWidth<=layout.width+1,'Workflow overflows the desktop');
      await click(context,'#recSlateList section:nth-of-type(2) .rec-select-plan-button');
      const selected=await wait(`${game} selected alternative`,async()=>{const value=await snapshot();return value.ready&&Object.keys(value.locks).length===2&&value.plans[0]?.selected?value:null;});
      assert.deepEqual(selected.plans[0].chars,initial.plans[1].chars,'Selecting an alternative must keep that entire plan');
      await click(context,'#recSlateList .selected .rec-slate-card .rec-fine-tune-button');
      const fine=await read(`({open:document.querySelector('#recFineTune').open,scope:rec.scope,locks:rec.locks})`);assert.equal(fine.open,true);assert.equal(fine.scope,selected.scopes[0]);assert.deepEqual(fine.locks,selected.locks);
      const preservedLock=selected.locks[`${game==='hsr'?'as':'sd'}|custom|${selected.scopes[1]}`];
      await click(context,'#recSlateList .selected .rec-slate-card .rec-team-exclude-button');
      const excluded=await wait(`${game} stage-local exclusion`,async()=>{const value=await snapshot();return value.ready&&Object.keys(value.locks).length===1&&Object.values(value.exclusions||{}).flat().length===1?value:null;});
      assert.equal(Object.values(excluded.locks)[0],preservedLock);assert.ok(excluded.plans.every(plan=>JSON.stringify(plan.chars[0])!==JSON.stringify(selected.plans[0].chars[0])));
      assert.deepEqual(await read(`JSON.parse(JSON.stringify(rec.constraints))`),{},'Whole-party feedback must not mutate character constraints');
      await read('setTimeout(()=>location.reload(),0);true');await delay(500);context=await frameContext(game);
      const reloaded=await wait(`${game} persisted exclusion`,async()=>{const value=await snapshot();return value.ready&&Object.keys(value.locks||{}).length===1&&Object.values(value.exclusions||{}).flat().length===1?value:null;});
      assert.equal(Object.values(reloaded.locks)[0],preservedLock);assert.ok(reloaded.plans.every(plan=>JSON.stringify(plan.chars[0])!==JSON.stringify(selected.plans[0].chars[0])));
      await click(context,'#recTeamExclusionSummary button');await click(context,'#recTeamExclusionList .rec-team-restore-button');
      await wait(`${game} restored team`,async()=>{const value=await snapshot();const chars=await read(`(recSlateCurrentPrepared?.fullCandidateLists?.[0]||[]).map(item=>item.finalChars.map(charName).sort())`);return value.ready&&Object.keys(value.exclusions||{}).length===0&&chars.some(team=>JSON.stringify(team)===JSON.stringify(selected.plans[0].chars[0]));});
      assert.equal(Object.keys((await snapshot()).locks).length,1,'Restoring feedback must not restore the failed lock');
      await click(context,'#recReplanBtn');await wait(`${game} fresh entire plan`,async()=>{const value=await snapshot();return value.ready&&value.plans.length>=2&&Object.keys(value.locks).length===0;});
      let division;
      if(game==='hsr'){
        await click(context,'#recStrategyControl button[data-value="final"]');await click(context,'#recModeControl button[data-value="aa"]');
        await click(context,'#recDivisionControl button:nth-child(2)');assert.deepEqual(await read('recPlanScopes().map(scope=>scope.key)'),['2-1']);
        await click(context,'#recDivisionControl button:nth-child(1)');division=await read('recPlanScopes().map(scope=>scope.key)');assert.ok(division.length===3&&division.every(scope=>scope.startsWith('1-')));
      }
      receipt.games.push({game,layout,selectedAlternative:true,stageExclusion:true,otherStagePreserved:true,persistedAcrossReload:true,restored:true,replanned:true,division});
    }finally{
      context=await frameContext(game);
      assert.equal(await evaluate(context,`(()=>{const raw=${JSON.stringify(saved.raw)};if(raw===null)localStorage.removeItem(${JSON.stringify(key)});else localStorage.setItem(${JSON.stringify(key)},raw);for(const key of Object.keys(rec))delete rec[key];Object.assign(rec,${JSON.stringify(saved.rec)});state.page=${JSON.stringify(saved.page)};location.hash=${JSON.stringify(saved.hash)};render();document.querySelector('#recFineTune').open=${JSON.stringify(saved.open)};return localStorage.getItem(${JSON.stringify(key)})===raw})()`),true,'Probe must restore the original user preferences');
    }
  }
  receipt.userPreferencesRestored=true;receipt.completedAt=new Date().toISOString();
  const text=JSON.stringify(receipt,null,2)+'\n';if(args.has('receipt'))writeFileSync(args.get('receipt'),text);process.stdout.write(text);
}finally{
  for(const sessionId of attached.values()){try{await command('Target.detachFromTarget',{sessionId});}catch{/* The frame may already have navigated away. */}}
  for(const call of pending.values()){clearTimeout(call.timer);call.reject(new Error('Probe finished'));}
  if(socket.readyState===WebSocket.OPEN){await new Promise(resolve=>{socket.addEventListener('close',resolve,{once:true});socket.close();setTimeout(resolve,3000);});}
}
