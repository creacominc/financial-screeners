"""Conservative eligibility gates; ratings refer to the issue, not its issuer."""
import calendar
from datetime import date

from .calculator import CorporateBond

MOODYS = ('Aaa', 'Aa1', 'Aa2', 'Aa3', 'A1', 'A2', 'A3', 'Baa1', 'Baa2', 'Baa3', 'Ba1', 'Ba2', 'Ba3', 'B1', 'B2', 'B3', 'Caa1', 'Caa2', 'Caa3', 'Ca', 'C')
SP = ('AAA', 'AA+', 'AA', 'AA-', 'A+', 'A', 'A-', 'BBB+', 'BBB', 'BBB-', 'BB+', 'BB', 'BB-', 'B+', 'B', 'B-', 'CCC+', 'CCC', 'CCC-', 'CC', 'C', 'SD', 'D')
SUPPORTED_TERMS = 'fixed_semiannual_noncallable_bullet_regular'


def maturity_limit(settlement: date, months: int) -> date:
    index = settlement.year * 12 + settlement.month - 1 + months
    year, month = divmod(index, 12)
    return date(year, month + 1, min(settlement.day, calendar.monthrange(year, month + 1)[1]))


def exclusion_reason(bond: CorporateBond, settlement: date, months: int = 24,
                     minimum_moodys: str = 'A2', minimum_sp: str = 'A-',
                     max_quote_age: int = 7, max_rating_age: int = 90) -> str:
    if not 1 <= months <= 24 or max_quote_age < 0 or max_rating_age < 0:
        raise ValueError('months must be 1..24 and age limits non-negative')
    if minimum_moodys not in MOODYS[:10] or minimum_sp not in SP[:10]:
        raise ValueError('minimum ratings must be investment grade')
    if bond.currency != 'USD' or bond.terms != SUPPORTED_TERMS or bond.coupon_rate <= 0:
        return 'Unsupported terms: require USD fixed semiannual noncallable regular bullet bond'
    if not settlement < bond.maturity_date <= maturity_limit(settlement, months):
        return 'Outside maturity window'
    if bond.price_settlement_date != settlement.isoformat():
        return 'Accrued interest/offer settlement date differs from requested settlement'
    for label, stamp, maximum in [('quote', bond.quote_date, max_quote_age), ('ratings', bond.ratings_date, max_rating_age)]:
        age = (settlement - date.fromisoformat(stamp)).days
        if age < 0 or age > maximum:
            return f'Stale or future {label} date'
    found = False
    for label, value, scale, minimum in [('Moody\'s', bond.moodys, MOODYS, minimum_moodys), ('S&P', bond.sp, SP, minimum_sp)]:
        if not value or value == 'NR':
            continue
        found = True
        if value not in scale:
            return f'Unknown {label} issue rating'
        if scale.index(value) > scale.index(minimum):
            return f'{label} issue rating below minimum'
    return '' if found else 'No recognised issue rating'
