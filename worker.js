// Deploy as a Cloudflare Worker. Add GEMINI_API_KEY as a secret in Worker settings.
const cors = { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Methods': 'POST, OPTIONS', 'Access-Control-Allow-Headers': 'Content-Type' };
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === 'OPTIONS') return new Response(null, { headers: cors });
    if (url.pathname !== '/explain' || request.method !== 'POST') return new Response('Not found', { status: 404, headers: cors });
    try {
      const { word, sentence } = await request.json();
      if (!word || !sentence || String(word).length > 80 || String(sentence).length > 1500) return json({error:'Please provide a word and its sentence.'},400);
      const prompt = `You are a careful English vocabulary tutor for a Bangla-speaking learner. Explain the selected word as used in the exact sentence. Return JSON with keys meaning_bn, context, daily_example, grammar, verification_status, verification_note. meaning_bn: concise natural Bangla meaning. context: explain this word's specific meaning in the provided sentence, in Bangla. daily_example: one natural, grammatically correct everyday English sentence using the same word in a useful way, followed by its Bangla translation. grammar: show a correct pattern and one short pattern example; mention part of speech if useful. Do not invent a grammar rule. verification_status must be one of "Checked with secondary review; still verify important usage", "Uncertain; please verify", or "Needs human review". Be transparent that this model review is not an authoritative dictionary or grammar source. Ensure the selected word occurs in the sentence (case-insensitive) or explain if it does not. WORD: ${String(word)}\nSENTENCE: ${String(sentence)}`;
      const first = await ask(env.GEMINI_API_KEY, prompt, 0.2);
      const reviewPrompt = `Check this English vocabulary explanation for grammar, contextual meaning, and natural usage. Fix mistakes. Do not claim external dictionary verification. If unsure, say so in verification_note and set verification_status to "Uncertain; please verify". Return only JSON with keys meaning_bn, context, daily_example, grammar, verification_status, verification_note. WORD: ${word}\nSENTENCE: ${sentence}\nDRAFT: ${JSON.stringify(first)}`;
      const checked = await ask(env.GEMINI_API_KEY, reviewPrompt, 0.1);
      return json(checked,200);
    } catch (e) { return json({error:'Could not generate an explanation. Try again later.'},500); }
  }
};
async function ask(key,prompt,temp){
  if(!key) throw new Error('Missing API key');
  const r=await fetch(`https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=${key}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({contents:[{parts:[{text:prompt}]}],generationConfig:{temperature:temp,responseMimeType:'application/json'}})});
  if(!r.ok) throw new Error('AI service failed');
  const j=await r.json(); const t=j.candidates?.[0]?.content?.parts?.[0]?.text; if(!t)throw new Error('Empty AI response'); return JSON.parse(t.replace(/^```json\s*|\s*```$/g,''));
}
function json(obj,status=200){return new Response(JSON.stringify(obj),{status,headers:{...cors,'Content-Type':'application/json; charset=utf-8'}})}
