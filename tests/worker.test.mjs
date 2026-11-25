import test from 'node:test';
import assert from 'node:assert/strict';
import worker from '../worker.js';

const siteOrigin = 'https://mdrahman-codes.github.io';
function req(path, body, origin=siteOrigin) {
  return new Request('https://worker.example'+path, {
    method:'POST',
    headers:{'Content-Type':'application/json',Origin:origin},
    body:JSON.stringify(body)
  });
}
const env = () => ({
  GEMINI_API_KEY: 'UNIT-TEST-ONLY',
  RATE_LIMITER: { limit: async () => ({success:true}) }
});
async function withGeminiReply(reply, callback) {
  const original = globalThis.fetch;
  globalThis.fetch = async () => new Response(JSON.stringify({
    candidates:[{content:{parts:[{text:JSON.stringify(reply)}]}}]
  }),{status:200,headers:{'Content-Type':'application/json'}});
  try { await callback(); } finally {globalThis.fetch=original;}
}
test('Adhuri chat returns a valid reply with allowed origin', async () => {
  await withGeminiReply({reply:'বাংলায় সাহায্য করতে পারি।'},async()=>{
    const response = await worker.fetch(req('/chat',{message:'Explain the business idea',history:[],briefing:{date:'test'}}),env());
    assert.equal(response.status,200);
    assert.equal((await response.json()).reply,'বাংলায় সাহায্য করতে পারি।');
  });
});
test('Word popup backend returns grammar and Bangla meaning',async()=>{
  await withGeminiReply({meaning_bn:'নিরাপদ',context:'সুরক্ষিত',daily_example:'A secure door. — নিরাপদ দরজা।',grammar:'adjective'},async()=>{
    const response=await worker.fetch(req('/explain',{word:'secure',sentence:'This network is secure.'}),env());
    assert.equal(response.status,200);
    const data=await response.json();
    assert.equal(data.grammar,'adjective');
    assert.equal(data.meaning_bn,'নিরাপদ');
  });
});
test('Rejects spoofed browser origin',async()=>{
  const response=await worker.fetch(req('/chat',{message:'hi'},'https://attacker.invalid'),env());
  assert.equal(response.status,403);
});
test('Rate limit prevents upstream Gemini requests',async()=>{
  const e=env();e.RATE_LIMITER={limit:async()=>({success:false})};
  const response=await worker.fetch(req('/chat',{message:'hi'}),e);
  assert.equal(response.status,429);
});
test('Chat rejects overlong prompts',async()=>{
  const response=await worker.fetch(req('/chat',{message:'x'.repeat(651)}),env());
  assert.equal(response.status,400);
});
test('OPTIONS preflight includes safe CORS headers',async()=>{
  const request=new Request('https://worker.example/explain',{method:'OPTIONS',headers:{Origin:siteOrigin}});
  const response=await worker.fetch(request,env());
  assert.equal(response.status,204);
  assert.equal(response.headers.get('access-control-allow-origin'),siteOrigin);
});
