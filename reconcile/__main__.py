"""Command line.

  python -m reconcile list                               every property and its records
  python -m reconcile history "12 Kelburn Pde" [--llm]   one property's reconciled record
  python -m reconcile evaluate [--llm]                   score against data/truth.json
  python -m reconcile ask "question" --address "..."     plain-language question (needs a key)
"""

import argparse
import json
import sys
from pathlib import Path

from . import address_key, build_history, llm, load_records, resolve_with_model, sales_history
from .records import group_by_property

DATA = Path(__file__).resolve().parent.parent / "data"


def records_for(address):
    key = address_key(address)
    if key is None:
        sys.exit(f"Couldn't read '{address}' as an address (needs a number and a street type).")
    records = [r for r in load_records(DATA / "records.csv") if r["key"] == key]
    if not records:
        sys.exit(f"No records match '{address}' (looked for '{key}'). "
                 f"Run 'python -m reconcile list' to see what's there.")
    return key, records


def warn_unmatched(unmatched):
    for r in unmatched:
        print(f"warning: {r['record_id']} not matched to a property: '{r['address']}'",
              file=sys.stderr)


def list_properties(args):
    groups, unmatched = group_by_property(load_records(DATA / "records.csv"))
    for key, group in sorted(groups.items()):
        print(f"  {key:24} {', '.join(r['record_id'] for r in group)}")
    warn_unmatched(unmatched)


def show_history(args):
    key, records = records_for(args.address)
    usage = llm.Usage()
    history = resolve_with_model(records, use_llm=args.llm, usage=usage)

    print(f"{key}  ({len(records)} records: {', '.join(r['record_id'] for r in records)})\n")
    for field, result in history.items():
        print(f"  {field:16} {str(result['value']):12} {result['confidence']:7} "
              f"[{result['decided_by']}] {result['reason']}")
        if result["confidence"] == "low":
            print(f"  {'':16} candidates: {result['candidates']}")

    sales = sales_history(records)
    if sales:
        print("\n  Sales the sources mention:")
        for sale in sales:
            prices = "; ".join(f"${price:,} ({', '.join(ids)})"
                               for price, ids in sale["prices"].items())
            print(f"    {sale['date']}  {prices or 'price not recorded'}")
    if args.llm:
        print(f"\nModel usage: {usage}")


def evaluate(args):
    truth = json.loads((DATA / "truth.json").read_text(encoding="utf-8"))
    truth.pop("_note", None)
    records = load_records(DATA / "records.csv")

    usage = llm.Usage()
    history, unmatched = build_history(records, use_llm=args.llm, usage=usage)
    warn_unmatched(unmatched)

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
    key, records = records_for(args.address)
    usage = llm.Usage()
    history = resolve_with_model(records, use_llm=True, usage=usage)
    history["sales"] = sales_history(records)
    try:
        print(llm.ask(args.question, history, records, usage))
    except llm.ModelError as e:
        sys.exit(f"Model call failed: {e}")
    print(f"\nModel usage: {usage}")


def main():
    # Windows consoles default to a legacy code page, which turns "m²" in model replies into "m?".
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(prog="reconcile")
    commands = parser.add_subparsers(dest="command", required=True)

    p = commands.add_parser("list", help="every property and the records matched to it")
    p.set_defaults(run=list_properties)

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
