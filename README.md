# RateBand

RateBand is a standalone Intelligent Contract that records an FX rate only when GenLayer validators agree within a fixed band. It keeps every observation. It has no frontend, no token, and no model call.

## Description

A caller chooses two currencies from a fixed list. The contract reads the rate from Frankfurter, and each validator reads it independently. The observation is stored only if the two scaled rates differ by at most 1 percent. Older observations stay readable by id. The latest pointer moves, but it does not erase history.

## Why the band exists

A public rate can change slightly between the leader's request and a validator's request. Requiring the JSON to be identical would reject a valid rate. Asking a model whether the numbers "look close" would not be a check. RateBand compares integers:

```text
abs(leader - validator) * 10000 <= leader * 100
```

One hundred basis points is the whole tolerance. The caller cannot widen it. If the band fails, nothing is stored.

## Source and inputs

The contract builds this URL itself:

`https://api.frankfurter.dev/v1/latest?from=BASE&to=QUOTE`

Allowed currencies are USD, EUR, GBP, CHF, and JPY. The two sides must differ. Any other input reverts with `UserError` before the request.

The stored rate is `round(decimal_rate * 100000000)`. Divide `scaled_rate` by `100000000` to get the decimal. `rate_date` is the date from the source, not the time of the transaction.

## Consensus

`record` runs `gl.vm.run_nondet_unsafe`.

1. The leader fetches the rate and returns `scaled_rate|YYYY-MM-DD`.
2. A validator fetches the rate again and applies the integer band to the scaled values.
3. The date strings do not have to match. The raw response does not have to match.
4. The agreed leader value is what gets stored.
5. The caller address, pair, scaled rate, and rate date are written only after consensus returns.

No `exec_prompt` or `prompt_comparative` call is used.

## State

| Field | Meaning |
|---|---|
| `observations[id]` | One permanent record: caller, pair, scaled rate, rate date |
| `latest[pair]` | Id of the newest observation for that pair |
| `next_id` | Number of observations stored |

`get_observation` reads one record. `get_latest` follows the pointer. There is no method that edits or deletes an observation.

## Methods

- `record(base, quote)` fetches, checks the band, and appends one observation
- `get_observation(obs_id)` returns that record
- `get_latest(base, quote)` returns the newest record for the pair

## Try it in Studio

Deploy `contracts/rate_band.py` with no constructor arguments.

1. Call `record` with `USD` and `EUR`.
2. Wait until the transaction is `FINALIZED` and the leader execution is `SUCCESS`.
3. Call `get_latest` with `USD` and `EUR`.
4. Divide `scaled_rate` by `100000000`.

Calling `record` with `USD` and `USD` must revert. This file does not claim that a deployment has been made.
