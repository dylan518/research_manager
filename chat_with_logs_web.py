import json
import threading
from typing import Any, Callable, Dict, List

from dotenv import load_dotenv
from flask import Flask, make_response, redirect, render_template_string, request, url_for
from openai import BadRequestError, OpenAI

import minimal_memory_chat as mm


HTML = """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>Research Manager Chat + Logs</title>
    <style>
      * { box-sizing: border-box; }
      body { margin: 0; background: #0f1115; color: #e6e8ef; font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif; }
      .wrap { display: flex; height: 100vh; width: 100vw; overflow: hidden; }
      .chat-panel { width: 68%; min-width: 520px; display: flex; flex-direction: column; border-right: 1px solid #2a2f3a; background: #12151c; }
      .logs-panel { width: 32%; min-width: 340px; display: flex; flex-direction: column; background: #0c0f14; }
      .meta { font-size: 12px; color: #9aa3b2; padding: 10px 14px; border-bottom: 1px solid #232936; background: #131722; }
      .chat-scroll, .logs-scroll { flex: 1; overflow-y: auto; padding: 14px; }
      .chat-scroll { scroll-behavior: smooth; }
      .msg { margin-bottom: 12px; padding: 10px 12px; border-radius: 10px; line-height: 1.35; white-space: pre-wrap; border: 1px solid transparent; }
      .u { background: #132235; border-color: #213f63; color: #b8dcff; }
      .a { background: #102318; border-color: #234331; color: #c7f6d2; }
      .s { background: #2a2212; border-color: #4b3b19; color: #ffe4a3; }
      .e { background: #30171a; border-color: #5d2c31; color: #ffb5bb; }
      #chat-form { display: flex; gap: 8px; padding: 12px; border-top: 1px solid #232936; background: #121722; }
      #prompt-input { flex: 1; padding: 10px 12px; background: #0f141d; color: #e6e8ef; border: 1px solid #394053; border-radius: 8px; }
      #send-btn { padding: 10px 14px; background: #2d6cdf; color: #fff; border: none; border-radius: 8px; cursor: pointer; }
      #send-btn:disabled { opacity: 0.7; cursor: not-allowed; }
      .log { margin-bottom: 10px; padding: 8px 10px; border-radius: 8px; background: #121722; border: 1px solid #202736; white-space: pre-wrap; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; color: #c9d2e3; }
    </style>
  </head>
  <body>
    <div class="wrap">
      <section class="chat-panel">
        <div class="meta">Model={{ model }} | History={{ history_path }} | Lines={{ index_lines }} | Updated={{ index_updated }}</div>
        <div class="chat-scroll" id="chat-pane">
          {% for m in messages %}
            <div class="msg {{ m.cls }}">{{ m.text }}</div>
          {% endfor %}
        </div>
        <form id="chat-form" method="post" action="/send">
          <input id="prompt-input" type="text" name="prompt" autocomplete="off" placeholder="Type message..." autofocus {% if processing %}readonly{% endif %} />
          <button id="send-btn" type="submit" {% if processing %}disabled{% endif %}>{% if processing %}Working...{% else %}Send{% endif %}</button>
        </form>
      </section>
      <section class="logs-panel">
        <div class="meta">Tool Logs (latest first)</div>
        <div class="logs-scroll">
          {% for l in logs %}
            <div class="log">{{ l }}</div>
          {% endfor %}
        </div>
      </section>
    </div>
    <script>
      (function () {
        const chatPane = document.getElementById("chat-pane");
        const form = document.getElementById("chat-form");
        const input = document.getElementById("prompt-input");
        const btn = document.getElementById("send-btn");
        if (chatPane) {
          chatPane.scrollTop = chatPane.scrollHeight;
        }
        form.addEventListener("submit", function () {
          btn.disabled = true;
          // Keep value submit-able; disabled inputs are omitted from form POST.
          input.readOnly = true;
          btn.textContent = "Working...";
        });
        const isProcessing = {{ "true" if processing else "false" }};
        if (isProcessing) {
          window.setTimeout(function () {
            window.location.reload();
          }, 1200);
        }
      })();
    </script>
  </body>
</html>
"""


