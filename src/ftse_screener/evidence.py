"""Apply explicit, dated issuer-source reviews, never a sector-based PFIC clearance."""
def apply_reviews(data):
    reviews = data.get('security_reviews', {})
    for stock in data['stocks']:
        review = reviews.get(stock['isin'])
        if not review or stock.get('gate_evidence'):
            continue
        if review['ticker'] != stock['ticker'] or stock['security_type'] in ('investment_trust','etf','fund','reit'):
            continue
        stock['security_type'] = review['security_type']
        stock['gate_evidence'] = {key:value for key,value in review.items() if key not in ('ticker','security_type')}
