from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_pymongo import PyMongo
from datetime import datetime, timedelta
from bson.objectid import ObjectId
from werkzeug.security import check_password_hash
import os
import qrcode
import io
import base64
import secrets
import json

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('HOSPITAL_SECRET', 'your-hospital-secret-key')
app.config['MONGO_URI'] = os.getenv('MONGO_URI') or 'mongodb+srv://praveensah2608_db_user:XEDQI2M5OWk4I3EE@cluster0.lilts6y.mongodb.net/lifelink_grid?retryWrites=true&w=majority'

mongo = PyMongo(app)

# Collections
hospitals = mongo.db.hospitals
blood_inventory = mongo.db.blood_inventory
blood_units = mongo.db.blood_units
donors = mongo.db.donors
blood_requests = mongo.db.blood_requests
activities = mongo.db.activities
notifications = mongo.db.notifications

def generate_blood_id():
    """Generate unique blood ID"""
    return f"BLOOD{secrets.token_hex(6).upper()}"

def generate_qr_code(data):
    """Generate QR code and return as base64"""
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(json.dumps(data))  # Convert dict to JSON string
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    img_base64 = base64.b64encode(buffer.getvalue()).decode()
    return f"data:image/png;base64,{img_base64}"

@app.route('/')
def index():
    if 'hospital_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.json
        
        hospital = hospitals.find_one({'email': data['email']})
        
        if hospital and check_password_hash(hospital['password'], data['password']):
            session['hospital_id'] = str(hospital['_id'])
            session['hospital_name'] = hospital['name']
            return jsonify({'success': True})
        
        return jsonify({'success': False, 'message': 'Invalid credentials'}), 401
    
    return render_template('hospital_login.html')

@app.route('/dashboard')
def dashboard():
    if 'hospital_id' not in session:
        return redirect(url_for('login'))
    
    hospital_id = ObjectId(session['hospital_id'])
    hospital = hospitals.find_one({'_id': hospital_id})
    hospital_dict = dict(hospital) if hospital else None
    
    inventory = blood_inventory.find_one({'hospital_id': hospital_id})
    inventory_dict = dict(inventory) if inventory else None
    
    # Get blood units
    available_units = list(blood_units.find({
        'hospital_id': hospital_id,
        'status': 'available'
    }).sort('expiry_date', 1))
    
    # Get used/expired units count
    used_count = blood_units.count_documents({
        'hospital_id': hospital_id,
        'status': 'used'
    })
    
    expired_count = blood_units.count_documents({
        'hospital_id': hospital_id,
        'status': 'expired'
    })
    
    # Get incoming blood requests
    incoming_requests = list(blood_requests.find({
        'donor_hospital_id': hospital_id,
        'status': {'$in': ['pending', 'approved']}
    }).sort('created_at', -1))
    
    # Convert requests to dictionaries
    incoming_requests_dict = [dict(req) for req in incoming_requests]
    
    # Get my blood requests
    my_requests = list(blood_requests.find({
        'requesting_hospital_id': hospital_id
    }).sort('created_at', -1).limit(10))
    
    # Convert requests to dictionaries
    my_requests_dict = [dict(req) for req in my_requests]
    
    # Process available_units to add days_until_expiry
    processed_units = []
    current_time = datetime.now()
    for unit in available_units:
        unit_dict = dict(unit)
        expiry = unit.get('expiry_date', current_time)
        if isinstance(expiry, datetime):
            days_left = (expiry - current_time).days
            unit_dict['days_until_expiry'] = days_left
            unit_dict['is_expiring_soon'] = days_left < 7
        else:
            unit_dict['days_until_expiry'] = 999
            unit_dict['is_expiring_soon'] = False
        processed_units.append(unit_dict)
    
    return render_template('hospital_dashboard.html',
                         hospital=hospital_dict,
                         inventory=inventory_dict,
                         available_units=processed_units,
                         used_count=used_count,
                         expired_count=expired_count,
                         incoming_requests=incoming_requests_dict,
                         my_requests=my_requests_dict,
                         now=datetime.now)

