import httpx
from PIL import Image, ImageDraw
import io

# Login
r = httpx.post('http://localhost:8000/auth/login', data={'username': 'test3@example.com', 'password': 'testpass123'}, headers={'Content-Type': 'application/x-www-form-urlencoded'})
token = r.json()['access_token']
headers = {'Authorization': f'Bearer {token}'}

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
r = httpx.post('http://localhost:8000/api/upload', files=files, headers=headers)
print('Upload:', r.status_code)
job_id = r.json()['job_id']
display_filename = r.json()['display_filename']
print('Job ID:', job_id)
print('Display filename:', display_filename)

# Confirm
confirm_data = {
    'job_id': job_id,
    'contractor_id': 1,
    'source_id': 1,
    'date': '2024-01-15',
    'amount': '100.00',
    'display_filename': display_filename
}
r = httpx.post('http://localhost:8000/confirm', data=confirm_data, headers=headers)
print('Confirm:', r.status_code)
print(r.json())