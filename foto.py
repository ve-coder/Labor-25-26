import time
import cv2
import numpy as np
from picamera2 import Picamera2, Preview

picam = Picamera2()

config = picam.create_preview_configuration()

picam.configure(config)

picam.start_preview(Preview.QTGL)

picam.start()
time.sleep(2)
picam.capture_file("test-python.jpg")

picam.close()

img = cv2.imread("test-python.jpg")
hsv_img = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

lower_range = (100, 100,50)
upper_range = (130, 255,255)
mask = cv2.inRange(hsv_img, lower_range, upper_range)

color_image =cv2.bitwise_and(image, image, mask=mask)

#display the color image

cv2.imshow('Color Image', color_image)
cv2.waitkey(0)
cv2.destroyAllWindows()

