// 피에조 진동 센서 (압전 센서)
// A0 → 센서 신호선
// GND → GND
// VCC → 5V 또는 3.3V

const int piezoPin = A0;   // 센서 핀
int sensorValue = 0;

void setup() {
  Serial.begin(9600);    // 전송 속도를 충분히 빠르게 (Python과 동일하게 맞추세요)
  Serial.println("피에조 진동 센서 측정 시작...");
}

void loop() {
  sensorValue = analogRead(piezoPin); // 센서 값 읽기 (0~1023)

  // 시리얼로 전송
  Serial.println(sensorValue);

  delay(10); // 🔹 10ms 대기 → 초당 약 100회 출력
}