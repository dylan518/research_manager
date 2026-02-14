import json
import os
from typing import Any, Dict, List

from dotenv import load_dotenv
from openai import OpenAI

from semantic_scholar_client import SemanticScholarClient


SYSTEM_PROMPT = """You are a research assistant connected to Semantic Scholar tools.

Rules:
- Use tools when answering paper search, recommendation, and full-text questions.
- Do not claim details from a paper unless they are in tool results.
- Include paper identifiers and URLs in your answers where possible.
- If a full paper is unavailable, explain why and suggest next best actions.
"""


TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "name": "search_papers",
        "description": "Search Semantic Scholar papers by query.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                "year": {"type": "string", "description": "Optional year or year range filter."},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_paper_details",
        "description": "Get details for a paper by Semantic Scholar paper ID, DOI, ArXiv ID, etc.",
        "parameters": {
            "type": "object",
            "properties": {"paper_id": {"type": "string"}},
            "required": ["paper_id"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "recommend_papers",
        "description": "Get recommended papers related to a seed paper.",
        "parameters": {
            "type": "object",
            "properties": {
                "paper_id": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
            },
            "required": ["paper_id"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "read_full_paper_text",
        "description": "Download and read open-access PDF text for a paper if available.",
        "parameters": {
            "type": "object",
            "properties": {
                "paper_id": {"type": "string"},
                "max_chars": {"type": "integer", "minimum": 1000, "maximum": 100000},
            },
            "required": ["paper_id"],
            "additionalProperties": False,
        },
    },
]


def run_tool(client: SemanticScholarClient, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    if name == "search_papers":
        return client.search_papers(
            query=arguments["query"],
            limit=arguments.get("limit", 10),
            year=arguments.get("year"),
        )
    if name == "get_paper_details":
        return client.get_paper_details(arguments["paper_id"])
    if name == "recommend_papers":
        return client.recommend_papers(
            paper_id=arguments["paper_id"],
            limit=arguments.get("limit", 10),
        )
    if name == "read_full_paper_text":
        return client.read_full_paper_text(
            paper_id=arguments["paper_id"],
            max_chars=arguments.get("max_chars", 15000),
        )
    return {"error": f"Unknown tool: {name}"}


def main() -> None:
    dotenv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    # Force values from .env to override shell-exported keys.
    load_dotenv(dotenv_path=dotenv_path, override=True)

    openai_api_key = os.getenv("OPENAI_API_KEY_COMPANY") or os.getenv("OPENAI_API_KEY")
    s2_api_key = os.getenv("S2_KEY")
    if not openai_api_key:
        raise ValueError(
            "Missing OpenAI key. Set OPENAI_API_KEY_COMPANY or OPENAI_API_KEY in your environment or .env file."
        )
    if not s2_api_key:
        raise ValueError("Missing S2_KEY. Set it in your environment or .env file.")

    s2_client = SemanticScholarClient(api_key=s2_api_key)
    openai_client = OpenAI(api_key=openai_api_key)
    model = "gpt-5.2"

    print("GPT-5 + Semantic Scholar chat")
    print("Type 'exit' to quit.\n")

    previous_response_id = None

    while True:
        user_input = input("You: ").strip()
        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit"}:
            print("Bye.")
            break

        response = openai_client.responses.create(
            model=model,
            instructions=SYSTEM_PROMPT,
            input=user_input,
            tools=TOOLS,
            previous_response_id=previous_response_id,
        )

        while True:
            function_calls = [item for item in response.output if item.type == "function_call"]
            if not function_calls:
                break

            tool_outputs = []
            for call in function_calls:
                try:
                    args = json.loads(call.arguments) if call.arguments else {}
                    result = run_tool(s2_client, call.name, args)
                except Exception as exc:
                    result = {"error": str(exc)}

                tool_outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": json.dumps(result),
                    }
                )

            response = openai_client.responses.create(
                model=model,
                previous_response_id=response.id,
                input=tool_outputs,
                tools=TOOLS,
            )

        print(f"\nAssistant: {response.output_text}\n")
        previous_response_id = response.id


if __name__ == "__main__":
    main()
