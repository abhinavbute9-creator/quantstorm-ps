# Name: Abhinav Bute
# College: SCTR's Pune Institute of Computer Technology
# Roll Number: 24109

"""
my_bot.py — Divided Oracle: "SplitSignal" (V2)
================================================

Built on top of the ideas in strategies/adaptive_bidder.py (state-conditional
power bidding, shaded first-price bids), with a pricing and negotiation layer
that goes beyond it in four ways. Each is traced to specific engine.py
behaviour below, not assumed from the docstrings of the reference bots.

1. THE OPPONENT-QUOTE READ SURVIVES INTO LATER ROUNDS, EVEN WHEN WE ARE
   MAKER.
   S does not change during a deal -- only our information about it does. So
   a read of the opponent's revealed sum from a round where we were Taker is
   still useful evidence in a later round where we are Maker. naive_ev,
   rational and adaptive_bidder all throw this away: their `_value()` returns
   just `k_mine + foresight` whenever `obs.is_maker` is true, discarding any
   anchor they are sitting on. This bot keeps one running read of the
   opponent's revealed sum and uses it everywhere -- quoting, responding,
   TRANSFORM valuation -- regardless of the current round's seat role.

2. THE ANCHOR IS CORRECTED FOR FORESIGHT CONTAMINATION (V2 fix).
   V1 treated the opening-quote midpoint as pure evidence about the
   opponent's own coins. That is wrong whenever the opponent held FORESIGHT
   at quote time: naive_ev, rational AND adaptive_bidder all quote
   `v = k_mine + sum(foresight)` (checked directly -- see each file's
   quote()), so a Maker holding a leak of OUR coins bakes part of OUR OWN
   revealed sum into their opening number. Reading that whole midpoint as
   "their k_mine" and then adding our own k_mine on top double-counts our
   own coins. Since FORESIGHT samples uniformly from the opponent's (here,
   from the Maker's point of view, OUR) currently-revealed coins
   (engine.apply_foresight), the expected contamination is
   (sample_fraction) * (our own k_mine at that round) -- both terms known
   exactly to us, because it is our own hand. We snapshot our own k_mine and
   whether the opponent held FORESIGHT at the moment we read their quote,
   and back the contamination out before using the anchor. This assumes the
   opponent quotes the same honest way the reference bots do; it is a
   strategic inference from observed convention, not an engine guarantee,
   so it is applied as a plain linear correction rather than anything more
   aggressive.

3. FORESIGHT'S RAW SAMPLE SUM IS KEPT UNSCALED -- ON PURPOSE (V2 re-check).
   engine.make_coins draws each of the 40 coins as an INDEPENDENT fair flip;
   there is no fixed population total tying them together. So the 4 coins a
   round-5 FORESIGHT sample misses (16 of the opponent's 20 revealed coins)
   are not "4 unknown members of a determined-total urn" -- they are
   unconditionally mean-zero regardless of what the sampled 16 turned out to
   be. A direct simulation of the actual sampling process (20 coins, sample
   16 without replacement, repeated 200k times) confirms this numerically:
   raw sample-sum against the true 20-coin sum has MSE 3.99; scaling the
   sample up by 20/16, which is the correction you would want under a
   fixed-total sampling model, is worse at MSE 4.99. It is a strictly worse
   estimator here, which is exactly what the "12x the variance" line in
   apply_foresight's own docstring is warning about, just applied to a
   smaller extrapolation gap. Rounds 1-4 need no estimator at all: FORESIGHT
   magnitude is 16 and 4*round <= 16 through round 4, so the sample is total
   coverage, not a sample.

4. THE FINAL NEGOTIATION TURN IS A THIRD PRICING DECISION, NOT A CONCESSION.
   Whoever responds on turn == N_TURNS and counters there does not "keep
   negotiating": engine.trade_round forces a fill at the midpoint of
   whatever range was just proposed, applies MIDPOINT_SIDE_RULE, and charges
   FORCED_FILL_FEE. Two things follow that the reference bots don't use:
     - engine._sanitise_response only re-centres a counter that is TOO WIDE
       (`if na - nb > max_width`); a *zero-width* counter (new_bid ==
       new_ask) is never touched, and trade_round settles at
       `(nb + na) // 2 + shift`, which for nb == na is just `nb + shift`
       exactly. So the forced price can be PINNED to a single chosen point
       inside the current (bid, ask), not merely nudged toward one.
     - TRICK_ROOM and STEALTH_ROCK shift a forced fill in the short seat's
       favour by their magnitude (RULEBOOK.md, "combining fill shifts";
       engine.fill_shift). Whoever ends up short benefits from holding more
       shift power than the counterparty.
   Put together, the final turn becomes a genuine three-way choice --
   ACCEPT_BUY, ACCEPT_SELL, or force at a self-chosen price -- decided by
   comparing expected values, instead of "counter if undecided". Who ends up
   short under a force is read off MIDPOINT_SIDE_RULE rather than assumed:
   under the shipped "last_quoter_sells" it is whoever calls respond() at
   turn N_TURNS (always us, since we only reach that branch by being called
   there), under "maker_sells" it is whoever obs.is_maker says, and under
   "coin_flip" the price terms cancel in expectation and forcing is worth
   exactly -FORCED_FILL_FEE regardless of where it is pinned.

Everything else -- the calibrated POWER_VALUES table, the 0.60 first-price
shade, and the flat-hand TRANSFORM test -- is taken from adaptive_bidder.py.
RULEBOOK.md section 12 names that file as free to copy, constants included,
and its own module docstring documents these three numbers as independently
measured and re-solved on the current spec (24 TE, 6 turns, drawn 1-slot
slate) rather than carried over from an older one.

DENIAL_WEIGHT (TRANSFORM denial) is shipped at 0.0. A local sweep over
{0.00, 0.15, 0.25, 0.35, 0.50, 0.75, 1.00} against all three reference bots
(40-60 seeds each, mirrored 10-deal matches) showed no value distinguishable
from noise at any setting -- see the accompanying report. Per RULEBOOK.md
section 12 that makes the honest default the field's own baseline of 0.0,
not a number this file introduces without evidence.

Everything below only reads GameConfig attributes/methods rather than
hard-coding the numbers those methods compute (final_cap, spread_cap,
MIN_REDUCTION, FORCED_FILL_FEE, TE_SALVAGE, MIDPOINT_SIDE_RULE, POWERS'
magnitudes), so it keeps working if the tournament host reruns with a
different GameConfig.
"""

