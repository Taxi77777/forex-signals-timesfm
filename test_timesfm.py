import numpy as np, os, sys
sys.path.insert(0, '.')
os.environ['TELEGRAM_BOT_TOKEN'] = '8347280600:AAGY6UJKbLULT58j1rJpC9TQm_kR0mJsQew'
os.environ['TELEGRAM_CHAT_ID'] = '375129602'
os.environ['USE_TIMESFM'] = 'true'
from src.timesfm_predictor import predict_timesfm, get_forecast_direction

print('Test TimesFM 2.5 avec prix EUR/USD...')
prices = np.array([1.0820 + i*0.0001 + np.random.normal(0, 0.0003) for i in range(512)], dtype=np.float32)
preds = predict_timesfm(prices)
print('OK - Shape:', preds.shape)
print('Prix actuel:', round(float(prices[-1]), 5))
print('Prediction 4h:', round(float(preds[3]), 5))
print('Prediction 24h:', round(float(preds[23]), 5))
result = get_forecast_direction(float(prices[-1]), preds)
print('Signal:', result['direction'], '| Confiance:', result['confidence'], '%')
print('TIMESFM 2.5 FONCTIONNE!')
