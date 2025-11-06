import os
from music21 import converter, instrument, note, chord, stream, tempo, meter, clef

# -------------------------------------------------------------------
# (신규) 악기 ID 맵
# -------------------------------------------------------------------
# (키: 악기 유형, 값: XML의 <instrument id="..."> 리스트)
# '질풍가도.xml' 원본 파일 기준입니다.
INSTRUMENT_MAP = {
    'kick': [
        'P1-I35', # Acoustic_Bass_Drum
        'P1-I36'  # Bass_Drum_1
    ],
    'snare': [
        'P1-I37', # Side_Stick
        'P1-I38', # Acoustic_Snare
        'P1-I40'  # Electric_Snare
    ],
    'hit': [
        'P1-I42', # Closed_Hi_Hat
        'P1-I44', # Pedal_Hi_Hat
        'P1-I46', # Open_Hi_Hat
        'P1-I49', # Crash_Cymbal_1
        'P1-I51', # Ride_Cymbal_1
        'P1-I52', # Chinese_Cymbal
        'P1-I53', # Ride_Bell
        'P1-I55', # Splash_Cymbal
        'P1-I57', # Crash_Cymbal_2
        'P1-I59'  # Ride_Cymbal_2
    ]
    # (탐 종류는 제외됨)
}
# -------------------------------------------------------------------

def list_xml_files(search_path):
    """
    지정된 디렉토리의 XML 파일들을 나열하는 함수
    """
    extensions = ('.xml', '.mxl', '.musicxml')
    try:
        xml_files = [f for f in os.listdir(search_path) if f.endswith(extensions)]
        return xml_files
    except FileNotFoundError:
        print(f"오류: '{search_path}' 디렉토리를 찾을 수 없습니다.")
        return []
    except NotADirectoryError:
        print(f"오류: '{search_path}'는 디렉토리가 아닙니다.")
        return []
    except PermissionError:
        print(f"오류: '{search_path}' 디렉토리에 접근할 권한이 없습니다.")
        return []

def find_drum_part(score):
    """
    악보에서 드럼 파트 객체를 찾아 반환합니다. (없으면 None)
    """
    print("악보에서 드럼 파트 검색 중...")
    
    # 1. (최우선) 퍼커션 악보 기호(Clef)가 있는 파트 검색
    for part in score.parts:
        first_measure = part.getElementsByClass('Measure').first()
        if first_measure:
            part_clef = first_measure.getElementsByClass('Clef').first()
            if part_clef and part_clef.sign == 'percussion':
                print(f"'percussion' 악보 기호가 있는 파트(ID: {part.id})를 찾았습니다.")
                return part
            
    # 2. (차선) 악기 정보를 스캔하여 'Percussion' 악기가 있는지 확인
    print("퍼커션 악보 기호를 찾지 못했습니다. 악기 정보에서 'Percussion' 검색 중...")
    for part in score.parts:
        instr = part.getInstrument(returnDefault=False)
        if isinstance(instr, instrument.Percussion):
            print(f"'{instr.instrumentName}' 타악기 파트를 찾았습니다.")
            return part
            
    # 3. (삼선) 파트 이름에 'Drum'이 들어간 파트 검색
    print("Percussion 악기 타입을 찾지 못했습니다. 파트 이름에서 'Drum' 검색 중...")
    for part in score.parts:
        part_name = part.partName or ""
        if 'drum' in part_name.lower():
            print(f"'{part_name}' 파트를 드럼 파트로 간주합니다.")
            return part

    print("경고: 드럼 파트를 특정하지 못했습니다.")
    return None


