# Extension 3(b): Avellaneda-Stoikov quotes as shadow orders through mbo-queue: KILLED by its rule

Status: **KILLED (design only).** Nothing was run, on synthetic or market data. No mbo-queue file
was edited. No number in this file is a result.

Kill rule (from the Extension 3 prompt): "if mbo-queue cannot express the quoting policy without
changing its code, write the design and stop; do not edit mbo-queue." It cannot, for the reasons
below, so this file is the design.

## 1. What mbo-queue can express today (verified by reading, 2026-10-12)

Sources read (read only): `mbo-queue/SPEC.md` v0.4 section 4, `mbo-queue/src/mboq/fast.py`, and
the shadow code in `mbo-queue/src/mboq/reference.py` (`_retire_and_place`, about lines 442 to 461).

* **Placement price is not an input.** SPEC section 4: "Placement price: the best price of side s
  at that boundary (no shadow if that side is empty)." `reference.py` does `px = self.best(side)`.
* **Both sides, always, together.** Each entry of `place_times` places one bid and one ask
  (`for side in ("B", "A")`). There is no per-shadow side.
* **One size and one life for every shadow.** `fast.run(rec, tick, place_times=(), ...,
  shadow_size=1, horizon_ns=60_000_000_000, ...)`: `shadow_size` and `horizon_ns` are scalars.
* **No cancel or requote.** A shadow's life ends only at `ts_place + horizon`, when the truth and
  every estimator have filled, or at an `R` record (SPEC section 4, "Life"). There is no way to
  pull a quote at a chosen time.
* **Open loop.** All `place_times` are passed up front and the whole session is processed in one
  call that rebuilds the book from the session start. Fills are only returned at the end, so no
  quoting decision can depend on fills that happened earlier in the same run.

The closest expressible policy is "join the best bid and the best ask every N seconds and hold for a
fixed horizon", which is what Line B's shadows already do. That is not Avellaneda-Stoikov.

## 2. Why Avellaneda-Stoikov quoting cannot be expressed

Avellaneda and Stoikov (2008) quote around a reservation price
r = s - q * gamma * sigma^2 * (T - t), with total spread
delta = gamma * sigma^2 * (T - t) + (2 / gamma) * ln(1 + gamma / k), so bid = r - delta/2 and
ask = r + delta/2 (s mid, q inventory, gamma risk aversion, sigma volatility, k order-arrival decay).

1. **Prices are chosen, not the touch.** After rounding to the tick, the AS bid and ask are often
   behind the touch (when delta/2 exceeds the half-spread, or when inventory skews one side away),
   sometimes inside the spread, and only sometimes exactly at the best price. mbo-queue only places
   at the best price.
2. **Requoting every step.** AS recomputes both quotes every step (for example every second) and
   cancels the old ones; the new order goes to the back of its new level. mbo-queue shadows cannot
   be cancelled and live for one fixed horizon.
3. **Inventory feedback.** r depends on q, and q depends on which quotes were filled. That needs a
   closed loop (fills up to time t must be known before the quotes at time t are set). mbo-queue's
   single batch call cannot provide that.
4. **Asymmetric quoting.** With inventory limits, AS may quote one side only; mbo-queue always
   places both sides.

## 3. Minimal engine features that would be needed (a future SPEC v0.5; not built)

Any change must keep `mboq.reference` (Python) and `mboq._core` (C++20) bitwise identical (D-024),
keep every existing output byte-identical with the new inputs absent (as v0.2 and v0.4 did), and
come with synthetic known-answer tests. Minimal set:

1. **Per-shadow quote schedule input:** arrays `(t_place, side, price, size, t_cancel)`. Placement
   at the first event boundary at or after `t_place`, at the back of level (side, price), with the
   ahead set = the orders resting at that price at that moment (possibly empty for a price behind
   the touch with no orders, or inside the spread). End reason `cancelled` at the first event
   boundary at or after `t_cancel`. Fill rules unchanged from section 4: an `F` at the shadow's price
   for an order not in the ahead set, or an `F` at a worse price on that side, fills it.
2. **Closed-loop stepping API** (needed for inventory skew): a stateful engine object with
   `advance_to(t)` that processes records up to t and returns the truth fills (and estimator fills)
   since the last call, plus `place(...)` and `cancel(shadow_id)`. Without it, only an open-loop
   variant (q = 0 always, symmetric quotes around the mid) is possible, which is not AS.
3. **Per-shadow outputs:** each fill's time, price and quantity (partial fills), end reason
   (`filled`, `cancelled`, `horizon`, `cleared`), and the ahead volume at placement, so that spread
   capture and markouts can be computed per fill.
4. A flag for quotes that **improve the touch**: such a quote would have changed the displayed book,
   so the no-impact assumption is weakest there; it must be counted and reported separately.

## 4. Design of the study for later (nothing run)

* **Question.** For an Avellaneda-Stoikov market maker quoting CL and NG outrights (ES as control),
  what are its true fill rate, spread capture and adverse selection when fills are decided by the
  order-ID-resolved queue (MBO truth), and how far off are the same quantities when fills are
  decided by the MBP queue estimators of SPEC section 5? This connects the repo's simulator result
  (AS pays adverse selection to get flat, synthetic flow) to real queues.
* **Data restriction.** Until Line B's confirmatory analysis is frozen and done, use only the
  exploratory days 2026-09-29, 2026-09-30 and 2026-10-01 (already viewed; excluded from Line B's
  confirmatory sample per `PREREG/B_confirmatory_DRAFT.md`). Never touch the holdout store for this.
  Any confirmatory use needs its own frozen PREREG first.
* **Policy.** Requote every 1 s (sensitivity 250 ms and 5 s); one lot per side; inventory limit
  (for example +/- 5 lots, quote one side only at the limit); gamma, k and sigma fixed in advance
  from the first exploratory day only (sigma from 1 s mid returns, k from the decay of fill
  intensity with distance from the mid), then held fixed on the other two days. Prices rounded
  away from the mid to the tick; never cross the opposite best. Session horizon T = end of the RTH
  window used by Line A/B.
* **Metrics (per product, per day, with the release window reported separately).**
  1. True fill rate: filled quotes / placed quotes, per side and by distance from the touch (0, 1, 2+
     ticks), and time to fill.
  2. Spread capture per fill: side * (mid at fill - fill price), in ticks.
  3. Adverse selection per fill at +1 s and +10 s: side * (mid(t_fill + h) - mid(t_fill)), in ticks;
     the markout of the fill (spread capture plus adverse selection) at both horizons.
  4. Inventory path and P&L split: spread capture, adverse selection, inventory mark to market, fees
     (CME exchange fee per contract) as a separate line.
  5. Model bias: the same metrics with fills from each SPEC section 5 estimator instead of the truth,
     reported as estimator minus truth.
* **Inference.** Day-level and event-level only (3 days is descriptive: no p-values claimed; any
  confirmatory claim waits for a frozen spec on a larger sample). Null and negative results (for
  example negative markout-adjusted P&L) are reported with the same prominence.
* **Known-answer tests first.** On `mboq.synthetic` streams with a scripted FIFO queue, a quote
  placed behind a known ahead volume must fill exactly when that volume has traded; a quote
  cancelled before that point must never fill.
* **Caveats to carry.** No-impact assumption (the quotes never enter the real book); implied
  liquidity is not in MBO; one-lot quotes; latency assumed zero unless a latency band is added
  (place and cancel take effect at the next event boundary at or after t + latency).
