import requests, json, os, logging
from flask import Flask, render_template, request
from flask_sqlalchemy import SQLAlchemy
from chatterbot import ChatBot
from chatterbot.trainers import ListTrainer, ChatterBotCorpusTrainer
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone
from collections import OrderedDict

base_path = os.path.dirname(os.path.abspath(__file__))      # Get application path (reused from Assignment 1; Ref: nkmk, 2023).

app = Flask(__name__)
current_map_city = None
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///weatherbot.sqlite3"      # Set SQLAlchemy database location.
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)                                                        # Create SQLAlchemy database.

# This block of code is reused from Assignment 1 (Ref: Python Software Foundation, 2025; StackOverflow, 2025).
log_handler = RotatingFileHandler("app.log", maxBytes=1000000, backupCount=3)
log_handler.setLevel(logging.INFO)
logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(log_handler)

# Define the chat history table to store all user and bot messages along with a timestamp in UTC (with timezone).
class ChatHistory(db.Model):            #  db.Model used to structure tables in the database (Ref StackOverflow, 2020).
    id = db.Column(db.Integer, primary_key=True)
    user_message = db.Column(db.String(500), nullable=False)        # Store user message, maximum 500 characters.
    bot_response = db.Column(db.String(500), nullable=False)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))      # Get the current date/time (localised to timezone) (Ref: StackOverflow, 2025).

# Define the weather table for storing current weather data sourced from OpenWeatherMap's API.
class WeatherData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    city = db.Column(db.String(100), nullable=False)
    date = db.Column(db.String(20), nullable=False)
    temperature = db.Column(db.Float, nullable=False)
    humidity = db.Column(db.Integer, nullable=False)
    description = db.Column(db.String(100), nullable=False)
    wind_speed = db.Column(db.Float, nullable=True, default=0.0)
    lat = db.Column(db.Float, nullable=False, default=0.0)
    lon = db.Column(db.Float, nullable=False, default=0.0)

# Define the table for storing the 5-day weather forecast data sourced from OpenWeatherMap's API.
class ForecastData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    city = db.Column(db.String(100), nullable=False)
    forecast_dt = db.Column(db.String(25), nullable=False)          # Include the forecast date, as we are getting 5 days worth.
    temp_max = db.Column(db.Float, nullable=True)
    humidity = db.Column(db.Integer, nullable=False)
    description = db.Column(db.String(100), nullable=False)
    wind_speed = db.Column(db.Float, nullable=True, default=0.0)
    lat = db.Column(db.Float, nullable=False, default=0.0)
    lon = db.Column(db.Float, nullable=False, default=0.0)

# This table will keep count of the number of API calls made in case we reach the daily limit of our API plan.
class APICallCount(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(20), nullable=False)         # Also storing the date because the API count would reset the next day.
    count = db.Column(db.Integer, nullable=False, default=0)

# Initialize the database and create all tables from the above classes.
with app.app_context():
    db.create_all()

# Initialize ChatterBot and apply basic training (Ref: Medium, 2020; Hackernoon, 2022).
chatbot = ChatBot(
    'WeatherBot',
    storage_adapter='chatterbot.storage.SQLStorageAdapter',
    database_uri='sqlite:///weatherbot.sqlite3'
)
corpus_trainer = ChatterBotCorpusTrainer(chatbot)
corpus_trainer.train("chatterbot.corpus.english.conversations","chatterbot.corpus.english.greetings")
list_trainer = ListTrainer(chatbot)
with open(os.path.join(base_path, "weather_training.json"), "r") as file:       # Using external json file for additional chatbot training. I didn't get much written into it though ...
    weather_conversations = json.load(file)["conversations"]
for conversation in weather_conversations:      # ... but putting it into the chatbot training anyway. I was going to add more to this json file but have run out of time.
    list_trainer.train(conversation)

# Has the chatbot return a default response if the confidence level is low (Ref: Quidget, 2025).
def get_bot_response(user_input):
    response = chatbot.get_response(user_input)
    if any(k in user_input.lower() for k in ["weather", "forecast", "temperature", "humidity", "rain", "wind"]) and response.confidence < 0.5:
        return "I'm not sure, but I can help with weather information."
    return str(response)

# Keep track of the number of API calls made per day. If we exceed the limit then the function where it's used will return an error-style message to the user.
def increment_api_call():
    today = datetime.now().strftime("%Y-%m-%d")
    usage = APICallCount.query.filter_by(date=today).first()
    if not usage:
        usage = APICallCount(date=today, count=0)
        db.session.add(usage)
        db.session.commit()
    usage.count += 1
    db.session.commit()             # Store count in database.
    return usage.count <= 1000      # False if we exceed 1000 API calls (true if usage count is less than or equal to 1000).