from __future__ import annotations

import random


# ── Calibrated per-round tick value of each power, from adaptive_bidder.py ──
# See that file's module docstring for how these were measured: grant the
# power to one seat for one round, free, with both seats otherwise running
# the same bot, so a mirrored match nets to zero and the residual PnL is the
# power's value. Re-derive if the spec (TE_BUDGET, N_TURNS, SLOTS_PER_ROUND)
# ever moves; these are specific to the current one.
POWER_VALUES = {
    "FORESIGHT":    {1: 0.76, 2: 1.16, 3: 1.48, 4: 1.97, 5: 2.02},
    "TRICK_ROOM":   {1: 1.14, 2: 0.00, 3: 0.00, 4: 0.60, 5: 0.52},
    "SUBSTITUTE":   {1: 1.46, 2: 1.15, 3: 0.95, 4: 0.57, 5: 0.29},
    "STEALTH_ROCK": {1: 1.51, 2: 0.75, 3: 0.75, 4: 0.75, 5: 0.00},
    "TRANSFORM":    {1: 1.58, 2: 1.24, 3: 1.31, 4: 0.00, 5: 0.00},
}

# Fraction of fair value bid in the first-price auction. You pay your own
# bid, so bidding true value captures zero surplus by construction; shading
# below 1.0 is what lets a won auction actually be profitable. 0.60 is
# adaptive_bidder's re-solved value for this exact spec, with a broad basin
# (0.55-0.65 all score within noise of each other on that measurement).
SHADE = 0.60

# How close to zero our OWN revealed sum has to be before we call the hand
# "flat" -- worth swapping away under TRANSFORM.
FLAT_THRESHOLD = 1

# How close to zero the OPPONENT's revealed sum has to look, by our own read
# of it, before we consider paying to deny them a TRANSFORM they'd likely
# use.
OPP_FLAT_THRESHOLD = 2.0

