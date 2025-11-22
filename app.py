from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_pymongo import PyMongo
from datetime import datetime, timedelta
import os
from bson.objectid import ObjectId
from math import radians, sin, cos, sqrt, atan2
import secrets

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('CONTROL_ROOM_SECRET', 'your-secret-key-here')
app.config['MONGO_URI'] = os.getenv('MONGO_URI') or 'mongodb+srv://praveensah2608_db_user:XEDQI2M5OWk4I3EE@cluster0.lilts6y.mongodb.net/lifelink_grid?retryWrites=true&w=majority'

mongo = PyMongo(app)

# Collections
hospitals = mongo.db.hospitals
blood_inventory = mongo.db.blood_inventory
blood_units = mongo.db.blood_units
ambulances = mongo.db.ambulances
emergency_requests = mongo.db.emergency_requests
donors = mongo.db.donors
organizations = mongo.db.organizations
activities = mongo.db.activities
blood_requests = mongo.db.blood_requests
notifications = mongo.db.notifications
ai_logs = mongo.db.ai_logs
blood_transfers = mongo.db.blood_transfers

def calculate_distance(lat1, lng1, lat2, lng2):
    """Calculate distance in kilometers"""
    R = 6371
    lat1, lng1, lat2, lng2 = map(radians, [lat1, lng1, lat2, lng2])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlng/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    return R * c

def check_expired_assignments():
    """Only check for expired assignments during the 1-minute acceptance window"""
    expired_time = datetime.now() - timedelta(minutes=1)
    
    expired_emergencies = emergency_requests.find({
        'status': 'assigned',
        'assigned_at': {'$lt': expired_time}
    })
    
    for emergency in expired_emergencies:
        ai_logs.insert_one({
            'log_type': 'assignment_expired',
            'action': 'auto_declined',
            'emergency_id': emergency['_id'],
            'ambulance_id': emergency.get('assigned_ambulance_id'),
            'vehicle_number': emergency.get('assigned_ambulance_number'),
            'reason': 'Driver did not respond within 1 minute',
            'timestamp': datetime.now(),
            'status': 'failed'
        })
        
        emergency_requests.update_one(
            {'_id': emergency['_id']},
            {'$set': {
                'status': 'pending',
                'assigned_ambulance_id': None,
                'assigned_ambulance_number': None,
                'assigned_distance': None,
                'assigned_at': None
            }}
        )
        
        if emergency.get('assigned_ambulance_id'):
            ambulances.update_one(
                {'_id': emergency['assigned_ambulance_id']},
                {'$set': {
                    'status': 'available',
                    'assigned_emergency_id': None
                }}
            )
            
            notifications.insert_one({
                'type': 'assignment_expired',
                'title': 'Assignment Expired',
                'message': f"Ambulance {emergency.get('assigned_ambulance_number')} did not respond. Retrying...",
                'priority': 'high',
                'read': False,
                'created_at': datetime.now()
            })

def cleanup_old_pending_emergencies():
    """Mark old pending emergencies as cancelled if they're more than 30 minutes old"""
    cutoff_time = datetime.now() - timedelta(minutes=30)
    
    old_pending = emergency_requests.find({
        'status': 'pending',
        'created_at': {'$lt': cutoff_time}
    })
    
    count = 0
    for emergency in old_pending:
        emergency_requests.update_one(
            {'_id': emergency['_id']},
            {'$set': {
                'status': 'cancelled',
                'cancelled_at': datetime.now(),
                'cancellation_reason': 'No ambulances available for 30 minutes'
            }}
        )
        
        notifications.insert_one({
            'type': 'emergency_cancelled',
            'title': 'Emergency Cancelled',
            'message': f"Emergency at {emergency['location']['address']} cancelled - no ambulances available",
            'priority': 'medium',
            'read': False,
            'created_at': datetime.now()
        })
        
        count += 1
    
    if count > 0:
        activities.insert_one({
            'type': 'emergencies_cancelled',
            'message': f"⚠️ {count} old pending emergencies cancelled (no ambulances available)",
            'timestamp': datetime.now()
        })

