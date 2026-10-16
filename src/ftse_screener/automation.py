"""UTC Actions triggers; calendar decisions in Europe/London, not runner time."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def report_reason(data, now):
    local = now.astimezone(ZoneInfo('Europe/London'))
    if local.weekday() == 0:
        return 'weekly'
    buffer = data['policy']['cutoff_buffer_days']
    for stock in data['stocks']:
        execution = stock.get('execution', {})
        if 'cutoff' not in execution:
            continue
        cutoff = datetime.fromisoformat(execution['cutoff'])
        if cutoff.tzinfo is None:
            raise ValueError('cutoff requires UTC offset')
        due = cutoff.astimezone(ZoneInfo('Europe/London')) - timedelta(days=buffer)
        if local.date() == due.date():
            return 'monthly cutoff review'
    return None
