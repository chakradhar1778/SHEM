# SHEM — Billing & smart-home TODO

Gaps found in the billing review (2026-11-10). Ordered by priority.

## Done

- [x] **1. Budget warnings must include simulated appliances** — done 2026-11-10
  `conflicts.py` (target exceeded / at risk) and `compute_recommendations` (budget projection) sum only real
  PZEM energy, while Home and Target include simulated appliances, so the AI can stay silent while the UI shows
  you over budget. Use the same metered + simulated total, and compare in ₹ using the bill engine.

- [x] **2. Realistic tariff + projected bill for the current billing cycle** — done 2026-11-10
  (Settings → Electricity tariff; projected bill on the Bill page and Home; `/api/billing/*`)
  - Slab tariff (rising ₹/kWh per slab), monthly fixed charge, fuel adjustment (FPPCA) ₹/kWh and electricity
    duty %. Flat rate stays available, so existing setups keep working.
  - Real billing cycle from the meter-reading day (e.g. the 14th → the 13th), not calendar months.
  - Projected bill for the current cycle: kWh so far, projected kWh, itemised bill (each slab, fixed, fuel,
    duty), current slab and kWh left before the next one, projected vs budget.
  - All cost estimates (insights, today, target kWh) use the configured tariff, not a flat kWh × rate.
  - The "bill rate differs from tariff" check compares the bill with the engine's expected amount.

- [x] **3. Cost per appliance on each bill** — done 2026-11-10
  (Bill history → "Where the money went"; "Where this bill is going" on the projected bill;
  `/api/billing/bills/{id}/appliances`)
  Split each bill (and the projected bill) across appliances using the metered + simulated kWh measured in
  that bill's period, e.g. "AC = 52% of your October bill (₹640)".

- [x] **4. Bill vs actual usage instead of rated-watt estimates** — done 2026-11-10
  (Bill page → "Bill vs recorded usage": billed vs recorded kWh per day over the recorded hours)
  The Bill page compares a bill with rated W × hours/day. Compare with the metered + simulated kWh for the
  bill's real period (`billingPeriodStart` → `billingPeriodEnd`), and fall back to estimates only without data.

- [x] **5. Billing cycle alignment everywhere** — done 2026-11-10
  (Insights bill comparison uses the bill's real period; Target and Home measure the current billing cycle
  priced with the tariff; bill form fills period dates from the meter reading day)
  The Insights bill comparison uses `monthrange()` (calendar month). Use the bill's own period dates and
  the configured cycle day; prefill the period dates in the bill form from the cycle.

- [x] **6. Store the bill document so it can be viewed later (no OCR)** — done 2026-11-10
  (attach JPG/PNG/WebP/PDF ≤ 10 MB when adding a bill or later from Bill history; "View bill" viewer;
  type verified from the file bytes; stored in backend/uploads, git-ignored)
  Today only the file name is saved. Upload the image/PDF to the backend (size + type limits), keep it with the
  bill, and add a "View bill" action in Bill history. Reading the contents (OCR) is out of scope.

- [x] **7. Alerts + working notification bell** — done 2026-11-10
  (bell in the top bar; bill due ≤3 days / overdue, budget 80%/100%, projected over budget, slab near/entered,
  bill vs usage ≥30%; checked every minute, pushed live; `/api/notifications`)
  The top-bar bell is decorative. Add a notifications feed (WebSocket + list) for: bill due soon / overdue,
  budget 80% / 100% used, about to cross into a higher slab, projected bill above budget, bill entered that
  disagrees with measured usage.

- [x] **8. Budget-driven automation (opt-in)** — done 2026-11-10
  (Target → Budget saver: Off / Suggest / Automatic, trigger at-risk or over; only Essential = No appliances;
  each switched off at most once per 24 h; actions logged; `/api/automation/budget-saver`)
  When the projected bill is above budget, offer (or, if enabled, perform) switching off non-essential
  appliances (`isEssential = no`) on the relay or the simulator, with a log of what was switched and why.

- [x] **9. Bills per location** — done 2026-11-10
  (Insights, Target, Home, conflicts and bill analysis use this home's bills only; Bill history filters by
  location with per-location averages)
  Bills can be tagged "Parents' home" / "Office", but all analytics treat every bill as this home's.
  Filter comparisons, target evaluation and trends to `locationTag = my_home`, and show other locations
  separately.

- [x] **Mark a bill as paid** — done 2026-11-10
  (Bill history and the latest bill: Paid / Due / Overdue status, "Mark as paid" with a payment date, undo;
  paid bills stop due/overdue alerts; AI tool `mark_bill_paid`)

## Next

- [ ] **10. Bi-monthly billing cycles**
  Some utilities bill every two months with doubled slab limits. Support a cycle length of 1 or 2 months.
