for (const name of ["RETELL_API_KEY", "RETELL_AGENT_ID", "DEMO_URL"]) {
  if (!process.env[name]) throw new Error(`${name} is required`);
}

const response = await fetch("https://api.retellai.com/v2/create-web-call", {
  method: "POST",
  headers: {
    Authorization: `Bearer ${process.env.RETELL_API_KEY}`,
    "Content-Type": "application/json",
  },
  body: JSON.stringify({
    agent_id: process.env.RETELL_AGENT_ID,
    metadata: { purpose: "staging-manual-voice-test" },
    retell_llm_dynamic_variables: {
      platform_call_id: `retell-web-${crypto.randomUUID()}`,
      called_phone: "+910000000000",
    },
  }),
});
if (!response.ok) {
  throw new Error(`Retell create web call failed: ${response.status} ${await response.text()}`);
}
const { access_token: accessToken, call_id: callId } = await response.json();
const demoUrl = new URL(process.env.DEMO_URL);
demoUrl.hash = new URLSearchParams({ access_token: accessToken }).toString();
console.log(JSON.stringify({ call_id: callId, demo_url: demoUrl.toString() }));