# Read an API key from a given filename. Similar function to the one used in Assignment 1 but now using cleaner code.
def get_api_key(filename):
    with open(os.path.join(base_path, filename), 'r') as file:
        return file.read().strip()
weatherapi = get_api_key("openweather_api_key.txt")             # OpenWeatherMap API key.
googleapi = get_api_key("google_api_key.txt")                   # Google Maps API key.
geoapify_api = get_api_key("geoapify_api_key.txt")              # Geoapify Places API key.

# User has asked for current weather data, so get it from OpenWeatherMap API.
def fetch_weather(city, lat=None, lon=None, api_key=weatherapi):
    if not increment_api_call():
        return city, {"error": "Daily API limit reached. Please try again tomorrow."}       # Return error message if API call limit exceeded.

    today = datetime.now().strftime("%Y-%m-%d")
    cached = WeatherData.query.filter_by(city=city, date=today).first()         # Check if today's weather data is already stored in the database.
    if cached:      # If already present then get data from database and return it.
        return city, {
            "name": cached.city,
            "main": {"temp": cached.temperature, "humidity": cached.humidity},
            "weather": [{"description": cached.description}],
            "wind": {"speed": cached.wind_speed},
            "coord": {"lat": cached.lat, "lon": cached.lon}
        }
    if lat is None or lon is None:          # If lat or lon aren't provided then source the lat/lon from OpenWeatherMap using city name. Show error message if city can't be found.
        url = f"http://api.openweathermap.org/geo/1.0/direct?q={city}&limit=1&appid={api_key}"
        geo_resp = requests.get(url).json()
        if geo_resp:
            lat, lon = geo_resp[0]["lat"], geo_resp[0]["lon"]
        else:
            return city, {"error": "City not found."}
    weather_url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={api_key}"
    resp = requests.get(weather_url).json()
    if "main" in resp:          # If 'main' included in response then we have a valid city so get the data from it.
        wind_speed = resp["wind"]["speed"] if ("wind" in resp and "speed" in resp["wind"]) else 0.0
        new_entry = WeatherData(
            city=city,
            date=today,
            temperature=round(resp["main"]["temp"] - 273.15, 1),
            humidity=resp["main"]["humidity"],
            description=resp["weather"][0]["description"],
            wind_speed=wind_speed,
            lat=lat,
            lon=lon
        )
        db.session.add(new_entry)
        db.session.commit()         # Save data to database.
        processed = {
            "name": new_entry.city,
            "main": {"temp": new_entry.temperature, "humidity": new_entry.humidity},
            "weather": [{"description": new_entry.description}],
            "wind": {"speed": new_entry.wind_speed},
            "coord": {"lat": new_entry.lat, "lon": new_entry.lon}
        }
        return city, processed
    else:
        return city, {"error": "Weather data not available."}

# User has asked for attractions in a city, so get them from Geoapify Places API.
def fetch_attractions(lat, lon):
    if not increment_api_call():
        return {"error": "Daily API limit reached. Please try again tomorrow."}

    category = "tourism.sights"         # Set category in Geoapify Places API to popular tourism sights.
    url = f"https://api.geoapify.com/v2/places?categories={category}&filter=circle:{lon},{lat},5000&limit=5&apiKey={geoapify_api}"      # URL provided by Geoapify.
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    else:
        return {"error": f"Geoapify API returned status {response.status_code}"}

