import logging
import ccxt
import sqlite3
from pathlib import Path
import time
from  datetime import datetime, timedelta

from cryptoadvance.specter.services.service import Service, devstatus_alpha
from flask_apscheduler import APScheduler

logger = logging.getLogger(__name__)

objects = {"aax":ccxt.aax(), "ascendex": ccxt.ascendex(),"bequant":ccxt.bequant(), "bibox":ccxt.bibox(), "bigone":ccxt.bigone(), "binance":ccxt.binance(), "bitbank":ccxt.bitbank(), "liquid":ccxt.liquid(), "phemex":ccxt.phemex(), "bitstamp":ccxt.bitstamp(), "ftx":ccxt.ftx()}
exchanges = ["bitstamp", "ascendex", "bequant", "bibox","bigone"]
def is_ms(timestamp):
    if timestamp % 1000 == 0:
        return True
    return False

def get_supported_pair_for(currency, exchange):
    result = ''
    exchange.load_markets()
    market_ids_found = [market for market in exchange.markets_by_id.keys() if ((market[:len('BTC')].upper() == 'BTC' or market[:len('XBT')].upper() == 'XBT') and market[-len(currency):].upper() == currency.upper())]
    if market_ids_found:
        market_id = market_ids_found[0]
        market = exchange.markets_by_id[exchange.market_id(market_id)] 
        if market:  
            result = market['symbol']
    return result
                    
