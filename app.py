from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import current_user, login_user, logout_user, LoginManager
import folium
import requests
import os
from datetime import datetime, timedelta
import polyline
from models import db, User, RouteHistory, Task, Expense
from pyowm import OWM
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from dotenv import load_dotenv
from functools import wraps

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")
# app.config['SESSION_TYPE'] = 'filesystem'  # Removed because we're not using Flask-Session
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///planner.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize extensions
db.init_app(app)
# Session(app)

# Custom login_required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

# Initialize OpenWeatherMap
owm = OWM(os.getenv("WEATHER_API_KEY"))
mgr = owm.weather_manager()

with app.app_context():
    db.create_all()

@app.route("/")
@login_required
def index():
    tasks = Task.query.filter_by(user_id=current_user.id).order_by(Task.date, Task.time).all()
    expenses = Expense.query.filter_by(user_id=current_user.id).order_by(Expense.date.desc()).all()

    return render_template("index.html",
                         google_maps_api_key=os.getenv("AIzaSyAl8f5_lixzi2wHH19dOnRXha9as3HTeBY"),
                         tasks=tasks,
                         expenses=expenses,
                         theme=current_user.theme_preference)

@app.route("/get_route", methods=["POST"])
@login_required
def get_route():
    start = request.form["start"]
    destination = request.form["destination"]
    stops = request.form.getlist("stops[]")
    stops = [stop for stop in stops if stop]

    # Get weather data for the route
    try:
        weather_data = mgr.weather_at_place(start).weather
        weather_status = weather_data.status
        temperature = weather_data.temperature('celsius')['temp']
    except Exception as e:
        app.logger.error(f"Weather fetch failed: {e}")
        weather_status = 'Unknown'
        temperature = 'N/A'

    # Create a map centered on the start location
    try:
        geocoding_url = f"https://maps.googleapis.com/maps/api/geocode/json?address={start}&key={os.getenv('GOOGLE_MAPS_API_KEY')}"
        response = requests.get(geocoding_url)
        start_location = response.json()["results"][0]["geometry"]["location"]
    except Exception as e:
        app.logger.error(f"Geocoding failed: {e}")
        flash("Could not get map location. Please try again.")
        return redirect(url_for('index'))

    m = folium.Map(location=[start_location["lat"], start_location["lng"]], zoom_start=12)

    # Get route from Google Maps API
    waypoints = "|".join(stops) if stops else ""
    directions_url = f"https://maps.googleapis.com/maps/api/directions/json?origin={start}&destination={destination}&waypoints={waypoints}&mode=driving&key={os.getenv('GOOGLE_MAPS_API_KEY')}"
    route_data = requests.get(directions_url).json()

    if route_data["status"] == "OK":
        route = route_data["routes"][0]
        route_polyline = route["overview_polyline"]["points"]
        decoded_route = polyline.decode(route_polyline)

        # Add weather-based route styling
        route_color = 'blue' if weather_status == 'Clear' else 'red'
        folium.PolyLine(
            decoded_route,
            weight=2,
            color=route_color,
            opacity=0.8
        ).add_to(m)

        # Add markers with weather info
        weather_info = f"Start - Weather: {weather_status}, Temp: {temperature}°C"
        folium.Marker(
            [start_location["lat"], start_location["lng"]],
            popup=weather_info
        ).add_to(m)

        # Save route history for AI suggestions
        route_history = RouteHistory(
            user_id=current_user.id,
            start_location=start,
            end_location=destination,
            stops=','.join(stops) if stops else None,
            weather_conditions=weather_status,
            travel_mode='driving',
            estimated_duration=route["legs"][0]["duration"]["value"]
        )
        db.session.add(route_history)
        db.session.commit()

        # Add expense estimation
        distance = route["legs"][0]["distance"]["value"] / 1000  # Convert to km
        fuel_cost = distance * 0.15  # Estimated fuel cost per km

        expense = Expense(
            user_id=current_user.id,
            amount=fuel_cost,
            category='Transportation',
            description=f'Estimated fuel cost for {distance:.1f}km trip',
            date=datetime.now().date(),
            route_id=route_history.id,
            transport_type='driving',
            distance=distance
        )
        db.session.add(expense)
        db.session.commit()

        # Get similar routes for suggestions
        similar_routes = RouteHistory.query.filter_by(
            user_id=current_user.id,
            start_location=start,
            end_location=destination
        ).order_by(RouteHistory.created_at.desc()).limit(5).all()

        return render_template("index.html",
                             google_maps_api_key=os.getenv("GOOGLE_MAPS_API_KEY"),
                             map_html=m._repr_html_(),
                             weather_status=weather_status,
                             temperature=temperature,
                             estimated_cost=fuel_cost,
                             similar_routes=similar_routes,
                             tasks=Task.query.filter_by(user_id=current_user.id).all(),
                             expenses=Expense.query.filter_by(user_id=current_user.id).all())

    # If route not found, return to index with current tasks and expenses
    tasks = Task.query.filter_by(user_id=current_user.id).order_by(Task.date, Task.time).all()
    expenses = Expense.query.filter_by(user_id=current_user.id).order_by(Expense.date.desc()).all()

    return render_template("index.html",
                         google_maps_api_key=os.getenv("GOOGLE_MAPS_API_KEY"),
                         map_html=m._repr_html_(),
                         tasks=tasks,
                         expenses=expenses)

