"""
src/economic_calendar.py — Filtre d'annonces économiques pour éviter la volatilité
"""

import logging
import requests
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

def get_blocked_currencies(window_minutes: int = 60) -> set[str]:
    """
    Télécharge le calendrier de la semaine et retourne l'ensemble des devises (ex: 'USD', 'GBP')
    qui sont actuellement bloquées par une annonce économique à fort impact (High).
    
    Une devise est bloquée si le moment présent se situe dans une fenêtre de :
    - window_minutes minutes AVANT l'annonce
    - window_minutes minutes APRÈS l'annonce
    """
    blocked = set()
    try:
        r = requests.get(CALENDAR_URL, timeout=15)
        if r.status_code != 200:
            logger.warning(f"⚠️ Impossible de récupérer le calendrier économique: HTTP {r.status_code}")
            return blocked
            
        events = r.json()
        now = datetime.now(timezone.utc)
        
        for ev in events:
            # Ne filtrer que les news à fort impact (High)
            if ev.get("impact") != "High":
                continue
                
            date_str = ev.get("date")
            country = ev.get("country")
            if not date_str or not country:
                continue
                
            try:
                # date_str ex: "2026-07-12T18:30:00-04:00"
                event_time = datetime.fromisoformat(date_str).astimezone(timezone.utc)
                diff = (event_time - now).total_seconds() / 60.0
                
                # Si le moment présent est compris entre -window_minutes et +window_minutes
                if -window_minutes <= diff <= window_minutes:
                    blocked.add(country.upper())
                    logger.info(f"🚫 Devise {country} bloquée en raison de l'annonce: '{ev.get('title')}' à {event_time}")
            except Exception as ex:
                continue
                
    except Exception as e:
        logger.error(f"❌ Erreur lors de la récupération du calendrier économique : {e}")
        
    return blocked
