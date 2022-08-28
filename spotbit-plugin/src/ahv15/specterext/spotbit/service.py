import logging
import ccxt as ccxt
import sqlite3
from pathlib import Path
import time
from  datetime import datetime, timedelta
import threading
from threading import Event
import os

from cryptoadvance.specter.services.service import Service, devstatus_alpha

logger = logging.getLogger(__name__)
path = Path("./sb.db")
path_hist = Path("./sb_hist.db")



objects = {"bitstamp":ccxt.bitstamp(), "bitfinex":ccxt.bitfinex(), "coinbase":ccxt.coinbase(), "kraken":ccxt.kraken(), "okcoin":ccxt.okcoin()}
exchanges = ['bitstamp', 'coinbase', 'kraken', 'bitfinex', 'okcoin']
currencies = ['usd', 'eur']
history_threads = []
event = "None"
chosen_exchanges = []
chosen_currencies = {}
frequency_config = 0
start_date_config = 0

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

def clear_threads(event):
    if (event != "None"):
        event.set()
    
    
def request_history(objects, exchange, currency, start_date, end_date, frequency, event):
    db_n = sqlite3.connect(path_hist, timeout=10)
    cur = db_n.cursor()
    ticker = get_supported_pair_for(currency, objects[exchange])
    true_end_date = end_date
    while(True):
        while start_date < end_date:
            if event.is_set():
                return
            params = {'start': int(start_date), 'end': int(end_date)}
            tick = objects[exchange].fetch_ohlcv(symbol=ticker, timeframe=frequency, params=params, limit = 1000)
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
        time.sleep(60)
        start_date = true_end_date
        end_date = datetime.now().timestamp()
        true_end_date = end_date

def request_history_periodically(histExchanges, currencies, frequency, start_date,  event):
    for h in histExchanges:
        for currency in currencies[h]:
            hThread = threading.Thread(target=request_history, args=(objects, h, currency, int(start_date), datetime.now().timestamp(), frequency, event))
            hThread.start()
            history_threads.append(hThread)
    return history_threads


def request_periodically(exchanges, currencies, event):
    thread = threading.Thread(target=request, args=(exchanges, currencies, event))
    thread.start()
    return thread

