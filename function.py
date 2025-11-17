# 파일명: tempo_pipeline.py

import numpy as np
import time

# ---------- 1) 파일에서 0/1 배열 읽기 ----------
def load_binary_from_txt(path):
    """
    텍스트 파일에서 0/1 문자들(공백·줄바꿈 무시)을 읽어 boolean numpy array로 반환.
    한 줄로 010001... 이거나 공백으로 구분되어 있어도 작동.
    """
    with open(path, 'r') as f:
        s = f.read()
    # 숫자 문자만 취함
    chars = [c for c in s if c in '01']
    arr = np.array([int(c) for c in chars], dtype=np.int8)
    return arr

# ---------- 2) A (타임스탬프 배열)와 B (IOI 배열) 생성 ----------
def make_A_from_binary(bin_arr, time_unit):
    """
    bin_arr: 0/1 numpy array
    time_unit: 한 인덱스의 시간 길이 (초 단위, float)
    반환: timestamps array (초 단위) = indices_of_1 * time_unit
    """
    idx = np.where(bin_arr == 1)[0]
    times = idx.astype(float) * float(time_unit)
    return times

def make_B_from_A(A):
    """
    A: timestamps (초)
    반환: IOI 배열 (len = len(A)-1) where B[i] = A[i+1] - A[i]
    """
    if len(A) < 2:
        return np.array([], dtype=float)
    return np.diff(A)

# ---------- 3) 실시간 업데이트용 클래스 (시리얼/시뮬레이션) ----------
class RealtimeIOI:
    """
    실시간으로 0/1 시퀀스를 받는다고 가정하고, A2,B2를 업데이트하는 helper 클래스.
    - time_unit: 샘플링 인덱스 하나의 시간(초)
    - debounce_time: 연속된 1 신호에서 중복 감지를 막기 위한 데바운스(초)
    """
    def __init__(self, time_unit=0.01, debounce_time=0.05):
        self.time_unit = time_unit
        self.debounce_time = debounce_time
        self.latest_index = -1  # 마지막으로 처리한 인덱스 (정수 인덱스, sample index)
        self.A2 = []  # timestamps of onsets (초)
        self.B2 = []  # IOI (초)
        self._last_onset_time = None

    def process_sample_at_index(self, index, value):
        """
        외부에서 매 샘플(인덱스, 0/1)을 투입하면 내부 A2/B2 업데이트.
        - index: 정수 샘플 인덱스 (시간 인덱스)
        - value: 0/1 (int)
        """
        t = index * self.time_unit  # 현재 샘플 시간(초)
        # detect rising onset: value == 1 and last sample was 0 (caller가 이걸 보장하거나 단순 판단)
        # 여기선 value==1이면 onset으로 간주하되, debounce로 다듬음.
        if value == 1:
            if (self._last_onset_time is None) or (t - self._last_onset_time > self.debounce_time):
                # new onset
                if len(self.A2) == 0:
                    self.A2.append(t)
                else:
                    self.A2.append(t)
                    # 새 IOI 추가
                    self.B2.append(t - self._last_onset_time)
                self._last_onset_time = t
        # update latest index
        self.latest_index = index

    def get_recent_A2(self, n=10):
        return np.array(self.A2[-n:], dtype=float)

    def get_recent_B2(self, n=10):
        return np.array(self.B2[-n:], dtype=float)

# ---------- 4) 예시: 악보 파일로부터 B1 만들기 ----------
def build_B1_from_score(score_txt_path, time_unit):
    bin_arr = load_binary_from_txt(score_txt_path)
    A1 = make_A_from_binary(bin_arr, time_unit)
    B1 = make_B_from_A(A1)
    return A1, B1

# ---------- 5) 모델 입력(최근 4 IOI) 준비 도움 함수 ----------
def make_dataset_from_Bs(B1, B2, window=4):
    """
    B1, B2: 각각 IOI 배열 (둘다 길이 >= window)
    생성 규칙: 각 샘플 t에 대해 input = [[B2[t-window], B1[t-window]], ..., [B2[t-1], B1[t-1]]]
    target: ratio = mean(B2_window) / mean(B1_window)  (또는 log ratio 가능)
    반환: X (samples, window, 2), y (samples,)
    """
    minlen = min(len(B1), len(B2))
    samples = []
    targets = []
    # we need indices i such that i-window >= 0 and i <= minlen
    for i in range(window, minlen+1):
        b2_window = B2[i-window:i]
        b1_window = B1[i-window:i]
        if np.any(np.isnan(b2_window)) or np.any(np.isnan(b1_window)):
            continue
        X_sample = np.stack([b2_window, b1_window], axis=1)  # shape (window, 2)
        # target ratio (avoid division by zero)
        mean_b1 = np.mean(b1_window)
        mean_b2 = np.mean(b2_window)
        if mean_b1 <= 0:
            continue
        ratio = mean_b2 / mean_b1
        samples.append(X_sample)
        targets.append(ratio)
    if len(samples) == 0:
        return None, None
    X = np.stack(samples, axis=0).astype(np.float32)
    y = np.array(targets, dtype=np.float32)
    return X, y

