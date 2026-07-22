"""
src/correlation_filter.py — Filtre de Corrélation des Devises (Matrice style Mataf)
Valide la force des signaux Forex par la corrélation inter-devises (EUR/USD, GBP/USD, USD/CHF, AUD/USD).
"""

import logging
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

# Groupes de corrélation forte positive (> 0.80)
CORRELATED_GROUPS = {
    "USD_WEAK": ["EURUSD=X", "GBPUSD=X", "AUDUSD=X", "NZDUSD=X"],  # Quand l'USD baisse, toutes ces paires montent
    "USD_STRONG": ["CAD=X", "CHF=X", "JPY=X"],                       # Quand l'USD monte, ces paires montent (ex: USD/CHF, USD/CAD)
    "JPY_CROSSES": ["EURJPY=X", "GBPJPY=X", "AUDJPY=X", "NZDJPY=X", "CADJPY=X"], # Corrélation Yen
}


def check_correlation_confirmation(symbol: str, signal: str, df_map: dict) -> tuple[bool, str]:
    """
    Vérifie si le signal (BUY ou SELL) est confirmé par les paires corrélées.
    
    Exemple: Si BUY EUR/USD, on vérifie que GBP/USD ou AUD/USD est également orienté à la hausse.
    Si les paires sœurs sont opposées, le mouvement est une anomalie/faux breakout -> Invalidé.
    """
    if signal not in ["BUY", "SELL"]:
        return True, "Neutre"

    # Trouver le groupe de corrélation de la paire
    group_name = None
    sister_pairs = []
    for g_name, pairs in CORRELATED_GROUPS.items():
        if symbol in pairs:
            group_name = g_name
            sister_pairs = [p for p in pairs if p != symbol]
            break

    if not sister_pairs:
        return True, "Pas de groupe de corrélation direct — Validé"

    # Vérifier le momentum des paires sœurs (sur les 5 dernières bougies)
    confirmations = 0
    total_sisters = 0

    for sister in sister_pairs:
        df = df_map.get(sister)
        if df is not None and not df.empty and len(df) >= 5:
            total_sisters += 1
            ret_5p = (float(df["Close"].iloc[-1]) - float(df["Close"].iloc[-5])) / float(df["Close"].iloc[-5]) * 100
            
            # Si BUY EUR/USD, les paires sœurs (GBP/USD, AUD/USD) doivent avoir un retour 5p positif (> 0)
            if signal == "BUY" and ret_5p > -0.05:
                confirmations += 1
            elif signal == "SELL" and ret_5p < 0.05:
                confirmations += 1

    if total_sisters > 0:
        ratio = confirmations / total_sisters
        if ratio >= 0.5:
            return True, f"✅ Confirmation Corrélation Matrice Mataf ({confirmations}/{total_sisters} paires sœurs alignées sur {group_name})"
        else:
            return False, f"⚠️ Divergence de Corrélation ({confirmations}/{total_sisters} paires sœurs alignées sur {group_name}) — Risque de Faux Breakout"

    return True, "Données sœurs indisponibles — Validé par défaut"
