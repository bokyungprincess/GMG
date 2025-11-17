# tempo_pipeline_modified.py
import numpy as np
import time
import os

# ---------- 1) 파일에서 0/1 배열 읽기 ----------
def load_binary_from_txt(path):
    """
    텍스트 파일에서 0/1 문자들(공백·줄바꿈 무시)을 읽어 numpy array로 반환.
    """
    with open(path, 'r') as f:
        s = f.read()
    chars = [c for c in s if c in '01']
    arr = np.array([int(c) for c in chars], dtype=np.int8)
    return arr

# ---------- 2) A (타임스탬프 배열)와 B (IOI 배열) 생성 ----------
def make_A_from_binary(bin_arr, time_unit):
    idx = np.where(bin_arr == 1)[0]
    times = idx.astype(float) * float(time_unit)
    return times

def make_B_from_A(A):
    if len(A) < 2:
        return np.array([], dtype=float)
    return np.diff(A)

# ---------- 3) 실시간 업데이트용 클래스 ----------
class RealtimeIOI:
    def __init__(self, time_unit=0.01, debounce_time=0.05):
        self.time_unit = time_unit
        self.debounce_time = debounce_time
        self.latest_index = -1
        self.A2 = []
        self.B2 = []
        self._last_onset_time = None

    def process_sample_at_index(self, index, value):
        t = index * self.time_unit
        if value == 1:
            if (self._last_onset_time is None) or (t - self._last_onset_time > self.debounce_time):
                if len(self.A2) == 0:
                    self.A2.append(t)
                else:
                    self.A2.append(t)
                    self.B2.append(t - self._last_onset_time)
                self._last_onset_time = t
        self.latest_index = index

    def get_recent_A2(self, n=10):
        return np.array(self.A2[-n:], dtype=float)

    def get_recent_B2(self, n=10):
        return np.array(self.B2[-n:], dtype=float)

# ---------- 4) 악보 파일로부터 B1 만들기 ----------
def build_B1_from_score(score_txt_path, time_unit):
    bin_arr = load_binary_from_txt(score_txt_path)
    A1 = make_A_from_binary(bin_arr, time_unit)
    B1 = make_B_from_A(A1)
    return A1, B1

# ---------- 5) 모델 입력(최근 4 IOI) 준비 도움 함수 ----------
def make_dataset_from_Bs(B1, B2, window=4):
    """
    변경된 동작: 입력은 B1/B2의 window(예: t..t+3)를 사용하고,
    타깃은 '다음 인덱스'의 time-ratio (즉 B1[t+4] / B2[t+4]) 를 학습하도록 함.
    # <<< 수정됨
    """
    minlen = min(len(B1), len(B2))
    samples = []
    targets = []
    # 이제 t의 범위: t in [0, minlen - window - 1] 이렇게 하면 target index = t+window 존재
    # equivalent to range(0, minlen - window)
    for t in range(0, minlen - window):
        b2_in = B2[t:t+window]
        b1_in = B1[t:t+window]
        # target uses the next index (t+window)
        b2_next = B2[t+window]
        b1_next = B1[t+window]
        # skip invalid values
        if np.any(np.isnan(b2_in)) or np.any(np.isnan(b1_in)):
            continue
        if b2_next <= 0 or b1_next <= 0:
            continue
        X_sample = np.stack([b2_in, b1_in], axis=1)  # shape (window, 2)
        # target: next IOI ratio = score_ioi_next / perf_ioi_next
        ratio = b1_next / b2_next   # <<< 수정됨: 목표를 다음 인덱스의 ratio로 변경
        samples.append(X_sample)
        targets.append(ratio)
    if len(samples) == 0:
        return None, None
    X = np.stack(samples, axis=0).astype(np.float32)
    y = np.array(targets, dtype=np.float32)
    return X, y

# ---------- 6) 간단한 GRU 모델 예시 ----------
def build_gru_model(window=4):
    from tensorflow.keras.models import Sequential
    from tensorflow.keras.layers import GRU, Dense, InputLayer
    m = Sequential()
    m.add(InputLayer(input_shape=(window, 2)))
    m.add(GRU(32, return_sequences=False))
    m.add(Dense(16, activation='relu'))
    m.add(Dense(1, activation='linear'))  # predicts next-index ratio
    m.compile(optimizer='adam', loss='mse', metrics=['mae'])
    return m