def process_drum_xml(xml_path, sensor_rate_hz=100, output_txt_path='drum_data.txt'):
    """
    MusicXML 드럼 악보를 파싱하여 KICK, SNARE, HIT로 분리된 비트 배열을 저장합니다.
    (*** 핵심 로직 수정: Instrument ID 맵 사용 ***)
    """
    try:
        # 1. MusicXML 파일 파싱
        print(f"'{xml_path}' 파일을 파싱 중입니다...")
        score = converter.parse(xml_path)
    except Exception as e:
        print(f"오류: '{xml_path}' 파일을 읽을 수 없습니다. 파일 경로를 확인하세요.")
        print(f"에러 상세: {e}")
        return

    # 2. 악보 기본 정보 추출
    try:
        bpm = score.recurse().getElementsByClass(tempo.MetronomeMark)[0].number
        # (중요) NoneType 오류 방지
        if bpm is None:
             raise IndexError("BPM이 None입니다.")
    except IndexError:
        print("경고: 악보에서 유효한 BPM 정보를 찾을 수 없습니다. 기본값 120으로 설정합니다.")
        bpm = 120

    try:
        ts = score.recurse().getElementsByClass(meter.TimeSignature)[0]
        time_signature_str = ts.ratioString
    except IndexError:
        print("경고: 악보에서 박자표를 찾을 수 없습니다. 기본값 4/4로 설정합니다.")
        ts = meter.TimeSignature('4/4')
        time_signature_str = ts.ratioString

    # 3. 드럼 파트 찾기
    drum_part = find_drum_part(score)
    
    if not drum_part:
        print("치명적 오류: 드럼 파트를 찾을 수 없습니다. 분석을 중단합니다.")
        return

    print(f"'{drum_part.id}' 파트를 기준으로 분석을 시작합니다.")

    # 4. '최소 음표' 찾기
    all_elements = list(drum_part.recurse().notesAndRests)
    
    min_duration_ql = float('inf')
    for el in all_elements:
        if hasattr(el, 'duration'):
            duration_ql = float(el.duration.quarterLength)
            if duration_ql > 0:
                min_duration_ql = min(min_duration_ql, duration_ql)

    if min_duration_ql == float('inf'): min_duration_ql = 1.0
    if min_duration_ql < 0.001: min_duration_ql = 1.0
        
    # 5. '배율' 및 '비트 배열' 3개 생성
    scale_multiplier = 1.0 / min_duration_ql
    total_duration_ql = float(drum_part.duration.quarterLength)
    
    array_length = int(total_duration_ql * scale_multiplier)
    
    beat_array_kick = [0] * array_length
    beat_array_snare = [0] * array_length
    beat_array_hit = [0] * array_length
    
    print(f"배열 길이: {array_length} (Part QL: {total_duration_ql} * Scale: {scale_multiplier})")

    # 6. (*** 수정됨 ***)
    # 비트 배열 3종 채우기 (Instrument ID 맵 기준)
    print("마디(Measure)를 기준으로 노트 오프셋 및 Instrument ID를 분석합니다...")

    try:
        all_measures = drum_part.getElementsByClass('Measure')
    except Exception as e:
        print(f"오류: 마디를 가져오는 데 실패했습니다. {e}")
        return

    kick_count, snare_count, hit_count = 0, 0, 0

    for measure in all_measures:
        measure_start_offset = float(measure.offset)
        elements_in_measure = measure.recurse().notesAndRests
        
        for el in elements_in_measure:
            # 쉼표가 아닌 '타격'만 (Unpitched 포함)
            if (not el.isRest) and hasattr(el, 'duration') and hasattr(el, 'offset'):
                
                absolute_offset_ql = measure_start_offset + float(el.offset)
                start_index = int(absolute_offset_ql * scale_multiplier)
                
                if not (0 <= start_index < array_length):
                    continue # 배열 범위 밖이면 무시

                # (신규) 이 노트(el)가 어떤 악기인지 Instrument ID로 확인
                inst_id = None
                if hasattr(el, 'instrument') and el.instrument is not None:
                    inst_id = el.instrument.id
                elif el.isChord:
                    # '질풍가도' 15마디처럼 동시 타격일 때,
                    # music21은 종종 첫 번째 노트에만 ID를 할당합니다.
                    # 이 코드는 단일 노트와 <chord/> 태그가 붙은 노트 모두 처리합니다.
                    if hasattr(el.notes[0], 'instrument') and el.notes[0].instrument is not None:
                         inst_id = el.notes[0].instrument.id

                if inst_id is None:
                    # print(f"  [디버그] 노트에서 Instrument ID를 찾을 수 없습니다: {el}")
                    continue

                # Instrument ID를 맵과 비교
                if inst_id in INSTRUMENT_MAP['kick']:
                    beat_array_kick[start_index] = 1
                    kick_count += 1
                elif inst_id in INSTRUMENT_MAP['snare']:
                    beat_array_snare[start_index] = 1
                    snare_count += 1
                elif inst_id in INSTRUMENT_MAP['hit']:
                    beat_array_hit[start_index] = 1
                    hit_count += 1

    print(f"총 {kick_count}개의 킥, {snare_count}개의 스네어, {hit_count}개의 힛(심벌/하이햇)을 마킹했습니다.")


    # 7. 실시간 센서 동기화 정보 계산
    samples_per_quarter_note = (sensor_rate_hz * 60.0) / bpm
    samples_per_array_element = samples_per_quarter_note / scale_multiplier

    # 8. TXT 파일로 3개의 배열 모두 저장
    print(f"'{output_txt_path}' 파일에 결과 저장 중...")
    try:
        with open(output_txt_path, 'w', encoding='utf-8') as f:
            f.write(f"## 드럼 악보 분석 및 동기화 정보 (악기 분리) ##\n\n")
            f.write(f"# 악보 기본 정보\n")
            f.write(f"source_xml: {os.path.basename(xml_path)}\n")
            f.write(f"bpm: {bpm}\n")
            f.write(f"time_signature: {time_signature_str}\n")
            f.write(f"total_quarter_length (part): {total_duration_ql}\n")
            
            f.write(f"\n# 배열 해상도 정보\n")
            f.write(f"smallest_note_ql: {min_duration_ql}\n")
            f.write(f"scale_multiplier: {scale_multiplier}\n")
            
            f.write(f"\n# 실시간 센서 동기화 정보 (중요)\n")
            f.write(f"sensor_rate_hz: {sensor_rate_hz}\n")
            f.write(f"samples_per_quarter_note: {samples_per_quarter_note}\n")
            f.write(f"samples_per_array_element: {samples_per_array_element}\n")
            
            # --- 3개 배열 저장 ---
            f.write(f"\n# 생성된 비트 배열 (Kick)\n")
            f.write(f"beat_array_len: {len(beat_array_kick)}\n")
            beat_array_str = ",".join(map(str, beat_array_kick))
            f.write(f"beat_array_kick: {beat_array_str}\n")
            
            f.write(f"\n# 생성된 비트 배열 (Snare)\n")
            f.write(f"beat_array_len: {len(beat_array_snare)}\n")
            beat_array_str = ",".join(map(str, beat_array_snare))
            f.write(f"beat_array_snare: {beat_array_str}\n")
            
            f.write(f"\n# 생성된 비트 배열 (Hit)\n")
            f.write(f"beat_array_len: {len(beat_array_hit)}\n")
            beat_array_str = ",".join(map(str, beat_array_hit))
            f.write(f"beat_array_hit: {beat_array_str}\n")
            
        print(f"성공! '{output_txt_path}' 파일이 생성되었습니다.")
        print("-" * 30)
        print(f"BPM: {bpm}")
        print(f"배열 요소당 센서 샘플 수: {samples_per_array_element}")
        print("-" * 30)

    except Exception as e:
        print(f"오류: TXT 파일 저장에 실패했습니다.")
        print(f"에러 상세: {e}")


