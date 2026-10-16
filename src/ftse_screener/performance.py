"""Price-only trailing returns from HL's public paginated performance table."""
from html.parser import HTMLParser
from urllib.parse import urljoin

from .engine import number
from .hl import BASE

PERFORMANCE = BASE + '/performance'


class PerformanceParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self.pages = [], set()
        self.row = self.cell = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'tr':
            self.row = []
        elif tag in ('td', 'th') and self.row is not None:
            self.cell = []
        elif tag == 'a':
            url = urljoin(PERFORMANCE, attrs.get('href',''))
            if url.startswith(PERFORMANCE+'?page=') and url[len(PERFORMANCE+'?page='):].isdigit():
                self.pages.add(url)

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in ('td','th') and self.row is not None and self.cell is not None:
            self.row.append(' '.join(''.join(self.cell).split()))
            self.cell = None
        elif tag == 'tr' and self.row is not None:
            self.rows.append(self.row)
            self.row = self.cell = None


def parse_performance(html, source, observed):
    parser = PerformanceParser()
    parser.feed(html)
    results = {}
    for row in parser.rows:
        if len(row) != 10 or row[0] in ('EPIC', ''):
            continue
        metrics = {}
        for index, name in [(6,'price_return_1y'),(8,'price_return_3y'),(9,'price_return_5y')]:
            raw = row[index].replace('%','').replace(',','').replace('−','-').strip()
            if raw.lower() in ('n/a','-',''):
                continue
            try:
                value = number(raw)
            except (ValueError, ArithmeticError):
                raise ValueError(f'Invalid HL performance value for {row[0]}: {raw}') from None
            # Large losses may reflect unadjusted redenominations, splits or corporate actions.
            if value <= -90:
                continue
            metrics[name] = dict(value=str(value), date=observed.isoformat(),source=source,
                                 basis='HL trailing cumulative price return (%), previous close; dividends excluded')
        if row[0] in results:
            raise ValueError('Duplicate performance ticker')
        results[row[0]] = metrics
    return results, parser.pages


def fetch_performance(get, pause, observed):
    pending, visited, results = {PERFORMANCE}, set(), {}
    while pending:
        url = min(pending)
        pending.remove(url)
        if url in visited:
            continue
        if len(visited) >= 10:
            raise ValueError('Unexpected performance pagination')
        rows, pages = parse_performance(get(url),url,observed)
        if set(rows) & set(results):
            raise ValueError('Repeated HL performance page/tickers')
        results.update(rows)
        visited.add(url)
        pending.update(pages-visited)
        pause(1)
    if not 300 <= len(results) <= 400:
        raise ValueError(f'Incomplete performance table: {len(results)} securities')
    return results
