import ast
import contextlib
import io
import json
import os
from typing import Any, Dict, List, Optional

from dotenv import dotenv_values, load_dotenv
from openai import OpenAI
import requests


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INSTRUCTIONS_PATH = os.path.join(BASE_DIR, "instructions.md")
INDEX_PATH = os.path.join(BASE_DIR, "index.jsonl")
ENV_PATH = os.path.join(BASE_DIR, ".env")
PYTHON_GLOBAL_SCOPE: Dict[str, Any] = {}


PYTHON_TOOL = [
    {
        "type": "function",
        "name": "python",
        "description": "Execute Python code with helper functions for index.jsonl memory operations.",
        "parameters": {
            "type": "object",
            "properties": {"code": {"type": "string"}},
            "required": ["code"],
            "additionalProperties": False,
        },
    }
]


def ensure_files() -> None:
    if not os.path.exists(INSTRUCTIONS_PATH):
        raise FileNotFoundError(f"Missing required file: {INSTRUCTIONS_PATH}")
    if not os.path.exists(INDEX_PATH):
        with open(INDEX_PATH, "w", encoding="utf-8"):
            pass


def load_instructions() -> str:
    with open(INSTRUCTIONS_PATH, "r", encoding="utf-8") as f:
        return f.read()


def read_index_entries() -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    entries.append(obj)
            except json.JSONDecodeError:
                continue
    return entries


def append_item(item: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(item, dict):
        raise ValueError("item must be a JSON object")
    with open(INDEX_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=True) + "\n")
    return item


def append_message(role: str, content: str) -> Dict[str, Any]:
    item = {"role": role, "content": content}
    return append_item(item)


def write_index_entries(entries: List[Dict[str, Any]]) -> int:
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=True) + "\n")
    return len(entries)


def delete_index_line(line_number: int) -> bool:
    if line_number < 1:
        return False
    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        lines = f.readlines()
    if line_number > len(lines):
        return False
    del lines[line_number - 1]
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        f.writelines(lines)
    return True


def recent_entries(limit: int = 20) -> List[Dict[str, Any]]:
    entries = read_index_entries()
    limit = max(1, limit)
    return entries[-limit:]


