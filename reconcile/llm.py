"""Optional second opinion from an LLM on the fields the rules weren't sure about.

Uses the DeepSeek chat API (OpenAI-compatible). Put DEEPSEEK_API_KEY in a .env
file at the project root (see .env.example), or set it in the environment.

The model is only allowed to choose one of the values the sources actually
contain, or say it can't tell. Anything else is rejected and the rules'
answer stands, so the model can't invent a number.
"""

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
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

Reconciled history (JSON):
{history}

Original records, including notes (one JSON object per line):
{records}

Question: {question}"""


class ModelError(Exception):
    """The API call failed: bad key, rate limit, network, or a malformed reply."""


class Usage:
    """Running count of calls, failures and tokens, so cost can be reported."""

    def __init__(self):
        self.calls = 0
        self.failures = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0

    def add(self, usage):
        self.calls += 1
        self.prompt_tokens += usage.get("prompt_tokens", 0)
        self.completion_tokens += usage.get("completion_tokens", 0)

    def __str__(self):
        text = (f"{self.calls} calls, {self.prompt_tokens} prompt tokens, "
                f"{self.completion_tokens} completion tokens")
        if self.failures:
            text += f", {self.failures} failed calls"
        return text


def load_env_file(path=ENV_FILE):
    """Read KEY=value lines from .env into the environment. Real environment variables win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        if value:
            os.environ.setdefault(name.strip(), value)


def available():
    load_env_file()
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
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            reply = json.load(response)
        content = reply["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        hint = " (check DEEPSEEK_API_KEY)" if e.code == 401 else ""
        raise ModelError(f"HTTP {e.code} from the API{hint}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise ModelError(f"could not reach the API: {e}") from e
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        raise ModelError("unexpected reply from the API") from e

    if usage is not None:
        usage.add(reply.get("usage", {}))
    return content


def format_records(records):
    lines = []
    for r in records:
        lines.append(json.dumps({k: v for k, v in r.items() if k != "key"}))
    return "\n".join(lines)


def match_candidate(value, candidates):
    """Return the candidate the model meant, or None.

    Models sometimes send 192 as "192" or 192.0, which is fine. They can also
    send true, which Python would treat as equal to 1, so booleans are refused.
    """
    if value is None or isinstance(value, bool):
        return None
    for candidate in candidates:
        if isinstance(candidate, int):
            try:
                if float(value) == candidate:
                    return candidate
            except (TypeError, ValueError):
                continue
        elif str(value).strip() == candidate:
            return candidate
    return None


def check_choice(reply_text, candidates):
    """Return (value, reason, source_ids) if the reply is usable, else None."""
    try:
        reply = json.loads(reply_text)
    except json.JSONDecodeError:
        return None
    if not isinstance(reply, dict):
        return None
    value = match_candidate(reply.get("value"), candidates)
    if value is None:
        return None
    return value, reply.get("reason", ""), reply.get("source_ids", [])


def second_opinion(records, field, result, usage=None):
    """Ask the model about one low-confidence field. Returns an updated result."""
    prompt = RESOLVE_PROMPT.format(
        field=field,
        candidates=result["candidates"],
        records=format_records(records),
    )
    try:
        reply = chat(prompt, usage, json_mode=True)
    except ModelError as e:
        if usage is not None:
            usage.failures += 1
        return {**result, "reason": result["reason"] + f"; model call failed ({e})"}

    choice = check_choice(reply, result["candidates"])
    if choice is None:
        return {**result, "reason": result["reason"] + "; model gave no usable answer"}

    value, reason, source_ids = choice
    known_ids = {r["record_id"] for r in records}
    source_ids = [i for i in source_ids if i in known_ids]
    return {
        **result,
        "value": value,
        "reason": reason,
        "sources": source_ids,
        "decided_by": "model",
    }


def ask(question, history, records, usage=None):
    prompt = ASK_PROMPT.format(
        history=json.dumps(history, indent=2),
        records=format_records(records),
        question=question,
    )
    return chat(prompt, usage)
