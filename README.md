# property-history

[![tests](https://github.com/ionxg/property-history/actions/workflows/tests.yml/badge.svg)](https://github.com/ionxg/property-history/actions/workflows/tests.yml)

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
   clear majority, or only one source has the value, it's medium. Otherwise the most recent record
   wins, with low confidence.
3. **Treat a sale as one event.** A sale date and price belong together. The newest sale any source
   reports is the last sale (a newer sale isn't a disagreement, it's news), and its price is settled
   among the sources that report that same sale. Every sale mentioned is kept as a sales history.
4. **Optional: ask a model about the low-confidence fields.** The model (DeepSeek) sees every record
   for that property, including the free-text notes the rules ignore, and picks one of the values the
   sources actually contain. If it answers with anything else, the answer is thrown away and the rule
   result stands, so it can't invent a number. If the API call fails, the rule result stands too.
5. **Ask questions in plain language** about one property, answered only from its reconciled
   history and records, with record ids cited.

## Results

```
$ python -m reconcile evaluate
rules only: 24/26 correct (92%)

  high     9/9 correct
  medium   11/11 correct
  low      4/6 correct
```

Every mistake is in a low-confidence field, which is the point of the confidence labels: a person
(or the model) only needs to look at 6 of 26 fields. The two misses are floor areas where the newest
record is the council roll, but the council data predates an extension. The notes on the valuer's
record say so. Rules can't read notes, and a model can.

With the model step on (DeepSeek, `deepseek-chat`, temperature 0):

```
$ python -m reconcile evaluate --llm
python -m reconcile evaluate --llm --save results/my-run.json   # keep a record of the run
rules + model: 26/26 correct (100%)

  high     9/9 correct
  medium   11/11 correct
  low      6/6 correct

Model usage: 6 calls, 2655 prompt tokens, 339 completion tokens
```

The model fixed both rule mistakes and changed nothing the rules already had right; the same score
came back on a second run. Only the 6 low-confidence fields are sent, so the other 20 cost nothing.
At 12 Kelburn Parade it chose 138 m² over 120 and 135, citing "the consented 2023 rear extension"
from the valuer's note.

Every checked field from both runs, with the value chosen and the reason, is saved in
[`results/`](results/): `rules-only.json` and `deepseek-run.json`.

**Caveat:** I wrote the answer key and the data together, so these numbers show the method works,
not how it would do on real records. The next step would be a few hundred real records and an answer
key written by someone who didn't write the rules.

## Run it

Python 3.10+ and nothing to install.

```
python -m unittest                                  # 25 tests, no API key needed
python -m reconcile list                            # every property and its records
python -m reconcile evaluate                        # rules only
python -m reconcile history "88 Karori Rd"          # one property, with reasons and sales

# with a DeepSeek API key: copy .env.example to .env and paste the key there
# (.env is git-ignored), or set DEEPSEEK_API_KEY in your shell
python -m reconcile evaluate --llm
python -m reconcile history "88 Karori Rd" --llm
python -m reconcile ask "When was it last sold and for how much?" --address "88 Karori Rd"
```

## Layout

```
reconcile/records.py   loading the CSV, address matching
reconcile/rules.py     the rule-based resolver and sales history (no AI)
reconcile/llm.py       DeepSeek calls, the guard on its answers, token counting
reconcile/__main__.py  command line and evaluation
tests/                 unit tests; the model is mocked
data/                  synthetic records and the answer key
results/               saved evaluation runs (every field, value, reason, token usage)
.github/workflows/     tests run on every push (Ubuntu and Windows, Python 3.10 and 3.13)
```

See [CHANGELOG.md](CHANGELOG.md) for what changed between versions, and
[AI_NOTES.md](AI_NOTES.md) for how AI was used to build this.