# ---------- 7) 사용 예제(시뮬레이션 포함) ----------
if __name__ == "__main__":
    # 설정
    TIME_UNIT = 0.01   # 1 인덱스 = 0.01초
    SCORE_TXT = 'score_binary.txt'
    # (악보는 전체 2000 인덱스로 만들어 둠; 이후 실시간 시뮬은 18초(1800 인덱스) 구간 사용)
    if not os.path.exists(SCORE_TXT):
        bpm = 120
        quarter_sec = 60.0 / bpm
        grid_per_quarter = int(round(quarter_sec / TIME_UNIT))
        total_indices = 2000
        arr = np.zeros(total_indices, dtype=int)
        for i in range(0, total_indices, grid_per_quarter):
            arr[i] = 1
        with open(SCORE_TXT, 'w') as f:
            f.write(''.join(map(str, arr.tolist())))
        print("score_binary.txt 생성 (시뮬레이션 전체)")

    # B1 생성 (악보 전체 기준)
    A1, B1 = build_B1_from_score(SCORE_TXT, TIME_UNIT)
    print("A1 (악보 타임스탬프) 샘플:", A1[:10])
    print("B1 (악보 IOI) 샘플:", B1[:10])
    print("전체 악보 온셋 개수 A1:", len(A1), "IOI 개수 B1:", len(B1))

    # ---------- 실시간 시뮬: 18초(1800 인덱스) 구간에서 전체 템포를 랜덤하게 빠르게 생성 ----------
    # 원함: 누락 없이(=drop 없음), 전체적으로 랜덤한 속도(tempo_factor > 1)로 빨라지게
    SIM_TOTAL_INDICES = 1800  # 18초 구간
    rt = RealtimeIOI(time_unit=TIME_UNIT, debounce_time=0.04)
    # score 전체 바이너리 읽음
    score_bin_full = load_binary_from_txt(SCORE_TXT)
    # 원본 온셋 인덱스들 (전체)
    orig_onset_indices = np.where(score_bin_full == 1)[0]
    # only keep onsets that are within the 18s window (index < SIM_TOTAL_INDICES)
    orig_onset_indices = orig_onset_indices[orig_onset_indices < SIM_TOTAL_INDICES]
    # 이제 전체 템포 scaling factor을 랜덤으로 뽑아 적용 (예: 1.02 ~ 1.08 사이)
    rng = np.random.RandomState(42)
    tempo_factor = float(rng.uniform(1.02, 1.08))  # >1 => faster (IOI shorter)
    print("시뮬 템포 스케일 팩터 (>1 => 빠름):", tempo_factor)
    # create live_bin length SIM_TOTAL_INDICES (no drops)
    live_bin = np.zeros(SIM_TOTAL_INDICES, dtype=int)

    # compute scaled onset positions: convert original index -> time -> scaled time -> new index
    # original_time = orig_idx * TIME_UNIT
    # scaled_time = original_time / tempo_factor  (faster => times earlier)
    # new_index = int(round(scaled_time / TIME_UNIT)) = int(round(orig_idx / tempo_factor))
    # 충돌이 생기면 근접한 빈 슬롯으로 배치
    placed_positions = []
    for orig_idx in orig_onset_indices:
        new_idx = int(round(orig_idx / tempo_factor))
        # clamp into window
        new_idx = max(0, min(SIM_TOTAL_INDICES - 1, new_idx))
        # collision resolution: if occupied, search nearest empty slot within +/- 5 indices
        if live_bin[new_idx] == 0:
            live_bin[new_idx] = 1
            placed_positions.append(new_idx)
        else:
            placed = False
            for delta in range(1, 6):  # search distance up to 5 samples
                for sign in (+1, -1):
                    cand = new_idx + sign * delta
                    if 0 <= cand < SIM_TOTAL_INDICES and live_bin[cand] == 0:
                        live_bin[cand] = 1
                        placed_positions.append(cand)
                        placed = True
                        break
                if placed:
                    break
            if not placed:
                # as a fallback, try to find any zero slot (very unlikely)
                zeros = np.where(live_bin == 0)[0]
                if zeros.size > 0:
                    pos = int(zeros[0])
                    live_bin[pos] = 1
                    placed_positions.append(pos)
                else:
                    # no slot available (extremely unlikely) -> skip (would be a drop)
                    pass

    # feed live_bin sequentially into RealtimeIOI (simulating real-time samples)
    for i, val in enumerate(live_bin):
        rt.process_sample_at_index(i, int(val))

    print("시뮬 A2 len:", len(rt.A2), "시뮬 B2 len:", len(rt.B2))
    print("B2 sample:", rt.get_recent_B2(10))

    # ---------- 데이터셋 만들기 (window=4) ----------
    X, y = make_dataset_from_Bs(B1, rt.get_recent_B2(len(rt.B2)), window=4)
    if X is not None:
        print("Dataset X shape:", X.shape, "y shape:", y.shape)
        # 모델 학습
        model = build_gru_model(window=4)
        # 권장: validation_split을 넣어 과적합 체크 가능
        model.fit(X, y, epochs=30, batch_size=8, verbose=1, validation_split=0.2)

        # 추론: 마지막 윈도우(t..t+3)를 사용하여 t+4의 ratio를 예측
        # (훈련 규칙과 동일하게 마지막 샘플의 입력은 X[-1])
        last_input = X[-1:,...]  # shape (1, window, 2)
        pred_ratio = float(model.predict(last_input)[0,0])  # 예측된 ratio = B1[next] / B2[next]
        print("예측된 next-index time ratio (B1_next / B2_next):", pred_ratio)
        nominal_bpm = 120
        pred_bpm = nominal_bpm * pred_ratio   # <<< 수정됨: ratio 정의에 따라 직관적으로 곱함
        print("예측 BPM (nominal_bpm * pred_ratio):", pred_bpm)
    else:
        print("데이터셋 생성 불충분 (B1/B2 길이 확인)")
