import cv2
import numpy as np

# Bild laden
image = cv2.imread('blau.jpeg')

# In HSV-Farbraum umwandeln
hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

# HSV-Bereich für Blau definieren
'''lower_blue = np.array([100, 150, 50])
upper_blue = np.array([140, 255, 255])'

#HSV-Bereich Rot
lower_red = np.array([0,128,77])
upper_red = np.array([10,255,255])

#HSV-Bereich Gelb
lower_yellow = np.array([20,102,128 ])
upper_yellow = np.array([35,255,255])

#HSV-Bereich Grün
lower_green = np.array([40, 76, 51])
upper_green = np.array([80,255 ,255])

#HSV-Bereich weiß
lower_white = np.array([0,0 ,230 ])
upper_white = np.array([179, 25, 255])

#HSV-Bereich Orange
lower_orange = np.array([10, 128, 102])
upper_orange = np.array([20,255 ,255 ])'''



# Maske für Blau erstellen
mask = cv2.inRange(hsv, lower_blue, upper_blue)
count= cv2.countNonZero(mask)


if count > 500:
    print(Farbe,"ist enthalten")

# Ergebnisbild: nur blaue Bereiche anzeigen
result = cv2.bitwise_and(image, image, mask=mask)

# boxes around areas
#for contour in contours:
  #  x, y, w, h = cv2.boundingRect (contour)
   # cv2.rectangle

# Anzeigen
#cv2.imshow('Original', image)
cv2.imshow('Maske (Blau)', mask)
cv2.imshow('Ergebnis', result)
cv2.waitKey(0)
cv2.destroyAllWindows()
