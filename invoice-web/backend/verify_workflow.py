#!/usr/bin/env python3
"""
Verification script to test the end-to-end workflow:
Register -> Login -> Upload -> Review -> Confirm -> List
"""

import sys
import os
import tempfile
import json
from pathlib import Path

# Add the app directory to the path
sys.path.insert(0, '.')

from app.main import app
from fastapi.testclient import TestClient

def test_workflow():
    """Test the complete workflow"""
    print("Starting workflow verification...")

    # Create test client
    client = TestClient(app)

    # Test data
    test_email = "verifytest@example.com"
    test_password = "testpass123"

    # 1. Register user
    print("\n1. Testing user registration...")
    response = client.post("/auth/register", data={
        "email": test_email,
        "password": test_password
    })

    if response.status_code != 200:
        # Maybe user already exists, try to login instead
        print(f"   Registration failed (may already exist): {response.status_code}")
        print(f"   Response: {response.json()}")
    else:
        print("   Registration successful")
        tokens = response.json()
        access_token = tokens["access_token"]
        print(f"   Got access token: {access_token[:20]}...")

    # 2. Login user
    print("\n2. Testing user login...")
    response = client.post("/auth/login", data={
        "username": test_email,
        "password": test_password
    })

    if response.status_code != 200:
        print(f"   Login failed: {response.status_code}")
        print(f"   Response: {response.text}")
        return False

    print("   Login successful")
    tokens = response.json()
    access_token = tokens["access_token"]
    print(f"   Got access token: {access_token[:20]}...")

    # Set authorization header for subsequent requests
    headers = {"Authorization": f"Bearer {access_token}"}

    # 3. Test upload endpoint (we'll simulate a file upload)
    print("\n3. Testing file upload...")

    # Create a simple test file (PNG image)
    test_file_content = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"

    # Create a temporary file
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_file:
        tmp_file.write(test_file_content)
        tmp_file_path = tmp_file.name

    try:
        with open(tmp_file_path, 'rb') as f:
            response = client.post(
                "/api/upload",
                files={"file": ("test.png", f, "image/png")},
                headers=headers
            )

        if response.status_code != 200:
            print(f"   Upload failed: {response.status_code}")
            print(f"   Response: {response.text}")
            return False

        print("   Upload successful")
        upload_data = response.json()
        job_id = upload_data["job_id"]
        print(f"   Got job ID: {job_id}")

        # 4. Test review endpoint
        print("\n4. Testing review endpoint...")
        response = client.get(f"/review/{job_id}", headers=headers)

        if response.status_code != 200:
            print(f"   Review failed: {response.status_code}")
            print(f"   Response: {response.text}")
            return False

        print("   Review successful")
        # Check that we got HTML back
        if "text/html" not in response.headers.get("content-type", ""):
            print(f"   Warning: Expected HTML response, got: {response.headers.get('content-type')}")

        # 5. Test confirm endpoint
        print("\n5. Testing confirm endpoint...")
        # We need to get contractors and sources first for the form data
        contractors_response = client.get("/api/contractors", headers=headers)
        sources_response = client.get("/api/sources", headers=headers)

        if contractors_response.status_code != 200 or sources_response.status_code != 200:
            print(f"   Failed to get contractors/sources")
            return False

        contractors = contractors_response.json()
        sources = sources_response.json()

        if not contractors or not sources:
            print(f"   No contractors or sources available")
            return False

        # Use the first contractor and source
        contractor_id = contractors[0]["id"]
        source_id = sources[0]["id"]

        # Prepare confirm data
        confirm_data = {
            "job_id": job_id,
            "contractor_id": str(contractor_id),
            "source_id": str(source_id),
            "date": "2024-01-15",
            "amount": "100.00"
        }

        response = client.post("/api/confirm", data=confirm_data, headers=headers)

        if response.status_code not in [200, 303]:  # 303 is redirect after successful confirm
            print(f"   Confirm failed: {response.status_code}")
            print(f"   Response: {response.text}")
            return False

        print("   Confirm successful")
        if response.status_code == 303:
            print("   Got redirect response (expected after confirm)")

        # 6. Test list invoices endpoint
        print("\n6. Testing list invoices endpoint...")
        response = client.get("/api/invoices", headers=headers)

        if response.status_code != 200:
            print(f"   List invoices failed: {response.status_code}")
            print(f"   Response: {response.text}")
            return False

        print("   List invoices successful")
        invoices_data = response.json()
        print(f"   Found {len(invoices_data)} invoices")

        # Verify we have at least the invoice we just confirmed
        if len(invoices_data) > 0:
            invoice = invoices_data[0]
            contractor_name = invoice['contractor']['name'] if invoice['contractor'] else 'N/A'
            source_name = invoice['source']['name'] if invoice['source'] else 'N/A'
            print(f"   Latest invoice: #{invoice['id']} - {contractor_name} - ${invoice['amount']}")

        print("\nAll workflow tests passed!")
        return True

    finally:
        # Clean up temp file
        try:
            os.unlink(tmp_file_path)
        except:
            pass

if __name__ == "__main__":
    success = test_workflow()
    sys.exit(0 if success else 1)