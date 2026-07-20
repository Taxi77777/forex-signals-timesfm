"""
src/macro_filter.py — Filtre macroéconomique Forex basé sur TradingEconomics
Récupère les taux d'intérêt, l'inflation et le PIB en direct pour enrichir et filtrer les signaux.
"""

import urllib.request
import re
import logging

logger = logging.getLogger(__name__)

CURRENCY_TO_COUNTRY = {
    "USD": "United States",
    "EUR": "Euro Area",
    "GBP": "United Kingdom",
    "JPY": "Japan",
    "CHF": "Switzerland",
    "CAD": "Canada",
    "AUD": "Australia",
    "NZD": "New Zealand",
    "MXN": "Mexico",
    "ZAR": "South Africa",
}

class MacroFilter:
    _macro_data = {}
    _initialized = False

    def __init__(self):
        pass

    def initialize(self):
        """Récupère et parse le tableau des indicateurs TradingEconomics."""
        if MacroFilter._initialized:
            return
        
        url = "https://tradingeconomics.com/matrix"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        try:
            logger.info("📡 Récupération des données macroéconomiques globales sur TradingEconomics...")
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as response:
                html = response.read().decode("utf-8")
            
            # Extraction robuste par bloc pays
            matches = list(re.finditer(r'href="/(?P<slug>[a-z\-]+)/indicators"><span class="whitespace-nowrap">(?P<country>[A-Za-z\s]+)</span>', html))
            
            parsed_count = 0
            for i in range(len(matches)):
                start = matches[i].start()
                end = matches[i+1].start() if i + 1 < len(matches) else len(html)
                sub = html[start:end]
                
                country = matches[i].group("country").strip()
                slug = matches[i].group("slug")
                
                gdp = re.search(r'href="/' + slug + r'/gdp">(?P<val>[0-9\.\,\-]+)</a>', sub)
                gdp_growth = re.search(r'href="/' + slug + r'/gdp-growth-annual">(?P<val>[0-9\.\,\-]+)</a>', sub)
                interest_rate = re.search(r'href="/' + slug + r'/interest-rate">(?P<val>[0-9\.\,\-]+)</a>', sub)
                inflation = re.search(r'href="/' + slug + r'/inflation-cpi">(?P<val>[0-9\.\,\-]+)</a>', sub)
                unemployment = re.search(r'href="/' + slug + r'/unemployment-rate">(?P<val>[0-9\.\,\-]+)</a>', sub)
                
                # Conversion des taux en float
                def to_float(match_obj):
                    if not match_obj:
                        return 0.0
                    val_str = match_obj.group("val").replace(",", "")
                    try:
                        return float(val_str)
                    except ValueError:
                        return 0.0

                MacroFilter._macro_data[country] = {
                    "gdp_growth": to_float(gdp_growth),
                    "interest_rate": to_float(interest_rate),
                    "inflation": to_float(inflation),
                    "unemployment": to_float(unemployment),
                }
                parsed_count += 1
                
            logger.info(f"✅ Données macroéconomiques de {parsed_count} pays chargées avec succès.")
            MacroFilter._initialized = True
        except Exception as e:
            logger.error(f"❌ Erreur lors du chargement des données macro Forex : {e}")
            MacroFilter._initialized = False

    def get_macro_info(self, symbol: str) -> dict | None:
        """Retourne la comparaison macroéconomique entre la devise de base et la devise de contrepartie."""
        if not MacroFilter._initialized:
            self.initialize()
            if not MacroFilter._initialized:
                return None

        # Nettoyage du symbole (ex: GBPCHF=X -> GBPCHF)
        clean_sym = symbol.replace("=X", "").replace("/", "")
        if len(clean_sym) != 6:
            return None

        base = clean_sym[:3].upper()
        quote = clean_sym[3:].upper()

        country_base = CURRENCY_TO_COUNTRY.get(base)
        country_quote = CURRENCY_TO_COUNTRY.get(quote)

        if not country_base or not country_quote:
            return None

        data_base = MacroFilter._macro_data.get(country_base)
        data_quote = MacroFilter._macro_data.get(country_quote)

        if not data_base or not data_quote:
            return None

        rate_diff = data_base["interest_rate"] - data_quote["interest_rate"]

        return {
            "base": base,
            "quote": quote,
            "rate_base": data_base["interest_rate"],
            "rate_quote": data_quote["interest_rate"],
            "rate_diff": rate_diff,
            "inf_base": data_base["inflation"],
            "inf_quote": data_quote["inflation"],
            "gdp_base": data_base["gdp_growth"],
            "gdp_quote": data_quote["gdp_growth"],
        }

    def check_macro_guard(self, symbol: str, signal_dir: str) -> tuple[bool, str]:
        """
        Vérifie si la pénalité de taux d'intérêt (Carry Trade) est acceptable.
        Retourne (is_allowed, reason).
        """
        info = self.get_macro_info(symbol)
        if not info:
            return True, "Pas de donnée macro disponible pour cette paire - Autorisé"

        diff = info["rate_diff"]

        if signal_dir == "BUY":
            # Si on achète une devise à taux très bas contre une devise à taux très haut, le swap est négatif
            if diff <= -3.0:
                reason = f"🚫 Bloqué par Macro Guard | Swap trop pénalisant (Différentiel de taux : {diff:+.2f}% | {info['base']}:{info['rate_base']}% vs {info['quote']}:{info['rate_quote']}%)"
                return False, reason
        elif signal_dir == "SELL":
            # Pour une vente, on veut vendre la devise à taux faible et acheter celle à taux fort
            if diff >= 3.0:
                reason = f"🚫 Bloqué par Macro Guard | Swap trop pénalisant pour un Short (Différentiel de taux : {diff:+.2f}% | {info['base']}:{info['rate_base']}% vs {info['quote']}:{info['rate_quote']}%)"
                return False, reason

        return True, f"Carry trade favorable ou neutre : {diff:+.2f}% ({info['base']}:{info['rate_base']}% vs {info['quote']}:{info['rate_quote']}%)"
