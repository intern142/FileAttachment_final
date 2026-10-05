import sys
import os
import threading
import time
import uvicorn
from app.main import app

def run_server():
    uvicorn.run(app, host='0.0.0.0', port=8000, workers=1)

server_thread = threading.Thread(target=run_server, daemon=True)
server_thread.start()

time.sleep(3)

import httpx
from PIL import Image, ImageDraw
import io

# Login
r = httpx.post('http://localhost:8000/auth/login', data={'username': 'test3@example.com', 'password': 'testpass123'}, headers={'Content-Type': 'application/x-www-form-urlencoded'})
token = r.json()['access_token']
print('Token:', token[:20])

# Create test image
img = Image.new('RGB', (400, 300), color='white')
draw = ImageDraw.Draw(img)
draw.text((50, 50), 'Contractor: ABC Company', fill='black')
draw.text((50, 100), 'Source: Online Store', fill='black')
draw.text((50, 150), 'Date: 2024-01-15', fill='black')
draw.text((50, 200), 'Amount: 100.00', fill='black')

img_bytes = io.BytesIO()
img.save(img_bytes, format='PNG')
img_bytes.seek(0)

# Upload
files = {'file': ('test_invoice.png', img_bytes, 'image/png')}
headers = {'Authorization': f'Bearer {token}'}
r = httpx.post('http://localhost:8000/api/upload', files=files, headers=headers)
print('Upload status:', r.status_code)
job_id = r.json()['job_id']
print('Job ID:', job_id)

# Test review page
r = httpx.get(f'http://localhost:8000/review/{job_id}', headers={'Authorization': f'Bearer {token}'})
print('Review status:', r.status_code)
print('Review text:', r.text[:3000])

time.sleep(1)