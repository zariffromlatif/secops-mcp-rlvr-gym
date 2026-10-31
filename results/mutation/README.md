# Mutation testing

Each mutant is the gold fix with one small change (`uv run python runtime/mutants.py`). A test
suite that catches more of them leaves less room for a wrong fix to earn full reward. A
surviving mutant is either equivalent to the gold fix (reviewed in `equivalent.yaml`) or a gap
in the tests.

| Task | Mutants | Killed | Kill rate | In the fixed lines: killed | Unreviewed survivors |
|---|---|---|---|---|---|
| `daily_report_timezone_006` | 10 | 10 | 100% | 5/5 | 0 |
| `idempotency_keys_011` | 12 | 10 | 83% | 4/4 | 0 |
| `inventory_reservation_009` | 14 | 14 | 100% | 7/7 | 0 |
| `invoice_sort_001` | 4 | 4 | 100% | 4/4 | 0 |
| `invoice_split_rounding_005` | 10 | 10 | 100% | 4/4 | 0 |
| `invoice_tenant_002` | 7 | 7 | 100% | 1/1 | 0 |
| `late_fees_014` | 35 | 28 | 80% | 14/14 | 0 |
| `loyalty_points_expiry_012` | 40 | 40 | 100% | 27/27 | 0 |
| `orders_pagination_004` | 23 | 22 | 96% | 4/5 | 0 |
| `report_auth_003` | 2 | 2 | 100% | 0/0 | 0 |
| `revenue_double_count_007` | 1 | 1 | 100% | 0/0 | 0 |
| `shipping_quote_013` | 28 | 26 | 93% | 10/12 | 0 |
| `subscription_proration_008` | 16 | 16 | 100% | 4/4 | 0 |
| `tiered_pricing_010` | 18 | 15 | 83% | 9/12 | 0 |

## Survivors

- `idempotency_keys_011 L38 201 -> 202` (constant): the handler sets response.status_code itself
- `idempotency_keys_011 L38 201 -> 200` (constant): the handler sets response.status_code itself
- `late_fees_014 L41 1 -> 2` (constant): Decimal(2) and Decimal(1) have the same exponent, so quantize rounds the same
- `late_fees_014 L41 1 -> 0` (constant): Decimal(0) and Decimal(1) have the same exponent, so quantize rounds the same
- `late_fees_014 L52 <= -> <` (comparison): with nothing outstanding, or zero days late, both branches give a fee of 0
- `late_fees_014 L52 <= -> <` (comparison): with nothing outstanding, or zero days late, both branches give a fee of 0
- `late_fees_014 L52 0 -> 1` (constant): a 1-cent outstanding balance only; 2% of 1 cent rounds to 0 anyway
- `late_fees_014 L52 0 -> -1` (constant): zero outstanding or zero days late give a fee of 0 on either branch
- `late_fees_014 L52 0 -> -1` (constant): zero outstanding or zero days late give a fee of 0 on either branch
- `orders_pagination_004 L18 1 -> 0` (constant): max(0, ...) differs only for an empty table; the seed has 9 orders
- `shipping_quote_013 L45 // -> /` (arithmetic): a fractional gram is rounded up to the same 0.5 kg step
- `shipping_quote_013 L47 1 -> 0` (constant): weights are > 0, so there is always at least one 0.5 kg step
- `tiered_pricing_010 L34 > -> >=` (comparison): a tier is only visited with units > 0, because the loop stops at the last tier used
- `tiered_pricing_010 L34 0 -> -1` (constant): a tier is only visited with units > 0, because the loop stops at the last tier used
- `tiered_pricing_010 L38 <= -> <` (comparison): on an exact bound the next tier gets 0 units, which `if units > 0` skips
