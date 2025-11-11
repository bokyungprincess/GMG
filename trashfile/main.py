import time
import serial
import threading
from collections import deque

########################################
# 1. drum_sync_data.txt 파서
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

    current_section = None

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
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
        raise ValueError("drum_sync_data.txt에서 필수 메타데이터(bpm/sensor_rate_hz/samples_per_array_element)를 찾지 못했습니다.")

    time_per_sample = 1.0 / sensor_rate_hz
    time_per_array_element = time_per_sample * samples_per_array_element

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
        """새로운 오차를 받아 BPM을 갱신해서 반환"""
        now = time.time()
        if self.prev_time is None:
            dt = 0.01
        else:
            dt = max(now - self.prev_time, 1e-4)

        self.prev_time = now

        # PID 항 계산
        P = error
        self.integral += error * dt
        D = (error - self.prev_error) / dt
        self.prev_error = error

        delta = self.Kp * P + self.Ki * self.integral + self.Kd * D

        # BPM 갱신 및 제한
        self.bpm += delta
        if self.bpm < self.bpm_min:
            self.bpm = self.bpm_min
            self.integral = 0.0
        elif self.bpm > self.bpm_max:
            self.bpm = self.bpm_max
            self.integral = 0.0

        return self.bpm

########################################
# 3. 기준 비트와 센서 이벤트 매칭
########################################

class BeatMatcher:
    """
    drum_sync_data.txt에서 로드한 기준 배열과
    센서로 들어오는 실제 타격 시각을 매칭해서
    오차(error)를 계산해 주는 헬퍼.
    """

    def __init__(self, ref_data):
        self.ref = ref_data
        self.dt = ref_data["time_per_array_element"]

        # 기준 배열
        self.arr = {
            "kick": ref_data["kick"],
            "snare": ref_data["snare"],
            "hit": ref_data["hit"],
        }

        # 각 악기별로 '다음에 기대되는 비트 인덱스' 포인터
        self.idx = {
            "kick": 0,
            "snare": 0,
            "hit": 0,
        }

    def _find_next_index(self, inst, start_idx):
        arr = self.arr[inst]
        n = len(arr)
        i = start_idx
        while i < n:
            if arr[i] == 1:
                return i
            i += 1
        return None

    def compute_error(self, inst, t_actual):
        """
        특정 악기(inst)에 대해,
        실제 타격 시각 t_actual(초)와
        기준 배열의 다음 비트 시각 차이를 반환.
        """
        if inst not in self.arr:
            return None

        start_idx = self.idx[inst]
        next_idx = self._find_next_index(inst, start_idx)
        if next_idx is None:
            # 더 이상 기준 비트 없음
            return None

        t_ref = next_idx * self.dt
        error = t_actual - t_ref

        # 다음부터는 그 다음 비트와 매칭하도록 포인터 이동
        self.idx[inst] = next_idx + 1

        return error

########################################
# 4. 센서(시리얼) 읽기 스레드
########################################

class SensorReader(threading.Thread):
    """
    시리얼 포트에서 센서 데이터를 읽어서
    (timestamp, instrument_type) 형태로 큐에 넣어주는 스레드.
    """

    def __init__(self, port, baudrate=9600):
        super().__init__(daemon=True)
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self.events = deque()
        self.running = False

    def open(self):
        self.ser = serial.Serial(self.port, self.baudrate, timeout=0.1)
        time.sleep(2)
        self.running = True

    def run(self):
        if self.ser is None:
            self.open()

        start_time = time.time()
        print("센서 데이터 수신 시작 (Ctrl+C로 종료)...")

        try:
            while self.running:
                line = self.ser.readline().decode("utf-8", errors="ignore").strip()
                if line:
                    now = time.time() - start_time

                    # TODO: 여기에서 line 내용을 분석해서
                    #       어떤 드럼인지 판별해야 함.
                    # 예시 프로토콜 가정:
                    #   "K" -> kick
                    #   "S" -> snare
                    #   "H" -> hit
                    inst = None
                    if "K" in line:
                        inst = "kick"
                    elif "S" in line:
                        inst = "snare"
                    elif "H" in line:
                        inst = "hit"

                    if inst:
                        self.events.append((now, inst))
                        # 디버그 출력
                        print(f"[{now:8.3f}s] 센서 이벤트: {inst} (raw: {line})")

                # 너무 바쁘지 않게 약간 쉼
                time.sleep(0.001)

        finally:
            if self.ser and self.ser.is_open:
                self.ser.close()
            print("센서 리더 종료")

    def get_event(self):
        """메인 루프에서 한 개씩 이벤트를 꺼낼 때 사용"""
        if self.events:
            return self.events.popleft()
        return None

    def stop(self):
        self.running = False

