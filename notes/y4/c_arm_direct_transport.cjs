// Direct single-shot transport for OpenCode Go (formal C path, config v2).
// One fetch, zero tools, zero agent loops, max_retries=0.
// Endpoint/auth from the local provider catalog + official Go docs:
//   POST https://opencode.ai/zen/go/v1/chat/completions
//   env OPENCODE_API_KEY | client UA | stable x-opencode-session
const fs = require("fs");
const crypto = require("crypto");

const args = process.argv.slice(2);
function arg(name, fallback) {
  const i = args.indexOf("--" + name);
  return i >= 0 ? args[i + 1] : fallback;
}

const packagePath = arg("package");
const slug = arg("slug", "opencode-go/deepseek-v4.1-flash");
const maxTokens = parseInt(arg("max-tokens"), 10);
const timeoutMs = parseInt(arg("timeout-ms", "120000"), 10);
const sessionId = arg("session");
const configVersion = arg("config-version", "C-ARM-CONFIG-V3");
const outReceipt = arg("out");
const outRequest = arg("request");
const outRaw = arg("raw");
const outText = arg("text");

if (!packagePath || !outReceipt || !outRequest || !outRaw || !outText || !sessionId ||
    !Number.isInteger(maxTokens) || maxTokens <= 0) {
  console.error("missing or invalid args");
  process.exit(2);
}
if (slug !== "opencode-go/deepseek-v4.1-flash") {
  console.error("slug does not resolve to the locked identity");
  process.exit(2);
}
const key = process.env.OPENCODE_API_KEY;
if (!key) {
  console.error("missing OPENCODE_API_KEY");
  process.exit(2);
}

const packageBytes = fs.readFileSync(packagePath);
const body = JSON.stringify({
  model: slug.split("/")[1],
  messages: [{ role: "user", content: packageBytes.toString("utf8") }],
  max_tokens: maxTokens,
  stream: false,
});
const requestBytes = Buffer.from(body, "utf8");
fs.writeFileSync(outRequest, requestBytes); // exact request bytes retained

const receipt = {
  document_type: "C_DIRECT_NODE_TRANSPORT_RECEIPT",
  config_version: configVersion,
  requested_identity: "DeepSeek V4.1 Flash",
  runtime_slug: slug,
  package_sha256: crypto.createHash("sha256").update(packageBytes).digest("hex"),
  request_body_sha256: crypto.createHash("sha256").update(requestBytes).digest("hex"),
  request_body_bytes: requestBytes.length,
  timeout_ms: timeoutMs,
  max_tokens: maxTokens,
  max_retries: 0,
  tools: 0,
  agent_steps: 0,
  http_request_count: 1,
  provider_generation_count: 0,
  successful_generation_count: 0,
};

const started = Date.now();
(async () => {
  try {
    const response = await fetch("https://opencode.ai/zen/go/v1/chat/completions", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "aedl-y4-dry-direct-c/1.0",
        "x-opencode-session": sessionId,
        "Authorization": "Bearer " + key,
      },
      body: requestBytes,
      signal: AbortSignal.timeout(timeoutMs),
    });
    receipt.provider_generation_count = 1;
    const raw = Buffer.from(await response.arrayBuffer());
    receipt.http_status = response.status;
    receipt.latency_ms = Date.now() - started;
    receipt.raw_response_sha256 = crypto.createHash("sha256").update(raw).digest("hex");
    fs.writeFileSync(outRaw, raw);
    if (response.status !== 200) {
      receipt.status = "FAILED_HTTP_" + response.status;
      receipt.error_snippet = raw.toString("utf8").slice(0, 300);
      fs.writeFileSync(outReceipt, JSON.stringify(receipt, null, 1));
      process.exit(2);
    }
    receipt.successful_generation_count = 1;
    const payload = JSON.parse(raw.toString("utf8"));
    const choice = (payload.choices && payload.choices[0]) || {};
    const message = choice.message || {};
    receipt.response_id = payload.id || null;
    receipt.usage = payload.usage || null;
    receipt.finish_reason = choice.finish_reason || null;
    receipt.tool_calls = (message.tool_calls || []).length;
    const content = message.content;
    if (typeof content !== "string") {
      receipt.status = "FAILED_NO_CONTENT";
      fs.writeFileSync(outReceipt, JSON.stringify(receipt, null, 1));
      process.exit(2);
    }
    const contentBytes = Buffer.from(content, "utf8");
    fs.writeFileSync(outText, contentBytes);
    receipt.model_text_sha256 = crypto.createHash("sha256").update(contentBytes).digest("hex");
    receipt.model_text_bytes = contentBytes.length;
    receipt.status = "COMPLETED";
    fs.writeFileSync(outReceipt, JSON.stringify(receipt, null, 1));
    console.log("COMPLETED");
    process.exit(0);
  } catch (err) {
    receipt.status = "FAILED_TRANSPORT";
    receipt.latency_ms = Date.now() - started;
    receipt.error = String(err && err.name ? err.name : err).slice(0, 200);
    fs.writeFileSync(outReceipt, JSON.stringify(receipt, null, 1));
    console.error(receipt.status + " " + receipt.error);
    process.exit(2);
  }
})();
