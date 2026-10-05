"""Optional second opinion from an LLM on the fields the rules weren't sure about.

Uses the DeepSeek chat API (OpenAI-compatible). Set DEEPSEEK_API_KEY to use it.

The model is only allowed to choose one of the values the sources actually
contain, or say it can't tell. Anything else is rejected and the rules'
answer stands, so the model can't invent a number.
"""

import json
import os
import urllib.request

API_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-chat"

RESOLVE_PROMPT = """You are checking property records from different sources that disagree.

Field: {field}
Candidate values (from the sources): {candidates}

Records for this property:
{records}

Pick the value that best describes the property today. Read the notes:
they often explain why a source is out of date. If the records don't give
enough to decide, answer null.

Reply with JSON only:
{{"value": <one of the candidate values, or null>, "reason": "<one sentence>", "source_ids": ["<record ids you relied on>"]}}"""

ASK_PROMPT = """Answer the question using only the property history below.
Cite the record ids you used in square brackets. If the history doesn't
contain the answer, say so plainly rather than guessing.

Property history (JSON):
{history}

Question: {question}"""


class Usage:
    """Running count of calls and tokens, so cost can be reported."""

    def __init__(self):
        self.calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0

    def add(self, usage):
        self.calls += 1
        self.prompt_tokens += usage.get("prompt_tokens", 0)
        self.completion_tokens += usage.get("completion_tokens", 0)

    def __str__(self):
        return (f"{self.calls} calls, {self.prompt_tokens} prompt tokens, "
                f"{self.completion_tokens} completion tokens")


def available():
    return bool(os.environ.get("DEEPSEEK_API_KEY"))


def chat(prompt, usage=None, json_mode=False):
    body = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}

    request = urllib.request.Request(
        API_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {os.environ['DEEPSEEK_API_KEY']}",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        reply = json.load(response)

    if usage is not None:
        usage.add(reply.get("usage", {}))
    return reply["choices"][0]["message"]["content"]


def format_records(records):
    lines = []
    for r in records:
        lines.append(json.dumps({k: v for k, v in r.items() if k != "key"}))
    return "\n".join(lines)


def check_choice(reply_text, candidates):
    """Return (value, reason, source_ids) if the reply is usable, else None."""
    try:
        reply = json.loads(reply_text)
    except json.JSONDecodeError:
        return None
    value = reply.get("value")
    if value is None or value not in candidates:
        return None
    return value, reply.get("reason", ""), reply.get("source_ids", [])


def second_opinion(records, field, result, usage=None):
    """Ask the model about one low-confidence field. Returns an updated result."""
    prompt = RESOLVE_PROMPT.format(
        field=field,
        candidates=result["candidates"],
        records=format_records(records),
    )
    choice = check_choice(chat(prompt, usage, json_mode=True), result["candidates"])
    if choice is None:
        return {**result, "reason": result["reason"] + "; model gave no usable answer"}

    value, reason, source_ids = choice
    return {
        **result,
        "value": value,
        "reason": reason,
        "sources": source_ids,
        "decided_by": "model",
    }


def ask(question, history, usage=None):
    prompt = ASK_PROMPT.format(history=json.dumps(history, indent=2), question=question)
    return chat(prompt, usage)
