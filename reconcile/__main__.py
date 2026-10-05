"""Command line.

  python -m reconcile history "12 Kelburn Pde"   show one property's reconciled record
  python -m reconcile evaluate [--llm]           score against data/truth.json
  python -m reconcile ask "question" --address "..."   plain-language question (needs a key)
"""

import argparse
import json
import sys
from pathlib import Path

from . import address_key, build_history, llm, load_records

DATA = Path(__file__).resolve().parent.parent / "data"


def show_history(args):
    key = address_key(args.address)
    records = [r for r in load_records(DATA / "records.csv") if r["key"] == key]
    if not records:
        sys.exit(f"No records match '{args.address}' (looked for '{key}').")

    usage = llm.Usage()
    history = build_history(records, use_llm=args.llm, usage=usage)[key]
    print(f"{key}  ({len(records)} records: {', '.join(r['record_id'] for r in records)})\n")
    for field, result in history.items():
        print(f"  {field:16} {str(result['value']):12} {result['confidence']:7} "
              f"[{result['decided_by']}] {result['reason']}")
    if args.llm:
        print(f"\nModel usage: {usage}")


def evaluate(args):
    truth = json.loads((DATA / "truth.json").read_text(encoding="utf-8"))
    truth.pop("_note", None)
    records = load_records(DATA / "records.csv")

    usage = llm.Usage()
    history = build_history(records, use_llm=args.llm, usage=usage)

    total = correct = 0
    by_confidence = {}
    mistakes = []
    for key, fields in truth.items():
        for field, (expected, why) in fields.items():
            result = history.get(key, {}).get(field)
            got = result["value"] if result else None
            confidence = result["confidence"] if result else "missing"
            ok = got == expected

            total += 1
            correct += ok
            seen, right = by_confidence.get(confidence, (0, 0))
            by_confidence[confidence] = (seen + 1, right + ok)
            if not ok:
                mistakes.append(f"  {key} / {field}: got {got}, expected {expected} ({why})")

    mode = "rules + model" if args.llm else "rules only"
    print(f"{mode}: {correct}/{total} correct ({correct / total:.0%})\n")
    for confidence in ("high", "medium", "low", "missing"):
        if confidence in by_confidence:
            seen, right = by_confidence[confidence]
            print(f"  {confidence:8} {right}/{seen} correct")
    if mistakes:
        print("\nMistakes:")
        print("\n".join(mistakes))
    if args.llm:
        print(f"\nModel usage: {usage}")


def ask(args):
    if not llm.available():
        sys.exit("Set DEEPSEEK_API_KEY to ask questions.")
    key = address_key(args.address)
    records = [r for r in load_records(DATA / "records.csv") if r["key"] == key]
    if not records:
        sys.exit(f"No records match '{args.address}'.")
    usage = llm.Usage()
    history = build_history(records, use_llm=True, usage=usage)
    print(llm.ask(args.question, history, usage))
    print(f"\nModel usage: {usage}")


def main():
    parser = argparse.ArgumentParser(prog="reconcile")
    commands = parser.add_subparsers(dest="command", required=True)

    p = commands.add_parser("history", help="show one property's reconciled record")
    p.add_argument("address")
    p.add_argument("--llm", action="store_true", help="ask the model about low-confidence fields")
    p.set_defaults(run=show_history)

    p = commands.add_parser("evaluate", help="score against the hand-checked answers")
    p.add_argument("--llm", action="store_true", help="ask the model about low-confidence fields")
    p.set_defaults(run=evaluate)

    p = commands.add_parser("ask", help="ask a plain-language question about a property")
    p.add_argument("question")
    p.add_argument("--address", required=True)
    p.set_defaults(run=ask)

    args = parser.parse_args()
    if getattr(args, "llm", False) and not llm.available():
        sys.exit("Set DEEPSEEK_API_KEY to use --llm.")
    args.run(args)


if __name__ == "__main__":
    main()