@app.route("/add_task", methods=["POST"])
@login_required
def add_task():
    task = request.form["task"]
    date = datetime.strptime(request.form["date"], "%Y-%m-%d").date()
    time = datetime.strptime(request.form["time"], "%H:%M").time()

    new_task = Task(
        user_id=current_user.id,
        task=task,
        date=date,
        time=time
    )
    db.session.add(new_task)
    db.session.commit()

    return redirect(url_for('index'))

@app.route("/add_expense", methods=["POST"])
@login_required
def add_expense():
    amount = float(request.form["amount"])
    category = request.form["category"]
    description = request.form.get("description", "")
    date = datetime.strptime(request.form["date"], "%Y-%m-%d").date()

    expense = Expense(
        user_id=current_user.id,
        amount=amount,
        category=category,
        description=description,
        date=date
    )
    db.session.add(expense)
    db.session.commit()

    return redirect(url_for('index'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        try:
            username = request.form.get('username')
            password = request.form.get('password')

            if not username or not password:
                flash('Username and password are required')
                return redirect(url_for('login'))

            user = User.query.filter_by(username=username).first()

            if user and check_password_hash(user.password_hash, password):
                login_user(user, remember=True)
                session.permanent = True
                app.permanent_session_lifetime = timedelta(days=31)
                next_page = request.args.get('next')
                if next_page:
                    # Ensure the next_page is a relative URL and not an absolute URL to prevent open redirect
                    if not next_page.startswith('//') and not next_page.startswith('http'):
                        return redirect(next_page)
                return redirect(url_for('index'))

            flash('Invalid username or password')
            return redirect(url_for('login'))

        except Exception as e:
            app.logger.error(f'Login error: {str(e)}')
            flash('An error occurred during login. Please try again.')
            return redirect(url_for('login'))

    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        if password != confirm_password:
            flash('Passwords do not match')
            return render_template('register.html')

        if User.query.filter_by(username=username).first():
            flash('Username already exists')
            return render_template('register.html')

        if User.query.filter_by(email=email).first():
            flash('Email already registered')
            return render_template('register.html')

        user = User(username=username, email=email)
        user.password_hash = generate_password_hash(password)

        db.session.add(user)
        db.session.commit()

        flash('Registration successful! Please login.')
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/api/tasks', methods=['GET'])
@login_required
def api_get_tasks():
    tasks = Task.query.filter_by(user_id=current_user.id).all()
    return jsonify([task.to_dict() for task in tasks])

if __name__ == "__main__":
    app.run(debug=True)