def run_python(code: str) -> Dict[str, Any]:
    # Ensure tool calls always see latest .env values.
    load_dotenv(dotenv_path=ENV_PATH, override=True)
    for key, value in dotenv_values(ENV_PATH).items():
        if value is not None:
            os.environ[key] = value

    stdout = io.StringIO()

    def get_env(name: str, default: Optional[str] = None) -> Optional[str]:
        return os.getenv(name, default)

    def s2_search_papers(query: str, limit: int = 20, year: Optional[str] = None) -> Dict[str, Any]:
        s2_key = os.getenv("S2_KEY")
        if not s2_key:
            raise ValueError("S2_KEY is not set in environment.")
        fields = ",".join(
            [
                "paperId",
                "title",
                "authors",
                "year",
                "abstract",
                "url",
                "venue",
                "citationCount",
                "influentialCitationCount",
                "openAccessPdf",
                "externalIds",
            ]
        )
        params: Dict[str, Any] = {
            "query": query,
            "limit": max(1, min(limit, 100)),
            "fields": fields,
        }
        if year:
            params["year"] = year
        response = requests.get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            headers={"x-api-key": s2_key},
            params=params,
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def s2_paper_details(paper_id: str) -> Dict[str, Any]:
        s2_key = os.getenv("S2_KEY")
        if not s2_key:
            raise ValueError("S2_KEY is not set in environment.")
        fields = ",".join(
            [
                "paperId",
                "title",
                "authors",
                "year",
                "abstract",
                "url",
                "venue",
                "citationCount",
                "influentialCitationCount",
                "openAccessPdf",
                "externalIds",
            ]
        )
        response = requests.get(
            f"https://api.semanticscholar.org/graph/v1/paper/{paper_id}",
            headers={"x-api-key": s2_key},
            params={"fields": fields},
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def s2_recommend_papers(paper_id: str, limit: int = 20) -> Dict[str, Any]:
        s2_key = os.getenv("S2_KEY")
        if not s2_key:
            raise ValueError("S2_KEY is not set in environment.")
        fields = ",".join(
            [
                "paperId",
                "title",
                "authors",
                "year",
                "abstract",
                "url",
                "venue",
                "citationCount",
                "openAccessPdf",
                "externalIds",
            ]
        )
        response = requests.get(
            f"https://api.semanticscholar.org/recommendations/v1/papers/forpaper/{paper_id}",
            headers={"x-api-key": s2_key},
            params={"limit": max(1, min(limit, 100)), "fields": fields},
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def http_get(url: str, params: Optional[Dict[str, Any]] = None, timeout: int = 30) -> Dict[str, Any]:
        response = requests.get(url, params=params, timeout=timeout)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type.lower():
            return {"status_code": response.status_code, "json": response.json()}
        return {"status_code": response.status_code, "text": response.text}

    runtime_scope = {
        "append_item": append_item,
        "append_message": append_message,
        "write_index_entries": write_index_entries,
        "delete_index_line": delete_index_line,
        "read_index_entries": read_index_entries,
        "recent_entries": recent_entries,
        "get_env": get_env,
        "s2_search_papers": s2_search_papers,
        "s2_paper_details": s2_paper_details,
        "s2_recommend_papers": s2_recommend_papers,
        "http_get": http_get,
        "os": os,
        "requests": requests,
        "INDEX_PATH": INDEX_PATH,
        "ENV_PATH": ENV_PATH,
    }
    PYTHON_GLOBAL_SCOPE.update(runtime_scope)

    try:
        PYTHON_GLOBAL_SCOPE.pop("__last_expression_result__", None)

        tree = ast.parse(code, mode="exec")
        if tree.body and isinstance(tree.body[-1], ast.Expr):
            tree.body[-1] = ast.Assign(
                targets=[ast.Name(id="__last_expression_result__", ctx=ast.Store())],
                value=tree.body[-1].value,
            )
            ast.fix_missing_locations(tree)
            compiled = compile(tree, "<python_tool>", "exec")
        else:
            compiled = compile(code, "<python_tool>", "exec")

        with contextlib.redirect_stdout(stdout):
            exec(compiled, PYTHON_GLOBAL_SCOPE, PYTHON_GLOBAL_SCOPE)
        stdout_text = stdout.getvalue()
        result = PYTHON_GLOBAL_SCOPE.get("result", PYTHON_GLOBAL_SCOPE.get("__last_expression_result__"))
        if result is None and stdout_text.strip():
            result = stdout_text.strip()
        return {
            "ok": True,
            "stdout": stdout_text,
            "result": result,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "stdout": stdout.getvalue(),
            "error": str(exc),
        }


def _to_json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(k): _to_json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_json_safe(v) for v in value]
    if isinstance(value, set):
        return [_to_json_safe(v) for v in sorted(value, key=lambda x: str(x))]
    if hasattr(value, "keys") and not isinstance(value, (str, bytes, dict)):
        # Handles dict_keys and similar views.
        try:
            return [_to_json_safe(v) for v in list(value)]
        except Exception:  # noqa: BLE001
            return str(value)
    return str(value)


def main() -> None:
    ensure_files()
    load_dotenv(dotenv_path=ENV_PATH, override=True)

    api_key_source = "OPENAI_API_KEY_COMPANY" if os.getenv("OPENAI_API_KEY_COMPANY") else "OPENAI_API_KEY"
    api_key = os.getenv(api_key_source)
    if not api_key:
        raise ValueError("Missing OpenAI key in .env: OPENAI_API_KEY_COMPANY or OPENAI_API_KEY")

    client = OpenAI(api_key=api_key)
    model = "gpt-5.2"
    instructions = load_instructions()

    print("Minimal memory chat")
    print(f"Model: {model}")
    print(f"API key source: {api_key_source} ({api_key[:10]}...)")
    print(f"S2_KEY loaded: {bool(os.getenv('S2_KEY'))}")
    print("Type 'exit' to quit.\n")

    while True:
        user_input = input("You: ").strip()
        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit"}:
            print("Bye.")
            break

        # index.jsonl is the full chat history; append current user turn first.
        append_message("user", user_input)
        history_items = read_index_entries()

        response = client.responses.create(
            model=model,
            instructions=instructions,
            input=history_items,
            tools=PYTHON_TOOL,
        )

        while True:
            function_calls = [item for item in response.output if item.type == "function_call"]
            if not function_calls:
                break

            tool_outputs: List[Dict[str, Any]] = []
            for call in function_calls:
                append_item(
                    {
                        "type": "function_call",
                        "name": call.name,
                        "call_id": call.call_id,
                        "arguments": call.arguments or "",
                    }
                )
                try:
                    args = json.loads(call.arguments) if call.arguments else {}
                    if call.name != "python":
                        output = {"ok": False, "error": f"Unknown tool: {call.name}"}
                    else:
                        code = args.get("code", "")
                        output = run_python(code)
                except Exception as exc:  # noqa: BLE001
                    output = {"ok": False, "error": str(exc)}

                output_str = json.dumps(_to_json_safe(output))
                append_item(
                    {
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": output_str,
                    }
                )
                tool_outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": output_str,
                    }
                )

            response = client.responses.create(
                model=model,
                previous_response_id=response.id,
                input=tool_outputs,
                tools=PYTHON_TOOL,
            )

        assistant_text = response.output_text or ""
        print(f"\nAssistant: {assistant_text}\n")
        if assistant_text.strip():
            append_message("assistant", assistant_text)


if __name__ == "__main__":
    main()