def retry_pending_emergencies():
    """Try to assign ambulances to pending emergencies"""
    pending_emergencies = list(emergency_requests.find({
        'status': 'pending'
    }).sort('created_at', 1))
    
    if not pending_emergencies:
        return
    
    for emergency in pending_emergencies:
        match = ai_match_ambulance(emergency['location'], emergency['severity'])
        
        if match:
            # Update emergency with assignment
            emergency_requests.update_one(
                {'_id': emergency['_id']},
                {'$set': {
                    'assigned_ambulance_id': match['ambulance']['_id'],
                    'assigned_ambulance_number': match['ambulance']['vehicle_number'],
                    'assigned_distance': round(match['distance'], 2),
                    'assigned_at': datetime.now(),
                    'status': 'assigned'
                }}
            )
            
            # Update ambulance
            ambulances.update_one(
                {'_id': match['ambulance']['_id']},
                {'$set': {
                    'status': 'assigned',
                    'assigned_emergency_id': emergency['_id']
                }}
            )
            
            # Notification
            notifications.insert_one({
                'type': 'emergency_assigned',
                'title': '✓ Ambulance Found!',
                'message': f"Ambulance {match['ambulance']['vehicle_number']} assigned to pending emergency at {emergency['location']['address']}",
                'priority': 'high',
                'read': False,
                'created_at': datetime.now()
            })
            
            activities.insert_one({
                'type': 'pending_emergency_assigned',
                'message': f"✓ Pending emergency assigned: {match['ambulance']['vehicle_number']} → {emergency['location']['address']}",
                'timestamp': datetime.now()
            })

def ai_match_ambulance(emergency_location, severity):
    """AI system to match nearest AVAILABLE ambulance"""
    available_ambulances = list(ambulances.find({'status': 'available'}))
    
    if not available_ambulances:
        return None
    
    scored_ambulances = []
    for amb in available_ambulances:
        if 'current_location' not in amb:
            continue
            
        distance = calculate_distance(
            emergency_location['lat'],
            emergency_location['lng'],
            amb['current_location']['lat'],
            amb['current_location']['lng']
        )
        
        score = 100 - (distance * 2)
        if amb['ambulance_type'] == 'advanced' and severity in ['high', 'critical']:
            score += 20
        
        scored_ambulances.append({
            'ambulance': amb,
            'distance': distance,
            'score': score
        })
    
    if not scored_ambulances:
        return None
    
    scored_ambulances.sort(key=lambda x: x['score'], reverse=True)
    best_match = scored_ambulances[0]
    
    ai_logs.insert_one({
        'log_type': 'ambulance_assignment',
        'action': 'assigned',
        'ambulance_id': str(best_match['ambulance']['_id']),
        'vehicle_number': best_match['ambulance']['vehicle_number'],
        'driver_name': best_match['ambulance'].get('driver_name', 'Unknown'),
        'distance_km': round(best_match['distance'], 2),
        'score': round(best_match['score'], 2),
        'emergency_location': emergency_location,
        'severity': severity,
        'alternatives_count': len(scored_ambulances) - 1,
        'acceptance_deadline': datetime.now() + timedelta(minutes=1),
        'timestamp': datetime.now(),
        'status': 'success'
    })
    
    return best_match

