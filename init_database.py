from pymongo import MongoClient
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash
import sys
import os
from dotenv import load_dotenv
import secrets

load_dotenv()

MONGO_URI = os.getenv('MONGO_URI') or "mongodb+srv://praveensah2608_db_user:XEDQI2M5OWk4I3EE@cluster0.lilts6y.mongodb.net/lifelink_grid?retryWrites=true&w=majority"
DB_NAME = 'lifelink_grid'

print("Connecting to MongoDB...")
try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    client.server_info()
    db = client[DB_NAME]
    print("[OK] Connected successfully!")
except Exception as e:
    print(f"[ERROR] Connection failed: {e}")
    sys.exit(1)

def clear_database():
    """Clear all collections"""
    collections = ['hospitals', 'blood_inventory', 'blood_units', 'ambulances', 
                   'emergency_requests', 'donors', 'organizations', 'activities', 
                   'predictions', 'blood_requests', 'notifications', 'ambulance_trips',
                   'ai_logs', 'blood_transfers']
    
    for collection in collections:
        db[collection].delete_many({})
    print("[OK] Database cleared!")

def initialize_data():
    """Initialize enhanced database with all features"""
    
    # ========== HOSPITALS ==========
    print("\n[1/7] Creating hospitals...")
    hospitals_data = [
        {
            'name': 'Manipal Hospital',
            'email': 'manipal@hospital.com',
            'password': generate_password_hash('demo123'),
            'address': 'HAL Airport Rd, Bangalore',
            'phone': '+91-80-2502-4444',
            'location': {'lat': 12.9576, 'lng': 77.6412},
            'type': 'hospital',
            'license_number': 'KA-BLR-H-001',
            'created_at': datetime.now(),
            'status': 'active',
            'avg_consumption': {
                'A+': 3, 'A-': 1, 'B+': 2, 'B-': 1,
                'O+': 4, 'O-': 1, 'AB+': 1, 'AB-': 1
            }
        },
        {
            'name': 'Apollo Hospitals',
            'email': 'apollo@hospital.com',
            'password': generate_password_hash('demo123'),
            'address': 'Bannerghatta Rd, Bangalore',
            'phone': '+91-80-2630-1234',
            'location': {'lat': 12.9116, 'lng': 77.5991},
            'type': 'hospital',
            'license_number': 'KA-BLR-H-002',
            'created_at': datetime.now(),
            'status': 'active',
            'avg_consumption': {
                'A+': 2, 'A-': 1, 'B+': 2, 'B-': 1,
                'O+': 3, 'O-': 1, 'AB+': 1, 'AB-': 1
            }
        },
        {
            'name': 'Fortis Hospital',
            'email': 'fortis@hospital.com',
            'password': generate_password_hash('demo123'),
            'address': 'Cunningham Rd, Bangalore',
            'phone': '+91-80-6621-4444',
            'location': {'lat': 12.9956, 'lng': 77.5945},
            'type': 'hospital',
            'license_number': 'KA-BLR-H-003',
            'created_at': datetime.now(),
            'status': 'active',
            'avg_consumption': {
                'A+': 3, 'A-': 2, 'B+': 3, 'B-': 1,
                'O+': 4, 'O-': 2, 'AB+': 1, 'AB-': 1
            }
        },
        {
            'name': 'Central Blood Bank',
            'email': 'central@bloodbank.com',
            'password': generate_password_hash('demo123'),
            'address': 'Seshadri Rd, Bangalore',
            'phone': '+91-80-2287-4444',
            'location': {'lat': 12.9822, 'lng': 77.5998},
            'type': 'blood_bank',
            'license_number': 'KA-BLR-BB-001',
            'created_at': datetime.now(),
            'status': 'active',
            'avg_consumption': {
                'A+': 5, 'A-': 3, 'B+': 4, 'B-': 2,
                'O+': 6, 'O-': 3, 'AB+': 2, 'AB-': 2
            }
        }
    ]
    
    hospital_ids = []
    for hospital in hospitals_data:
        result = db.hospitals.insert_one(hospital)
        hospital_ids.append(result.inserted_id)
        
        # Initialize inventory
        inventory_levels = [
            {'A+': 8, 'A-': 3, 'B+': 6, 'B-': 2, 'O+': 10, 'O-': 1, 'AB+': 4, 'AB-': 2},
            {'A+': 2, 'A-': 0, 'B+': 5, 'B-': 2, 'O+': 10, 'O-': 1, 'AB+': 4, 'AB-': 2},
            {'A+': 12, 'A-': 4, 'B+': 9, 'B-': 3, 'O+': 15, 'O-': 2, 'AB+': 6, 'AB-': 3},
            {'A+': 25, 'A-': 15, 'B+': 20, 'B-': 10, 'O+': 30, 'O-': 8, 'AB+': 12, 'AB-': 7}
        ]
        
        db.blood_inventory.insert_one({
            'hospital_id': result.inserted_id,
            **inventory_levels[len(hospital_ids) - 1],
            'last_updated': datetime.now()
        })
    
    print(f"   ✓ {len(hospital_ids)} hospitals created")
    
    # ========== AMBULANCES (ALL OFFLINE) ==========
    print("\n[2/7] Creating ambulances...")
    ambulances_data = [
        {
            'vehicle_number': 'KA-01-AB-1234',
            'device_id': 'AMB001',
            'password': generate_password_hash('1234'),
            'driver_name': 'Rajesh Kumar',
            'driver_phone': '+91-9876543210',
            'driver_license': 'KA0123456789',
            'ambulance_type': 'advanced',
            'equipment': ['ventilator', 'defibrillator', 'oxygen', 'trauma_kit'],
            'base_location': {
                'lat': 12.9716,
                'lng': 77.5946,
                'address': 'Central Station, MG Road'
            },
            'current_location': {'lat': 12.9716, 'lng': 77.5946},
            'status': 'offline',
            'last_seen': None,
            'created_at': datetime.now()
        },
        {
            'vehicle_number': 'KA-01-CD-5678',
            'device_id': 'AMB002',
            'password': generate_password_hash('1234'),
            'driver_name': 'Suresh Patel',
            'driver_phone': '+91-9876543211',
            'driver_license': 'KA9876543210',
            'ambulance_type': 'basic',
            'equipment': ['first_aid', 'oxygen', 'stretcher'],
            'base_location': {
                'lat': 12.9352,
                'lng': 77.6245,
                'address': 'East Station, Whitefield'
            },
            'current_location': {'lat': 12.9352, 'lng': 77.6245},
            'status': 'offline',
            'last_seen': None,
            'created_at': datetime.now()
        },
        {
            'vehicle_number': 'KA-01-EF-9012',
            'device_id': 'AMB003',
            'password': generate_password_hash('1234'),
            'driver_name': 'Arun Sharma',
            'driver_phone': '+91-9876543212',
            'driver_license': 'KA1122334455',
            'ambulance_type': 'advanced',
            'equipment': ['ventilator', 'defibrillator', 'oxygen', 'ultrasound'],
            'base_location': {
                'lat': 12.8406,
                'lng': 77.6956,
                'address': 'South Station, Electronic City'
            },
            'current_location': {'lat': 12.8406, 'lng': 77.6956},
            'status': 'offline',
            'last_seen': None,
            'created_at': datetime.now()
        },
        {
            'vehicle_number': 'KA-01-GH-3456',
            'device_id': 'AMB004',
            'password': generate_password_hash('1234'),
            'driver_name': 'Priya Menon',
            'driver_phone': '+91-9876543213',
            'driver_license': 'KA5566778899',
            'ambulance_type': 'neonatal',
            'equipment': ['incubator', 'neonatal_ventilator', 'oxygen'],
            'base_location': {
                'lat': 12.9698,
                'lng': 77.7499,
                'address': 'North Station, Yelahanka'
            },
            'current_location': {'lat': 12.9698, 'lng': 77.7499},
            'status': 'offline',
            'last_seen': None,
            'created_at': datetime.now()
        }
    ]
    
    ambulance_ids = db.ambulances.insert_many(ambulances_data)
    print(f"   ✓ {len(ambulance_ids.inserted_ids)} ambulances created (all offline)")
    
    # ========== ORGANIZATIONS (GAMIFICATION) ==========
    print("\n[3/7] Creating organizations...")
    organizations_data = [
        {
            'name': 'Gopalan College of Engineering',
            'type': 'college',
            'total_points': 27840,
            'active_donors': 487,
            'total_donations': 1856,
            'lives_saved': 156,
            'awards': ['Best Alumni Donors Award', 'Highest Social Impact'],
            'monthly_growth': 24,
            'badge': 'gold'
        },
        {
            'name': 'Rathinam Technical Campus',
            'type': 'college',
            'total_points': 18705,
            'active_donors': 342,
            'total_donations': 1247,
            'lives_saved': 104,
            'awards': ['Community Champion'],
            'monthly_growth': 12,
            'badge': 'silver'
        },
        {
            'name': 'VIT Vellore',
            'type': 'college',
            'total_points': 16335,
            'active_donors': 298,
            'total_donations': 1089,
            'lives_saved': 91,
            'awards': [],
            'monthly_growth': 8,
            'badge': 'bronze'
        },
        {
            'name': 'Infosys Foundation',
            'type': 'corporate',
            'total_points': 14730,
            'active_donors': 276,
            'total_donations': 982,
            'lives_saved': 82,
            'awards': ['Corporate Social Champion'],
            'monthly_growth': 15,
            'badge': 'bronze'
        }
    ]
    
    org_ids = db.organizations.insert_many(organizations_data)
    print(f"   ✓ {len(org_ids.inserted_ids)} organizations created")
    
    # ========== DONORS ==========
    print("\n[4/7] Creating donors...")
    donors_data = [
        {
            'donor_id': 'DNR' + secrets.token_hex(4).upper(),
            'name': 'Rahul Kumar',
            'blood_type': 'B+',
            'phone': '+91-9999999991',
            'email': 'rahul@example.com',
            'organization': 'VIT Vellore',
            'district': 'Bangalore Urban',
            'state': 'Karnataka',
            'location': 'Koramangala',
            'status': 'active',
            'last_donation': datetime.now() - timedelta(days=100),
            'next_eligible_date': datetime.now() + timedelta(days=20),
            'total_donations': 6,
            'total_points': 120,
            'created_at': datetime.now()
        },
        {
            'donor_id': 'DNR' + secrets.token_hex(4).upper(),
            'name': 'Priya Sharma',
            'blood_type': 'O+',
            'phone': '+91-9999999992',
            'email': 'priya@example.com',
            'organization': 'Gopalan College of Engineering',
            'district': 'Bangalore Urban',
            'state': 'Karnataka',
            'location': 'Whitefield',
            'status': 'active',
            'last_donation': datetime.now() - timedelta(days=95),
            'next_eligible_date': datetime.now() + timedelta(days=25),
            'total_donations': 8,
            'total_points': 160,
            'created_at': datetime.now()
        },
        {
            'donor_id': 'DNR' + secrets.token_hex(4).upper(),
            'name': 'Amit Patel',
            'blood_type': 'A+',
            'phone': '+91-9999999993',
            'email': 'amit@example.com',
            'organization': 'Infosys Foundation',
            'district': 'Bangalore Urban',
            'state': 'Karnataka',
            'location': 'Electronic City',
            'status': 'active',
            'last_donation': datetime.now() - timedelta(days=120),
            'next_eligible_date': datetime.now(),
            'total_donations': 5,
            'total_points': 100,
            'created_at': datetime.now()
        },
        {
            'donor_id': 'DNR' + secrets.token_hex(4).upper(),
            'name': 'Sneha Reddy',
            'blood_type': 'AB+',
            'phone': '+91-9999999994',
            'email': 'sneha@example.com',
            'organization': 'Rathinam Technical Campus',
            'district': 'Bangalore Urban',
            'state': 'Karnataka',
            'location': 'Indiranagar',
            'status': 'active',
            'last_donation': datetime.now() - timedelta(days=110),
            'next_eligible_date': datetime.now() + timedelta(days=10),
            'total_donations': 4,
            'total_points': 80,
            'created_at': datetime.now()
        }
    ]
    
    donor_ids = db.donors.insert_many(donors_data)
    print(f"   ✓ {len(donor_ids.inserted_ids)} donors created")
    
    # ========== SAMPLE BLOOD UNITS WITH QR CODES ==========
    print("\n[5/7] Creating blood units with QR codes...")
    blood_units_data = []
    
    # Create 5 sample blood units
    for i in range(5):
        unit = {
            'blood_id': 'BLD' + secrets.token_hex(6).upper(),
            'qr_code': secrets.token_urlsafe(16),
            'blood_type': ['A+', 'B+', 'O+', 'A-', 'O-'][i],
            'donor_id': donors_data[i % len(donors_data)]['donor_id'],
            'hospital_id': hospital_ids[0],
            'hospital_name': 'Manipal Hospital',
            'units': 2 if i < 3 else 1,
            'collection_date': datetime.now() - timedelta(days=5),
            'expiry_date': datetime.now() + timedelta(days=30),
            'status': 'available',
            'created_at': datetime.now()
        }
        blood_units_data.append(unit)
    
    db.blood_units.insert_many(blood_units_data)
    print(f"   ✓ {len(blood_units_data)} blood units with QR codes created")
    
    # ========== NOTIFICATIONS ==========
    print("\n[6/7] Creating sample notifications...")
    notifications_data = [
        {
            'type': 'blood_request',
            'title': 'Blood Request Received',
            'message': 'Apollo Hospital requested 3 units of O+',
            'priority': 'high',
            'read': False,
            'created_at': datetime.now() - timedelta(minutes=5)
        },
        {
            'type': 'system',
            'title': 'System Update',
            'message': 'AI routing system optimized. Response time improved by 15%.',
            'priority': 'medium',
            'read': False,
            'created_at': datetime.now() - timedelta(hours=2)
        }
    ]
    
    db.notifications.insert_many(notifications_data)
    print(f"   ✓ {len(notifications_data)} notifications created")
    
    # ========== AI LOGS ==========
    print("\n[7/7] Creating AI log collection...")
    db.ai_logs.insert_one({
        'log_type': 'system_init',
        'message': 'AI routing system initialized',
        'timestamp': datetime.now(),
        'status': 'success'
    })
    print("   ✓ AI logs collection initialized")
    
    print("\n" + "="*70)
    print("[SUCCESS] DATABASE INITIALIZATION COMPLETE!")
    print("="*70)
    print("\n📋 TEST CREDENTIALS:\n")
    print("HOSPITALS:")
    print("  • manipal@hospital.com / demo123")
    print("  • apollo@hospital.com / demo123")
    print("  • fortis@hospital.com / demo123")
    print("  • central@bloodbank.com / demo123")
    print("\nAMBULANCES (All Offline - Login to activate):")
    print("  • AMB001 / 1234")
    print("  • AMB002 / 1234")
    print("  • AMB003 / 1234")
    print("  • AMB004 / 1234")
    print("\n🌐 ACCESS URLs:")
    print("  • Control Room: http://localhost:5000")
    print("  • Hospital Portal: http://localhost:5001")
    print("  • Ambulance Interface: http://localhost:5002")
    print("  • Accident Register: http://localhost:5003")
    print("\n" + "="*70)

if __name__ == '__main__':
    print("\n🚀 LifeLink Grid - Enhanced Database Setup\n")
    
    response = input("⚠️  Clear existing data? (yes/no): ")
    if response.lower() == 'yes':
        clear_database()
    
    initialize_data()
    
    print("\n✅ You can now start all Flask applications!")