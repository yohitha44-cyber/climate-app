import pandas as pd
import requests
import streamlit as st

GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
COUNTRIES_URL = "https://countriesnow.space/api/v0.1/countries/iso"
STATES_URL = "https://countriesnow.space/api/v0.1/countries/states"
CITIES_URL = "https://countriesnow.space/api/v0.1/countries/state/cities"

WEATHER_CODES = {
    0: ("Clear sky", "☀️"),
    1: ("Mainly clear", "🌤️"),
    2: ("Partly cloudy", "⛅"),
    3: ("Overcast", "☁️"),
    45: ("Fog", "🌫️"),
    48: ("Fog", "🌫️"),
    51: ("Light drizzle", "🌦️"),
    53: ("Drizzle", "🌦️"),
    55: ("Heavy drizzle", "🌦️"),
    61: ("Light rain", "🌧️"),
    63: ("Rain", "🌧️"),
    65: ("Heavy rain", "🌧️"),
    71: ("Light snow", "🌨️"),
    73: ("Snow", "🌨️"),
    75: ("Heavy snow", "❄️"),
    80: ("Rain showers", "🌦️"),
    81: ("Rain showers", "🌧️"),
    82: ("Violent showers", "⛈️"),
    95: ("Thunderstorm", "⛈️"),
    96: ("Thunderstorm + hail", "⛈️"),
    99: ("Thunderstorm + hail", "⛈️"),
}


def describe(code):
    return WEATHER_CODES.get(code, ("Unknown", "❓"))


@st.cache_data(ttl=86400)
def get_countries():
    response = requests.get(COUNTRIES_URL, timeout=20)
    response.raise_for_status()
    result = response.json()
    data = result.get("data", [])

    countries = {}
    for item in data:
        name = item.get("name") or item.get("Name")
        code = item.get("Iso2") or item.get("iso2")
        if name and code:
            countries[name] = code.upper()

    if not countries:
        raise ValueError("Country list is empty.")
    return dict(sorted(countries.items()))


def post_location_api(url, payload):
    response = requests.post(url, json=payload, timeout=20)
    response.raise_for_status()
    result = response.json()
    if result.get("error"):
        raise ValueError(result.get("msg", "Location lookup failed"))
    return result.get("data")


@st.cache_data(ttl=86400)
def get_states(country):
    data = post_location_api(STATES_URL, {"country": country})
    if not isinstance(data, dict):
        return []
    return sorted({
        item["name"]
        for item in (data.get("states") or [])
        if isinstance(item, dict) and item.get("name")
    })


@st.cache_data(ttl=86400)
def get_cities(country, state):
    data = post_location_api(
        CITIES_URL,
        {"country": country, "state": state},
    )
    if not isinstance(data, list):
        return []
    return sorted({
        city.strip()
        for city in data
        if isinstance(city, str) and city.strip()
    })


@st.cache_data(ttl=600)
def search_city(city, country_code):
    response = requests.get(
        GEO_URL,
        params={
            "name": city,
            "count": 100,
            "language": "en",
            "format": "json",
            "countryCode": country_code,
        },
        timeout=20,
    )
    response.raise_for_status()
    return response.json().get("results", [])