########################################
# 5. (옵션) 메트로놈 / MIDI 출력 (단순 버전)
########################################

class SimpleMetronome(threading.Thread):
    """
    현재 BPM에 맞춰 '틱'을 출력하는 매우 단순한 메트로놈.
    실제 프로젝트에서는 pygame.midi나 외부 DAW 연동으로 교체.
    """

    def __init__(self, get_bpm_func):
        super().__init__(daemon=True)
        self.get_bpm = get_bpm_func
        self.running = True

    def run(self):
        next_tick = time.time()
        while self.running:
            bpm = self.get_bpm()
            if bpm <= 0:
                time.sleep(0.01)
                continue

            interval = 60.0 / bpm  # 1박(4분음표) 간격
            now = time.time()
            if now >= next_tick:
                print(f"[METRO] BPM={bpm:6.2f}")
                # 여기에서 실제 MIDI click / sound 재생 가능
                next_tick = now + interval
            time.sleep(0.001)

    def stop(self):
        self.running = False

########################################
# 6. main: 전체 오케스트레이션
########################################

def main():
    # 1) 전처리 결과 로드 (drum_v16.py가 미리 생성한 파일)
    ref = load_drum_sync_data("drum_sync_data.txt")
    print(f"기준 BPM: {ref['bpm']}")
    print(f"배열 요소당 시간: {ref['time_per_array_element']} 초")

    # 2) 매칭기 & PID 초기화
    matcher = BeatMatcher(ref)

    # PID 게인 값은 실험적으로 튜닝 필요
    pid = PIDController(
        Kp=0.5,
        Ki=0.1,
        Kd=0.05,
        initial_bpm=ref["bpm"],
        bpm_min=40.0,
        bpm_max=240.0
    )

    # 3) 센서 리더 시작 (포트 이름은 환경에 맞게 수정)
    sensor = SensorReader(port="COM3", baudrate=9600)
    sensor.start()

    # 4) 메트로놈(또는 MIDI 출력) 시작
    metro = SimpleMetronome(get_bpm_func=lambda: pid.bpm)
    metro.start()

    print("\n=== 실시간 템포 추적 시작 ===")
    print("센서 이벤트 → 기준 비트와 비교 → 오차 → PID → 수정 BPM")
    print("Ctrl+C로 종료.\n")

    try:
        while True:
            event = sensor.get_event()
            if event is None:
                time.sleep(0.001)
                continue

            t_actual, inst = event

            # 기준 비트와 비교해서 오차 계산
            error = matcher.compute_error(inst, t_actual)
            if error is None:
                # 더 이상 매칭할 기준 비트가 없거나, 해당 악기에 대한 기준 없음
                continue

            # PID 업데이트
            new_bpm = pid.update(error)

            # 디버그 출력: 오차와 보정된 BPM
            print(f"[{t_actual:8.3f}s] inst={inst:5s} "
                  f"error={error*1000:+7.2f} ms  ->  BPM={new_bpm:7.3f}")

    except KeyboardInterrupt:
        print("\n종료 신호 감지. 정리 중...")

    finally:
        sensor.stop()
        metro.stop()
        sensor.join()
        metro.join()
        print("정상 종료.")

########################################

if __name__ == "__main__":
    main()