@app.route('/')
def index():
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
def dashboard():
    # Maintenance tasks
    check_expired_assignments()
    cleanup_old_pending_emergencies()
    retry_pending_emergencies()
    
    # Statistics
    # Lives saved = sum of all patients from completed emergencies
    total_lives_saved = 0
    completed_emergencies = emergency_requests.find({'status': 'completed'})
    for emergency in completed_emergencies:
        total_lives_saved += emergency.get('patient_count', 1)
    
    # Alternative: Count life_saved activities
    # total_lives_saved = activities.count_documents({'type': 'life_saved'})
    
    # Average response time (time from emergency creation to ambulance acceptance)
    recent_emergencies = list(emergency_requests.find({
        'status': 'completed',
        'response_time_minutes': {'$exists': True}
    }).limit(50))
    
    response_times = [e['response_time_minutes'] for e in recent_emergencies if 'response_time_minutes' in e]
    avg_response_time = sum(response_times) / len(response_times) if response_times else 0
    
    active_donors = donors.count_documents({'status': 'active'})
    
    # Active emergencies - show 'assigned' and 'on_duty' ONLY
    active_emergencies = list(emergency_requests.find({
        'status': {'$in': ['assigned', 'on_duty']}
    }).sort('created_at', -1))
    
    # Pending emergencies (waiting for ambulance)
    pending_emergencies = list(emergency_requests.find({
        'status': 'pending'
    }).sort('created_at', -1))
    
    # Get ambulance details
    for emergency in active_emergencies:
        if emergency.get('assigned_ambulance_id'):
            amb = ambulances.find_one({'_id': emergency['assigned_ambulance_id']})
            if amb:
                emergency['ambulance'] = amb
                if emergency['status'] == 'on_duty' and 'accepted_at' in emergency:
                    elapsed = (datetime.now() - emergency['accepted_at']).total_seconds() / 60
                    emergency['elapsed_minutes'] = int(elapsed)
    
    # All ambulances
    all_ambulances = list(ambulances.find())
    available_count = sum(1 for a in all_ambulances if a['status'] == 'available')
    on_duty_count = sum(1 for a in all_ambulances if a['status'] == 'on_duty')
    
    # Notifications
    unread_notifications = list(notifications.find({'read': False}).sort('created_at', -1).limit(10))
    
    # Top organizations
    top_organizations = list(organizations.find().sort('total_points', -1).limit(5))
    
    # Recent activities
    recent_activities = list(activities.find().sort('timestamp', -1).limit(10))
    
    # AI logs
    recent_ai_logs = list(ai_logs.find().sort('timestamp', -1).limit(15))
    
    return render_template('dashboard.html',
                         lives_saved=total_lives_saved,
                         avg_response_time=round(avg_response_time, 1),
                         active_donors=active_donors,
                         active_emergencies=active_emergencies,
                         pending_emergencies=pending_emergencies,
                         all_ambulances=all_ambulances,
                         available_ambulances_count=available_count,
                         on_duty_count=on_duty_count,
                         unread_notifications=unread_notifications,
                         top_organizations=top_organizations,
                         recent_activities=recent_activities,
                         recent_ai_logs=recent_ai_logs)

@app.route('/mark-in-transit/<unit_id>', methods=['POST'])
def mark_in_transit(unit_id):
    data = request.json
    
    blood_units.update_one(
        {'_id': ObjectId(unit_id)},
        {'$set': {
            'location': 'transit',
            'ambulance_info': {
                'vehicle_number': data['vehicle_number'],
                'driver_name': data['driver_name'],
                'driver_phone': data['driver_phone']
            }
        }}
    )
    
    return jsonify({'success': True})


@app.route('/api/register-emergency', methods=['POST'])
def register_emergency():
    """Register emergency and auto-assign to available ambulance"""
    data = request.json
    
    emergency = {
        'type': data.get('type', 'accident'),
        'location': {
            'lat': float(data['latitude']),
            'lng': float(data['longitude']),
            'address': data.get('address', 'Unknown location')
        },
        'severity': data.get('severity', 'medium'),
        'patient_count': int(data.get('patient_count', 1)),
        'description': data.get('description', ''),
        'caller_name': data.get('caller_name', 'Anonymous'),
        'caller_phone': data.get('caller_phone', ''),
        'blood_type_needed': data.get('blood_type_needed'),
        'status': 'pending',
        'created_at': datetime.now()
    }
    
    result = emergency_requests.insert_one(emergency)
    emergency_id = result.inserted_id
    
    # AI matching
    match = ai_match_ambulance(emergency['location'], emergency['severity'])
    
    if match:
        emergency_requests.update_one(
            {'_id': emergency_id},
            {'$set': {
                'assigned_ambulance_id': match['ambulance']['_id'],
                'assigned_ambulance_number': match['ambulance']['vehicle_number'],
                'assigned_distance': round(match['distance'], 2),
                'assigned_at': datetime.now(),
                'status': 'assigned'
            }}
        )
        
        ambulances.update_one(
            {'_id': match['ambulance']['_id']},
            {'$set': {
                'status': 'assigned',
                'assigned_emergency_id': emergency_id
            }}
        )
        
        notifications.insert_one({
            'type': 'emergency_assigned',
            'title': 'Emergency Assigned',
            'message': f"Ambulance {match['ambulance']['vehicle_number']} assigned. Waiting for driver response (1 min).",
            'priority': 'high',
            'read': False,
            'created_at': datetime.now()
        })
        
        activities.insert_one({
            'type': 'emergency_assigned',
            'message': f"AI assigned {match['ambulance']['vehicle_number']} to emergency ({round(match['distance'], 1)}km away)",
            'timestamp': datetime.now()
        })
        
        return jsonify({
            'success': True,
            'emergency_id': str(emergency_id),
            'ambulance': {
                'vehicle_number': match['ambulance']['vehicle_number'],
                'driver_name': match['ambulance']['driver_name'],
                'driver_phone': match['ambulance']['driver_phone'],
                'distance': round(match['distance'], 2),
                'eta_minutes': round(match['distance'] * 3, 0)
            },
            'message': f"Ambulance {match['ambulance']['vehicle_number']} assigned. Driver has 1 minute to accept."
        })
    else:
        notifications.insert_one({
            'type': 'emergency_no_ambulance',
            'title': '⚠️ NO AMBULANCES AVAILABLE',
            'message': f"CRITICAL: Emergency at {emergency['location']['address']} - All ambulances offline or on-duty!",
            'priority': 'critical',
            'read': False,
            'created_at': datetime.now()
        })
        
        activities.insert_one({
            'type': 'emergency_no_ambulance',
            'message': f"⚠️ Emergency registered but NO ambulances available at {emergency['location']['address']}",
            'timestamp': datetime.now()
        })
        
        return jsonify({
            'success': False,
            'emergency_id': str(emergency_id),
            'message': 'Emergency registered. Waiting for ambulances to come online. Will auto-assign when available.'
        })

