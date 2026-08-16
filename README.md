# Divided Oracle — QuantStorm 2026



**Last Updated at: 12:30 AM, if your version is older please re-fetch the repository**



**Read** [**`RULEBOOK.md`**](RULEBOOK.md) **first. It is the complete specification.**

**Mandatory:** [Join the WhatsApp community for all updates and queries](https://chat.whatsapp.com/ELJQfcO8VUT3nmwhdXvhmw)

Your submission is **one `.py` file**. Copy `starter\_bot.py`, fill it in, and
submit that.

## Quick start

```bash
python backtester.py --bot1 starter\_bot.py --bot2 strategies/naive\_ev.py
```

1. Copy `starter\_bot.py` to `strategies/my\_bot.py`.
2. Fill in the three metadata lines at the top — `Name`, `College`,
`Roll Number`. A file that still has the placeholders is rejected.
3. Implement all five methods: `reset`, `bid`, `quote`, `respond`,
`use\_transform`.
4. Duel it against the baselines:

```bash
python backtester.py --bot1 strategies/my\_bot.py --bot2 strategies/rational.py
```

5. Check it would be accepted:

```bash
python backtester.py --validate strategies/my\_bot.py
```

6. Before you submit, confirm it behaves identically under tournament
conditions:

```bash
python backtester.py --bot1 strategies/my\_bot.py --bot2 strategies/rational.py --isolate
```

A different score with `--isolate` means your bot is relying on something
the tournament takes away — state carried between deals, a call over the
time limit, or a module-level cache.

## Requirements

Python 3.10 or newer. No third-party packages, at any point.

Your submission may import only `math`, `random`, `statistics`, `collections`,
`heapq`, `bisect`, `itertools`, `functools`, `typing`.

`from \_\_future\_\_ import annotations` is also permitted, and
`collections.namedtuple` and `typing.NamedTuple` both work, with or without it.

## What is here

|Path|Purpose|
|-|-|
|`RULEBOOK.md`|The complete rules, parameters and interface specification|
|`starter\_bot.py`|Annotated template — copy this to begin|
|`backtester.py`|Duel two bots; `--validate` checks a submission would be accepted|
|`strategies/naive\_ev.py`|Baseline: prices on its own coins, never bids|
|`strategies/rational.py`|Baseline: reads the opponent's quote, never bids|
|`strategies/adaptive\_bidder.py`|Reference: reads quotes *and* values the auction|
|`engine.py`|The game engine — **do not modify**|
|`game\_config.py`|Every tunable parameter — **do not modify**|
|`bot\_loader.py`|The submission gate|
|`sandbox.py`, `policy.py`, `limits.py`|The isolation `--isolate` reproduces|

Modifying `engine.py` or `game\_config.py` changes nothing about the tournament,
which runs its own copies. Change them only to experiment locally, and
re-derive anything you concluded from a modified spec.

## The two baselines are there for a reason

`rational` is `naive\_ev` plus the entire pricing layer — it reads the
opponent's opening quote and infers their hand — and it still loses to anything
that bids in the auction. A bot that prices naively but bids sensibly beats a
bot that prices perfectly and never bids.

Beating the field takes both halves. Start by clearing `naive\_ev`, then see how
you do against `adaptive\_bidder`.

## Submission Guideline

A google form link will be shared in this README soon, where you can submit your bot python file by 11:59PM, 17th August. Please follow all the guidelines mentioned in the rulebook for the submission.

