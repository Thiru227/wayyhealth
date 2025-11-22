from pymongo import MongoClient
from datetime import datetime, timedelta
import json

# MongoDB connection
MONGO_URI = "mongodb+srv://praveensah2608_db_user:XEDQI2M5OWk4I3EE@cluster0.lilts6y.mongodb.net/lifelink_grid?retryWrites=true&w=majority"
client = MongoClient(MONGO_URI)
db = client.lifelink_grid

def fix_existing_blood_units():
    """Fix blood units with missing or invalid dates"""
    
    blood_units = db.blood_units
    
    # Find all blood units
    units = list(blood_units.find({}))
    
    print(f"Found {len(units)} blood units to check...")
    fixed_count = 0
    
    for unit in units:
        needs_update = False
        update_data = {}
        
        # Check if collected_date is missing or invalid
        if 'collected_date' not in unit or unit['collected_date'] is None or unit['collected_date'] == 'N/A':
            # Set to yesterday for older units, today for recent ones
            collected_date = datetime.now() - timedelta(days=1)
            update_data['collected_date'] = collected_date
            update_data['collected_date_formatted'] = collected_date.strftime('%B %d, %Y at %I:%M %p')
            needs_update = True
            print(f"  Fixing collected_date for {unit.get('blood_id', 'Unknown')}")
        elif isinstance(unit['collected_date'], str):
            # Parse string date
            try:
                collected_date = datetime.fromisoformat(unit['collected_date'].replace('Z', '+00:00'))
                update_data['collected_date'] = collected_date
                update_data['collected_date_formatted'] = collected_date.strftime('%B %d, %Y at %I:%M %p')
                needs_update = True
            except:
                collected_date = datetime.now() - timedelta(days=1)
                update_data['collected_date'] = collected_date
                update_data['collected_date_formatted'] = collected_date.strftime('%B %d, %Y at %I:%M %p')
                needs_update = True
        else:
            collected_date = unit['collected_date']
            # Add formatted version if missing
            if 'collected_date_formatted' not in unit:
                update_data['collected_date_formatted'] = collected_date.strftime('%B %d, %Y at %I:%M %p')
                needs_update = True
        
        # Check if expiry_date is missing or invalid
        if 'expiry_date' not in unit or unit['expiry_date'] is None or unit['expiry_date'] == 'N/A':
            # Set expiry to 35 days from collection
            expiry_date = collected_date + timedelta(days=35)
            update_data['expiry_date'] = expiry_date
            update_data['expiry_date_formatted'] = expiry_date.strftime('%B %d, %Y at %I:%M %p')
            needs_update = True
            print(f"  Fixing expiry_date for {unit.get('blood_id', 'Unknown')}")
        elif isinstance(unit['expiry_date'], str):
            # Parse string date
            try:
                expiry_date = datetime.fromisoformat(unit['expiry_date'].replace('Z', '+00:00'))
                update_data['expiry_date'] = expiry_date
                update_data['expiry_date_formatted'] = expiry_date.strftime('%B %d, %Y at %I:%M %p')
                needs_update = True
            except:
                expiry_date = collected_date + timedelta(days=35)
                update_data['expiry_date'] = expiry_date
                update_data['expiry_date_formatted'] = expiry_date.strftime('%B %d, %Y at %I:%M %p')
                needs_update = True
        else:
            expiry_date = unit['expiry_date']
            # Add formatted version if missing
            if 'expiry_date_formatted' not in unit:
                update_data['expiry_date_formatted'] = expiry_date.strftime('%B %d, %Y at %I:%M %p')
                needs_update = True
        
        # Update QR data if needed
        if 'qr_data' in unit and needs_update:
            qr_data = unit['qr_data']
            if isinstance(qr_data, dict):
                qr_data['collected_date'] = collected_date.strftime('%Y-%m-%d %H:%M:%S')
                qr_data['expiry_date'] = expiry_date.strftime('%Y-%m-%d %H:%M:%S')
                update_data['qr_data'] = qr_data
        
        # Perform update if needed
        if needs_update:
            blood_units.update_one(
                {'_id': unit['_id']},
                {'$set': update_data}
            )
            fixed_count += 1
            print(f"✓ Fixed blood unit: {unit.get('blood_id', 'Unknown')}")
    
    print(f"\n✅ Successfully fixed {fixed_count} blood units!")
    print(f"📊 Total units in database: {len(units)}")

if __name__ == '__main__':
    print("🔧 Fixing existing blood units with missing dates...\n")
    fix_existing_blood_units()
    print("\n✨ All done!")