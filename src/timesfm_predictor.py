"""
src/timesfm_predictor.py — Prédictions de séries temporelles via Google TimesFM
"""

import logging
import numpy as np
from typing import Optional
import config

logger = logging.getLogger(__name__)

# ─── Chargement paresseux du modèle ────────────────────────────────────────────
_model = None


def _load_model():
    """Charge le modèle TimesFM une seule fois (singleton)."""
    global _model
    if _model is not None:
        return _model

    if not config.USE_TIMESFM:
        logger.info("ℹ️  TimesFM désactivé — utilisation du fallback statistique")
        return None

    try:
        import timesfm

        logger.info("⏳ Chargement du modèle TimesFM (peut prendre 1-2 min la 1ère fois)…")
        _model = timesfm.TimesFm(
            hparams=timesfm.TimesFmHparams(
                backend=config.TIMESFM_BACKEND,
                per_core_batch_size=32,
                horizon_len=config.FORECAST_HORIZON,
            ),
            checkpoint=timesfm.TimesFmCheckpoint(
                huggingface_repo_id=config.TIMESFM_MODEL_ID
            ),
        )
        logger.info("✅ Modèle TimesFM chargé avec succès !")
        return _model

    except ImportError:
        logger.warning("⚠️  Package 'timesfm' non installé — fallback activé")
        return None
    except Exception as e:
        logger.error(f"❌ Erreur chargement TimesFM: {e} — fallback activé")
        return None


def predict_timesfm(price_series: np.ndarray) -> Optional[np.ndarray]:
    """
    Génère une prédiction via TimesFM.
    
    Args:
        price_series: Série de prix historiques (array 1D float32)
    
    Returns:
        Array des prix prédits sur FORECAST_HORIZON périodes, ou None si échec
    """
    model = _load_model()
    if model is None:
        return _fallback_predict(price_series)

    try:
        forecast_input = [price_series.astype(np.float32)]
        freq_input = [0]  # 0 = haute fréquence (horaire)

        point_forecast, _ = model.forecast(forecast_input, freq=freq_input)
        predictions = point_forecast[0]  # Premier (unique) batch

        logger.debug(f"✅ Prédiction TimesFM: {predictions[:5]}…")
        return predictions.astype(np.float64)

    except Exception as e:
        logger.error(f"❌ Erreur prédiction TimesFM: {e}")
        return _fallback_predict(price_series)


def _fallback_predict(price_series: np.ndarray) -> np.ndarray:
    """
    Prédiction de repli basée sur tendance linéaire + bruit faible.
    Utilisée quand TimesFM n'est pas disponible.
    
    Args:
        price_series: Série de prix historiques
    
    Returns:
        Array de prédictions approximatives
    """
    logger.info("🔄 Utilisation du fallback prédictif (régression linéaire)")
    horizon = config.FORECAST_HORIZON
    n = len(price_series)

    # Régression linéaire simple
    x = np.arange(n)
    coeffs = np.polyfit(x, price_series, deg=1)
    slope, intercept = coeffs

    # Extrapolation
    future_x = np.arange(n, n + horizon)
    predictions = slope * future_x + intercept

    # Ajout d'un léger bruit aléatoire reproductible
    np.random.seed(42)
    noise_scale = np.std(np.diff(price_series[-20:])) * 0.5
    noise = np.random.normal(0, noise_scale, size=horizon)
    return predictions + noise


def get_forecast_direction(current_price: float, predictions: np.ndarray) -> dict:
    """
    Analyse la direction de la prédiction et calcule la confiance.
    
    Args:
        current_price: Prix actuel
        predictions:   Array de prix prédits
    
    Returns:
        Dict avec direction, variation %, confiance, prix cible
    """
    if predictions is None or len(predictions) == 0:
        return {"direction": "HOLD", "variation_pct": 0, "confidence": 0}

    # Prix prédit à 4h et 24h
    target_4h  = float(predictions[min(3,  len(predictions) - 1)])
    target_24h = float(predictions[min(23, len(predictions) - 1)])

    variation_4h  = (target_4h  - current_price) / current_price * 100
    variation_24h = (target_24h - current_price) / current_price * 100

    # Direction basée sur 4h (signal court terme)
    direction = "BUY" if variation_4h > 0 else "SELL" if variation_4h < 0 else "HOLD"

    # Confiance basée sur la cohérence des prédictions
    mid_predictions = predictions[:min(12, len(predictions))]
    rising_count  = np.sum(mid_predictions > current_price)
    falling_count = len(mid_predictions) - rising_count
    dominance = max(rising_count, falling_count) / len(mid_predictions)
    confidence = int(dominance * 100)

    return {
        "direction":     direction,
        "variation_4h":  round(variation_4h, 4),
        "variation_24h": round(variation_24h, 4),
        "target_4h":     round(target_4h, 5),
        "target_24h":    round(target_24h, 5),
        "confidence":    confidence,
    }
