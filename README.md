# Saffron Pantry Manager

A small Python pantry management and recipe suggestion app for household kitchens.

## What it does
- manages pantry items with expiry dates
- suggests recipes for a given number of people
- deducts ingredients after user confirmation
- uploads receipt images and auto-adds parsed bill items
- shows items expiring within the next 3 days

## Files
- `ui.py` — main user interface and app entrypoint
- `pantry_engine.py` — pantry logic, stock tracking, and deduction
- `utils.py` — helper utilities for parsing and normalization
- `ai.py` — receipt parsing and ingredient metadata helpers
- `constants.json` — static ingredient metadata
- `pantry_data.json` — sample pantry inventory data
- `requirements.txt` — Python dependencies

## Run
```powershell
cd "c:\Users\intel\OneDrive\Desktop\Python\Saffron"
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python ui.py
```

## Notes
- `ui.py` is the recommended entrypoint.
- Receipt upload requires a valid image path and `ollama` installed.
- Use option `5` in the menu to see items expiring in 3 days.
