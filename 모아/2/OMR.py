import cv2
import numpy as np

img = cv2.imread("music0.jpg")
src = img.copy()

gray = cv2.cvtColor(src, cv2.COLOR_BGR2GRAY)
ret, gray = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
height, width = gray.shape

mask = np.zeros(gray.shape, np.uint8)
cnt, labels, stats, centroids = cv2.connectedComponentsWithStats(gray)

for i in range(1, cnt):
    x, y, w, h, area = stats[i]
    if w > width * 0.5:
        roi = src[y:y+h, x:x+w]
        cv2.imwrite('line%s.png' %i, roi)
for i in range(1, cnt):
    x, y, w, h, area = stats[i]
    if w > width * 0.5:
        cv2.rectangle(mask, (x, y, w, h), (255, 255, 255), -1)
masked = cv2.bitwise_and(gray, mask)

staves = []
for row in range(height):
    pixels = 0
    for col in range(width):
        pixels += (masked[row][col] == 255)
    if pixels >= width * 0.5:
        if len(staves) == 0 or abs(staves[-1][0] + staves[-1][1] - row) > 1:
            staves.append([row, 0])
        else:
            staves[-1][1] += 1

for staff in range(len(staves)):
    top_pixel = staves[staff][0]
    bot_pixel = staves[staff][0] + staves[staff][1]
    for col in range(width):
        if height-staves[staff][1] > bot_pixel and masked[top_pixel - 1][col] == 0 and masked[bot_pixel + 1][col] == 0:
            for row in range(top_pixel, bot_pixel + 1):
                masked[row][col] = 0
cv2.imwrite('score.png', 255-masked)

contours, hierarchy = cv2.findContours(masked, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

i=1
for contour in contours:
    x, y, w, h = cv2.boundingRect(contour)
    roi = 255-masked[y-5:y+h+5, x-5:x+w+5]
    cv2.imwrite('save%s.jpg' %i, roi)
    i+=1
for contour in contours:
    x, y, w, h = cv2.boundingRect(contour)
    cv2.rectangle(src, (x, y, w, h), (255, 0, 0), 2)
    

cv2.imwrite('result.png', result)

cv2.imshow('Result', src)
cv2.waitKey(0)
cv2.destroyAllWindows()