# property-history

Property records from different sources rarely agree. A council roll, an old listing and a valuer's
report can give three different floor areas for the same house, and an address can be written five
ways. This tool lines those records up, settles each conflicting field, and says how sure it is and
which records it relied on. It also checks itself against a hand-checked answer key.

The data in `data/` is **synthetic**: eight made-up Wellington properties, three sources each,
written to include the conflicts that show up in real records (abbreviated addresses, unit formats,
stale council data, pre-settlement prices, a study listed as a bedroom).

## How it works

1. **Match records to a property.** `12 Kelburn Pde`, `12 Kelburn Parade, Kelburn` and
   `12 Kelburn Parade Kelburn Wellington` all reduce to `12 kelburn parade`. `Unit 2, 14 Aro St`
   becomes `2/14 aro street`.
2. **Settle each field with plain rules.** If all sources agree, the confidence is high. If there's a
   clear majority, it's medium. Otherwise the most recent record wins, with low confidence.
3. **Optional: ask a model about the low-confidence fields.** The model (DeepSeek) sees every record
   for that property, including the free-text notes the rules ignore, and picks one of the values the
   sources actually contain. If it answers with anything else, the answer is thrown away and the rule
   result stands, so it can't invent a number.
4. **Ask questions in plain language** about one property, answered only from its reconciled
   history, with record ids cited.

## Results

```
$ python -m reconcile evaluate
rules only: 23/26 correct (88%)

  high     10/10 correct
  medium   8/8 correct
  low      5/8 correct
```

Every mistake is in a low-confidence field, which is the point of the confidence labels: a person
(or the model) only needs to look at 8 of 26 fields. The three misses are all cases where the newest
record is the council roll, but the council data is out of date. The notes on the other records say
why. Rules can't read notes, and a model can.

`python -m reconcile evaluate --llm` runs the same check with the model step and reports
calls and tokens used, so accuracy can be weighed against cost.

**Caveat:** I wrote the answer key and the data together, so these numbers show the method works,
not how it would do on real records. The next step would be a few hundred real records and an answer
key written by someone who didn't write the rules.

## Run it

Python 3.10+ and nothing to install.

```
python -m unittest                                  # 14 tests, no API key needed
python -m reconcile evaluate                        # rules only
python -m reconcile history "88 Karori Rd"          # one property, with reasons

# with a DeepSeek API key
set DEEPSEEK_API_KEY=...        (PowerShell: $env:DEEPSEEK_API_KEY="...")
python -m reconcile evaluate --llm
python -m reconcile history "88 Karori Rd" --llm
python -m reconcile ask "When was it last sold and for how much?" --address "88 Karori Rd"
```

## Layout

```
reconcile/records.py   loading the CSV, address matching
reconcile/rules.py     the rule-based resolver (no AI)
reconcile/llm.py       DeepSeek calls, the guard on its answers, token counting
reconcile/__main__.py  command line and evaluation
tests/                 unit tests; the model is mocked
data/                  synthetic records and the answer key
```

See [AI_NOTES.md](AI_NOTES.md) for how AI was used to build this.