@app.route('/api/clear-pending-emergency/<emergency_id>', methods=['POST'])
def clear_pending_emergency(emergency_id):
    """Manually clear/cancel a pending emergency"""
    emergency_requests.update_one(
        {'_id': ObjectId(emergency_id)},
        {'$set': {
            'status': 'cancelled',
            'cancelled_at': datetime.now(),
            'cancellation_reason': 'Manually cancelled by operator'
        }}
    )
    
    activities.insert_one({
        'type': 'emergency_cancelled',
        'message': f"Emergency {emergency_id} cancelled by operator",
        'timestamp': datetime.now()
    })
    
    return jsonify({'success': True})

@app.route('/api/mark-notification-read/<notification_id>', methods=['POST'])
def mark_notification_read(notification_id):
    notifications.update_one(
        {'_id': ObjectId(notification_id)},
        {'$set': {'read': True}}
    )
    return jsonify({'success': True})

@app.route('/gamification')
def gamification():
    all_organizations = list(organizations.find().sort('total_points', -1))
    return render_template('gamification.html', organizations=all_organizations)

@app.route('/live-map')
def live_map():
    hospitals_list = []
    for hospital in hospitals.find():
        inventory = blood_inventory.find_one({'hospital_id': hospital['_id']})
        
        if inventory:
            total_units = sum(inventory.get(bt, 0) for bt in ['A+', 'A-', 'B+', 'B-', 'O+', 'O-', 'AB+', 'AB-'])
            if total_units < 10:
                status = 'critical'
            elif total_units < 30:
                status = 'low'
            else:
                status = 'good'
        else:
            status = 'critical'
            inventory = {}
        
        hospitals_list.append({
            '_id': str(hospital['_id']),
            'name': hospital['name'],
            'address': hospital['address'],
            'location': hospital['location'],
            'inventory': inventory,
            'status': status
        })
    
    return render_template('live_map.html', hospitals=hospitals_list)

@app.route('/donors')
def donors_page():
    return render_template('donors_list.html')

@app.route('/api/donors')
def api_donors():
    blood_type = request.args.get('blood_type', '')
    district = request.args.get('district', '')
    state = request.args.get('state', '')
    organization = request.args.get('organization', '')
    
    query = {'status': 'active'}
    if blood_type:
        query['blood_type'] = blood_type
    if district:
        query['district'] = {'$regex': district, '$options': 'i'}
    if state:
        query['state'] = {'$regex': state, '$options': 'i'}
    if organization:
        query['organization'] = {'$regex': organization, '$options': 'i'}
    
    donors_list = list(donors.find(query).sort('created_at', -1))
    
    for donor in donors_list:
        donor['_id'] = str(donor['_id'])
        if 'last_donation' in donor:
            donor['last_donation'] = donor['last_donation'].isoformat()
        if 'next_eligible_date' in donor:
            donor['next_eligible_date'] = donor['next_eligible_date'].isoformat()
        if 'created_at' in donor:
            donor['created_at'] = donor['created_at'].isoformat()
    
    return jsonify({'donors': donors_list, 'count': len(donors_list)})

if __name__ == '__main__':
    app.run(debug=True, port=5000)