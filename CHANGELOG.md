# Changelog

## 0.2.2 (2026-10-05)

### Fixed
- `m²` in model replies printed as `m?` on Windows consoles. Output is now always UTF-8.

### Results
- First real run of the model step: **26/26** correct (rules only: 24/26), 6 API calls,
  2,655 prompt + 339 completion tokens. Same score on a second run. Added to the README.

## 0.2.1 (2026-10-05)

### Added
- The API key can go in a `.env` file at the project root (git-ignored; template in `.env.example`)
  instead of a shell variable. A variable already set in the shell takes priority.

## 0.2.0 (2026-10-05)

### Fixed
- **Address matching broke on street names containing a street type.** `1 Parade Road` was read as
  `1 parade`. The last street-type word now counts, so it stays `1 parade road`.
- **Addresses with no street number were accepted.** `Kelburn Parade` would have matched as a
  property. A key now needs a number first (`12`, `12A` or `2/14`).
- **Sale date and price could come from different sales.** They were settled separately, so the
  result could pair a 2023 date with a 2020 price. They're now settled as one event.
- **A newer sale was treated as a disagreement.** At 88 Karori Road the council roll knows the 2012
  sale and the valuer knows the 2025 one; the rules picked the 2012 price. The newest sale now wins.
- **Model answers sent as text were thrown away.** `"192"` or `192.0` is now accepted as 192.
- **`true` was accepted as the value 1** (Python treats them as equal). Booleans are now refused.
- **A failed API call crashed the whole run.** A bad key, rate limit or network error now leaves the
  rule result in place and is counted as a failed call in the usage report.
- **The model could cite record ids that don't exist.** Unknown ids are dropped.
- **A value from a single source was marked high confidence.** Nothing backs it up, so it's now medium.
- **Answer key wording for 12 Kelburn Parade** said the valuer measured "most recently", which the
  dates don't support. It now gives the real reason (the council area predates the extension).

### Added
- `python -m reconcile list` shows every property and the records matched to it.
- `history` shows every sale the sources mention, and the candidate values for low-confidence fields.
- Records that can't be matched to any property are reported as warnings instead of silently dropped.
- `ask` now sees the original records and notes as well as the reconciled history, so it can explain
  *why* a value was chosen.
- Clearer messages for an address that can't be read or isn't in the data.
- 10 more tests (24 in total) covering each fix above.
- `.gitattributes` so line endings stay consistent on Windows and Linux.

### Results
- Rules only: 23/26 → **24/26** correct. Low-confidence fields needing a second look: 8 → 6.

## 0.1.0 (2026-10-05)

- First version: address matching, rule-based resolver with confidence levels, optional DeepSeek
  second opinion limited to values the sources contain, plain-language questions, evaluation against
  a hand-checked answer key.
