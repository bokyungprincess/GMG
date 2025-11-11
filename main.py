import time
import threading
from collections import deque

import serial  # pip install pyserial

########################################
# 1. drum_sync_data.txt 로드
########################################

def load_drum_sync_data(path="drum_sync_data.txt"):
    """
    drum_v16.py가 생성한 drum_sync_data.txt를 읽어서
    - 기준 BPM
    - 센서 주파수
    - 배열 요소당 시간
    - 킥/스네어/힛 기준 비트 배열
    을 로드.
    """
    bpm = None
    sensor_rate_hz = None
    samples_per_array_element = None

    beat_array_kick = []
    beat_array_snare = []
    beat_array_hit = []

    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("##") or line.startswith("# "):
                continue

            if line.startswith("bpm:"):
                bpm = float(line.split(":", 1)[1].strip())
            elif line.startswith("sensor_rate_hz:"):
                sensor_rate_hz = float(line.split(":", 1)[1].strip())
            elif line.startswith("samples_per_array_element:"):
                samples_per_array_element = float(line.split(":", 1)[1].strip())

            elif line.startswith("beat_array_kick:"):
                arr = line.split(":", 1)[1].strip()
                beat_array_kick = [int(x) for x in arr.split(",") if x != ""]
            elif line.startswith("beat_array_snare:"):
                arr = line.split(":", 1)[1].strip()
                beat_array_snare = [int(x) for x in arr.split(",") if x != ""]
            elif line.startswith("beat_array_hit:"):
                arr = line.split(":", 1)[1].strip()
                beat_array_hit = [int(x) for x in arr.split(",") if x != ""]

    if bpm is None or sensor_rate_hz is None or samples_per_array_element is None:
        raise ValueError("drum_sync_data.txt에서 bpm / sensor_rate_hz / samples_per_array_element를 찾지 못했습니다.")

    # 배열 하나의 칸(한 grid)의 실제 시간 (초)
    time_per_array_element = samples_per_array_element / sensor_rate_hz

    return {
        "bpm": bpm,
        "sensor_rate_hz": sensor_rate_hz,
        "samples_per_array_element": samples_per_array_element,
        "time_per_array_element": time_per_array_element,
        "kick": beat_array_kick,
        "snare": beat_array_snare,
        "hit": beat_array_hit,
    }

########################################
# 2. PID 제어기
########################################

class PIDController:
    def __init__(self, Kp, Ki, Kd, initial_bpm, bpm_min=40.0, bpm_max=240.0):
        self.Kp = Kp
        self.Ki = Ki
        self.Kd = Kd

        self.integral = 0.0
        self.prev_error = 0.0
        self.prev_time = None

        self.bpm = initial_bpm
        self.bpm_min = bpm_min
        self.bpm_max = bpm_max

    def update(self, error):
        """
        새로운 오차(초 단위)를 받아서 BPM을 갱신하고 반환.
        error > 0  = 연주가 기준보다 늦음 → BPM 약간 올리기
        error < 0  = 연주가 기준보다 빠름 → BPM 약간 내리기
        """
        now = time.time()
        if self.prev_time is None:
            dt = 0.01
        else:
            dt = max(now - self.prev_time, 1e-4)
        self.prev_time = now

        # PID
        P = error
        self.integral += error * dt
        D = (error - self.prev_error) / dt
        self.prev_error = error

        delta = self.Kp * P + self.Ki * self.integral + self.Kd * D

        # BPM 업데이트 + 제한
        self.bpm += delta
        if self.bpm < self.bpm_min:
            self.bpm = self.bpm_min
            self.integral = 0.0
        elif self.bpm > self.bpm_max:
            self.bpm = self.bpm_max
            self.integral = 0.0

        return self.bpm

########################################
# 3. 기준 비트와 센서 이벤트 매칭기
########################################

class BeatMatcher:
    """
    drum_sync_data.txt에서 가져온 기준 배열에 대해
    실제 타격 시각을 넣으면 오차(초)를 계산해 주는 클래스.
    """

    def __init__(self, ref_data):
        self.dt = ref_data["time_per_array_element"]

        self.arr = {
            "kick": ref_data["kick"],
            "snare": ref_data["snare"],
            "hit": ref_data["hit"],
        }

        # 각 악기별로 "다음에 기대되는 비트" 인덱스
        self.next_idx = {k: 0 for k in self.arr.keys()}

    def _find_next_beat(self, inst, start):
        arr = self.arr[inst]
        n = len(arr)
        i = start
        while i < n:
            if arr[i] == 1:
                return i
            i += 1
        return None

    def compute_error(self, inst, t_actual):
        """
        inst: 'kick' / 'snare' / 'hit'
        t_actual: 실제 타격 시각 (초, 시작 기준)
        return: error(초) 또는 None (더 이상 기준 없음)
        """
        if inst not in self.arr:
            return None

        start = self.next_idx[inst]
        idx = self._find_next_beat(inst, start)
        if idx is None:
            return None  # 곡 끝났거나 기준 없음

        t_ref = idx * self.dt
        error = t_actual - t_ref

        # 다음 비트로 포인터 이동
        self.next_idx[inst] = idx + 1
        return error

