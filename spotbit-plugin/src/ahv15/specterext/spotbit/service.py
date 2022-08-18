import logging
import ccxt as ccxt
import ccxt.async_support as ccxt_async
import sqlite3
from pathlib import Path
import time
from  datetime import datetime, timedelta
import asyncio
from asyncio import gather
import threading
import itertools

from cryptoadvance.specter.services.service import Service, devstatus_alpha
from flask_apscheduler import APScheduler

logger = logging.getLogger(__name__)
path = Path("./sb.db")
path_hist = Path("./sb_hist.db")


# https://stackoverflow.com/a/58616001

class EventLoopThread(threading.Thread):
    loop = None
    _count = itertools.count(0)

    def __init__(self):
        self.started = threading.Event()
        name = f"{type(self).__name__}-{next(self._count)}"
        super().__init__(name=name, daemon=True)

    def run(self):
        self.loop = loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.call_later(0, self.started.set)

        try:
            loop.run_forever()
        finally:
            try:
                shutdown_asyncgens = loop.shutdown_asyncgens()
            except AttributeError:
                pass
            else:
                loop.run_until_complete(shutdown_asyncgens)
            try:
                shutdown_executor = loop.shutdown_default_executor()
            except AttributeError:
                pass
            else:
                loop.run_until_complete(shutdown_executor)
            asyncio.set_event_loop(None)
            loop.close()

_lock = threading.Lock()
_loop_thread = None

def get_event_loop():
    global _loop_thread
    if _loop_thread is None:
        with _lock:
            if _loop_thread is None:
                _loop_thread = EventLoopThread()
                _loop_thread.start()
                _loop_thread.started.wait(1)

    return _loop_thread.loop

def run_coroutine(coro):
    return asyncio.run_coroutine_threadsafe(coro, get_event_loop())

objects = {"aax":ccxt.aax(), "ascendex": ccxt.ascendex(),"bequant":ccxt.bequant(), "bibox":ccxt.bibox(), "bigone":ccxt.bigone(), "binance":ccxt.binance(), "bitbank":ccxt.bitbank(), "liquid":ccxt.liquid(), "phemex":ccxt.phemex(), "bitstamp":ccxt.bitstamp(), "ftx":ccxt.ftx()}
async_objects = {"aax":ccxt_async.aax(), "ascendex": ccxt_async.ascendex(),"bequant":ccxt_async.bequant(), "bibox":ccxt_async.bibox(), "bigone":ccxt_async.bigone(), "binance":ccxt_async.binance(), "bitbank":ccxt_async.bitbank(), "liquid":ccxt_async.liquid(), "phemex":ccxt_async.phemex(), "bitstamp":ccxt_async.bitstamp(), "ftx":ccxt_async.ftx()}
exchanges = ["binance", "ascendex", "bequant", "bibox","bigone", "bitstamp"]
historicalExchanges = ["bitstamp"]

def is_ms(timestamp):
    if timestamp % 1000 == 0:
        return True
    return False

def get_supported_pair_for(currency, exchange):
    result = ''
    exchange.load_markets()
    market_ids_found = [market for market in exchange.markets_by_id.keys() if ((market[:len('BTC')].upper() == 'BTC' or market[:len('XBT')].upper() == 'XBT') and market[-len(currency):].upper() == currency.upper() and len(market) == (3 + len(currency)))]
    if market_ids_found:
        market_id = market_ids_found[0]
        market = exchange.markets_by_id[exchange.market_id(market_id)] 
        if market:  
            result = market['symbol']
    return result

async def fetch_ohlcv(exchange, symbol, timeframe, limit, exchange_name):
    since = None
    try:
        ohlcv = await exchange.fetch_ohlcv(symbol, timeframe, since, limit)
        if len(ohlcv):
            return [exchange_name, symbol, ohlcv]
    except Exception as e:
        print(type(e).__name__, str(e))


def request_history(objects, exchange, currency, start_date, end_date, frequencies):
    db_n = sqlite3.connect(path_hist, timeout=10)
    cur = db_n.cursor()
    ticker = get_supported_pair_for(currency, objects[exchange])
    while start_date < end_date:
        params = {'start': start_date, 'end': int(end_date)}
        tick = objects[exchange].fetch_ohlcv(symbol=ticker, timeframe='1m', params=params, limit = 1000)
        records = []
        dt = None
        for line in tick:
            dt = None
            try:
                if is_ms(int(line['timestamp'])):
                    dt = datetime.fromtimestamp(line['timestamp'] / 1e3)
                else:
                    dt = datetime.fromtimestamp(line['timestamp'])
                records.append([line['timestamp'], dt, ticker, 0.0, 0.0, 0.0, line['last'], 0.0])
            except TypeError:
                if line[0] % 1000 == 0:
                    dt = datetime.fromtimestamp(line[0] / 1e3)
                else:
                    dt = datetime.fromtimestamp(line[0])
                records.append([line[0], dt, ticker, line[1], line[2], line[3], line[4], line[5]])
        statement = f"INSERT INTO {exchange} (timestamp, datetime, pair, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?, ?);"
        cur.executemany(statement, records)
        db_n.commit()
        l = len(tick)
        end_date = int(datetime.timestamp(datetime.fromtimestamp(end_date) - timedelta(minutes=l)))

def request_history_periodically(histExchanges, frequencies):
    history_threads = []
    historyEnd = 0
    for h in histExchanges:
        hThread = threading.Thread(target=request_history, args=(objects, h, "USD", historyEnd, datetime.now().timestamp(), frequencies))
        hThread.start()
        history_threads.append(hThread)
    return history_threads

