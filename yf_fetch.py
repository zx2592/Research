import yfinance as yf
import sys
import json

ticker = sys.argv[1]
stock = yf.Ticker(ticker)

info = stock.info
financials = stock.financials
cashflow = stock.cashflow

res = {
    "info": {k: info.get(k) for k in ["longName", "sector", "industry", "marketCap", "forwardPE", "trailingPE", "pegRatio", "priceToBook", "enterpriseToEbitda", "totalRevenue", "revenueGrowth", "operatingMargins", "netIncomeToCommon", "trailingEps", "forwardEps", "dividendYield", "currentPrice", "targetMeanPrice", "recommendationKey", "numberOfAnalystOpinions"]},
    "financials_keys": list(financials.index) if not financials.empty else [],
    "cashflow_keys": list(cashflow.index) if not cashflow.empty else []
}

if not financials.empty:
    res["financials"] = financials.iloc[:, :4].rename(columns=lambda x: str(x)).to_dict()
if not cashflow.empty:
    res["cashflow"] = cashflow.iloc[:, :4].rename(columns=lambda x: str(x)).to_dict()

print(json.dumps(res, default=str))
