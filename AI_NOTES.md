# Where AI helped and where it didn't

Built with Claude Code (Anthropic's coding assistant) in October 2026. Kept as I went, because
"it works" doesn't tell anyone how much of it I can vouch for.

## How it was built

I set the problem: messy property records from several sources, settled field by field, with a
confidence level and a way to measure accuracy. The assistant wrote most of the first draft of the
code, tests and synthetic data. I then read every file and ran everything before calling it mine.

## Where it helped

- **Boilerplate:** the CSV loading, the command line and the test scaffolding. Fast, and easy to
  check by reading.
- **Thinking of awkward addresses:** unit formats like `Flat 5, 30 The Terrace` and `Apt 45` with no
  unit number.
- **Testing the model step without a key:** mocking the API call so the guard logic is tested on
  every run.

## Where it didn't, or needed checking

- **The first version of the rules got everything right on its own data,** which proved nothing. The
  data was changed so the rules have real blind spots (stale council records whose problems are only
  explained in free-text notes), which gives the model step something to do.
- **The model has to be fenced in.** Left alone, a model will happily answer "130 m2" as a compromise
  between 120 and 138. `check_choice` only accepts values a source actually contains.
- **The evaluation can't be trusted beyond this data.** The same person (and assistant) wrote the data
  and the answer key.

## My own notes

<!-- Add what you noticed when you read and ran it: anything you changed, anything that surprised
you, what you'd do next. This section should be in your words. -->
