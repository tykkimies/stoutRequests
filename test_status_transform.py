#!/usr/bin/env python3
"""Test the status transformation logic"""

def test_status_transformation():
    """Test how database status values are transformed for the template"""
    print("🧪 Testing status transformation logic...\n")
    
    # Simulate the database enum values
    database_statuses = ['PENDING', 'APPROVED', 'AVAILABLE', 'REJECTED']
    
    for db_status in database_statuses:
        # Simulate the transformation logic from the endpoint
        raw_status = db_status.lower()
        # Map database status to template status
        status_str = 'downloading' if raw_status == 'available' else raw_status
        final_status = f'requested_{status_str}'
        
        print(f"📊 Database: {db_status:>9} → Template: {final_status}")
    
    print("\n✅ Expected template status values:")
    expected_statuses = [
        'requested_pending',
        'requested_approved', 
        'requested_downloading',
        'requested_rejected'
    ]
    
    for status in expected_statuses:
        print(f"   • {status}")
    
    print("\n🎯 Checking if these match the macro conditions...")
    
    # These are the conditions in the status_display.html macro
    template_conditions = [
        'requested_pending',
        'requested_approved',
        'requested_downloading', 
        'requested_rejected'
    ]
    
    # Simulate the actual database data we found
    actual_requests = [
        ('F1', 'APPROVED'),
        ('M3GAN 2.0', 'PENDING'),
        ('The Last Rodeo', 'APPROVED'),
        ('Foundation', 'APPROVED'),
        ('Superman', 'APPROVED')
    ]
    
    print("\n📋 Current database requests and their transformed statuses:")
    for title, db_status in actual_requests:
        raw_status = db_status.lower()
        status_str = 'downloading' if raw_status == 'available' else raw_status
        final_status = f'requested_{status_str}'
        
        # Check if this status has a matching template condition
        has_template = final_status in template_conditions
        status_indicator = "✅" if has_template else "❌"
        
        print(f"   {status_indicator} {title:>15}: {db_status} → {final_status}")

if __name__ == "__main__":
    test_status_transformation()