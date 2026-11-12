const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),assert=require('node:assert/strict');
const root=fs.mkdtempSync(path.join(os.tmpdir(),'rem-native-source-verified-'));
process.env.CODEX_HOME=root;process.env.NODE_ENV='test';process.env.BUILD_FLAVOR='test';
Object.defineProperty(process.versions,'electron',{value:'isolated-storage-test'});
const Module=require('node:module'),load=Module._load;
Module._load=function(name,parent,isMain){if(name==='electron')return {app:{isPackaged:false,getPath:()=>root}};return load.apply(this,arguments)};
const native=require('/tmp/rem-native-desktop-source/build/src-BSSLXJxP.js');
const base={kind:'cron',name:'REM native structure verification',prompt:'Isolated data test; no model calls.',status:'PAUSED',rrule:'FREQ=WEEKLY;BYDAY=SU;BYHOUR=9;BYMINUTE=0',cwds:[root],executionEnvironment:'local',model:'gpt-6-luna',reasoningEffort:'low',autoArchive:true};
const task=native.kn(base);assert(task);const db=native.gr();
const file=path.join(root,'automations',task.id,'automation.toml');assert(fs.existsSync(file));
const select=()=>db.prepare('SELECT * FROM automations WHERE id=?').get(task.id);
assert.equal(select().status,'PAUSED');assert.equal(select().next_run_at,null);assert.equal(select().auto_archive,1);assert.deepEqual(JSON.parse(select().cwds),[root]);
assert(native.Bn().some(x=>x.id===task.id));
const active=native.Zn({...base,id:task.id,status:'ACTIVE'});assert(active.nextRunAt>Date.now());assert.equal(select().next_run_at,active.nextRunAt);
assert(native.Vn(active.nextRunAt+2000).some(x=>x.id===task.id));
const paused=native.Zn({...base,id:task.id,status:'PAUSED'});assert.equal(paused.status,'PAUSED');assert(!native.Vn(active.nextRunAt+2000).some(x=>x.id===task.id));
// A legacy file can seed the index: a DB row is not universally mandatory.
db.prepare('DELETE FROM automations WHERE id=?').run(task.id);assert.equal(select(),undefined);
assert(native.Bn().some(x=>x.id===task.id));assert(select());
// Completed owner migration filters legacy rows and files out.
const owner={accountId:'isolated-account',userId:'isolated-user',installationId:'isolated-installation'};
native.Xn(owner,'complete');assert(!native.Bn().some(x=>x.id===task.id));
const owned={...paused,id:task.id+'-owned'};assert(native.On(owned,owner,task.id));
assert(native.Bn().some(x=>x.id===owned.id));assert.equal(db.prepare('SELECT account_id FROM automations WHERE id=?').get(owned.id).account_id,owner.accountId);
// This is the same pruning function called after remote synchronization.
native.qn(new Set(),owner);assert(!native.Bn().some(x=>x.id===owned.id));
native.Xn(null);assert.equal(native.An(task.id),'deleted');assert(!fs.existsSync(file));assert.equal(select(),undefined);
const result={native_module_sha256:require('node:crypto').createHash('sha256').update(fs.readFileSync('/tmp/rem-native-desktop-source/build/src-BSSLXJxP.js')).digest('hex'),isolated_root:root,actual_native_create_writes_file_and_database:true,native_list_accepts_structure:true,native_rrule_computes_next_run:true,native_due_selector_accepts_task:true,native_pause_removes_due_slot:true,file_only_rebuilds_index_in_legacy_mode:true,owner_migration_filters_legacy:true,owner_cache_registration_visible:true,remote_sync_prunes_unregistered_owner_rows:true,native_delete_cleans_file_and_row:true,desktop_electron_surface_stubbed:true,sqlite_driver:'real better-sqlite3',live_desktop_trigger_tested:false,model_calls:0};
fs.writeFileSync('/tmp/rem-native-source-verification.json',JSON.stringify(result,null,2));console.log(JSON.stringify(result));
db.close();fs.rmSync(root,{recursive:true});