def extract_assistant_text(response: Any) -> str:
    text = getattr(response, "output_text", "") or ""
    if text.strip():
        return text
    # Fallback path for responses where output_text is empty but message chunks exist.
    chunks: List[str] = []
    for item in getattr(response, "output", []) or []:
        if getattr(item, "type", None) != "message":
            continue
        for part in getattr(item, "content", []) or []:
            if getattr(part, "type", None) in {"output_text", "text"}:
                value = getattr(part, "text", None)
                if isinstance(value, str) and value.strip():
                    chunks.append(value)
    return "\n".join(chunks).strip()


def process_turn(
    user_input: str, client: OpenAI, model: str, log_callback: Callable[[str], None], *, append_user: bool = True
) -> str:
    if append_user:
        mm.append_message("user", user_input)
    compact_info = mm.auto_compact_context_if_needed()
    if compact_info.get("triggered"):
        log_callback(
            f"[context] auto-compacted: {compact_info['messages_before']} -> {compact_info['messages_after']} messages"
        )

    entries = mm.read_index_entries()
    history_items = mm.build_model_history_items(entries)
    tool_items = mm.build_tool_observation_items(entries)
    history_items = history_items + tool_items
    system_prompt = mm._truncate_text(mm.build_system_prompt(), mm.MAX_SYSTEM_PROMPT_CHARS)

    try:
        response = client.responses.create(
            model=model,
            instructions=system_prompt,
            input=history_items,
            tools=mm.PYTHON_TOOL,
        )
    except BadRequestError as exc:
        if "context_length_exceeded" not in str(exc):
            raise
        log_callback("[context] context_length_exceeded -> retrying with aggressive truncation")
        fallback_history_items = mm.build_model_history_items(
            mm.read_index_entries(),
            per_message_chars=mm.FALLBACK_SINGLE_MESSAGE_CHARS,
            max_messages=mm.FALLBACK_HISTORY_MESSAGES,
        )
        fallback_prompt = mm._truncate_text(system_prompt, mm.MAX_SYSTEM_PROMPT_CHARS // 2)
        response = client.responses.create(
            model=model,
            instructions=fallback_prompt,
            input=fallback_history_items,
            tools=mm.PYTHON_TOOL,
        )

    while True:
        function_calls = [item for item in response.output if item.type == "function_call"]
        if not function_calls:
            break
        tool_outputs: List[Dict[str, Any]] = []
        for call in function_calls:
            args_text = mm._truncate_text(call.arguments or "", mm.MAX_TOOL_ARGS_CHARS)
            mm.append_item({"type": "function_call", "name": call.name, "call_id": call.call_id, "arguments": args_text})
            log_callback(f"[tool] CALL {call.name}\n{args_text}")
            try:
                args = json.loads(call.arguments) if call.arguments else {}
                output = mm.run_python(args.get("code", "")) if call.name == "python" else {"ok": False, "error": f"Unknown tool: {call.name}"}
            except Exception as exc:  # noqa: BLE001
                output = {"ok": False, "error": str(exc)}

            output_obj = mm._compact_tool_output_obj(output)
            output_str = json.dumps(output_obj, ensure_ascii=False)
            mm.append_item({"type": "function_call_output", "call_id": call.call_id, "output": output_str})
            log_callback(f"[tool] OUTPUT {call.name}\n{mm._truncate_text(output_str, 2000)}")
            tool_outputs.append({"type": "function_call_output", "call_id": call.call_id, "output": output_str})

        response = client.responses.create(
            model=model,
            previous_response_id=response.id,
            input=tool_outputs,
            tools=mm.PYTHON_TOOL,
        )

    assistant_text = extract_assistant_text(response)
    if assistant_text.strip():
        mm.append_message("assistant", assistant_text)
    return assistant_text


app = Flask(__name__)
load_dotenv(dotenv_path=mm.ENV_PATH, override=True)
api_key = mm.os.getenv("OPENAI_API_KEY_COMPANY") or mm.os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("Missing OpenAI key in .env")
CLIENT = OpenAI(api_key=api_key)
MODEL = "gpt-5.2"
TOOL_LOGS: List[str] = []
UI_NOTICES: List[Dict[str, str]] = []
LOCK = threading.Lock()
PROCESSING = False


def add_log(text: str) -> None:
    with LOCK:
        TOOL_LOGS.insert(0, text)
        del TOOL_LOGS[100:]


def run_turn_worker(prompt: str) -> None:
    global PROCESSING
    try:
        _ = process_turn(prompt, CLIENT, MODEL, add_log, append_user=False)
    except Exception as exc:  # noqa: BLE001
        add_log(f"[error] {exc}")
        with LOCK:
            UI_NOTICES.append({"cls": "e", "text": f"ERROR: {exc}"})
    finally:
        with LOCK:
            PROCESSING = False


def build_chat_messages() -> List[Dict[str, str]]:
    messages: List[Dict[str, str]] = [{"cls": "s", "text": f"SYSTEM: Ready. Model={MODEL}. History={mm.INDEX_PATH}"}]
    role_to_cls = {"user": "u", "assistant": "a", "system": "s", "developer": "s"}
    role_to_prefix = {"user": "USER", "assistant": "ASSISTANT", "system": "SYSTEM", "developer": "DEVELOPER"}

    for entry in mm.read_index_entries():
        role = entry.get("role")
        content = entry.get("content")
        if role not in role_to_cls or content is None:
            continue
        text = content if isinstance(content, str) else str(content)
        messages.append({"cls": role_to_cls[role], "text": f"{role_to_prefix[role]}: {text}"})

    with LOCK:
        messages.extend(UI_NOTICES[-20:])
    return messages[-300:]


def index_stats() -> Dict[str, str]:
    line_count = 0
    with open(mm.INDEX_PATH, "r", encoding="utf-8") as f:
        for _ in f:
            line_count += 1
    updated = mm.time.strftime("%Y-%m-%d %H:%M:%S", mm.time.localtime(mm.os.path.getmtime(mm.INDEX_PATH)))
    return {"line_count": str(line_count), "updated": updated}


@app.get("/")
def home():
    with LOCK:
        logs = list(TOOL_LOGS)
        processing = PROCESSING
    messages = build_chat_messages()
    stats = index_stats()
    rendered = render_template_string(
        HTML,
        messages=messages,
        logs=logs,
        model=MODEL,
        history_path=mm.INDEX_PATH,
        processing=processing,
        index_lines=stats["line_count"],
        index_updated=stats["updated"],
    )
    response = make_response(rendered)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response


@app.post("/send")
def send():
    global PROCESSING
    prompt = (request.form.get("prompt") or "").strip()
    if not prompt:
        with LOCK:
            UI_NOTICES.append({"cls": "s", "text": "SYSTEM: Empty prompt received; message was not sent."})
        return redirect(url_for("home"))
    with LOCK:
        if PROCESSING:
            UI_NOTICES.append(
                {
                    "cls": "s",
                    "text": (
                        "SYSTEM: A response is still running. Message was not sent: "
                        f"\"{prompt[:180]}\""
                    ),
                }
            )
            return redirect(url_for("home"))
        PROCESSING = True
    try:
        mm.append_message("user", prompt)
        add_log(f"[ui] USER appended to index\n{prompt[:400]}")
    except Exception as exc:  # noqa: BLE001
        with LOCK:
            UI_NOTICES.append({"cls": "e", "text": f"ERROR: Failed to write user message to index.jsonl: {exc}"})
            PROCESSING = False
        return redirect(url_for("home"))

    threading.Thread(target=run_turn_worker, args=(prompt,), daemon=True).start()
    return redirect(url_for("home"))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=7860, debug=False)
