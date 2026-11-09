from . import db

# A deliberately lumpy book: mega caps, a couple of PSUs, mid-cap manufacturers,
# and a few names that file constantly (Adani, Eternal) so the digest has something to filter.
DEFAULT_PORTFOLIO = [
    {"symbol": "RELIANCE", "name": "Reliance Industries", "sector": "Conglomerate", "weight": 9},
    {"symbol": "HDFCBANK", "name": "HDFC Bank", "sector": "Banks", "weight": 9},
    {"symbol": "TCS", "name": "Tata Consultancy Services", "sector": "IT services", "weight": 7},
    {"symbol": "BHARTIARTL", "name": "Bharti Airtel", "sector": "Telecom", "weight": 7},
    {"symbol": "LT", "name": "Larsen & Toubro", "sector": "Infra / E&C", "weight": 6},
    {"symbol": "BAJFINANCE", "name": "Bajaj Finance", "sector": "NBFC", "weight": 6},
    {"symbol": "SUNPHARMA", "name": "Sun Pharmaceutical", "sector": "Pharma", "weight": 5},
    {"symbol": "MARUTI", "name": "Maruti Suzuki", "sector": "Autos", "weight": 5},
    {"symbol": "TITAN", "name": "Titan Company", "sector": "Consumer", "weight": 5},
    {"symbol": "ASIANPAINT", "name": "Asian Paints", "sector": "Consumer", "weight": 4},
    {"symbol": "COALINDIA", "name": "Coal India", "sector": "PSU / Mining", "weight": 5},
    {"symbol": "HAL", "name": "Hindustan Aeronautics", "sector": "PSU / Defence", "weight": 5},
    {"symbol": "ETERNAL", "name": "Eternal (Zomato)", "sector": "Internet", "weight": 5},
    {"symbol": "ADANIENT", "name": "Adani Enterprises", "sector": "Conglomerate", "weight": 3},
    {"symbol": "DIXON", "name": "Dixon Technologies", "sector": "EMS", "weight": 4},
    {"symbol": "POLYCAB", "name": "Polycab India", "sector": "Cables", "weight": 4},
    {"symbol": "DEEPAKNTR", "name": "Deepak Nitrite", "sector": "Chemicals", "weight": 3},
    {"symbol": "KPITTECH", "name": "KPIT Technologies", "sector": "IT services", "weight": 3},
]

# Off-book names for the research demo. Nothing in the engine is specific to these.
RESEARCH_DEMO = ["TRENT", "PERSISTENT", "CDSL", "KAYNES"]


def get_portfolio():
    return db.kv_get("portfolio", DEFAULT_PORTFOLIO)


def symbols():
    return [p["symbol"] for p in get_portfolio()]


def weight_of(symbol):
    for p in get_portfolio():
        if p["symbol"] == symbol:
            return p["weight"]
    return 0


def name_of(symbol):
    for p in get_portfolio():
        if p["symbol"] == symbol:
            return p["name"]
    return symbol