@app.route('/blood-entry', methods=['GET', 'POST'])
def blood_entry():
    if 'hospital_id' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        data = request.json
        hospital_id = ObjectId(session['hospital_id'])
        
        # Determine collection date (default to now, but allow past dates)
        collection_date_str = data.get('collection_date', 'today')
        if collection_date_str == 'today':
            collected_date = datetime.now()
        elif collection_date_str == 'yesterday':
            collected_date = datetime.now() - timedelta(days=1)
        else:
            # Parse custom date if provided
            try:
                collected_date = datetime.fromisoformat(collection_date_str)
            except:
                collected_date = datetime.now()
        
        # Find or create donor
        donor = donors.find_one({'donor_id': data['donor_id']})
        
        if not donor:
            donor_id_generated = data['donor_id']
            donor = {
                'donor_id': donor_id_generated,
                'name': data['donor_name'],
                'blood_type': data['blood_type'],
                'phone': data['donor_phone'],
                'email': data.get('donor_email', ''),
                'organization': data.get('organization', ''),
                'district': data.get('district', ''),
                'state': data.get('state', ''),
                'status': 'active',
                'last_donation': collected_date,
                'next_eligible_date': collected_date + timedelta(days=90),
                'total_donations': 1,
                'created_at': datetime.now()
            }
            donors.insert_one(donor)
        else:
            donors.update_one(
                {'donor_id': data['donor_id']},
                {'$set': {
                    'last_donation': collected_date,
                    'next_eligible_date': collected_date + timedelta(days=90),
                    'status': 'active'
                },
                '$inc': {'total_donations': 1}}
            )
        
        # Determine units per donation
        blood_type = data['blood_type']
        if blood_type == 'O+':
            units_per_donation = 1
            total_qrs = int(data['units'])
        else:
            units_per_donation = 2
            total_qrs = int(data['units']) // 2
        
        # Calculate expiry date (35 days from collection)
        expiry_date = collected_date + timedelta(days=35)
        
        # Generate QR codes for blood units
        blood_unit_ids = []
        for i in range(total_qrs):
            blood_id = generate_blood_id()
            
            # Create QR data as dictionary with proper datetime strings
            qr_data = {
                'blood_id': blood_id,
                'blood_type': blood_type,
                'donor_id': donor['donor_id'],
                'units': units_per_donation,
                'collected_date': collected_date.strftime('%Y-%m-%d %H:%M:%S'),
                'expiry_date': expiry_date.strftime('%Y-%m-%d %H:%M:%S'),
                'hospital_id': str(hospital_id),
                'hospital': session['hospital_name'],
                'status': 'in_storage',
                'location': 'storage'
            }
            
            # Generate QR code
            qr_code_image = generate_qr_code(qr_data)
            
            # Save blood unit with proper datetime objects
            blood_unit = {
                'blood_id': blood_id,
                'hospital_id': hospital_id,
                'donor_id': donor['donor_id'],
                'blood_type': blood_type,
                'units': units_per_donation,
                'collected_date': collected_date,
                'collected_date_formatted': collected_date.strftime('%B %d, %Y at %I:%M %p'),
                'expiry_date': expiry_date,
                'expiry_date_formatted': expiry_date.strftime('%B %d, %Y at %I:%M %p'),
                'status': 'available',
                'location': 'storage',
                'qr_code': qr_code_image,
                'qr_data': qr_data,
                'created_at': datetime.now()
            }
            
            result = blood_units.insert_one(blood_unit)
            blood_unit_ids.append(str(result.inserted_id))
        
        # Update inventory
        blood_inventory.update_one(
            {'hospital_id': hospital_id},
            {
                '$inc': {blood_type: int(data['units'])},
                '$set': {'last_updated': datetime.now()}
            },
            upsert=True
        )
        
        # Log activity
        activities.insert_one({
            'type': 'donation_recorded',
            'message': f"{data['units']} units of {blood_type} donated at {session['hospital_name']} on {collected_date.strftime('%B %d, %Y')}",
            'hospital_id': hospital_id,
            'timestamp': datetime.now()
        })
        
        return jsonify({
            'success': True,
            'message': f'{total_qrs} QR code(s) generated successfully',
            'blood_unit_ids': blood_unit_ids
        })
    
    return render_template('blood_entry.html')
@app.route('/scan-test')
def scan_test():
    """Simple QR scanner test page"""
    return render_template('scan_test.html')