# --- 메인 실행 부분 (파일 선택 로직) ---
if __name__ == "__main__":
    
    input_file = None
    
    search_path_input = input("XML 파일을 검색할 폴더 경로를 입력하세요 (그냥 Enter시 현재 폴더): ").strip()
    
    if not search_path_input:
        search_path = '.'
    else:
        search_path = search_path_input
        
    print(f"'{os.path.abspath(search_path)}'에서 XML 파일을 검색합니다...")

    xml_files_list = list_xml_files(search_path)
    
    if xml_files_list:
        print("\nMusicXML 파일들을 찾았습니다:")
        for i, file in enumerate(xml_files_list, 1):
            print(f"  {i}. {file}")
        
        while True: 
            try:
                choice_str = input(f"\n처리할 파일 번호를 입력하세요 (1-{len(xml_files_list)}): ")
                
                if not choice_str:
                    print("번호를 입력해야 합니다.")
                    continue
                    
                choice = int(choice_str) - 1
                
                if 0 <= choice < len(xml_files_list):
                    chosen_filename = xml_files_list[choice]
                    input_file = os.path.join(search_path, chosen_filename) 
                    
                    print(f"-> '{input_file}' 파일을 선택했습니다.")
                    break
                else:
                    print(f"잘못된 번호입니다. 1에서 {len(xml_files_list)} 사이의 숫자를 입력하세요.")
            
            except ValueError:
                print("숫자만 입력해주세요.")

    else:
        print(f"'{search_path}' 디렉토리에 XML 파일이 없습니다.")
        input_file = input("XML 파일의 전체 경로를 직접 입력하세요: ")

    # --- 센서 HZ 입력 ---
    try:
        sensor_hz_input = input(f"센서 입력 횟수(Hz)를 입력하세요 (기본값 100): ")
        SENSOR_HZ = int(sensor_hz_input) if sensor_hz_input else 100
    except ValueError:
        print("잘못된 입력입니다. 기본값 100Hz로 설정합니다.")
        SENSOR_HZ = 100

    OUTPUT_FILE = "drum_sync_data.txt" 

    # --- 파일 존재 여부 최종 확인 및 분석 실행 ---
    if input_file and os.path.exists(input_file):
        process_drum_xml(input_file, SENSOR_HZ, OUTPUT_FILE)
    elif not input_file:
        print("오류: 파일이 선택되지 않았습니다. 프로그램을 종료합니다.")
    else:
        print(f"오류: '{input_file}' 파일을 찾을 수 없습니다. 경로를 다시 확인해주세요.")