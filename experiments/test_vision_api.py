import sys, urllib.request, json
import numpy as np, cv2

# Create a small valid test image with text
img = np.full((360, 640, 3), 255, dtype=np.uint8)
cv2.putText(img, "TEST SLIDE TITLE", (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2)
_, encoded = cv2.imencode('.jpg', img)
jpeg_bytes = encoded.tobytes()

req = urllib.request.Request(
    'http://localhost:8004/api/live/vision/frame',
    data=jpeg_bytes,
    headers={
        'Content-Type': 'image/jpeg',
        'X-Session-ID': 'test_sess',
        'X-Source-Epoch': '1',
        'X-Frame-ID': 'f_test_1',
        'X-Captured-Client-Ms': '1000'
    },
    method='POST'
)

res = urllib.request.urlopen(req)
print('Frame POST status:', res.status, json.loads(res.read()))

# Poll result
import time
time.sleep(1.0)
res_poll = urllib.request.urlopen('http://localhost:8004/api/live/vision/result?session_id=test_sess&source_epoch=1')
print('Vision result:', res_poll.status, json.loads(res_poll.read()))