async def request(exchanges, currencies):
    while True:
        loops = []
        for e in exchanges:
            for curr in currencies:
                    if(currencies == "None"):
                        continue
                    ticker = get_supported_pair_for(curr, objects[e])
                    if(ticker == ''):
                        continue
                    if async_objects[e].has['fetchOHLCV']:
                        tframe = '1m'
                        lim = 1
                        if e == "bleutrade" or e == "btcalpha" or e == "rightbtc" or e == "hollaex":
                            tframe = '1h'
                        if e == "poloniex":
                            tframe = '5m'
                        try:
                            loops.append(fetch_ohlcv(async_objects[e], ticker, tframe, lim, e))
                        except Exception as err:
                            if "does not have" not in str(err):
                                print(f"error fetching candle: {e} {curr} {err}")
        responses = await gather(*loops)
        db_n = sqlite3.connect(path, timeout=30)
        cursor = db_n.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        if(cursor.fetchall() == []):
            continue
        for response in responses:
            datetime_ = []
            for line in response[2]:
                datetime_.append(datetime.fromtimestamp(line[0]/1e3)) #check here if we have a ms timestamp or not
                for l in line:
                    if l == None:
                        l = 0
            statement = "INSERT INTO {} (timestamp, datetime, pair, open, high, low, close, volume) VALUES ({}, '{}', '{}', {}, {}, {}, {}, {});".format(response[0], response[2][0][0], datetime_, response[1], response[2][0][1], response[2][0][2], response[2][0][3], response[2][0][4], response[2][0][5])
            db_n.execute(statement)
            db_n.commit()
        for each_exchange in async_objects.values():
            await each_exchange.close()
        await asyncio.sleep(60)
                    
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

        def prune(start_date):
            with scheduler.app.app_context():
                db_n = sqlite3.connect(path, timeout=10)
                for exchange in exchanges:
                    check = f"SELECT MAX(timestamp) FROM {exchange};"
                    cursor = db_n.execute(check)
                    check_ts = cursor.fetchone()
                    statement = ""
                    if check_ts[0] is not None:
                        statement = f"DELETE FROM {exchange} WHERE timestamp < {start_date};"
                        try:
                            db_n.execute(statement)
                            break
                        except sqlite3.OperationalError as op:
                            print(f"{op}")
                        db_n.commit()
                        
        scheduler.add_job("prune", prune, trigger = 'interval', args = [0], minutes = 1)
        self.scheduler = scheduler                   

 
    @classmethod
    def init_table(cls, exchanges, currencies, frequencies):
        p = Path("./sb.db")
        db = sqlite3.connect(p)
        for exchange in exchanges:
            if(exchange == "None"):
                continue
            sql = f"CREATE TABLE IF NOT EXISTS {exchange} (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp INTEGER, datetime TEXT, pair TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL)"
            print(f"created table for {exchange}")
            db.execute(sql)
            db.commit()
        db.close()
        
        p = Path("./sb_hist.db")
        db = sqlite3.connect(p)
        for exchange in historicalExchanges:
            sql = f"CREATE TABLE IF NOT EXISTS {exchange} (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp INTEGER, datetime TEXT, pair TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL)"
            print(f"created table for {exchange}")
            db.execute(sql)
            db.commit()
        db.close()
        
        run_coroutine(request(exchanges, currencies))
        request_history_periodically(historicalExchanges, frequencies)

    @classmethod
    def current_exchange_rate(cls, currency, exchange):
        p = Path("./sb.db")
        db_n = sqlite3.connect(p, timeout=5)
        exchange = 'binance'
        currency = 'usdt'
        ticker = get_supported_pair_for(currency, objects[exchange])
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
            
            
            
    @classmethod
    def historical_exchange_rate(cls, currency, exchange, date_start, date_end):
        p = Path("./sb_hist.db")
        db_n = sqlite3.connect(p, timeout=5)
        ticker = get_supported_pair_for(currency, objects[exchange])
        if (str(date_start)).isdigit():
            date_s = int(date_start)
            date_e = int(date_end)
        else:
            #error checking for malformed dates
            try:
                date_s = (datetime.fromisoformat(date_start.replace("T", " "))).timestamp()*1000
                date_e = (datetime.fromisoformat(date_end.replace("T", " "))).timestamp()*1000
            except Exception:
                return "malformed dates. Provide both dates in the same format: use YYYY-MM-DDTHH:mm:SS or millisecond timestamps"
        check = f"SELECT timestamp FROM {exchange} ORDER BY timestamp DESC LIMIT 1;"
        cursor = db_n.execute(check)
        statement = ""
        ts = cursor.fetchone()
        if ts != None and is_ms(int(ts[0])):
            statement = f"SELECT * FROM {exchange} WHERE timestamp > {date_s} AND timestamp < {date_e} AND pair = '{ticker}' ORDER BY timestamp DESC;"
        else:
            # for some exchanges we cannot use ms precision timestamps (such as coinbase)
            date_s /= 1e3
            date_e /= 1e3
            statement = f"SELECT * FROM {exchange} WHERE timestamp > {date_s} AND timestamp < {date_e} AND pair = '{ticker}';"
        # keep trying in case of database locked error
        while True:
            try:
                cursor = db_n.execute(statement)
                break
            except sqlite3.OperationalError as oe:
                time.sleep(5)
            
        res = cursor.fetchall()
        db_n.close()
        return {'columns': ['id', 'timestamp', 'datetime', 'currency_pair', 'open', 'high', 'low', 'close', 'vol'], 'data':res}