import time
import threading
from collections import deque
import random

########################################
# 1. drum_sync_data.txt 로드
########################################

def load_drum_sync_data(path="drum_sync_data.txt"):
    """
    drum_v16.py가 생성한 drum_sync_data.txt를 읽어서
    기준 정보와 비트 배열을 로드.
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
        error: 기준 시각 대비 실제 타격 시각 차이 (초)
        >0: 실제가 늦음 → BPM ↑
        <0: 실제가 빠름 → BPM ↓
        """
        now = time.time()
        if self.prev_time is None:
            dt = 0.01
        else:
            dt = max(now - self.prev_time, 1e-4)
        self.prev_time = now

        P = error
        self.integral += error * dt
        D = (error - self.prev_error) / dt
        self.prev_error = error

        delta = self.Kp * P + self.Ki * self.integral + self.Kd * D

        self.bpm += delta
        if self.bpm < self.bpm_min:
            self.bpm = self.bpm_min
            self.integral = 0.0
        elif self.bpm > self.bpm_max:
            self.bpm = self.bpm_max
            self.integral = 0.0

        return self.bpm

########################################
# 3. 기준 비트 매칭기
########################################

class BeatMatcher:
    """
    기준 배열(kick/snare/hit)에 대해 실제 타격 시각을 넣으면
    다음 기대 비트와의 시간 오차(초)를 반환.
    """

    def __init__(self, ref_data):
        self.dt = ref_data["time_per_array_element"]
        self.arr = {
            "kick": ref_data["kick"],
            "snare": ref_data["snare"],
            "hit": ref_data["hit"],
        }
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
        t_actual: 실제 타격 시각(초), 전체 시작 기준
        """
        if inst not in self.arr:
            return None

        start = self.next_idx[inst]
        idx = self._find_next_beat(inst, start)
        if idx is None:
            return None  # 더 이상 기대 비트 없음

        t_ref = idx * self.dt
        error = t_actual - t_ref

        self.next_idx[inst] = idx + 1
        return error

########################################
# 4. 가짜 센서 (시뮬레이터)
########################################

class SimulatedSensor(threading.Thread):
    """
    실제 센서 대신:
    - drum_sync_data의 기준 비트 시각들을 보고
    - 약간 빠르거나 느리게(오프셋 + 랜덤 지터) 이벤트를 만들어내는 가짜 센서.
    """

    def __init__(self, ref_data, events_queue,
                 timing_offset_ms=40.0,  # 전체적으로 40ms 늦게 치는 드러머
                 jitter_ms=15.0):        # ±15ms 랜덤 변동
        super().__init__(daemon=True)
        self.dt = ref_data["time_per_array_element"]
        self.arr = {
            "kick": ref_data["kick"],
            "snare": ref_data["snare"],
            "hit": ref_data["hit"],
        }
        self.events = events_queue
        self.offset = timing_offset_ms / 1000.0
        self.jitter = jitter_ms / 1000.0
        self.running = True
        self.finished = False

        # 미리 (t_ref, inst) 리스트 생성
        self.schedule = []
        for inst, arr in self.arr.items():
            for i, v in enumerate(arr):
                if v == 1:
                    t_ref = i * self.dt
                    self.schedule.append((t_ref, inst))
        # 시간 순으로 정렬
        self.schedule.sort(key=lambda x: x[0])

    def run(self):
        if not self.schedule:
            print("[SIM] 기준 비트가 없습니다. 시뮬레이터 종료.")
            self.finished = True
            return

        start_time = time.time()
        print("[SIM] 가짜 센서 시작 (offset=%.1fms, jitter=±%.1fms)" %
              (self.offset*1000, self.jitter*1000))

        for t_ref, inst in self.schedule:
            if not self.running:
                break

            # 이 비트에 대한 실제 타격 시간 (조금 늦거나/빠르게)
            jitter = random.uniform(-self.jitter, self.jitter)
            t_actual = t_ref + self.offset + jitter  # 기준보다 약간 늦게/빠르게

            target = start_time + t_actual

            # 해당 시각까지 대기
            while self.running and time.time() < target:
                time.sleep(0.001)

            if not self.running:
                break

            now = time.time() - start_time
            # 이벤트 큐에 추가
            self.events.append((now, inst))
            print(f"[SIM]  {now:8.3f}s  inst={inst:5s} (ref={t_ref:7.3f}s)")

        self.finished = True
        print("[SIM] 모든 이벤트 전송 완료.")

    def stop(self):
        self.running = False

########################################
# 5. 메트로놈
########################################

class SimpleMetronome(threading.Thread):
    """
    PID가 만들어낸 현재 BPM에 맞춰 tick 로그를 찍는 메트로놈.
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

            interval = 60.0 / bpm
            now = time.time()
            if now >= next_tick:
                print(f"[METRO] BPM={bpm:7.3f}")
                next_tick = now + interval
            time.sleep(0.001)

    def stop(self):
        self.running = False

########################################
# 6. main: 전체 통합
########################################

def main():
    # 1) 기준 데이터 로드
    ref = load_drum_sync_data("drum_sync_data.txt")
    print("=== drum_sync_data.txt 로드 완료 ===")
    print(f"기준 BPM: {ref['bpm']}")
    print(f"배열 요소당 시간: {ref['time_per_array_element']:.6f} s")
    print()

    # 2) BeatMatcher + PID 세팅
    matcher = BeatMatcher(ref)

    # 초기값/게인은 실험용. 필요하면 조정해봐도 됨.
    pid = PIDController(
        Kp=25.0,
        Ki=0.0,
        Kd=8.0,
        initial_bpm=ref["bpm"],
        bpm_min=40.0,
        bpm_max=240.0
    )

    # 3) 공유 이벤트 큐
    events = deque()

    # 4) 가짜 센서 시작
    sim = SimulatedSensor(ref, events_queue=events,
                          timing_offset_ms=40.0,  # 일부러 늦게 치게
                          jitter_ms=10.0)         # 약간의 랜덤 오차
    sim.start()

    # 5) 메트로놈 시작
    metro = SimpleMetronome(get_bpm=lambda: pid.bpm)
    metro.start()

    print("=== 시뮬레이션 시작 ===")
    print("SIM(가짜 센서) → MATCH(오차 계산) → PID → METRO(BPM 출력)")
    print()

    try:
        # 시뮬레이터가 끝날 때까지 루프
        while True:
            # 모든 이벤트를 순차적으로 처리
            while events:
                t_actual, inst = events.popleft()
                error = matcher.compute_error(inst, t_actual)
                if error is None:
                    continue

                new_bpm = pid.update(error)

                print(
                    f"[MATCH] t={t_actual:8.3f}s inst={inst:5s} "
                    f"err={error*1000:+7.2f} ms  ->  BPM={new_bpm:7.3f}"
                )

            # 시뮬레이터 끝났고, 더 이상 이벤트도 없으면 종료
            if sim.finished and not events:
                break

            time.sleep(0.001)

    except KeyboardInterrupt:
        print("\n[MAIN] 강제 종료 요청.")

    finally:
        sim.stop()
        metro.stop()
        sim.join()
        metro.join()
        print("[MAIN] 시뮬레이션 종료.")

########################################

if __name__ == "__main__":
    main()