# User has asked for weather forecast, so get 5-day forecast from OpenWeatherMap API.
def fetch_5day_forecast(city, lat=None, lon=None, api_key=weatherapi):
    if not increment_api_call():
        return {"error": "Daily API limit reached. Please try again tomorrow."}

    if lat is None or lon is None:
        geo_url = f"http://api.openweathermap.org/geo/1.0/direct?q={city}&limit=1&appid={api_key}"              # URL provided by OpenWeatherMap API documentation.
        geo_resp = requests.get(geo_url).json()
        if geo_resp:
            lat, lon = geo_resp[0]["lat"], geo_resp[0]["lon"]
        else:
            return {"error": "City not found."}

    forecast_url = f"https://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&appid={api_key}"      # URL provided by OpenWeatherMap API documentation.
    resp = requests.get(forecast_url).json()

    if "list" not in resp:      # Forecast response from API must contain 'list' key otherwise we know the data isn't available.
        return {"error": "No forecast data available."}

    results = []
    for entry in resp["list"]:
        dt_txt = entry["dt_txt"]        # Get date and time of the forecast (it's providing forecast data for every 3 hours, we only need the first one to get temp_max).
        existing = ForecastData.query.filter_by(city=city, forecast_dt=dt_txt).first()       # Check if this forecast entry already exists in the database.
        if existing:        # If so then just read it, otherwise create it.
            forecast_info = {
                "dt": existing.forecast_dt,
                "temp_max": existing.temp_max,
                "humidity": existing.humidity,
                "description": existing.description,
                "wind_speed": existing.wind_speed
            }
        else:
            temp_max_c = round(entry["main"]["temp_max"] - 273.15, 1)        # Convert kelvin to celsius.
            humidity = entry["main"]["humidity"]
            desc = entry["weather"][0]["description"]
            wind = entry["wind"]["speed"] if "wind" in entry and "speed" in entry["wind"] else 0.0

            new_record = ForecastData(      # This is what we will add into the database.
                city=city,
                forecast_dt=dt_txt,
                temp_max=temp_max_c,
                humidity=humidity,
                description=desc,
                wind_speed=wind,
                lat=lat,
                lon=lon
            )
            db.session.add(new_record)
            db.session.commit()
            forecast_info = {
                "dt": dt_txt,
                "temp_max": temp_max_c,
                "humidity": humidity,
                "description": desc,
                "wind_speed": wind
            }
        results.append(forecast_info)

    return {
        "city": city,
        "lat": lat,
        "lon": lon,
        "forecasts": results
    }

