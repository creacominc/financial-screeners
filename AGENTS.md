# Contributor instructions

## Scope

This project compares conventional UK gilts bought at a supplied clean offer price and held to maturity. Do not add web scraping until it is explicitly requested. Do not silently extend calculations to index-linked gilts, strips, corporate bonds, or tax advice.

## Financial calculation conventions

1. Use `Decimal` from input parsing through every money, price, rate, quantity, cash-flow, profit, and yield calculation. Never introduce binary `float` into financial logic. Conversion for a presentation-only Excel cell is permitted after the result is final.
2. Prices and redemption values are quoted per £100 nominal. `coupon_rate` is an annual percentage (for example `0.375`, not `0.00375`). Conventional coupons are paid semi-annually, so each coupon is annual coupon divided by two.
3. Construct the regular coupon schedule backwards from maturity in six-month calendar increments. Coupon cash flows must be strictly after settlement. Redemption occurs on maturity.
4. Accrued interest uses Actual/Actual within the coupon period: semi-annual coupon × actual elapsed days / actual days in that coupon period. The dirty price is clean price plus accrued interest.
5. The initial cash outflow is dirty consideration plus the configured dealing fee. Round nominal purchased down to £0.01 so it fits the user budget. Report unused cash and calculate yield on cash actually deployed.
6. Total proceeds are remaining gross coupons plus redemption. Total cash profit is total proceeds less dirty consideration and dealing fee.
7. Report gross coupon income separately. Report the redemption gain as redemption proceeds minus clean consideration; label it as the conventional-gilt UK CGT-exempt redemption gain. Accrued interest and dealing fees remain costs in total profit and must not be mislabelled as redemption gain.
8. Net annualised return means the annual effective money-weighted yield after the dealing fee and before personal income tax. Solve from dated cash flows using Actual/365 exponents. Do not describe it as a tax-adjusted return.
9. The current model assumes cum-dividend settlement and regular coupons. Any implementation of UK ex-dividend entitlement, irregular coupons, holiday settlement rules, or special gilt terms must be explicit, documented, and tested against an authoritative example.

## Testing requirements

Every change to a financial formula, schedule, rounding rule, input convention, or report field requires automated tests. At minimum preserve tests for coupon scheduling, coupon-date accrued interest, mid-period accrued interest, dirty price, affordability rounding, fee inclusion, remaining cash flows, redemption gain separation, total profit, annualised yield, report ordering, and invalid inputs.

Run the full suite with `pytest`. A financial calculation change is not complete while any test is failing or while its new behavior lacks a focused test.