class SpotbitService(Service):
    id = "spotbit"
    name = "Spotbit"
    icon = "spotbit/img/spotbit_avatar.jpg"
    logo = "spotbit/img/logo.jpeg"
    desc = "Price Info Service"
    has_blueprint = True
    blueprint_module = "ahv15.specterext.spotbit.controller"
    devstatus = devstatus_alpha
    isolated_client = False
    sort_priority = 2

    SPECTER_WALLET_ALIAS = "wallet"
    
    def callback_after_serverpy_init_app(self, scheduler: APScheduler):
        path = Path("./sb.db")
        
        def request(ex_objs):
            with scheduler.app.app_context():
                tic = time.perf_counter()
                currencies      = ["usd", "gbp", "jpy", "usdt", "eur", "0xcafebabe"]
                interval = 5
                db_n = sqlite3.connect(path, timeout=30)
                cursor = db_n.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                if(cursor.fetchall() == []):
                    return
                for e in exchanges:
                    for curr in currencies:
                            ticker = get_supported_pair_for(curr, ex_objs[e])
                            if(ticker == ''):
                                continue
                            success = True
                            if ex_objs[e].has['fetchOHLCV']:
                                candle = None
                                tframe = '1m'
                                lim = 1000
                                if e == "bleutrade" or e == "btcalpha" or e == "rightbtc" or e == "hollaex":
                                    tframe = '1h'
                                if e == "poloniex":
                                    tframe = '5m'
                                if e == "bitstamp":
                                    lim = 1000
                                if e == "bybit":
                                    lim = 200
                                if e == "eterbase":
                                    lim = 1000000
                                if e == "exmo":
                                    lim = 3000
                                if e == "btcalpha":
                                    lim = 720
                                if e == "bitfinex":
                                    params = {'limit':100, 'start':(round((datetime.now()-timedelta(hours=1)).timestamp()*1000)), 'end':round(datetime.now().timestamp()*1000)}
                                    try:
                                        candle = ex_objs[e].fetch_ohlcv(symbol=ticker, timeframe=tframe, since=None, params=params)
                                        if candle == None:
                                            raise Exception(f"candle from {e} is null")
                                        
                                    except Exception as err: #figure out this error type
                                        #the point so far is to gracefully handle the error, but waiting for the next cycle should be good enough
                                        if "does not have" not in str(err):
                                            print(f"error fetching candle: {e} {curr} {err}")
                                        success = False
                                else:
                                    try:
                                        candle = ex_objs[e].fetch_ohlcv(symbol=ticker, timeframe=tframe, since=None, limit=lim) #'ticker' was listed as 'symbol' before | interval should be determined in the config file
                                        if candle == None:
                                            raise Exception(f"candle from {e} is nulll")
                                    except Exception as err:
                                        print(err)
                                        if "does not have" not in str(err):
                                            print(f"error fetching candle: {e} {curr} {err}")
                                        success = False
                                if success:
                                    for line in candle:
                                        ts = datetime.fromtimestamp(line[0]/1e3) #check here if we have a ms timestamp or not
                                        for l in line:
                                            if l == None:
                                                l = 0
                                        statement = "INSERT INTO {} (timestamp, datetime, pair, open, high, low, close, volume) VALUES ({}, '{}', '{}', {}, {}, {}, {}, {});".format(e, line[0], ts, ticker, line[1], line[2], line[3], line[4], line[5])
                                        try:
                                            db_n.execute(statement)
                                            db_n.commit()

                                        except sqlite3.OperationalError as op:
                                            nulls = []
                                            c = 0
                                            for l in line:
                                                if l == None:
                                                    nulls.append(c)
                                                    c += 1
                                            print(f"exchange: {e} currency: {curr}\nsql statement: {statement}\nerror: {op}(moving on)")
                            else:
                                try:
                                    price = ex_objs[e].fetch_ticker(ticker)
                                except Exception as err:
                                    print(f"error fetching ticker: {err}")
                                    success = False
                                if success:
                                    ts = None
                                    try:
                                        if is_ms(int(price['timestamp'])):
                                            ts = datetime.fromtimestamp(int(price['timestamp'])/1e3)
                                        else:
                                            ts = datetime.fromtimestamp(int(price['timestamp']))
                                    except OverflowError as oe:
                                        print(f"{oe} caused by {ts}")
                                    ticker = ticker.replace("/", "-")
                                    statement = f"INSERT INTO {e} (timestamp, datetime, pair, open, high, low, close, volume) VALUES ({price['timestamp']}, '{ts}', '{ticker}', 0.0, 0.0, 0.0, {price['last']}, 0.0);"
                                    db_n.execute(statement)
                                    db_n.commit()
                            time.sleep(interval)
                toc = time.perf_counter()
                print(f"It took {toc - tic:0.4f} seconds")
    
        
        
        
        def prune(keepWeeks):
            with scheduler.app.app_context():
                db_n = sqlite3.connect(path, timeout=10)
                for exchange in exchanges:
                    check = f"SELECT MAX(timestamp) FROM {exchange};"
                    cursor = db_n.execute(check)
                    check_ts = cursor.fetchone()
                    statement = ""
                    if check_ts[0] is not None:
                        if is_ms(int(check_ts[0])):
                            cutoff = (datetime.now()-timedelta(weeks=int(keepWeeks))).timestamp()*1000
                            statement = f"DELETE FROM {exchange} WHERE timestamp < {cutoff};"
                        else:
                            cutoff = (datetime.now()-timedelta(weeks=int(keepWeeks))).timestamp()
                            statement = f"DELETE FROM {exchange} WHERE timestamp < {cutoff};"
                        while True:
                            try:
                                db_n.execute(statement)
                                break
                            except sqlite3.OperationalError as op:
                                print(f"{op}")
                        db_n.commit()
                                
        scheduler.add_job("prune", prune, trigger = 'interval', args = [10], minutes = 1)
        scheduler.add_job("request", request, trigger = 'interval', args =[objects], minutes = 15)
        self.scheduler = scheduler

 
    @classmethod
    def init_table(cls):
        p = Path("./sb.db")
        db = sqlite3.connect(p)
        for exchange in exchanges:
            sql = f"CREATE TABLE IF NOT EXISTS {exchange} (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp INTEGER, datetime TEXT, pair TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL)"
            print(f"created table for {exchange}")
            db.execute(sql)
            db.commit()
        db.close()

    @classmethod
    def current_exchange_rate(cls, currency, exchange):
        p = Path("./sb.db")
        db_n = sqlite3.connect(p, timeout=30)
        ticker = get_supported_pair_for(currency, objects[exchange])
        print(ticker)
        if exchange in exchanges:
            statement = f"SELECT * FROM {exchange} WHERE pair = '{ticker}' ORDER BY timestamp DESC LIMIT 1;"
            try:
                cursor = db_n.execute(statement)
                res = cursor.fetchone()
            except sqlite3.OperationalError:
                print("database is locked. Cannot access it")
                return {'err': 'database locked'}
            if res != None:
                db_n.close()
                return {'id':res[0], 'timestamp':res[1], 'datetime':res[2], 'currency_pair':res[3], 'open':res[4], 'high':res[5], 'low':res[6], 'close':res[7], 'vol':res[8]}