def request(exchanges, currencies, event):
    while True:
        if event.is_set():
            break
        candles = []
        for e in exchanges:
            for curr in currencies[e]:
                    if(currencies == "None"):
                        continue
                    ticker = get_supported_pair_for(curr, objects[e])
                    if(ticker == ''):
                        continue
                    if objects[e].has['fetchOHLCV']:
                        tframe = '1m'
                        lim = 1
                        try:
                            candles.append([e, ticker, objects[e].fetch_ohlcv(symbol=ticker, timeframe=tframe, since=None, limit=lim)])
                        except Exception as err:
                            if "does not have" not in str(err):
                                print(f"error fetching candle: {e} {curr} {err}")
                    else:
                        print("check4")
                        try:
                            price = objects[e].fetch_ticker(ticker)
                            print("check")
                            print(price)
                            candles.append(e, ticker, [[price['timestamp'], 0.0, 0.0, 0.0, price['last'], 0.0]])
                        except Exception as err:
                            print(f"error fetching ticker: {err}")
        db_n = sqlite3.connect(path, timeout=30)
        cursor = db_n.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        if(cursor.fetchall() == []):
            continue
        for response in candles:
            datetime_ = []
            ts = None
            try:
                if is_ms(int(response[2][0][0])):
                    datetime_ = datetime.fromtimestamp(int(response[2][0][0])/1e3)
                else:
                    datetime_ = datetime.fromtimestamp(int(response[2][0][0]))
            except OverflowError as oe:
                print(f"{oe} caused by {ts}")
            for l in response[2][0]:
                if l == None:
                    l = 0
            statement = "INSERT INTO {} (timestamp, datetime, pair, open, high, low, close, volume) VALUES ({}, '{}', '{}', {}, {}, {}, {}, {});".format(response[0], response[2][0][0], datetime_, response[1], response[2][0][1], response[2][0][2], response[2][0][3], response[2][0][4], response[2][0][5])
            db_n.execute(statement)
            db_n.commit()
        time.sleep(60)
                    
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

    @classmethod
    def init_table(cls, exchanges, currencies, frequency, start_date):
        global event
        global frequency_config
        global start_date_config        
        p = Path("./sb.db")
        db = sqlite3.connect(p)
        for exchange in exchanges:
            if(exchange == "None"):
                continue
            if (exchange not in chosen_exchanges):
                chosen_exchanges.append(exchange)
            sql = f"CREATE TABLE IF NOT EXISTS {exchange} (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp INTEGER, datetime TEXT, pair TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL)"
            print(f"created table for {exchange}")
            db.execute(sql)
            db.commit()
        db.close()
        
        p = Path("./sb_hist.db")
        db = sqlite3.connect(p)
        for exchange in exchanges:
            sql = f"CREATE TABLE IF NOT EXISTS {exchange} (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp INTEGER, datetime TEXT, pair TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL)"
            print(f"created table for {exchange}")
            db.execute(sql)
            db.commit()
        db.close()
        
        for exchange in exchanges:
            if(exchange == "None"):
                continue
            for currency in currencies:
                if(currency == "None"):
                    continue
                if(chosen_currencies.__contains__(exchange)):
                    if(currency not in chosen_currencies[exchange]):
                        chosen_currencies[exchange].append(currency)
                else:
                    chosen_currencies[exchange] = [currency]
        
        clear_threads(event)
        event = Event()
        frequency_config = frequency
        start_date_config = start_date
        request_periodically(chosen_exchanges, chosen_currencies, event)
        if(start_date != "None" and frequency != "None"):
            request_history_periodically(chosen_exchanges, chosen_currencies, frequency, start_date, event)

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
            date_s /= 1e3
            date_e /= 1e3
            statement = f"SELECT * FROM {exchange} WHERE timestamp > {date_s} AND timestamp < {date_e} AND pair = '{ticker}';"
        while True:
            try:
                cursor = db_n.execute(statement)
                break
            except sqlite3.OperationalError as oe:
                time.sleep(5)
        res = cursor.fetchall()
        db_n.close()
        return {'columns': ['id', 'timestamp', 'datetime', 'currency_pair', 'open', 'high', 'low', 'close', 'vol'], 'data':res}
    
    
    @classmethod
    def status_info(cls):
        p = Path("./sb.db")
        status_info = []
        db_n = sqlite3.connect(p, timeout=5)
        info_check = False
        for exchange in chosen_exchanges:
            for currency in chosen_currencies[exchange]:
                ticker = get_supported_pair_for(currency, objects[exchange])
                if(ticker == '') :
                    status_info.append([exchange, currency, 'Not Available'])
                else:
                    try:
                        statement = f"SELECT * FROM {exchange} WHERE pair = '{ticker}' ORDER BY timestamp DESC LIMIT 1;"
                        cursor = db_n.execute(statement)
                        res = cursor.fetchone()
                    except sqlite3.OperationalError:
                        status_info.append([exchange, currency, 'Syncing'])
                        info_check = True
                    if res != None:
                        difference = (datetime.now() - datetime.strptime(res[2], '%Y-%m-%d %H:%M:%S')).total_seconds()
                        if(difference < 300):
                            status_info.append([exchange, currency, 'Updated'])
                        else:
                            status_info.append([exchange, currency, 'Syncing'])
                    else:
                        if(not info_check):
                            status_info.append([exchange, currency, 'Syncing'])
                        else:
                            info_check = False
        db_n.close()
        
        
        p = Path("./sb_hist.db")
        db_n = sqlite3.connect(p, timeout=5)
        info_check = False
        for exchange in chosen_exchanges:
            for currency in chosen_currencies[exchange]:
                ticker = get_supported_pair_for(currency, objects[exchange])
                if(ticker == '') :
                    status_info.append([exchange, currency, 'Not Available'])
                else:
                    try:
                        statement = f"SELECT * FROM {exchange} WHERE pair = '{ticker}' ORDER BY timestamp ASC LIMIT 1;"
                        cursor = db_n.execute(statement)
                        res = cursor.fetchone()
                    except sqlite3.OperationalError:
                        status_info.append([exchange, currency, 'Historical Data is Syncing'])
                        info_check = True
                    if res != None:
                        difference = (datetime.fromtimestamp(start_date_config) - datetime.strptime(res[2], '%Y-%m-%d %H:%M:%S')).total_seconds()
                        if(abs(difference) < 300):
                            status_info.append([exchange, currency, 'Historical Data is Updated'])
                        else:
                            status_info.append([exchange, currency, 'Historical Data is Syncing'])
                    else:
                        if(not info_check):
                            status_info.append([exchange, currency, 'Historical Data is Syncing'])
                        else:
                            info_check = False
        return status_info
    
    @classmethod
    def remove_exchange(cls, info):
        global event
        global chosen_currencies
        clear_threads(event)
        event = Event()
        chosen_currencies[info[0].strip('\'')].remove(info[1].strip('\''))
        request_periodically(chosen_exchanges, chosen_currencies, event)
        request_history_periodically(chosen_exchanges, chosen_currencies, frequency_config, start_date_config, event)
        
    @classmethod
    def remove_db(cls):
        global event
        global chosen_currencies
        global chosen_exchanges
        clear_threads(event)
        event = Event()
        time.sleep(1)
        chosen_exchanges = []
        chosen_currencies = {}
        path = Path("./sb.db")
        path_hist = Path("./sb_hist.db")
        os.remove(path)
        os.remove(path_hist)
        
        