# Weight on denying TRANSFORM to an opponent who reads flat, as a multiple
# of the swap's own value. adaptive_bidder ships this at 0.0, flagging the
# question as open rather than settled on the 24-TE spec. A local sweep
# (0.00 through 1.00, see the module docstring and the accompanying report)
# found no distinguishable difference at any setting against the three
# reference bots, so there is no measured evidence to justify moving off
# the conservative default. Denial only ever triggers when our own hand is
# decisive (so it never competes with our own "fire it" bid) and our read
# says the opponent's hand is flat too -- so even at 0.0 the logic stays in
# place and only needs a nonzero weight to become an active bid.
DENIAL_WEIGHT = 0.0


class Bot:
    name = "SplitSignal"

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def reset(self, seat, config, seed):
        self.seat = seat
        self.config = config
        self.rng = random.Random(seed)

        # Our single best read of the opponent's revealed-coin sum, from the
        # most recent round in which we were Taker and saw their opening
        # quote. `None` until we have one. Deliberately a single scalar, not
        # a per-round dict: a more recent read always covers more of the
        # opponent's revealed coins than an older one (they only reveal
        # more over time), so the latest read is always the best one we
        # have, and nothing is lost by overwriting rather than keeping a
        # history.
        self._opp_anchor = None
        # Snapshot taken alongside the anchor, needed to correct it for
        # FORESIGHT contamination (see module docstring, point 2):
        # our own k_mine at the moment we read the anchor, the round it was
        # read in, and whether the opponent held FORESIGHT that round.
        self._opp_anchor_round = None
        self._opp_anchor_my_k = None
        self._opp_anchor_saw_us = False

    # ------------------------------------------------------------------
    # Shared pricing: estimate S from whatever we legally know right now
    # ------------------------------------------------------------------

    def _corrected_anchor(self):
        """The opening-quote anchor, adjusted for FORESIGHT contamination.

        The raw anchor is the Maker's opening-quote midpoint, taken as a
        read of their revealed sum. That is only clean if they quoted from
        their OWN information alone. If they held FORESIGHT that round, the
        reference-bot quoting convention (`v = k_mine + sum(foresight)`,
        confirmed identical in naive_ev.py, rational.py and
        adaptive_bidder.py) bakes a sample of OUR revealed coins into that
        same number. FORESIGHT samples uniformly from the currently-revealed
        coins (engine.apply_foresight), so the expected size of that
        contamination is (sample_fraction) * (our own k_mine at that round)
        -- both known to us exactly, since it is our own hand. Subtract it
        out before the anchor is used for anything.

        This assumes the opponent quotes the way the reference bots do. It
        is the best available inference, not a guarantee, so the correction
        is a plain linear one rather than anything that could overcorrect
        by more than the leak itself could have contributed.
        """
        if self._opp_anchor is None:
            return None
        value = self._opp_anchor
        if self._opp_anchor_saw_us and self._opp_anchor_round:
            n_revealed_then = 4 * self._opp_anchor_round
            if n_revealed_then > 0:
                magnitude = self.config.POWERS.get("FORESIGHT", {}).get("magnitude", 16)
                sample_fraction = min(1.0, magnitude / n_revealed_then)
                value -= sample_fraction * self._opp_anchor_my_k
        return value

    def _opp_component(self, obs):
        """Best estimate of the opponent's revealed-coin contribution to S.

        FORESIGHT, when we hold it this round, is a direct sample of the
        opponent's currently-revealed coins and is preferred outright over
        an older quote-derived anchor: through round 4 it is total coverage,
        not a sample (see the module docstring, points 3-4), so an anchor
        could only add noise on top of it. Only fall back to the
        (contamination-corrected) anchor when there is no current leak to
        read.

        The raw sample sum is used as-is, unscaled: engine.make_coins draws
        every coin independently, so coins a FORESIGHT sample misses are
        unconditionally mean-zero regardless of what the sampled coins
        turned out to be (see module docstring, point 3, including a direct
        simulation). Coins neither of us has seen, and -- for the anchor
        branch -- coins the opponent has revealed since the anchor was
        taken, are treated as mean-zero for the same reason.
        """
        if obs.foresight:
            return float(sum(obs.foresight))
        anchor = self._corrected_anchor()
        if anchor is not None:
            return anchor
        return 0.0

    def _estimate_S(self, obs):
        """Point estimate of the hidden score S, given legal information only."""
        return obs.k_mine + self._opp_component(obs)

    # ------------------------------------------------------------------
    # Phase 1: the auction
    # ------------------------------------------------------------------

    def _transform_value(self, obs):
        """What winning TRANSFORM is worth to us right now, in ticks.

        Two live cases:
          flat hand           -> win it and FIRE it: take the better hand.
          decisive hand        -> win it and DECLINE it, which is only worth
                                  paying for if our read says the opponent
                                  is flat too and would actually use it.
        Buying it and declining is a legitimate defence because the power is
        CONSUMED either way (RULEBOOK.md section 5): a TRANSFORM we bought
        and did not fire cannot then be bought and fired by the opponent.
        """
        swap = POWER_VALUES["TRANSFORM"].get(obs.round, 0.5)
        if abs(obs.k_mine) <= FLAT_THRESHOLD:
            return swap
        anchor = self._corrected_anchor()
        if anchor is not None and abs(anchor) <= OPP_FLAT_THRESHOLD:
            return swap * DENIAL_WEIGHT
        return 0.0

    def bid(self, obs, offered):
        """Blind TE bids: shaded first-price bids on calibrated tick values.

        A power is worth what it does for us MINUS what it does for the
        opponent if they win it instead -- for TRANSFORM those pull in
        opposite directions (see _transform_value); for the other four,
        a power we don't win simply never fires, so "worth to us" is the
        whole story.
        """
        if not offered or obs.te_mine <= 0:
            return {}

        bids = {}
        for name in offered:
            if name == "TRANSFORM":
                value = self._transform_value(obs)
            else:
                value = POWER_VALUES.get(name, {}).get(obs.round, 0.5)
            if value <= 0:
                continue
            fair_te = value / self.config.TE_SALVAGE
            amount = int(fair_te * SHADE)
            if amount > 0:
                bids[name] = amount

        # Defensive re-shade if the vector we built doesn't fit the budget
        # (only possible if more than one power is on the block at once --
        # SLOTS_PER_ROUND is 1 on the shipped spec, but this reads that from
        # `offered` rather than assuming it). An unaffordable vector is
        # zeroed entirely by the engine (RULEBOOK.md section 4), which is
        # much worse than shading it ourselves.
        total = sum(bids.values())
        if total > obs.te_mine:
            scale = obs.te_mine / total
            bids = {name: int(amount * scale) for name, amount in bids.items()}
            bids = {name: amount for name, amount in bids.items() if amount > 0}

        return bids

    def use_transform(self, obs):
        """Fire from a flat hand, decline (as a defence) from a decisive one.

        A hand of twenty of the same sign is already about as informative as
        a hand can be -- there is nothing to gain from trading it away. A
        hand near zero tells us nothing the +/-1 prior didn't already say,
        so it is the one worth swapping.
        """
        return abs(obs.k_mine) <= FLAT_THRESHOLD

    # ------------------------------------------------------------------
    # Phase 2: the negotiation
    # ------------------------------------------------------------------

    def quote(self, obs):
        """Our opening two-sided quote, called only when we are Maker.

        Centre on the best S estimate available -- including a live anchor
        from an earlier round where we were Taker, which the reference bots
        discard on a Maker turn (see module docstring, point 1).

        Width defaults to the round's floor: the maker obligation is scored
        at the width actually quoted (RULEBOOK.md section 7.2), so an honest
        quote breaks even at ANY width, and the floor pays no WIDTH_PREMIUM
        while collecting the largest obligation payout when it lands. The
        one reason to open wider is defensive: if the opponent holds
        FORESIGHT this round, they see up to 16 of OUR revealed coins
        directly (a much sharper read on us than our own width would leak),
        so a tight quote is exactly what lets them cross us efficiently on
        their information advantage rather than ours. Trade some of the
        obligation's edge for a harder target in that specific situation.
        """
        s_hat = self._estimate_S(obs)
        centre = round(s_hat)

        if "FORESIGHT" in obs.powers_theirs:
            width = (obs.final_cap + obs.spread_cap) // 2
        else:
            width = obs.final_cap
        width = max(obs.final_cap, min(width, obs.spread_cap))

        lo = centre - width // 2
        return (lo, lo + width)

    def _shift_magnitude(self, obs, mine):
        """Total TRICK_ROOM/STEALTH_ROCK magnitude one side holds this round.

        Reimplemented from the table in RULEBOOK.md section 5, since
        engine.shift_sources lives in a module we cannot import.
        """
        active = obs.powers_mine if mine else obs.powers_theirs
        total = 0
        for name in ("TRICK_ROOM", "STEALTH_ROCK"):
            if name in active and name in self.config.POWERS:
                total += self.config.POWERS[name]["magnitude"]
        return total

    def _force_outcome(self, obs, bid, ask, s_hat):
        """Price and EV of countering on the final negotiation turn.

        On the shipped spec (N_TURNS=6, even) only the Taker ever calls
        respond() on turn == N_TURNS, because the responder alternates
        taker/maker starting with the taker at turn 2. The logic below does
        not rely on that, though: it asks MIDPOINT_SIDE_RULE who would be
        short if *whoever is calling this* forces right now, so it stays
        correct even if N_TURNS ever changed parity. Countering on this
        turn forces a fill instead of continuing the negotiation. Returns
        (price_to_pin, expected_value).
        """
        fee = self.config.FORCED_FILL_FEE
        rule = self.config.MIDPOINT_SIDE_RULE

        if rule == "coin_flip":
            # Which side we land on is an independent 50/50 draw, so
            # whatever price we pin cancels out in expectation -- forcing
            # is worth exactly -fee here, regardless of where we pin it.
            return bid, -fee

        i_am_short = obs.is_maker if rule == "maker_sells" else True
        target = ask if i_am_short else bid

        my_shift = self._shift_magnitude(obs, mine=True)
        their_shift = self._shift_magnitude(obs, mine=False)
        shift = (my_shift - their_shift) if i_am_short else (their_shift - my_shift)
        price = target + shift

        ev = (price - s_hat - fee) if i_am_short else (s_hat - price - fee)
        return target, ev

    def respond(self, obs, quote, turn):
        """Accept, counter, or -- on the final turn -- force at a chosen price."""
        if turn == 2 and not obs.is_maker:
            # The pristine opening quote: the one clean read of the Maker's
            # information (RULEBOOK.md section 9, on obs.contracts, makes
            # the same point about open_bid/open_ask). Every later range is
            # a negotiated object contaminated by both sides, so only turn 2
            # ever updates the anchor. We also snapshot what we'd need to
            # correct it for FORESIGHT contamination later (module
            # docstring, point 2): our own k_mine right now, and whether the
            # opponent holds FORESIGHT this round.
            self._opp_anchor = (quote[0] + quote[1]) / 2.0
            self._opp_anchor_round = obs.round
            self._opp_anchor_my_k = float(obs.k_mine)
            self._opp_anchor_saw_us = "FORESIGHT" in obs.powers_theirs

        bid, ask = quote
        s_hat = self._estimate_S(obs)
        edge_buy = s_hat - ask
        edge_sell = bid - s_hat

        if turn == self.config.N_TURNS:
            # Three genuine options now, not two-plus-a-default. Take
            # whichever has the best expected value.
            target, ev_force = self._force_outcome(obs, bid, ask, s_hat)
            action, best = "buy", edge_buy
            if edge_sell > best:
                action, best = "sell", edge_sell
            if ev_force > best:
                action, best = "force", ev_force

            if action == "buy":
                return "ACCEPT_BUY"
            if action == "sell":
                return "ACCEPT_SELL"
            return ("COUNTER", target, target)  # zero-width: pins the fill price

        # Not the final turn: a real "keep negotiating" option exists, so
        # only cross on a genuine edge rather than any positive one -- noise
        # in our own estimate shouldn't spend a trade. SUBSTITUTE caps our
        # loss on this round at 2 ticks with uncapped upside, so it is worth
        # crossing on a thinner, even slightly negative, edge while it's
        # active.
        margin = -1.5 if "SUBSTITUTE" in obs.powers_mine else 0.5
        if edge_buy > margin and edge_buy >= edge_sell:
            return "ACCEPT_BUY"
        if edge_sell > margin:
            return "ACCEPT_SELL"

        # Counter toward our estimate, shrinking by the legal minimum so we
        # keep as much negotiating room as possible for later turns.
        w = max(0, (ask - bid) - self.config.MIN_REDUCTION)
        centre = max(bid, min(round(s_hat), ask - w))
        return ("COUNTER", centre, centre + w)
