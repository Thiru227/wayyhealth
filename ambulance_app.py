from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_pymongo import PyMongo
from datetime import datetime
from bson.objectid import ObjectId
from werkzeug.security import check_password_hash
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('AMBULANCE_SECRET', 'your-ambulance-secret-key')
app.config['MONGO_URI'] = os.getenv('MONGO_URI') or 'mongodb+srv://praveensah2608_db_user:XEDQI2M5OWk4I3EE@cluster0.lilts6y.mongodb.net/lifelink_grid?retryWrites=true&w=majority'

mongo = PyMongo(app)

ambulances = mongo.db.ambulances
emergency_requests = mongo.db.emergency_requests
activities = mongo.db.activities
notifications = mongo.db.notifications
blood_requests = mongo.db.blood_requests
ai_logs = mongo.db.ai_logs

@app.route('/')
def index():
    if 'ambulance_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.json
        
        ambulance = ambulances.find_one({'device_id': data['device_id']})
        
        if ambulance and check_password_hash(ambulance['password'], data['password']):
            session['ambulance_id'] = str(ambulance['_id'])
            session['device_id'] = ambulance['device_id']
            session['vehicle_number'] = ambulance['vehicle_number']
            session['driver_name'] = ambulance.get('driver_name', 'Driver')
            
            # Mark ambulance as AVAILABLE when logged in
            ambulances.update_one(
                {'_id': ambulance['_id']},
                {'$set': {
                    'status': 'available',
                    'last_seen': datetime.now()
                }}
            )
            
            # AI Log
            ai_logs.insert_one({
                'log_type': 'ambulance_status',
                'action': 'came_online',
                'vehicle_number': ambulance['vehicle_number'],
                'driver_name': ambulance.get('driver_name', 'Unknown'),
                'status': 'success',
                'timestamp': datetime.now()
            })
            
            activities.insert_one({
                'type': 'ambulance_online',
                'message': f"🚑 {ambulance['vehicle_number']} came online (Available)",
                'timestamp': datetime.now()
            })
            
            return jsonify({'success': True})
        
        return jsonify({'success': False, 'message': 'Invalid credentials'}), 401
    
    return render_template('ambulance_login.html')

@app.route('/dashboard')
def dashboard():
    if 'ambulance_id' not in session:
        return redirect(url_for('login'))
    
    ambulance_id = ObjectId(session['ambulance_id'])
    ambulance = ambulances.find_one({'_id': ambulance_id})
    
    # Check for ASSIGNED emergency (waiting for accept/decline - 1 min timer)
    assigned_emergency = emergency_requests.find_one({
        'assigned_ambulance_id': ambulance_id,
        'status': 'assigned'
    })
    
    # Calculate time remaining for acceptance (only if assigned)
    if assigned_emergency and 'assigned_at' in assigned_emergency:
        elapsed = (datetime.now() - assigned_emergency['assigned_at']).total_seconds()
        time_remaining = max(0, 60 - int(elapsed))
        assigned_emergency['time_remaining'] = time_remaining
    
    # Check for ON-DUTY emergency (accepted and actively responding)
    on_duty_emergency = emergency_requests.find_one({
        'assigned_ambulance_id': ambulance_id,
        'status': 'on_duty'
    })
    
    # Calculate elapsed time for on-duty emergency
    if on_duty_emergency and 'accepted_at' in on_duty_emergency:
        elapsed = (datetime.now() - on_duty_emergency['accepted_at']).total_seconds() / 60
        on_duty_emergency['elapsed_minutes'] = int(elapsed)
    
    # Check for blood transport
    active_blood_transport = blood_requests.find_one({
        'ambulance_id': ambulance_id,
        'status': {'$in': ['approved', 'in_transit']}
    })
    
    return render_template('ambulance_dashboard.html',
                         ambulance=ambulance,
                         assigned_emergency=assigned_emergency,
                         on_duty_emergency=on_duty_emergency,
                         active_blood_transport=active_blood_transport)

