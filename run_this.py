import qrcode
import io
import base64
import json
from datetime import datetime, timedelta
from pymongo import MongoClient

# MongoDB connection
MONGO_URI = "mongodb+srv://praveensah2608_db_user:XEDQI2M5OWk4I3EE@cluster0.lilts6y.mongodb.net/lifelink_grid?retryWrites=true&w=majority"

def generate_qr_code(data):
    """Generate QR code and return as base64"""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    json_data = json.dumps(data)
    qr.add_data(json_data)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    img_base64 = base64.b64encode(buffer.getvalue()).decode()
    
    return f"data:image/png;base64,{img_base64}"

print("🔧 Fixing ALL blood units QR codes...\n")

client = MongoClient(MONGO_URI)
db = client.lifelink_grid
blood_units = db.blood_units
hospitals_col = db.hospitals

units = list(blood_units.find({}))
print(f"Found {len(units)} blood units\n")

fixed = 0

for unit in units:
    # Fix dates
    collected_date = unit.get('collected_date')
    if not isinstance(collected_date, datetime):
        collected_date = datetime.now() - timedelta(days=1)
    
    expiry_date = unit.get('expiry_date')
    if not isinstance(expiry_date, datetime):
        expiry_date = collected_date + timedelta(days=35)
    
    # Get hospital name
    hospital = hospitals_col.find_one({'_id': unit['hospital_id']})
    hospital_name = hospital.get('name', 'Unknown Hospital') if hospital else 'Unknown Hospital'
    
    # Create QR data
    qr_data = {
        'blood_id': unit['blood_id'],
        'blood_type': unit['blood_type'],
        'donor_id': unit['donor_id'],
        'units': unit['units'],
        'collected_date': collected_date.strftime('%Y-%m-%d %H:%M:%S'),
        'expiry_date': expiry_date.strftime('%Y-%m-%d %H:%M:%S'),
        'hospital_id': str(unit['hospital_id']),
        'hospital': hospital_name,
        'status': unit.get('status', 'available'),
        'location': unit.get('location', 'storage')
    }
    
    # Generate QR code
    qr_code_image = generate_qr_code(qr_data)
    
    # Update database
    blood_units.update_one(
        {'_id': unit['_id']},
        {'$set': {
            'qr_code': qr_code_image,
            'qr_data': qr_data,
            'collected_date': collected_date,
            'collected_date_formatted': collected_date.strftime('%B %d, %Y at %I:%M %p'),
            'expiry_date': expiry_date,
            'expiry_date_formatted': expiry_date.strftime('%B %d, %Y at %I:%M %p')
        }}
    )
    
    fixed += 1
    print(f"✓ Fixed: {unit['blood_id']}")

print(f"\n✅ Done! Fixed {fixed} blood units")
print("🎉 Refresh your hospital dashboard - QR codes should now appear!")

client.close()