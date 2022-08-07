from flask import redirect, render_template, request, url_for
from flask import current_app as app

from cryptoadvance.specter.specter import Specter
from .service import SpotbitService


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
    keepWeeks = request.form["keepWeeks"]
    exchanges = request.form["exchanges"]
    currencies = request.form["currencies"]
    interval = request.form["interval"]
    service = ext()
    service.scheduler.scheduler.modify_job(job_id = 'prune', args = [keepWeeks])
    service.init_table()
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
    