########################################
# 4. 시리얼 센서 리더 (reader.py 확장)
########################################

class SensorReader(threading.Thread):
    """
    reader.py 아이디어 기반:
    시리얼에서 한 줄씩 읽고, 타임스탬프와 함께 큐에 저장.
    """

    def __init__(self, port, baudrate=9600):
        super().__init__(daemon=True)
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self.running = False
        self.events = deque()
        self.start_time = None

    def open(self):
        self.ser = serial.Serial(self.port, self.baudrate, timeout=0.1)
        time.sleep(2)  # 아두이노 리셋 대기
        self.running = True
        self.start_time = time.time()
        print(f"시리얼 포트 열림: {self.port} (baud {self.baudrate})")

    def run(self):
        if self.ser is None:
            self.open()

        print("센서 데이터 수신 시작 (Ctrl+C로 종료)...")

        try:
            while self.running:
                line = self.ser.readline().decode("utf-8", errors="ignore").strip()
                if line:
                    now = time.time() - self.start_time

                    # 여기서 line 내용으로 어떤 드럼인지 판별
                    # 실제 센서 프로토콜에 맞게 수정해야 함.
                    inst = None
                    up = line.upper()
                    if "K" in up:
                        inst = "kick"
                    elif "S" in up:
                        inst = "snare"
                    elif "H" in up:
                        inst = "hit"

                    if inst:
                        self.events.append((now, inst))
                        print(f"[SENSOR] {now:8.3f}s  inst={inst}  raw={line}")

                time.sleep(0.001)

        finally:
            if self.ser and self.ser.is_open:
                self.ser.close()
            print("센서 리더 종료")

    def get_event(self):
        if self.events:
            return self.events.popleft()
        return None

    def stop(self):
        self.running = False

########################################
# 5. 메트로놈 (보정 BPM 모니터용)
########################################

class SimpleMetronome(threading.Thread):
    """
    현재 PID에서 나온 BPM을 보고 일정 간격으로 로그를 찍는 메트로놈.
    실제 프로젝트에선 여기서 MIDI 클릭 사운드 내면 됨.
    """

    def __init__(self, get_bpm):
        super().__init__(daemon=True)
        self.get_bpm = get_bpm
        self.running = True

    def run(self):
        next_tick = time.time()
        while self.running:
            bpm = self.get_bpm()
            if bpm <= 0:
                time.sleep(0.01)
                continue

            interval = 60.0 / bpm  # 4분음표 기준
            now = time.time()
            if now >= next_tick:
                print(f"[METRO] BPM={bpm:6.2f}")
                next_tick = now + interval
            time.sleep(0.001)

    def stop(self):
        self.running = False

########################################
# 6. main: 전체 통합
########################################

def main():
    # 1) 전처리 결과 로드
    ref = load_drum_sync_data("drum_sync_data.txt")
    print("=== drum_sync_data.txt 로드 완료 ===")
    print(f"기준 BPM: {ref['bpm']}")
    print(f"센서 주파수: {ref['sensor_rate_hz']} Hz")
    print(f"배열 요소당 시간: {ref['time_per_array_element']:.6f} s")
    print()

    # 2) 매칭기 & PID 설정
    matcher = BeatMatcher(ref)

    # PID gain은 실험적으로 조정 필요
    pid = PIDController(
        Kp=30.0,   # 너무 작으면 반응이 없고, 너무 크면 요동침
        Ki=0.0,
        Kd=5.0,
        initial_bpm=ref["bpm"],
        bpm_min=40.0,
        bpm_max=240.0
    )

    # 3) 시리얼 리더 시작 (포트 이름 꼭 수정!!)
    # macOS 예시: "/dev/tty.usbmodem1101" 등
    SERIAL_PORT = "/dev/tty.usbmodemXXXX"  # TODO: 실제 포트로 변경
    sensor = SensorReader(port=SERIAL_PORT, baudrate=9600)
    sensor.start()

    # 4) 메트로놈 시작
    metro = SimpleMetronome(get_bpm=lambda: pid.bpm)
    metro.start()

    print("=== 실시간 드럼 동기화 시작 ===")
    print("센서 → 기준 비트 매칭 → 오차 → PID → 보정 BPM")
    print("Ctrl + C 로 종료\n")

    try:
        while True:
            ev = sensor.get_event()
            if ev is None:
                time.sleep(0.001)
                continue

            t_actual, inst = ev

            # 기준 비트와의 시간차 계산
            error = matcher.compute_error(inst, t_actual)
            if error is None:
                # 기준 비트 소진 or 해당 악기 기준 없음
                continue

            new_bpm = pid.update(error)

            print(f"[MATCH] t={t_actual:8.3f}s inst={inst:5s} "
                  f"err={error*1000:+7.2f} ms  ->  BPM={new_bpm:7.3f}")

    except KeyboardInterrupt:
        print("\n종료 요청 감지. 스레드 정리 중...")

    finally:
        sensor.stop()
        metro.stop()
        sensor.join()
        metro.join()
        print("정상 종료.")

########################################

if __name__ == "__main__":
    main()