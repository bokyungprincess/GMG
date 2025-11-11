import time
import threading
import random
from collections import deque

########################################
# 1. drum_sync_data.txt 로드
########################################

def load_drum_sync_data(path="drum_sync_data.txt"):
    """
    drum_v16.py가 생성한 drum_sync_data.txt에서
    기준 BPM, 배열 해상도, 비트 배열을 로드한다.
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
        raise ValueError("drum_sync_data.txt에서 bpm/sensor_rate_hz/samples_per_array_element 를 찾지 못했습니다.")

    dt = samples_per_array_element / sensor_rate_hz  # 배열 1칸당 실제 시간(초)

    return {
        "bpm": bpm,
        "dt": dt,
        "kick": beat_array_kick,
        "snare": beat_array_snare,
        "hit": beat_array_hit,
    }

########################################
# 2. PID 제어기 (음의 피드백)
########################################

class PIDController:
    def __init__(self, Kp, Ki, Kd, initial_bpm, bpm_min=40.0, bpm_max=240.0):
        self.Kp = Kp
        self.Ki = Ki
        self.Kd = Kd

        self.integral = 0.0
        self.prev_error = 0.0
        self.prev_time = None

        self.bpm = float(initial_bpm)
        self.bpm_min = bpm_min
        self.bpm_max = bpm_max

    def update(self, error):
        """
        error = t_actual - t_ref (초)
        > 0 : 실제가 늦음 → BPM을 줄여서(느리게) 다음 기준을 늦춘다
        < 0 : 실제가 빠름 → BPM을 올려서(빠르게) 다음 기준을 당긴다

        => delta = - (Kp*e + Ki*∫e + Kd*de/dt)  (음의 피드백)
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

        # 음의 피드백 핵심: 앞에 '-' 붙임
        delta = - (self.Kp * P + self.Ki * self.integral + self.Kd * D)

        self.bpm += delta

        # 안전 범위
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
    기준 배열과 dt를 가지고 있고,
    (t_actual, inst)에 대해 다음 기준 비트의 오차를 계산해줌.
    """
    def __init__(self, ref_data):
        self.dt = ref_data["dt"]
        # 하나만 써도 되는데, 구조 유지 차원에서 dict 사용
        self.arr = {
            "kick": ref_data["kick"],
            "snare": ref_data["snare"],
            "hit": ref_data["hit"],
        }
        self.next_idx = {k: 0 for k in self.arr.keys()}

    def _find_next_beat(self, inst, start):
        arr = self.arr[inst]
        n = len(arr)
        for i in range(start, n):
            if arr[i] == 1:
                return i
        return None

    def compute_error(self, inst, t_actual):
        if inst not in self.arr:
            return None

        idx0 = self.next_idx[inst]
        idx = self._find_next_beat(inst, idx0)
        if idx is None:
            return None

        t_ref = idx * self.dt
        error = t_actual - t_ref  # (양수: 실제 늦음)

        self.next_idx[inst] = idx + 1
        return error, t_ref

########################################
# 4. 가짜 센서: 기준시간 ± 랜덤 오차
########################################

class SimulatedSensor(threading.Thread):
    """
    각 기준 비트 시각 t_ref를 중심으로,
    t_actual = t_ref + U(-jitter, +jitter) 로 값을 생성해서 events에 넣는다.
    """
    def __init__(self, ref_data, events_queue,
                 jitter_ms=20.0):  # ±20ms 랜덤 오차
        super().__init__(daemon=True)
        self.dt = ref_data["dt"]
        self.arr = {
            "kick": ref_data["kick"],
            "snare": ref_data["snare"],
            "hit": ref_data["hit"],
        }
        self.events = events_queue
        self.jitter = jitter_ms / 1000.0
        self.running = True
        self.finished = False

        # kick 없으면 snare, 그것도 없으면 hit 사용
        base = self.arr["kick"] or self.arr["snare"] or self.arr["hit"]
        self.schedule = []
        for i, v in enumerate(base):
            if v == 1:
                t_ref = i * self.dt
                # 일단 킥으로 통일 (구조만 확인하려는 목적)
                self.schedule.append((t_ref, "kick"))

    def run(self):
        if not self.schedule:
            print("[SIM] 기준 비트가 없습니다. 시뮬레이터 종료.")
            self.finished = True
            return

        start = time.time()
        print(f"[SIM] 가짜 센서 시작 (jitter=±{self.jitter*1000:.1f}ms)")

        for t_ref, inst in self.schedule:
            if not self.running:
                break

            # 기준 시각 기준 ±jitter 랜덤
            jitter = random.uniform(-self.jitter, self.jitter)
            t_actual = t_ref + jitter

            # wall-clock 기준으로 대기
            target = start + t_actual
            while self.running and time.time() < target:
                time.sleep(0.0005)

            if not self.running:
                break

            now = time.time() - start
            # now ~= t_actual (약간의 계산 오차는 무시)
            self.events.append((now, inst))
            print(f"[SIM] t={now:7.3f}s inst={inst:4s} (ref={t_ref:7.3f}s, err={(now - t_ref)*1000:+6.2f}ms)")

        self.finished = True
        print("[SIM] 모든 이벤트 전송 완료.")

    def stop(self):
        self.running = False

########################################
# 5. 메트로놈: 현재 BPM 출력
########################################

class SimpleMetronome(threading.Thread):
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
    ref = load_drum_sync_data("drum_sync_data.txt")
    base_bpm = ref["bpm"]
    print("=== drum_sync_data.txt 로드 완료 ===")
    print(f"기준 BPM: {base_bpm}")
    print(f"배열 1칸 시간(dt): {ref['dt']:.6f} s\n")

    matcher = BeatMatcher(ref)

    # PID gain은 작게 시작 (너무 크면 튄다)
    pid = PIDController(
        Kp=80.0,     # 필요하면 줄이거나 늘려보자
        Ki=0.0,
        Kd=10.0,
        initial_bpm=base_bpm,
        bpm_min=60.0,
        bpm_max=180.0
    )

    events = deque()
    sim = SimulatedSensor(ref, events_queue=events, jitter_ms=20.0)
    metro = SimpleMetronome(get_bpm=lambda: pid.bpm)

    sim.start()
    metro.start()

    print("=== 시뮬레이션 시작 ===")
    print("가짜 센서(±랜덤 오차) -> MATCH(오차 계산) -> PID(보정 BPM) -> METRO 출력\n")

    try:
        while True:
            while events:
                t_actual, inst = events.popleft()
                result = matcher.compute_error(inst, t_actual)
                if result is None:
                    continue
                error, t_ref = result

                new_bpm = pid.update(error)

                print(
                    f"[MATCH] inst={inst:4s} t_ref={t_ref:7.3f}s "
                    f"t_act={t_actual:7.3f}s err={error*1000:+6.2f}ms "
                    f"-> BPM={new_bpm:7.3f}"
                )

            if sim.finished and not events:
                break

            time.sleep(0.001)

    except KeyboardInterrupt:
        print("\n[MAIN] 강제 종료.")

    finally:
        sim.stop()
        metro.stop()
        sim.join()
        metro.join()
        print("=== 시뮬레이션 종료 ===")

########################################

if __name__ == "__main__":
    main()