@app.route('/accept-emergency/<emergency_id>', methods=['POST'])
def accept_emergency(emergency_id):
    """
    Accept assigned emergency - Status: assigned → on_duty
    NO TIMER once accepted - stays on_duty until driver marks complete
    """
    if 'ambulance_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    ambulance_id = ObjectId(session['ambulance_id'])
    ambulance = ambulances.find_one({'_id': ambulance_id})
    
    # Update emergency status to 'on_duty' (no more timer)
    emergency = emergency_requests.find_one_and_update(
        {'_id': ObjectId(emergency_id)},
        {'$set': {
            'status': 'on_duty',
            'accepted_at': datetime.now()
        }},
        return_document=True
    )
    
    if not emergency:
        return jsonify({'error': 'Emergency not found'}), 404
    
    # Update ambulance status to 'on_duty' (will stay until driver marks complete)
    ambulances.update_one(
        {'_id': ambulance_id},
        {'$set': {
            'status': 'on_duty',
            'current_emergency_id': ObjectId(emergency_id)
        }}
    )
    
    # Calculate response time
    response_time = (datetime.now() - emergency['assigned_at']).total_seconds()
    
    # AI Log
    ai_logs.insert_one({
        'log_type': 'emergency_response',
        'action': 'accepted',
        'vehicle_number': ambulance['vehicle_number'],
        'driver_name': ambulance.get('driver_name', 'Unknown'),
        'emergency_id': str(emergency_id),
        'location': emergency['location']['address'],
        'severity': emergency.get('severity', 'unknown'),
        'response_time_seconds': response_time,
        'status': 'success',
        'timestamp': datetime.now()
    })
    
    # Notification
    notifications.insert_one({
        'type': 'emergency_accepted',
        'title': '✓ Emergency Accepted',
        'message': f"Ambulance {ambulance['vehicle_number']} accepted and is ON DUTY - En route to emergency",
        'priority': 'high',
        'read': False,
        'created_at': datetime.now()
    })
    
    # Activity
    activities.insert_one({
        'type': 'emergency_accepted',
        'message': f"✓ {ambulance['vehicle_number']} accepted emergency at {emergency['location']['address']} - NOW ON DUTY",
        'timestamp': datetime.now()
    })
    
    # Google Maps link
    google_maps_link = f"https://www.google.com/maps?q={emergency['location']['lat']},{emergency['location']['lng']}"
    
    return jsonify({
        'success': True,
        'google_maps_link': google_maps_link,
        'message': 'Emergency accepted - You are now ON DUTY. Complete the mission to become available again.',
        'emergency': {
            'address': emergency['location']['address'],
            'severity': emergency.get('severity', 'unknown')
        }
    })

@app.route('/decline-emergency/<emergency_id>', methods=['POST'])
def decline_emergency(emergency_id):
    """Decline assigned emergency - Status: assigned → available"""
    if 'ambulance_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    ambulance_id = ObjectId(session['ambulance_id'])
    ambulance = ambulances.find_one({'_id': ambulance_id})
    
    emergency = emergency_requests.find_one({'_id': ObjectId(emergency_id)})
    
    # AI Log
    ai_logs.insert_one({
        'log_type': 'emergency_response',
        'action': 'declined',
        'vehicle_number': ambulance['vehicle_number'],
        'driver_name': ambulance.get('driver_name', 'Unknown'),
        'emergency_id': str(emergency_id),
        'location': emergency['location']['address'] if emergency else 'Unknown',
        'reason': 'Driver manually declined',
        'status': 'failed',
        'timestamp': datetime.now()
    })
    
    # Reset emergency to pending
    emergency_requests.update_one(
        {'_id': ObjectId(emergency_id)},
        {'$set': {
            'status': 'pending',
            'assigned_ambulance_id': None,
            'assigned_ambulance_number': None,
            'assigned_distance': None,
            'assigned_at': None
        }}
    )
    
    # Reset ambulance to available
    ambulances.update_one(
        {'_id': ambulance_id},
        {'$set': {
            'status': 'available',
            'assigned_emergency_id': None
        }}
    )
    
    # Notification
    notifications.insert_one({
        'type': 'emergency_declined',
        'title': 'Emergency Declined',
        'message': f"Ambulance {ambulance['vehicle_number']} declined. Finding alternative...",
        'priority': 'high',
        'read': False,
        'created_at': datetime.now()
    })
    
    # Activity
    activities.insert_one({
        'type': 'emergency_declined',
        'message': f"✗ {ambulance['vehicle_number']} declined assignment",
        'timestamp': datetime.now()
    })
    
    return jsonify({'success': True, 'message': 'Emergency declined - You are now available for new assignments'})

