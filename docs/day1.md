# Day 1 checklist

## 1. Payout check (researched 2026-10-18)

Key finding: Stripe *does* pay out to Bangladesh-resident individuals on US platforms, but only to a
**local Bangladeshi bank account, in BDT**. The Payoneer USD receiving account cannot be used for
Stripe-based platforms. Keep Payoneer for direct clients and platforms that support it.

| Platform | Payout method | Works from BD? | Evidence | Action |
|---|---|---|---|---|
| Mercor | Stripe Express → local bank (BDT) | ✅ Yes | Bangladesh listed on talent.docs.mercor.com/policies/supported-countries | Apply now |
| Algora | Stripe Connect | ✅ Payouts yes, but see below | Bangladesh in Algora's connect country list | Deprioritize (bounty board is dead) |
| Datacurve / Shipd | Stripe or Wise | ⚠️ Likely | Payout page offers Stripe + Wise, BDT in currency list | Apply, ask support |
| micro1 | Deel | ⚠️ Likely | Pays contractors via Deel | Apply, ask support |
| AfterQuery | Stripe only | ⚠️ Unconfirmed | Needs "a Stripe-supported country" | Ask support first |
| Prime Intellect | Not published | ❓ Unknown | — | Ask on Discord |

Payment rails:
- [x] Payoneer verified (for direct clients / B2B sprint deposits)
- [ ] A Bangladeshi bank account you can attach to Stripe (USD→BDT cross-border payouts)

### Support questions to send

- **Prime Intellect (Discord):** "How are environment bounties paid (Stripe, Wise, Deel, crypto,
  compute credits)? Can a Bangladesh-resident individual receive payment, and is KYC required?"
- **Shipd (team@shipd.ai):** "Is Bangladesh a supported payout country for Stripe or Wise, and is
  identity verification available for Bangladesh?"
- **AfterQuery (support@afterquery.com):** "Does your Stripe Express onboarding allow
  Bangladesh-resident individuals?"
- **micro1:** "Do you pay through Deel, and which withdrawal methods are available in Bangladesh
  (Payoneer, local bank)?"

## 2. Advisor outreach

This project is an independent research paper, not a course thesis. The current proposal and
advisor email live outside this public repo (E:\Thesis); the research plan is summarized in
results/evals/README.md.

## 3. CV top block

Fill in after 3+ tasks and the first training run exist. Do not list results that have not been measured.

## 4. Algora: dropped from Phase 1

As of Oct 2026 Algora has pivoted to recruiting; its public bounty board returns 404. Remaining
open bounties are either farmed (dozens of AI-generated PRs per issue) or abandoned by maintainers.
The best candidates found were all risky:

- onyx-dot-app/onyx#2281, $250, Python, ~45 competing PRs, no maintainer reply on the issue since 2024
- outerbase/starbasedb#59, $250, TypeScript, maintainer inactive since Jan 2025

Replacement for that time slot: environment bounties (Prime Intellect, Shipd) built from this repo,
and the Mercor application.