@app.route('/debug-qr/<unit_id>')
def debug_qr(unit_id):
    """Debug QR code issues"""
    if 'hospital_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        blood_unit = blood_units.find_one({'_id': ObjectId(unit_id)})
        
        if not blood_unit:
            return jsonify({'error': 'Blood unit not found'}), 404
        
        # Debug info
        debug_info = {
            'blood_id': blood_unit.get('blood_id'),
            'has_qr_code': 'qr_code' in blood_unit,
            'qr_code_length': len(blood_unit.get('qr_code', '')) if 'qr_code' in blood_unit else 0,
            'qr_code_starts_with': blood_unit.get('qr_code', '')[:50] if 'qr_code' in blood_unit else 'N/A',
            'collected_date_type': type(blood_unit.get('collected_date')).__name__,
            'collected_date_value': str(blood_unit.get('collected_date')),
            'expiry_date_type': type(blood_unit.get('expiry_date')).__name__,
            'expiry_date_value': str(blood_unit.get('expiry_date')),
            'has_qr_data': 'qr_data' in blood_unit,
            'qr_data': blood_unit.get('qr_data') if 'qr_data' in blood_unit else None
        }
        
        return jsonify(debug_info)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/regenerate-qr/<unit_id>', methods=['POST'])
def regenerate_qr(unit_id):
    """Regenerate QR code for a specific blood unit"""
    if 'hospital_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        blood_unit = blood_units.find_one({'_id': ObjectId(unit_id)})
        
        if not blood_unit:
            return jsonify({'error': 'Blood unit not found'}), 404
        
        # Ensure dates are datetime objects
        collected_date = blood_unit.get('collected_date')
        if isinstance(collected_date, str):
            collected_date = datetime.fromisoformat(collected_date)
        elif not isinstance(collected_date, datetime):
            collected_date = datetime.now() - timedelta(days=1)
        
        expiry_date = blood_unit.get('expiry_date')
        if isinstance(expiry_date, str):
            expiry_date = datetime.fromisoformat(expiry_date)
        elif not isinstance(expiry_date, datetime):
            expiry_date = collected_date + timedelta(days=35)
        
        # Get hospital info
        hospital = hospitals.find_one({'_id': blood_unit['hospital_id']})
        hospital_name = hospital.get('name', 'Unknown Hospital') if hospital else 'Unknown Hospital'
        
        # Create QR data
        qr_data = {
            'blood_id': blood_unit['blood_id'],
            'blood_type': blood_unit['blood_type'],
            'donor_id': blood_unit['donor_id'],
            'units': blood_unit['units'],
            'collected_date': collected_date.strftime('%Y-%m-%d %H:%M:%S'),
            'expiry_date': expiry_date.strftime('%Y-%m-%d %H:%M:%S'),
            'hospital_id': str(blood_unit['hospital_id']),
            'hospital': hospital_name,
            'status': blood_unit.get('status', 'in_storage'),
            'location': blood_unit.get('location', 'storage')
        }
        
        # Generate QR code
        qr_code_image = generate_qr_code(qr_data)
        
        if not qr_code_image:
            return jsonify({'error': 'Failed to generate QR code'}), 500
        
        # Update database
        blood_units.update_one(
            {'_id': ObjectId(unit_id)},
            {'$set': {
                'qr_code': qr_code_image,
                'qr_data': qr_data,
                'collected_date': collected_date,
                'collected_date_formatted': collected_date.strftime('%B %d, %Y at %I:%M %p'),
                'expiry_date': expiry_date,
                'expiry_date_formatted': expiry_date.strftime('%B %d, %Y at %I:%M %p')
            }}
        )
        
        return jsonify({
            'success': True,
            'message': 'QR code regenerated successfully',
            'qr_code_length': len(qr_code_image)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
@app.route('/view-qr/<unit_id>')
def view_qr(unit_id):
    """View QR code for a blood unit"""
    if 'hospital_id' not in session:
        return redirect(url_for('login'))
    
    blood_unit = blood_units.find_one({'_id': ObjectId(unit_id)})
    
    if not blood_unit:
        return "Blood unit not found", 404
    
    # Convert MongoDB document to dictionary for template access
    blood_unit_dict = {}
    for key, value in blood_unit.items():
        if key == '_id':
            blood_unit_dict['_id'] = str(value)
        elif isinstance(value, datetime):
            blood_unit_dict[key] = value
            # Also create formatted string versions for easy template access
            blood_unit_dict[f'{key}_formatted'] = value.strftime('%B %d, %Y')
        else:
            blood_unit_dict[key] = value
    
    # Get hospital information
    hospital = hospitals.find_one({'_id': blood_unit['hospital_id']})
    hospital_dict = dict(hospital) if hospital else None
    
    # Get donor information
    donor = donors.find_one({'donor_id': blood_unit['donor_id']})
    donor_dict = dict(donor) if donor else None
    
    # Calculate days until expiry
    expiry_date = blood_unit.get('expiry_date')
    if isinstance(expiry_date, datetime):
        days_until_expiry = (expiry_date - datetime.now()).days
    else:
        days_until_expiry = 999
    
    return render_template('view_qr.html', 
                         blood_unit=blood_unit_dict,
                         donor=donor_dict,
                         hospital=hospital_dict,
                         days_until_expiry=days_until_expiry,
                         now=datetime.now)

@app.route('/api/verify-qr', methods=['POST'])
def verify_qr():
    """Verify scanned QR code data"""
    if 'hospital_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        data = request.json
        qr_data = json.loads(data['qr_data'])
        
        # Find blood unit by blood_id
        blood_unit = blood_units.find_one({'blood_id': qr_data['blood_id']})
        
        if not blood_unit:
            return jsonify({
                'success': False,
                'error': 'Blood unit not found in database'
            })
        
        # Get hospital info
        hospital = hospitals.find_one({'_id': blood_unit['hospital_id']})
        
        # Check if in transit
        in_transit = blood_unit.get('location') == 'transit'
        ambulance_info = None
        
        if in_transit:
            ambulance_info = blood_unit.get('ambulance_info', {})
        
        # Get donor info
        donor = donors.find_one({'donor_id': blood_unit['donor_id']})
        
        response = {
            'success': True,
            'blood_unit': {
                'blood_id': blood_unit['blood_id'],
                'blood_type': blood_unit['blood_type'],
                'units': blood_unit['units'],
                'status': blood_unit['status'],
                'location': blood_unit.get('location', 'storage'),
                'collected_date': blood_unit['collected_date'].isoformat(),
                'expiry_date': blood_unit['expiry_date'].isoformat(),
                'days_until_expiry': (blood_unit['expiry_date'] - datetime.now()).days
            },
            'hospital': {
                'name': hospital['name'],
                'address': hospital.get('address', 'N/A'),
                'phone': hospital.get('phone', 'N/A')
            },
            'donor': {
                'donor_id': donor['donor_id'],
                'total_donations': donor.get('total_donations', 1)
            },
            'in_transit': in_transit,
            'ambulance_info': ambulance_info
        }
        
        return jsonify(response)
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/mark-used/<unit_id>', methods=['POST'])
def mark_used(unit_id):
    """Mark blood unit as used"""
    if 'hospital_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    hospital_id = ObjectId(session['hospital_id'])
    
    blood_unit = blood_units.find_one({'_id': ObjectId(unit_id), 'hospital_id': hospital_id})
    
    if not blood_unit:
        return jsonify({'error': 'Blood unit not found'}), 404
    
    # Update unit status
    blood_units.update_one(
        {'_id': ObjectId(unit_id)},
        {'$set': {
            'status': 'used',
            'location': 'used',
            'used_at': datetime.now()
        }}
    )
    
    # Update inventory
    blood_inventory.update_one(
        {'hospital_id': hospital_id},
        {
            '$inc': {blood_unit['blood_type']: -blood_unit['units']},
            '$set': {'last_updated': datetime.now()}
        }
    )
    
    # Log activity
    activities.insert_one({
        'type': 'blood_used',
        'message': f"{blood_unit['units']} units of {blood_unit['blood_type']} used at {session['hospital_name']}",
        'hospital_id': hospital_id,
        'timestamp': datetime.now()
    })
    
    return jsonify({'success': True})

@app.route('/mark-in-transit/<unit_id>', methods=['POST'])
def mark_in_transit(unit_id):
    """Mark blood unit as in transit"""
    if 'hospital_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
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

@app.route('/request-emergency-blood', methods=['POST'])
def request_emergency_blood():
    """Request emergency blood from other hospitals"""
    if 'hospital_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.json
    hospital_id = ObjectId(session['hospital_id'])
    hospital = hospitals.find_one({'_id': hospital_id})
    
    if not hospital:
        return jsonify({'error': 'Hospital not found'}), 404
    
    # Create blood request
    blood_request = {
        'requesting_hospital_id': hospital_id,
        'requesting_hospital_name': hospital.get('name', 'Unknown'),
        'requesting_hospital_location': hospital.get('location', {}),
        'blood_type': data['blood_type'],
        'units': int(data['units']),
        'urgency': data.get('urgency', 'high'),
        'reason': data.get('reason', ''),
        'status': 'pending',
        'created_at': datetime.now(),
        'auto_approve_at': datetime.now() + timedelta(minutes=1)
    }
    
    result = blood_requests.insert_one(blood_request)
    request_id = result.inserted_id
    
    # Find nearest hospital with blood
    from math import radians, sin, cos, sqrt, atan2
    
    def calculate_distance(lat1, lng1, lat2, lng2):
        R = 6371
        lat1, lng1, lat2, lng2 = map(radians, [lat1, lng1, lat2, lng2])
        dlat = lat2 - lat1
        dlng = lng2 - lng1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlng/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))
        return R * c
    
    hospital_location = hospital.get('location', {})
    hospital_lat = hospital_location.get('lat') if isinstance(hospital_location, dict) else None
    hospital_lng = hospital_location.get('lng') if isinstance(hospital_location, dict) else None
    
    potential_donors = []
    for h in hospitals.find({'_id': {'$ne': hospital_id}}):
        inv = blood_inventory.find_one({'hospital_id': h['_id']})
        if inv and inv.get(data['blood_type'], 0) >= int(data['units']):
            h_location = h.get('location', {})
            h_lat = h_location.get('lat') if isinstance(h_location, dict) else None
            h_lng = h_location.get('lng') if isinstance(h_location, dict) else None
            
            # Only calculate distance if both hospitals have valid coordinates
            if hospital_lat and hospital_lng and h_lat and h_lng:
                distance = calculate_distance(hospital_lat, hospital_lng, h_lat, h_lng)
            else:
                distance = 9999  # Use a large default distance if coordinates unavailable
            
            potential_donors.append({
                'hospital_id': h['_id'],
                'hospital_name': h.get('name', 'Unknown'),
                'distance': distance,
                'available_units': inv.get(data['blood_type'], 0)
            })
    
    if not potential_donors:
        return jsonify({
            'success': False,
            'message': 'No hospitals found with requested blood type'
        })
    
    # Sort by distance
    potential_donors.sort(key=lambda x: x['distance'])
    nearest = potential_donors[0]
    
    # Update request with donor hospital
    blood_requests.update_one(
        {'_id': request_id},
        {'$set': {
            'donor_hospital_id': nearest['hospital_id'],
            'donor_hospital_name': nearest['hospital_name'],
            'distance': nearest['distance']
        }}
    )
    
    # Create notification for donor hospital
    notifications.insert_one({
        'type': 'blood_request',
        'hospital_id': nearest['hospital_id'],
        'title': 'Emergency Blood Request',
        'message': f"{hospital['name']} needs {data['units']} units of {data['blood_type']}",
        'priority': 'high',
        'read': False,
        'created_at': datetime.now(),
        'request_id': request_id
    })
    
    return jsonify({
        'success': True,
        'message': f'Request sent to {nearest["hospital_name"]} ({nearest["distance"]:.1f} km away)',
        'request_id': str(request_id)
    })