# Now we have created the functions, let's bring it all together.
@app.route("/", methods=["POST", "GET"])
def home():
    # Declare the variables that will be used in this function
    global current_map_city
    formatted_history = []
    weather_data = None
    map_url = None
    attractions_data = None
    forecast_data = None

    if request.method == "GET":             # GET used for the initial page load.
        ChatHistory.query.delete()          # Clear the chat history for this session.
        db.session.commit()
        current_map_city = None
        return render_template("index.html",chat_history=[],weather=None,map_img=None,attractions=None,forecast=None)        # Send these variables/values to the webpage.

    if request.method == "POST":            # POST used when the user sends a message to the chatbot.
        user_input = request.form.get("user_input")
        if user_input:                      # If user has entered text (not just pressed enter).
            lower_input = user_input.lower()        # Lower case is easier to sort through than having to play with case later.
            bot_response = get_bot_response(user_input)         # Run get_bot_response function and pass in user_input as argument.
            entry = ChatHistory(user_message=user_input, bot_response=str(bot_response))        # Create the data to put into the database, then add and commit it.
            db.session.add(entry)
            db.session.commit()

            # This section processes the 5-day forecast.
            if any(term in lower_input for term in ["5 day forecast", "five day forecast", "5-day forecast", "multi-day forecast"]):    # If user's message contains any of these ...
                if " in " in lower_input:                                                   # ... and these ...
                    city = lower_input.split(" in ", 1)[1].strip("?!., ")
                elif " for " in lower_input:
                    city = lower_input.split(" for ", 1)[1].strip("?!., ")
                else:
                    city = current_map_city if current_map_city else ""
                if city:
                    raw_forecast_data = fetch_5day_forecast(city)                           # ... then get the 5-day forecast from API (via function) and process it.
                    if "forecasts" in raw_forecast_data:
                        daily_forecasts = OrderedDict()                                     # Create dictionary sorted by date, one entry per date.
                        for f in raw_forecast_data["forecasts"]:
                            date_part = f["dt"].split(" ")[0]
                            if date_part not in daily_forecasts:
                                daily_forecasts[date_part] = f
                        forecast_summary = []                                               # Create a summary list for first 5 days (this API returns 6 days, we only want 5 days).
                        day_count = 0
                        for date_key, f in daily_forecasts.items():
                            if day_count < 5:
                                line = (f"{date_key}: {f['description']}, max {f['temp_max']}°C, humidity {f['humidity']}%")        # Build line and add it to list.
                                forecast_summary.append(line)
                                day_count += 1
                            else:
                                break
                        forecast_str = "\n".join(forecast_summary)
                        bot_response = f"5-Day forecast for {city.title()}:\n{forecast_str}"
                        forecast_data = {"city": city, "daily_summary": forecast_summary}
                        w_result = fetch_weather(city)[1]       # Get the map image from Google Map API.
                        if "coord" in w_result:
                            lat = w_result["coord"]["lat"]
                            lon = w_result["coord"]["lon"]
                            map_url = f"https://maps.googleapis.com/maps/api/staticmap?center={lat},{lon}&zoom=14&size=600x300&key={googleapi}"
                    else:
                        bot_response = "Sorry, I couldn't retrieve a 5-day forecast for that location."     # Any issues with the location then throw error.
                else:
                    bot_response = "Please specify the city for a 5-day forecast."      # If the user asks for forecast but doesn't provide a valid location.
                entry.bot_response = bot_response
                db.session.commit()

            # This section gets the attractions for the selected city.
            elif any(term in lower_input for term in ["attractions", "things to do", "something i can do", "things i can do"]):
                if " in " in lower_input:
                    city = lower_input.split(" in ", 1)[1].strip("?!., ")
                else:
                    city = current_map_city if current_map_city else ""
                if city:
                    if city.lower() != current_map_city:
                        w_result = fetch_weather(city)[1]
                        if "main" in w_result:
                            lat = w_result["coord"]["lat"]
                            lon = w_result["coord"]["lon"]
                            attractions_data = fetch_attractions(lat, lon)
                            map_url = f"https://maps.googleapis.com/maps/api/staticmap?center={lat},{lon}&zoom=14&size=600x300&key={googleapi}"
                            weather_data = w_result
                            current_map_city = city.lower()
                            if "features" in attractions_data and attractions_data["features"]:
                                suggestions = [feat["properties"].get("name", "Unnamed place") for feat in attractions_data["features"]]
                                suggestions_str = ", ".join(suggestions)        # Get all the suggestions and put them together into a single string (like a legible sentence).
                            else:
                                suggestions_str = "No suggestions found."
                            bot_response = f"Here are some things to do in {city.title()}: {suggestions_str}"
                        else:
                            bot_response = "Sorry, I couldn't retrieve data for that location."
                    else:
                        if not weather_data:
                            w_result = fetch_weather(city)[1]
                            weather_data = w_result
                        lat = weather_data["coord"]["lat"]
                        lon = weather_data["coord"]["lon"]
                        attractions_data = fetch_attractions(lat, lon)
                        if "features" in attractions_data and attractions_data["features"]:
                            suggestions = [feat["properties"].get("name", "Unnamed place") for feat in attractions_data["features"]]
                            suggestions_str = ", ".join(suggestions)
                        else:
                            suggestions_str = "No suggestions found."
                        bot_response = f"Here are some things to do in {city.title()}: {suggestions_str}"
                else:
                    bot_response = "Please specify the city for attraction suggestions."
                entry.bot_response = bot_response
                db.session.commit()

            # This section gets the weather data for the city requested by the user.
            elif any(k in lower_input for k in ["weather", "forecast", "temperature", "humidity", "rain", "wind"]):
                if " in " in lower_input:
                    city = lower_input.split(" in ", 1)[1].strip("?!., ")
                else:
                    city = lower_input.strip("?!., ")
                w_result = fetch_weather(city)[1]
                if "main" in w_result:
                    lat = w_result["coord"]["lat"]
                    lon = w_result["coord"]["lon"]
                    map_url = f"https://maps.googleapis.com/maps/api/staticmap?center={lat},{lon}&zoom=14&size=600x300&key={googleapi}"
                    temp_c = w_result["main"]["temp"]
                    humidity = w_result["main"]["humidity"]
                    wind_speed_kmh = (w_result["wind"]["speed"] * 3.6) if ("wind" in w_result and "speed" in w_result["wind"]) else 0.0
                    attractions_data = fetch_attractions(lat, lon)
                    bot_response = (f"The weather in {city.title()} is {w_result['weather'][0]['description']} with a temperature of {temp_c}°C, humidity {humidity}%, and wind speed ~{round(wind_speed_kmh,1)} km/h.")
                    weather_data = w_result
                    current_map_city = city.lower()
                else:
                    bot_response = "Sorry, I couldn't find the weather for that location."
                entry.bot_response = bot_response
                db.session.commit()

            # Add latest user and chatbot messages to the chat history list.
            for rec in ChatHistory.query.order_by(ChatHistory.timestamp).all():
                formatted_history.append({"user": "You", "text": rec.user_message})
                formatted_history.append({"user": "Bot", "text": rec.bot_response})

    return render_template("index.html",chat_history=formatted_history,weather=weather_data,map_img=map_url,attractions=attractions_data,forecast=forecast_data)

if __name__ == "__main__":
    app.run()
