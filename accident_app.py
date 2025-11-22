from flask import Flask, render_template, request, jsonify, session
from flask_pymongo import PyMongo
from datetime import datetime
from bson.objectid import ObjectId
import os
import requests

app = Flask(__name__)
app.config['SECRET_KEY'] = 'accident-register-secret-key'
app.config['MONGO_URI'] = os.getenv('MONGO_URI') or 'mongodb+srv://praveensah2608_db_user:XEDQI2M5OWk4I3EE@cluster0.lilts6y.mongodb.net/lifelink_grid?retryWrites=true&w=majority'

mongo = PyMongo(app)

# Collections
emergency_requests = mongo.db.emergency_requests
ambulances = mongo.db.ambulances
activities = mongo.db.activities

def calculate_distance(lat1, lng1, lat2, lng2):
    """Calculate distance between two points (simplified)"""
    from math import radians, sin, cos, sqrt, atan2
    
    R = 6371  # Earth's radius in km
    
    lat1, lng1, lat2, lng2 = map(radians, [lat1, lng1, lat2, lng2])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlng/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    distance = R * c
    
    return distance

@app.route('/')
def index():
    return render_template('accident_register.html')

@app.route('/report-accident', methods=['POST'])
def report_accident():
    data = request.json
    
    # Create emergency request
    emergency = {
        'type': 'accident',
        'location': {
            'lat': float(data['latitude']),
            'lng': float(data['longitude']),
            'address': data.get('address', 'Unknown location')
        },
        'severity': data.get('severity', 'medium'),  # low, medium, high, critical
        'patient_count': int(data.get('patient_count', 1)),
        'description': data.get('description', ''),
        'caller_name': data.get('caller_name', 'Anonymous'),
        'caller_phone': data.get('caller_phone', ''),
        'injuries': data.get('injuries', []),  # Types of injuries
        'vehicle_involved': data.get('vehicle_involved', False),
        'fire_hazard': data.get('fire_hazard', False),
        'chemical_hazard': data.get('chemical_hazard', False),
        'blood_type_needed': data.get('blood_type_needed'),
        'status': 'pending',
        'created_at': datetime.now(),
        'notified_ambulances': []
    }
    
    result = emergency_requests.insert_one(emergency)
    emergency_id = result.inserted_id
    
    # Find nearest available ambulances
    available_ambulances = list(ambulances.find({'status': 'available'}))
    
    nearest_ambulances = []
    for amb in available_ambulances:
        if 'current_location' in amb:
            distance = calculate_distance(
                emergency['location']['lat'],
                emergency['location']['lng'],
                amb['current_location']['lat'],
                amb['current_location']['lng']
            )
            nearest_ambulances.append({
                '_id': str(amb['_id']),
                'vehicle_number': amb['vehicle_number'],
                'driver_name': amb.get('driver_name', 'Unknown'),
                'driver_phone': amb.get('driver_phone', ''),
                'distance': round(distance, 2),
                'ambulance_type': amb.get('ambulance_type', 'basic'),
                'equipment': amb.get('equipment', [])
            })
    
    # Sort by distance
    nearest_ambulances.sort(key=lambda x: x['distance'])
    
    # Take top 5 nearest
    nearest_5 = nearest_ambulances[:5]
    
    # Log activity
    activities.insert_one({
        'type': 'emergency_reported',
        'message': f"Accident reported at {emergency['location']['address']}",
        'severity': emergency['severity'],
        'timestamp': datetime.now()
    })
    
    return jsonify({
        'success': True,
        'emergency_id': str(emergency_id),
        'nearest_ambulances': nearest_5,
        'estimated_arrival': f"{nearest_5[0]['distance'] * 3:.0f} minutes" if nearest_5 else "Unknown"
    })

@app.route('/get-location-from-ip')
def get_location_from_ip():
    """Get approximate location from IP address"""
    try:
        # Using ipapi.co for geolocation
        response = requests.get('https://ipapi.co/json/')
        data = response.json()
        
        return jsonify({
            'latitude': data.get('latitude'),
            'longitude': data.get('longitude'),
            'city': data.get('city'),
            'region': data.get('region'),
            'country': data.get('country_name')
        })
    except:
        # Default to a central location if API fails
        return jsonify({
            'latitude': 12.9716,
            'longitude': 77.5946,
            'city': 'Bangalore',
            'region': 'Karnataka',
            'country': 'India'
        })

@app.route('/emergency-status/<emergency_id>')
def emergency_status(emergency_id):
    """Check status of reported emergency"""
    emergency = emergency_requests.find_one({'_id': ObjectId(emergency_id)})
    
    if not emergency:
        return jsonify({'error': 'Emergency not found'}), 404
    
    response_data = {
        'status': emergency['status'],
        'created_at': emergency['created_at'].isoformat(),
        'severity': emergency['severity']
    }
    
    if emergency['status'] == 'accepted':
        # Get ambulance details
        ambulance = ambulances.find_one({'_id': emergency.get('assigned_ambulance')})
        if ambulance:
            response_data['ambulance'] = {
                'vehicle_number': ambulance['vehicle_number'],
                'driver_name': ambulance.get('driver_name'),
                'driver_phone': ambulance.get('driver_phone'),
                'current_location': ambulance.get('current_location')
            }
            response_data['accepted_at'] = emergency.get('accepted_at').isoformat()
    
    return jsonify(response_data)

if __name__ == '__main__':
    app.run(debug=True, port=5003)