@app.route('/approve-blood-request/<request_id>', methods=['POST'])
def approve_blood_request(request_id):
    """Approve blood transfer request"""
    if 'hospital_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    hospital_id = ObjectId(session['hospital_id'])
    blood_request = blood_requests.find_one({'_id': ObjectId(request_id)})
    
    if not blood_request or blood_request['donor_hospital_id'] != hospital_id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    # Update request status
    blood_requests.update_one(
        {'_id': ObjectId(request_id)},
        {'$set': {
            'status': 'approved',
            'approved_at': datetime.now()
        }}
    )
    
    # Update inventory
    blood_inventory.update_one(
        {'hospital_id': hospital_id},
        {
            '$inc': {blood_request['blood_type']: -blood_request['units']},
            '$set': {'last_updated': datetime.now()}
        }
    )
    
    # Create notification for requesting hospital
    notifications.insert_one({
        'type': 'blood_approved',
        'hospital_id': blood_request['requesting_hospital_id'],
        'title': 'Blood Request Approved',
        'message': f"Your request for {blood_request['units']} units of {blood_request['blood_type']} has been approved.",
        'priority': 'high',
        'read': False,
        'created_at': datetime.now()
    })
    
    return jsonify({'success': True})

@app.route('/reject-blood-request/<request_id>', methods=['POST'])
def reject_blood_request(request_id):
    """Reject blood transfer request"""
    if 'hospital_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    blood_requests.update_one(
        {'_id': ObjectId(request_id)},
        {'$set': {
            'status': 'rejected',
            'rejected_at': datetime.now()
        }}
    )
    
    return jsonify({'success': True})

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True, port=5001, host='0.0.0.0')