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

## 2. Supervisor email

> Subject: CSE400 thesis topic: deterministic verifiers vs LLM judges for RL training of code agents
>
> Dear [Supervisor name],
>
> I would like to propose the following topic for my CSE400 thesis this semester:
> "Preventing reward hacking in RL post-training of code agents: multi-signal deterministic
> verifiers vs LLM-as-a-judge rewards."
>
> I am building a set of small, containerized FastAPI + PostgreSQL tasks where a model must fix a
> security flaw. Each fix is scored by functional tests, hidden security tests, and static
> analysis. I plan to train a small open model (Qwen3-4B) with GRPO under three reward settings
> (LLM judge, public tests only, full deterministic verifier) and compare held-out fix rates and
> how often the model games the reward.
>
> I would like to release the code as open source. Could you let me know:
> 1. Whether this topic fits the CSE400 scope and timeline.
> 2. Whether open-sourcing the code (and using it in freelance work) causes any issue.
> 3. Any milestones or report deadlines I should plan around.
>
> Thank you,
> [Your name], [Student ID]

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
