import pytest
from main import fetch_weather, fetch_5day_forecast, fetch_attractions

def test_fetch_weather_valid_city():
    city, data = fetch_weather("Melbourne")
    assert "main" in data
    assert "temp" in data["main"]
    assert -10 < data["main"]["temp"] < 50          # Check temperature is in celsius (values within a valid range).

def test_fetch_weather_invalid_city():
    city, data = fetch_weather("ZiggyStardust")
    assert "error" in data                          # See if 'error' comes back if invalid city sent.

def test_fetch_5day_forecast():
    forecast = fetch_5day_forecast("Paris")         # Get 5-day forecast for Paris.
    assert "forecasts" in forecast
    assert isinstance(forecast["forecasts"], list)
    assert len(forecast["forecasts"]) > 0           # Check that results are returned (count is greater than zero).

def test_fetch_attractions_valid_coords():
    data = fetch_attractions(51.5074, -0.1278)      # Using London coordinates for testing attractions.
    assert "features" in data                       # Confirm response includes 'features' key.
    assert isinstance(data["features"], list)
