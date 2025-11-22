import qrcode
import io
import base64
import json
from datetime import datetime, timedelta
from pymongo import MongoClient
from bson.objectid import ObjectId

# MongoDB connection
MONGO_URI = "mongodb+srv://praveensah2608_db_user:XEDQI2M5OWk4I3EE@cluster0.lilts6y.mongodb.net/lifelink_grid?retryWrites=true&w=majority"

def generate_qr_code(data):
    """Generate QR code and return as base64"""
    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        # Convert dict to JSON string for QR code
        json_data = json.dumps(data)
        qr.add_data(json_data)
        qr.make(fit=True)
        
        # Create the image
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Convert to base64
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        img_base64 = base64.b64encode(buffer.getvalue()).decode()
        
        return f"data:image/png;base64,{img_base64}"
    except Exception as e:
        print(f"Error generating QR code: {e}")
        return None

def test_qr_generation():
    """Test QR code generation"""
    print("🧪 Testing QR Code Generation...\n")
    
    # Test data
    collected_date = datetime.now()
    expiry_date = collected_date + timedelta(days=35)
    
    test_data = {
        'blood_id': 'BLOODTEST123',
        'blood_type': 'A+',
        'donor_id': 'DONOR001',
        'units': 2,
        'collected_date': collected_date.strftime('%Y-%m-%d %H:%M:%S'),
        'expiry_date': expiry_date.strftime('%Y-%m-%d %H:%M:%S'),
        'hospital_id': 'test_hospital',
        'hospital': 'Test Hospital',
        'status': 'in_storage',
        'location': 'storage'
    }
    
    print("Test Data:")
    print(json.dumps(test_data, indent=2))
    print()
    
    qr_code = generate_qr_code(test_data)
    
    if qr_code:
        print("✅ QR Code generated successfully!")
        print(f"📏 QR Code length: {len(qr_code)} characters")
        print(f"🔤 First 100 chars: {qr_code[:100]}...")
        
        # Save to file for testing
        if qr_code.startswith('data:image/png;base64,'):
            img_data = qr_code.split(',')[1]
            with open('test_qr.png', 'wb') as f:
                f.write(base64.b64decode(img_data))
            print("💾 Saved test QR code to: test_qr.png")
    else:
        print("❌ Failed to generate QR code!")
    
    return qr_code

def regenerate_all_qr_codes():
    """Regenerate QR codes for all blood units in database"""
    print("\n🔄 Regenerating QR codes for all blood units...\n")
    
    client = MongoClient(MONGO_URI)
    db = client.lifelink_grid
    blood_units = db.blood_units
    
    units = list(blood_units.find({}))
    print(f"Found {len(units)} blood units")
    
    regenerated = 0
    failed = 0
    
    for unit in units:
        try:
            # Ensure dates are datetime objects
            collected_date = unit.get('collected_date')
            if isinstance(collected_date, str):
                collected_date = datetime.fromisoformat(collected_date)
            elif not isinstance(collected_date, datetime):
                collected_date = datetime.now() - timedelta(days=1)
            
            expiry_date = unit.get('expiry_date')
            if isinstance(expiry_date, str):
                expiry_date = datetime.fromisoformat(expiry_date)
            elif not isinstance(expiry_date, datetime):
                expiry_date = collected_date + timedelta(days=35)
            
            # Create QR data
            qr_data = {
                'blood_id': unit['blood_id'],
                'blood_type': unit['blood_type'],
                'donor_id': unit['donor_id'],
                'units': unit['units'],
                'collected_date': collected_date.strftime('%Y-%m-%d %H:%M:%S'),
                'expiry_date': expiry_date.strftime('%Y-%m-%d %H:%M:%S'),
                'hospital_id': str(unit['hospital_id']),
                'hospital': unit.get('hospital', 'Unknown Hospital'),
                'status': unit.get('status', 'in_storage'),
                'location': unit.get('location', 'storage')
            }
            
            # Generate QR code
            qr_code_image = generate_qr_code(qr_data)
            
            if qr_code_image:
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
                regenerated += 1
                print(f"✓ Regenerated QR for {unit['blood_id']}")
            else:
                failed += 1
                print(f"✗ Failed to generate QR for {unit['blood_id']}")
                
        except Exception as e:
            failed += 1
            print(f"✗ Error processing {unit.get('blood_id', 'Unknown')}: {e}")
    
    print(f"\n✅ Successfully regenerated {regenerated} QR codes")
    if failed > 0:
        print(f"❌ Failed to regenerate {failed} QR codes")
    
    client.close()

if __name__ == '__main__':
    print("=" * 60)
    print("QR Code Generation Test Suite")
    print("=" * 60)
    
    # Test basic QR generation
    test_qr_generation()
    
    # Ask user if they want to regenerate all QR codes
    print("\n" + "=" * 60)
    response = input("\nDo you want to regenerate QR codes for all blood units in database? (yes/no): ")
    
    if response.lower() in ['yes', 'y']:
        regenerate_all_qr_codes()
    else:
        print("Skipped database regeneration.")
    
    print("\n✨ All done!")