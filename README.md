# COS60016 | Assignment 2 – Web-Based API Integration Framework with ChatBot

**Author:** Jace Garth  
**Date:** 24 March 2025

## Overview
This Flask-based web application allows users to interact with a chatbot to request real-time weather data, 5-day forecasts, and local attraction suggestions for selected cities. It integrates three APIs (OpenWeatherMap, Google Static Map, Geoapify Places) and responds via a conversational interface.

## How to Run the Application

1. Clone this repository to your local machine.
2. Create a virtual environment and install dependencies:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate    # Windows
   pip install -r requirements.txt
3. Create the following files in the root directory and paste in your API keys:

   - `openweather_api_key.txt`  
   - `google_api_key.txt`  
   - `geoapify_api_key.txt`

4. Run the app:
   ```bash
   python main.py
5. Open a browser and go to **http://127.0.0.1:5000**


## Project Structure

- `main.py` – Core application logic  
- `templates/` – HTML templates (Jinja2)  
- `static/` – CSS styling and JavaScript  
- `tests/` – Contains `test_app.py` with Pytest test cases  
- `weather_training.json` – Custom training data for chatbot  

## Known Limitations

- Error handling for failed API calls (e.g. invalid keys) currently triggers a generic internal error.  
- Cache usage is implemented but not programmatically verified in testing.  
- Manual testing was used for chatbot responses; no automation.

## Requirements

- Python 3.10+  
- Flask  
- requests  
- ChatterBot  
- SQLAlchemy  
- Pytest  

## License

This project is for academic purposes only.

