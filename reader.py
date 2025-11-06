import serial
import time

ser = serial.Serial('COM3', 9600)
time.sleep(2)

print("데이터 수신 중... (Ctrl+C로 종료)")

try:
    # 데이터 수신 시작 시각 기록 (기준점)
    start_time = time.time()
    while True:
        line = ser.readline().decode('utf-8', errors='ignore').strip()
        if line:
            # 시작 이후 경과 시간 계산
            elapsed = time.time() - start_time
            minutes = int(elapsed // 60)
            seconds = int(elapsed % 60)
            milliseconds = int((elapsed % 1) * 100)

            # "분:초.밀리초" 형식으로 출력
            timestamp = f"{minutes:02d}:{seconds:02d}.{milliseconds:02d}"
            print(f"[{timestamp}] : {line}")
        
        time.sleep(1)  # 초당 n회

except KeyboardInterrupt:
    print("\n종료합니다.")
finally:
    ser.close()
