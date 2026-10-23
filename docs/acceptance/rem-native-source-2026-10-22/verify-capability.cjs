const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const file = '/tmp/rem-native-renderer/app-shared-36eae88777f2.js';
const source = fs.readFileSync(file, 'utf8');
const start = source.indexOf('XSn=tk(');
const end = source.indexOf(',ZSn=', start);
assert(start >= 0 && end > start);
const expression = source.slice(start + 4, end);
const symbols = {Q: 'Q', WK: 'access', Dq: 'host', DK: 'loading', EK: 'rollout'};
const evaluate = (state) => vm.runInNewContext(expression, {
  ...symbols,
  tk: (_, callback) => callback({get: (key) => state[key]}),
  zX: (_, required) => ({isLoading: false, isError: false, isCapable: state.entitled, required}),
});
const base = {access: {status:'allowed'}, host: {kind:'local'}, loading:false, rollout:false, entitled:true};
assert.equal(evaluate(base).isCapable, true);
assert.equal(evaluate({...base,host:{kind:'remote'}}).isCapable, false);
assert.equal(evaluate({...base,access:{status:'denied'}}).isCapable, false);
assert.equal(evaluate({...base,loading:true}).isCapable, false);
assert.equal(evaluate({...base,rollout:true,entitled:false}).isCapable, false);
assert.equal(evaluate({...base,rollout:true,entitled:true}).isCapable, true);
const result = {
  bundle_sha256:require('node:crypto').createHash('sha256').update(source).digest('hex'),
  exact_native_access_policy_executed:true,
  cases_passed:6,
  native_policy_requires_local_host:true,
  native_policy_requires_allowed_local_access:true,
  workspace_entitlement_checked_when_rollout_enabled:true,
  renderer_also_checks_feature:'in_app_local_automation',
  cli_feature_observed_enabled:true,
  running_desktop_capability_observed:false,
  live_trigger_verified:false,
};
fs.writeFileSync('/tmp/rem-native-capability-result.json', JSON.stringify(result,null,2)+'\n');
console.log(JSON.stringify(result));