@st.cache_data(ttl=600)
def get_weather(latitude, longitude):
    response = requests.get(
        WEATHER_URL,
        params={
            "latitude": latitude,
            "longitude": longitude,
            "current": (
                "temperature_2m,relative_humidity_2m,"
                "apparent_temperature,wind_speed_10m,weather_code"
            ),
            "daily": (
                "weather_code,temperature_2m_max,"
                "temperature_2m_min,precipitation_probability_max"
            ),
            "timezone": "auto",
            "forecast_days": 7,
        },
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def build_forecast_df(daily):
    rows = []
    for i, day in enumerate(daily["time"]):
        description, emoji = describe(daily["weather_code"][i])
        rows.append({
            "Date": pd.to_datetime(day).strftime("%a, %d %b"),
            "Weather": f"{emoji} {description}",
            "Min °C": daily["temperature_2m_min"][i],
            "Max °C": daily["temperature_2m_max"][i],
            "Rain %": daily["precipitation_probability_max"][i],
        })
    return pd.DataFrame(rows)


def main():
    st.set_page_config(
        page_title="Worldwide Weather App",
        page_icon="🌦️",
        layout="wide",
    )

    st.title("🌦️ Worldwide Weather App")
    st.write("Choose a country, state and city from the dropdowns.")

    try:
        with st.spinner("Loading countries..."):
            countries = get_countries()
    except (requests.RequestException, ValueError) as error:
        st.error(f"Could not load countries. Please try again. Details: {error}")
        st.stop()

    country_names = list(countries.keys())
    default_index = country_names.index("India") if "India" in country_names else 0

    country = st.selectbox(
        "🌍 Select Country",
        country_names,
        index=default_index,
        key="country_dropdown",
    )
    country_code = countries[country]

    try:
        with st.spinner(f"Loading states/regions in {country}..."):
            states = get_states(country)
    except (requests.RequestException, ValueError) as error:
        st.error(f"Could not load states. Details: {error}")
        st.stop()

    if not states:
        st.warning("States/regions are not available for this country.")
        st.stop()

    state = st.selectbox(
        "🗺️ Select State / Region",
        states,
        key=f"state_{country}",
    )

    try:
        with st.spinner(f"Loading cities in {state}..."):
            cities = get_cities(country, state)
    except (requests.RequestException, ValueError) as error:
        st.error(f"Could not load cities. Details: {error}")
        st.stop()

    if not cities:
        st.warning("No cities were found for this state/region.")
        st.stop()

    city = st.selectbox(
        "🏙️ Select City",
        cities,
        key=f"city_{country}_{state}",
    )

    if st.button("🌦️ Get Weather", type="primary", use_container_width=True):
        st.session_state["weather_selection"] = {
            "country": country,
            "country_code": country_code,
            "state": state,
            "city": city,
        }

    selection = st.session_state.get("weather_selection")

    if not selection:
        st.info("Select a country, state and city, then click Get Weather.")
        st.stop()

    # Use the latest dropdown selection after the button has been clicked.
    if (
        selection["country"] != country
        or selection["state"] != state
        or selection["city"] != city
    ):
        st.info("Your selection changed. Click Get Weather to update.")
        st.stop()

    try:
        with st.spinner(f"Finding {city}..."):
            places = search_city(city, country_code)
    except requests.RequestException:
        st.error("Could not find this city. Check your internet and try again.")
        st.stop()

    if not places:
        st.error(
            "This city was not found in the weather database. "
            "Try another city in the dropdown."
        )
        st.stop()

    # Prefer a result that matches the selected state/region.
    state_lower = state.casefold()
    matches = [
        place for place in places
        if state_lower in str(place.get("admin1", "")).casefold()
        or str(place.get("admin1", "")).casefold() in state_lower
    ]
    place = matches[0] if matches else places[0]

    try:
        with st.spinner("Loading weather..."):
            weather = get_weather(place["latitude"], place["longitude"])
    except requests.RequestException:
        st.error("Could not load weather data. Please try again.")
        st.stop()

    current = weather["current"]
    description, emoji = describe(current["weather_code"])

    st.divider()
    st.header(f"{emoji} {place.get('name', city)} — {description}")
    st.caption(
        f"{state}, {country} · Timezone: "
        f"{place.get('timezone', 'Unknown')}"
    )

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("🌡️ Temperature", f"{current['temperature_2m']} °C")
    col2.metric("🤔 Feels like", f"{current['apparent_temperature']} °C")
    col3.metric("💧 Humidity", f"{current['relative_humidity_2m']}%")
    col4.metric("💨 Wind speed", f"{current['wind_speed_10m']} km/h")

    st.caption(f"Last updated: {current['time']} (local time)")
    st.divider()
    st.subheader("📅 7-Day Weather Forecast")

    forecast = build_forecast_df(weather["daily"])
    st.dataframe(forecast, hide_index=True, use_container_width=True)

    st.subheader("📈 Temperature Forecast")
    st.line_chart(forecast.set_index("Date")[["Min °C", "Max °C"]])
    st.caption("Weather data provided by Open-Meteo.")


if __name__ == "__main__":
    main()