@app.route('/complete-emergency/<emergency_id>', methods=['POST'])
def complete_emergency(emergency_id):
    """
    Mark emergency as completed - Status: on_duty → available
    Updates: Life saving count, response time stats
    """
    if 'ambulance_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    ambulance_id = ObjectId(session['ambulance_id'])
    ambulance = ambulances.find_one({'_id': ambulance_id})
    
    emergency = emergency_requests.find_one({'_id': ObjectId(emergency_id)})
    
    # Calculate times
    total_time = None
    response_time = None
    
    if emergency and 'created_at' in emergency:
        # Total time from emergency creation to completion
        total_time = (datetime.now() - emergency['created_at']).total_seconds() / 60
        
        # Response time from emergency creation to ambulance acceptance
        if 'accepted_at' in emergency:
            response_time = (emergency['accepted_at'] - emergency['created_at']).total_seconds() / 60
    
    # Update emergency
    emergency_requests.update_one(
        {'_id': ObjectId(emergency_id)},
        {'$set': {
            'status': 'completed',
            'completed_at': datetime.now(),
            'total_time_minutes': round(total_time, 1) if total_time else None,
            'response_time_minutes': round(response_time, 1) if response_time else None
        }}
    )
    
    # Update ambulance back to AVAILABLE and increment missions completed
    ambulances.update_one(
        {'_id': ambulance_id},
        {
            '$set': {
                'status': 'available',
                'current_emergency_id': None,
                'assigned_emergency_id': None
            },
            '$inc': {
                'missions_completed': 1
            }
        }
    )
    
    # Calculate lives saved (number of patients)
    lives_saved = emergency.get('patient_count', 1) if emergency else 1
    
    # Record life-saving activity for each patient
    for i in range(lives_saved):
        activities.insert_one({
            'type': 'life_saved',
            'emergency_id': emergency_id,
            'ambulance_id': ambulance_id,
            'vehicle_number': ambulance['vehicle_number'],
            'driver_name': ambulance.get('driver_name', 'Unknown'),
            'patient_number': i + 1,
            'total_patients': lives_saved,
            'response_time_minutes': round(response_time, 1) if response_time else None,
            'timestamp': datetime.now()
        })
    
    # AI Log
    ai_logs.insert_one({
        'log_type': 'emergency_response',
        'action': 'completed',
        'vehicle_number': ambulance['vehicle_number'],
        'driver_name': ambulance.get('driver_name', 'Unknown'),
        'emergency_id': str(emergency_id),
        'location': emergency['location']['address'] if emergency else 'Unknown',
        'lives_saved': lives_saved,
        'response_time_minutes': round(response_time, 1) if response_time else None,
        'total_time_minutes': round(total_time, 1) if total_time else None,
        'status': 'success',
        'timestamp': datetime.now()
    })
    
    # Notification
    notifications.insert_one({
        'type': 'emergency_completed',
        'title': '✓ Emergency Completed',
        'message': f"Ambulance {ambulance['vehicle_number']} completed mission - {lives_saved} {'life' if lives_saved == 1 else 'lives'} saved! Now AVAILABLE.",
        'priority': 'medium',
        'read': False,
        'created_at': datetime.now()
    })
    
    # Activity
    activities.insert_one({
        'type': 'emergency_completed',
        'message': f"✓ {ambulance['vehicle_number']} completed emergency - {lives_saved} {'life' if lives_saved == 1 else 'lives'} saved! (Response: {round(response_time, 1) if response_time else 'N/A'}min, Total: {round(total_time, 1) if total_time else 'N/A'}min)",
        'timestamp': datetime.now()
    })
    
    return jsonify({
        'success': True,
        'message': f'Mission completed! {lives_saved} {"life" if lives_saved == 1 else "lives"} saved! You are now AVAILABLE.',
        'lives_saved': lives_saved,
        'response_time': round(response_time, 1) if response_time else None,
        'total_time': round(total_time, 1) if total_time else None
    })

@app.route('/complete-blood-transport/<request_id>', methods=['POST'])
def complete_blood_transport(request_id):
    """Complete blood transport"""
    if 'ambulance_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    ambulance_id = ObjectId(session['ambulance_id'])
    ambulance = ambulances.find_one({'_id': ambulance_id})
    
    # Update blood request
    blood_requests.update_one(
        {'_id': ObjectId(request_id)},
        {'$set': {
            'status': 'completed',
            'completed_at': datetime.now()
        }}
    )
    
    # Update ambulance to available
    ambulances.update_one(
        {'_id': ambulance_id},
        {'$set': {'status': 'available'}}
    )
    
    # AI Log
    ai_logs.insert_one({
        'log_type': 'blood_transport',
        'action': 'completed',
        'vehicle_number': ambulance['vehicle_number'],
        'request_id': str(request_id),
        'status': 'success',
        'timestamp': datetime.now()
    })
    
    activities.insert_one({
        'type': 'blood_transport_completed',
        'message': f"🩸 {ambulance['vehicle_number']} completed blood delivery - AVAILABLE AGAIN",
        'timestamp': datetime.now()
    })
    
    return jsonify({'success': True})

@app.route('/update-location', methods=['POST'])
def update_location():
    """Update ambulance GPS location"""
    if 'ambulance_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.json
    ambulance_id = ObjectId(session['ambulance_id'])
    
    ambulances.update_one(
        {'_id': ambulance_id},
        {'$set': {
            'current_location': {
                'lat': float(data['latitude']),
                'lng': float(data['longitude'])
            },
            'last_seen': datetime.now()
        }}
    )
    
    return jsonify({'success': True})

@app.route('/logout')
def logout():
    if 'ambulance_id' in session:
        ambulance = ambulances.find_one({'_id': ObjectId(session['ambulance_id'])})
        
        # Mark ambulance as OFFLINE
        ambulances.update_one(
            {'_id': ObjectId(session['ambulance_id'])},
            {'$set': {
                'status': 'offline',
                'last_seen': datetime.now()
            }}
        )
        
        # AI Log
        ai_logs.insert_one({
            'log_type': 'ambulance_status',
            'action': 'went_offline',
            'vehicle_number': session.get('vehicle_number', 'Unknown'),
            'driver_name': session.get('driver_name', 'Unknown'),
            'status': 'success',
            'timestamp': datetime.now()
        })
        
        activities.insert_one({
            'type': 'ambulance_offline',
            'message': f"🚑 {session['vehicle_number']} went offline",
            'timestamp': datetime.now()
        })
    
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True, port=5002, host='0.0.0.0')