import { readFile } from "node:fs/promises";

for (const name of ["BACKEND_URL", "RETELL_API_KEY", "RETELL_TOOL_TOKEN"]) {
  if (!process.env[name]) throw new Error(`${name} is required`);
}

const backendUrl = process.env.BACKEND_URL.replace(/\/$/, "");
if (!/^https?:\/\//.test(backendUrl)) {
  throw new Error("BACKEND_URL must use HTTP or HTTPS");
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
    "Read the live clinic businesses, practitioners, and appointment types before searching availability. Present appointment types using branch_name and visit_type_name as separate fields, not the raw combined name. Never invent IDs.",
    "/v1/tools/clinic-catalog",
    { type: "object", properties: {} },
    { method: "GET", speakDuringExecution: false },
  ),
  customTool(
    "bootstrap_call",
    "Create or resume a call session using Retell's caller ID. Use {{user_number}} for caller_phone on inbound calls; do not ask the caller to repeat it unless bootstrap rejects it. Use Retell's call_id, direction, and agent_number system variables for call metadata.",
    "/v1/tools/bootstrap-call",
    {
      type: "object",
      properties: {
        platform_call_id: { ...string, description: "Use {{call_id}} exactly." },
        direction: { ...string, enum: ["inbound"], description: "Use {{direction}} exactly." },
        caller_phone: { ...string, description: "Use {{user_number}} exactly for the inbound caller phone in E.164 format. Ask for the number only if caller-ID bootstrap is rejected." },
        called_phone: { ...string, description: "Use {{agent_number}} exactly." },
      },
      required: ["platform_call_id", "direction", "caller_phone", "called_phone"],
    },
  ),
  customTool(
    "search_availability",
    "Search fresh live availability. For same-date results, state spoken_date once and present spoken_time_range values as a compact numbered list; never repeat the weekday before every slot. Use spoken_label as the fallback for a cross-date slot. Call again whenever the caller changes any scheduling constraint.",
    "/v1/tools/search-availability",
    {
      type: "object",
      properties: {
        session_id: { ...string, description: "Use the session_id returned by bootstrap_call exactly." },
        business_id: string,
        practitioner_ids: { type: "array", items: string },
        appointment_type_id: string,
        starts_at: { ...string, description: "Timezone-aware ISO 8601 timestamp." },
        ends_at: { ...string, description: "Timezone-aware ISO 8601 timestamp." },
      },
      required: [
        "session_id",
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
        session_id: { ...string, description: "Use the session_id returned by bootstrap_call exactly." },
        patient_id: string,
        full_name: string,
        availability_token: string,
        idempotency_key: string,
      },
      required: ["session_id", "patient_id", "full_name", "availability_token", "idempotency_key"],
    },
  ),
  customTool(
    "list_patient_appointments",
    "List only the selected caller's appointments before a reschedule or cancellation.",
    "/v1/tools/list-patient-appointments",
    {
      type: "object",
      properties: {
        session_id: { ...string, description: "Use the session_id returned by bootstrap_call exactly." },
        patient_id: string,
        full_name: string,
      },
      required: ["session_id", "patient_id", "full_name"],
    },
  ),
  customTool(
    "reschedule_appointment",
    "Reschedule one selected appointment after a fresh availability search and confirmation.",
    "/v1/tools/reschedule-appointment",
    {
      type: "object",
      properties: {
        session_id: { ...string, description: "Use the session_id returned by bootstrap_call exactly." },
        patient_id: string,
        full_name: string,
        appointment_id: string,
        availability_token: string,
        idempotency_key: string,
      },
      required: ["session_id", "patient_id", "full_name", "appointment_id", "availability_token", "idempotency_key"],
    },
  ),
  customTool(
    "cancel_appointment",
    "Cancel one selected appointment after caller confirmation.",
    "/v1/tools/cancel-appointment",
    {
      type: "object",
      properties: {
        session_id: { ...string, description: "Use the session_id returned by bootstrap_call exactly." },
        patient_id: string,
        full_name: string,
        appointment_id: string,
        idempotency_key: string,
      },
      required: ["session_id", "patient_id", "full_name", "appointment_id", "idempotency_key"],
    },
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
    "Hello. I am the automated appointment assistant for Physiotattva. I can help in English or Hindi. How may I help you today?",
  general_prompt: prompt,
  general_tools: tools,
  default_dynamic_variables: {
    direction: "inbound",
    agent_number: "+14177428846",
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
    voice_speed: 0.95,
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
