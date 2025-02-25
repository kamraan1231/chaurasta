from flask import Flask, render_template, request, jsonify
import requests
import sqlite3
from datetime import datetime
import threading
import time

app = Flask(__name__)
app.secret_key = "8b8adeefa2a10df513cd1d5f5de4d5b202600b4660704ba4d3beadf01b102fad"

GOOGLE_MAPS_API_KEY = "AIzaSyAl8f5_lixzi2wHH19dOnRXha9as3HTeBY"
OPENWEATHER_API_KEY = "d955e4dfe227a0ec3d37d6d0abeae4ed"


# Function to get route
@app.route("/get_route", methods=["POST"])
def get_route():
    data = request.json
    start = data.get("start")
    end = data.get("end")
    mode = data.get("mode", "driving")

    directions_url = f"https://maps.googleapis.com/maps/api/directions/json?origin={start}&destination={end}&mode={mode}&key={GOOGLE_MAPS_API_KEY}"

    response = requests.get(directions_url)
    directions_data = response.json()

    if directions_data["status"] == "OK":
        route = directions_data["routes"][0]["overview_polyline"]["points"]
        return jsonify({"route": route})
    else:
        return jsonify({"error": "Route not found"}), 400


# Function to get weather for travel route
@app.route("/get_weather", methods=["POST"])
def get_weather():
    data = request.json
    location = data.get("location")

    weather_url = f"https://api.openweathermap.org/data/2.5/weather?q={location}&appid={OPENWEATHER_API_KEY}&units=metric"
    response = requests.get(weather_url)
    weather_data = response.json()

    if weather_data.get("cod") == 200:
        return jsonify({
            "temperature": weather_data["main"]["temp"],
            "description": weather_data["weather"][0]["description"]
        })
    else:
        return jsonify({"error": "Weather data not found"}), 400


# Function to add task
@app.route("/add_task", methods=["POST"])
def add_task():
    data = request.json
    task = data.get("task")
    date = data.get("date")
    time = data.get("time")
    reminder_time = data.get("reminder_time", 10)  # Default 10 minutes before

    with sqlite3.connect("planner.db") as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO tasks (task, date, time, reminder_time) VALUES (?, ?, ?, ?)",
                       (task, date, time, reminder_time))
        conn.commit()

    return jsonify({"message": "Task added successfully"})


# Function to get all tasks
@app.route("/get_tasks", methods=["GET"])
def get_tasks():
    with sqlite3.connect("planner.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, task, date, time FROM tasks ORDER BY date, time")
        tasks = cursor.fetchall()

    return jsonify(tasks)


# Smart Reminder System (Local Notifications)
def schedule_reminders():
    while True:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        with sqlite3.connect("planner.db") as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, task FROM tasks WHERE datetime(date || ' ' || time) <= datetime('now', '+' || reminder_time || ' minutes')")
            reminders = cursor.fetchall()

            for task_id, task_name in reminders:
                print(f"🔔 Reminder: {task_name} is coming up!")

        time.sleep(60)  # Check every minute


# Start reminder scheduler in a background thread
reminder_thread = threading.Thread(target=schedule_reminders)
reminder_thread.daemon = True
reminder_thread.start()

# Create database if not exists
with sqlite3.connect("planner.db") as conn:
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task TEXT,
            date TEXT,
            time TEXT,
            reminder_time INTEGER
        )
    """)
    conn.commit()


# Home route
@app.route("/")
def index():
    return render_template("index.html", google_maps_api_key=GOOGLE_MAPS_API_KEY)


if __name__ == "__main__":
    app.run(debug=True)
