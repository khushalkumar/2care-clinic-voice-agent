import { readFile } from "node:fs/promises";

for (const name of ["BACKEND_URL", "RETELL_API_KEY", "RETELL_TOOL_TOKEN"]) {
  if (!process.env[name]) throw new Error(`${name} is required`);
}

const backendUrl = process.env.BACKEND_URL.replace(/\/$/, "");
if (!backendUrl.startsWith("https://")) {
  throw new Error("BACKEND_URL must use HTTPS for Retell custom tools");
}

const prompt = await readFile(
  new URL("../integrations/voice/retell/prompt.md", import.meta.url),
  "utf8",
);
const agentName = "2care Physiotattva Bilingual Receptionist (Staging)";
const string = { type: "string" };

async function retellRequest(path, method, body) {
  const response = await fetch(`https://api.retellai.com${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${process.env.RETELL_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    throw new Error(`Retell ${method} ${path} failed: ${response.status} ${await response.text()}`);
  }
  return response.json();
}

function customTool(name, description, path, parameters, options = {}) {
  return {
    type: "custom",
    name,
    description,
    url: `${backendUrl}${path}`,
    method: options.method ?? "POST",
    headers: { "X-2Care-Platform-Token": process.env.RETELL_TOOL_TOKEN },
    parameters,
    args_at_root: true,
    parameter_type: "json",
    speak_during_execution: options.speakDuringExecution ?? true,
    speak_after_execution: true,
    execution_message_type: "prompt",
    execution_message_description:
      "Say one brief acknowledgement in the caller's current language, then wait silently for the result.",
    timeout_ms: 12_000,
  };
}

const tools = [
  customTool(
    "clinic_catalog",
    "Read the live clinic businesses, practitioners, and appointment types before searching availability. Never invent IDs.",
    "/v1/tools/clinic-catalog",
    { type: "object", properties: {} },
    { method: "GET", speakDuringExecution: false },
  ),
  customTool(
    "bootstrap_call",
    "Create or resume a call session after the caller gives their phone number. Use configured platform_call_id and called_phone exactly.",
    "/v1/tools/bootstrap-call",
    {
      type: "object",
      properties: {
        platform_call_id: { ...string, description: "Use {{platform_call_id}} exactly." },
        direction: { ...string, enum: ["inbound"] },
        caller_phone: { ...string, description: "Caller phone in E.164 format." },
        called_phone: { ...string, description: "Use {{called_phone}} exactly." },
      },
      required: ["platform_call_id", "direction", "caller_phone", "called_phone"],
    },
  ),
  customTool(
    "search_availability",
    "Search fresh live availability. Call again whenever the caller changes any scheduling constraint.",
    "/v1/tools/search-availability",
    {
      type: "object",
      properties: {
        call_id: string,
        business_id: string,
        practitioner_ids: { type: "array", items: string },
        appointment_type_id: string,
        starts_at: { ...string, description: "Timezone-aware ISO 8601 timestamp." },
        ends_at: { ...string, description: "Timezone-aware ISO 8601 timestamp." },
      },
      required: [
        "call_id",
        "business_id",
        "practitioner_ids",
        "appointment_type_id",
        "starts_at",
        "ends_at",
      ],
    },
  ),
  customTool(
    "book_appointment",
    "Book one current availability token after the caller confirms their full name and slot details.",
    "/v1/tools/book-appointment",
    {
      type: "object",
      properties: {
        call_id: string,
        patient_id: string,
        full_name: string,
        availability_token: string,
        idempotency_key: string,
      },
      required: ["call_id", "patient_id", "full_name", "availability_token", "idempotency_key"],
    },
  ),
  customTool(
    "list_patient_appointments",
    "List only the selected caller's appointments before a reschedule or cancellation.",
    "/v1/tools/list-patient-appointments",
    { type: "object", properties: { call_id: string, patient_id: string }, required: ["call_id", "patient_id"] },
  ),
  customTool(
    "reschedule_appointment",
    "Reschedule one selected appointment after a fresh availability search and confirmation.",
    "/v1/tools/reschedule-appointment",
    {
      type: "object",
      properties: { call_id: string, appointment_id: string, starts_at: string, ends_at: string, idempotency_key: string },
      required: ["call_id", "appointment_id", "starts_at", "ends_at", "idempotency_key"],
    },
  ),
  customTool(
    "cancel_appointment",
    "Cancel one selected appointment after caller confirmation.",
    "/v1/tools/cancel-appointment",
    { type: "object", properties: { call_id: string, appointment_id: string, idempotency_key: string }, required: ["call_id", "appointment_id", "idempotency_key"] },
  ),
  customTool(
    "save_call_checkpoint",
    "Persist authoritative state after identity, slot offer, or completed mutation. Never store availability tokens.",
    "/v1/tools/save-call-checkpoint",
    {
      type: "object",
      properties: { session_id: string, checkpoint: { type: "object" }, patient_id: string, language_mode: string },
      required: ["session_id", "checkpoint"],
    },
  ),
  customTool(
    "log_follow_up",
    "Create a callback request for a human request, clinical concern, or unsupported issue.",
    "/v1/tools/log-follow-up",
    {
      type: "object",
      properties: { session_id: string, idempotency_key: string, reason: string, details: { type: "object" } },
      required: ["session_id", "idempotency_key", "reason", "details"],
    },
  ),
];

const llmPayload = {
  model: "gpt-5.1",
  model_temperature: 0,
  tool_call_strict_mode: true,
  begin_message:
    "Hello, I am the automated appointment assistant for Physiotattva. I can help in English or Hindi. May I have your phone number to get started?",
  general_prompt: prompt,
  general_tools: tools,
  default_dynamic_variables: {
    platform_call_id: "retell-staging-web-demo",
    called_phone: "+910000000000",
  },
};

function agentPayload(llmId) {
  return {
    agent_name: agentName,
    version_title: "staging",
    version_description: "Bilingual Physiotattva appointment receptionist backed by Cliniko.",
    response_engine: { type: "retell-llm", llm_id: llmId, version: 0 },
    voice_id: "11labs-Monika",
    voice_model: "eleven_multilingual_v2",
    language: ["en-IN", "hi-IN"],
    responsiveness: 0.9,
    interruption_sensitivity: 0.85,
    enable_dynamic_responsiveness: true,
    enable_backchannel: false,
    data_storage_setting: "everything_except_pii",
    boosted_keywords: ["Physiotattva", "Jayanagar", "Indiranagar", "Cliniko"],
  };
}

const listed = await retellRequest("/list-agents", "GET");
const existing = (Array.isArray(listed) ? listed : listed.agents ?? []).find(
  (agent) => agent.agent_name === agentName,
);
let llmId;
let agentId;
let action;
if (existing) {
  const agent = await retellRequest(`/get-agent/${existing.agent_id}`, "GET");
  if (agent.response_engine?.type !== "retell-llm") {
    throw new Error(`Existing agent ${existing.agent_id} does not use a Retell LLM`);
  }
  llmId = agent.response_engine.llm_id;
  await retellRequest(`/update-retell-llm/${llmId}`, "PATCH", llmPayload);
  await retellRequest(`/update-agent/${existing.agent_id}`, "PATCH", agentPayload(llmId));
  agentId = existing.agent_id;
  action = "updated";
} else {
  const llm = await retellRequest("/create-retell-llm", "POST", llmPayload);
  llmId = llm.llm_id;
  const agent = await retellRequest("/create-agent", "POST", agentPayload(llmId));
  agentId = agent.agent_id;
  action = "created";
}

console.log(JSON.stringify({ action, agent_id: agentId, llm_id: llmId, backend_url: backendUrl }));
