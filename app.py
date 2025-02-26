from flask import Flask, render_template, request, jsonify, redirect, url_for
import sqlite3
import requests
import os
from datetime import datetime
import folium

app = Flask(__name__)
app.secret_key = "b'[z!\xa0m\x1bOX\x17y\xb6\x01f\x92\x9e\x81\x8d\x99\xc2\x96\xe6\x07\x93\x9f'"

GOOGLE_MAPS_API_KEY = "AIzaSyAl8f5_lixzi2wHH19dOnRXha9as3HTeBY"


# Ensure database setup
def init_db():
    with sqlite3.connect("planner.db") as conn:
        cursor = conn.cursor()
        # Task Planner Table
        cursor.execute('''CREATE TABLE IF NOT EXISTS tasks (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            task TEXT NOT NULL,
                            date TEXT NOT NULL,
                            time TEXT NOT NULL)''')

        # Expense Tracking Table
        cursor.execute('''CREATE TABLE IF NOT EXISTS expenses (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            amount REAL NOT NULL,
                            category TEXT NOT NULL,
                            description TEXT,
                            date TEXT NOT NULL)''')

        conn.commit()


init_db()  # Initialize the database


# 📍 Get Current Location
def get_current_location():
    response = requests.get("https://ipinfo.io/json")
    data = response.json()
    location = data.get("loc", "37.7749,-122.4194")  # Default to SF if not found
    return location.split(",")


# 🗺️ Get Route
def get_route(start, destination, travel_mode="driving"):
    url = f"https://maps.googleapis.com/maps/api/directions/json?origin={start}&destination={destination}&mode={travel_mode}&key={GOOGLE_MAPS_API_KEY}"
    response = requests.get(url)
    return response.json()


@app.route("/", methods=["GET", "POST"])
def index():
    route_data = None
    start_location, end_location, mode = "", "", "driving"

    if request.method == "POST":
        start_location = request.form.get("start")
        end_location = request.form.get("destination")
        mode = request.form.get("mode", "driving")

        if start_location and end_location:
            route_data = get_route(start_location, end_location, mode)

    # Fetch tasks
    with sqlite3.connect("planner.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, task, date, time FROM tasks ORDER BY date, time")
        tasks = cursor.fetchall()

    # Fetch expenses
    with sqlite3.connect("planner.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, amount, category, description, date FROM expenses ORDER BY date DESC")
        expenses = cursor.fetchall()

    user_location = get_current_location()

    return render_template("index.html", route_data=route_data, tasks=tasks, expenses=expenses,
                           user_location=user_location, start=start_location, destination=end_location, mode=mode)


# ✅ Add Task
@app.route("/add_task", methods=["POST"])
def add_task():
    task_name = request.form.get("task_name")
    date = request.form.get("date")
    time = request.form.get("time")

    with sqlite3.connect("planner.db") as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO tasks (task, date, time) VALUES (?, ?, ?)", (task_name, date, time))
        conn.commit()

    return redirect(url_for("index"))


# ❌ Delete Task
@app.route("/delete_task/<int:task_id>")
def delete_task(task_id):
    with sqlite3.connect("planner.db") as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        conn.commit()
    return redirect(url_for("index"))


# 💰 Add Expense
@app.route("/add_expense", methods=["POST"])
def add_expense():
    amount = request.form.get("amount")
    category = request.form.get("category")
    description = request.form.get("description")
    date = request.form.get("date")

    with sqlite3.connect("planner.db") as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO expenses (amount, category, description, date) VALUES (?, ?, ?, ?)",
                       (amount, category, description, date))
        conn.commit()

    return redirect(url_for("index"))


# ❌ Delete Expense
@app.route("/delete_expense/<int:expense_id>")
def delete_expense(expense_id):
    with sqlite3.connect("planner.db") as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
        conn.commit()
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True)