# ---------- 6) (옵션) 간단한 GRU 모델 예시 ----------
def build_gru_model(window=4):
    from tensorflow.keras.models import Sequential
    from tensorflow.keras.layers import GRU, Dense, InputLayer
    m = Sequential()
    m.add(InputLayer(input_shape=(window, 2)))
    m.add(GRU(32, return_sequences=False))
    m.add(Dense(16, activation='relu'))
    m.add(Dense(1, activation='linear'))  # predicts ratio
    m.compile(optimizer='adam', loss='mse', metrics=['mae'])
    return m

# ---------- 7) 사용 예제(시뮬레이션 포함) ----------
if __name__ == "__main__":
    # 설정 예시
    TIME_UNIT = 0.01   # 한 인덱스 = 0.01초 (샘플링 그리드)
    SCORE_TXT = 'score_binary.txt'  # 악보 0/1 파일 (없으면 아래 시뮬 생성)
    import os

    # 만약 score 파일이 없으면 간단히 시뮬로 만듬 (예: 4분음표 꾸준히 120bpm)
    if not os.path.exists(SCORE_TXT):
        # 120 BPM -> quarter note = 0.5s. 만약 그리드가 0.01s라면 50 인덱스마다 1
        bpm = 120
        quarter_sec = 60.0 / bpm
        grid_per_quarter = int(round(quarter_sec / TIME_UNIT))
        total_indices = 2000
        arr = np.zeros(total_indices, dtype=int)
        for i in range(0, total_indices, grid_per_quarter):
            arr[i] = 1
        # 파일로 저장
        with open(SCORE_TXT, 'w') as f:
            f.write(''.join(map(str, arr.tolist())))
        print("score_binary.txt 생성 (시뮬레이션)")

    # B1 생성
    A1, B1 = build_B1_from_score(SCORE_TXT, TIME_UNIT)
    print("A1 (악보 타임스탬프) 샘플:", A1[:10])
    print("B1 (악보 IOI) 샘플:", B1[:10])

    # 시뮬레이션된 실시간 입력(악보에 약간 jitter와 tempo 변동 적용)
    # 실세계라면 RealtimeIOI()를 생성하고 serial에서 샘플들을 받아 process_sample_at_index 호출
    rt = RealtimeIOI(time_unit=TIME_UNIT, debounce_time=0.04)
    # 시뮬: 악보값을 읽어 일부 jitter/마지막 miss/tempo change 삽입
    score_bin = load_binary_from_txt(SCORE_TXT)
    live_bin = score_bin.copy()
    # 예: 50% 확률로 몇 개 누락, 그리고 전체 tempo를 1.05배 빠르게 만들기 위해 밀림 적용
    rng = np.random.RandomState(42)
    # apply small jitter by shifting some onsets by +-1~3 indices
    indices = np.where(score_bin == 1)[0]
    for idx in indices:
        if rng.rand() < 0.05:
            # miss (drop)
            live_bin[idx] = 0
        else:
            if rng.rand() < 0.2:
                shift = rng.randint(-3, 4)
                new_idx = max(0, min(len(live_bin)-1, idx + shift))
                live_bin[idx] = 0
                live_bin[new_idx] = 1
    # apply uniform tempo scaling -> shift later onsets slightly
    # (여기선 간단 시뮬; 실제는 시간보간 필요)
    # 이제 live_bin을 순차적으로 feed
    for i, val in enumerate(live_bin):
        rt.process_sample_at_index(i, int(val))

    print("A2 len:", len(rt.A2), "B2 len:", len(rt.B2))
    print("B2 sample:", rt.get_recent_B2(10))

    # 데이터셋 만들기 (window=4)
    X, y = make_dataset_from_Bs(B1, rt.get_recent_B2(len(rt.B2)), window=4)
    if X is not None:
        print("Dataset X shape:", X.shape, "y shape:", y.shape)
        # 모델 학습 (간단 데모)
        model = build_gru_model(window=4)
        model.fit(X, y, epochs=30, batch_size=8, verbose=1)
        # 추론: 마지막 4개 IOI로 예측
        last_b2 = rt.get_recent_B2(4)
        last_b1 = B1[-4:]
        if len(last_b2) == 4 and len(last_b1) == 4:
            inp = np.stack([last_b2, last_b1], axis=1)[None, ...]  # shape (1,4,2)
            pred_ratio = float(model.predict(inp)[0,0])
            print("예측된 tempo ratio:", pred_ratio)
            nominal_bpm = 120
            pred_bpm = nominal_bpm * pred_ratio
            print("예측 BPM:", pred_bpm)
    else:
        print("데이터셋 생성 불충분 (B1/B2 길이 확인)")
