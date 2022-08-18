from flask import redirect, render_template, request, url_for
from flask import current_app as app

from cryptoadvance.specter.specter import Specter
from .service import SpotbitService

from  datetime import datetime


spotbit_endpoint = SpotbitService.blueprint

def ext() -> SpotbitService:
    ''' convenience for getting the extension-object'''
    return app.specter.ext["spotbit"]

def specter() -> Specter:
    ''' convenience for getting the specter-object'''
    return app.specter


@spotbit_endpoint.route("/")
def index():
    return render_template(
        "spotbit/index.jinja",
    )
    
    
@spotbit_endpoint.route("/hist/<currency>/<exchange>/<date_start>/<date_end>")
def historical_exchange_rate(currency, exchange, date_start, date_end):
    service = ext()
    return(service.historical_exchange_rate(currency, exchange, date_start, date_end))

@spotbit_endpoint.route("/now/<currency>/<exchange>")
def current_exchange_rate(currency, exchange):
    service = ext()
    return(service.current_exchange_rate(currency, exchange))

@spotbit_endpoint.route("/settings", methods=["GET"])
def settings_get():
    return render_template(
        "spotbit/settings.jinja",
    )

@spotbit_endpoint.route("/settings", methods=["POST"])
def settings_post():
    print(request.values)
    exchange1 = request.form.get('exchange1', "None")
    exchange2 = request.form.get('exchange2', "None")
    exchange3 = request.form.get('exchange3', "None")
    exchange4 = request.form.get('exchange4', "None")
    currency1 = request.form.get('currency1', "None")
    currency2 = request.form.get('currency2', "None")
    currency3 = request.form.get('currency3', "None")
    currency4 = request.form.get('currency4', "None")
    start_date = request.form.get('start_date', "None")
    frequencies = request.form.get('frequencies', "None")
    service = ext()
    service.scheduler.scheduler.modify_job(job_id = 'prune', args = [datetime.timestamp(datetime. strptime(start_date, '%Y-%m-%d'))])
    service.init_table([exchange1, exchange2, exchange3, exchange4], [currency1, currency2, currency3, currency4], frequencies)
    '''
    user = app.specter.user_manager.get_user()
    if show_menu == "yes":
        user.add_service(SpotbitService.id)
    else:
        user.remove_service(SpotbitService.id)
    used_wallet_alias = request.form.get("used_wallet")
    if used_wallet_alias != None:
        wallet = current_user.wallet_manager.get_by_alias(used_wallet_alias)
        SpotbitService.set_associated_wallet(wallet)
    ''' 
    return redirect(url_for(f"{ SpotbitService.get_blueprint_name()}.settings_get"))
    
