import os
import xml.etree.ElementTree as ET # <-- ElementTree 임포트
from music21 import converter, instrument, note, chord, stream, tempo, meter, clef

# -------------------------------------------------------------------
# 악보상 '표시 위치' 맵 (Octave는 문자열)
# '질풍가도.xml' 및 '나비야.xml' 원본 파일 기준
# -------------------------------------------------------------------
DISPLAY_MAP = {
    'kick': [
        ('F', '4')  # 악보에서 F4 위치 (베이스 드럼)
    ],
    'snare': [
        ('C', '5')  # 악보에서 C5 위치 (스네어 드럼)
    ],
    'hit': [
        ('G', '5'),  # G5 위치 (하이햇) - '질풍가도.xml'에는 이 노트가 없음
        ('F', '5'),
        ('A', '5'),  # A5 위치 (크래시) - '질풍가도.xml'에는 이 노트가 없음
        # (필요시 '질풍가도'의 탐 위치 추가: ('E', '5'), ('D', '5'), ('A', '4'))
    ]
}
# -------------------------------------------------------------------

def list_xml_files(search_path):
    """지정된 디렉토리의 XML 파일들을 나열하는 함수"""
    extensions = ('.xml', '.mxl', '.musicxml')
    try:
        xml_files = [f for f in os.listdir(search_path) if f.endswith(extensions)]
        return xml_files
    except Exception as e:
        print(f"오류: 디렉토리 검색 실패: {e}")
        return []

def find_drum_part_m21(score):
    """(Music21) 악보에서 드럼 파트 객체를 찾아 반환"""
    print("악보에서 드럼 파트 검색 중 (music21)...")
    for part in score.parts:
        first_measure = part.getElementsByClass('Measure').first()
        if first_measure:
            part_clef = first_measure.getElementsByClass('Clef').first()
            if part_clef and part_clef.sign == 'percussion':
                print(f"'percussion' 악보 기호가 있는 파트(ID: {part.id})를 찾았습니다.")
                return part
    return None

def find_drum_part_et(root):
    """(ElementTree) XML 루트에서 드럼 파트 Element를 찾아 반환"""
    print("악보에서 드럼 파트 검색 중 (ElementTree)...")
    try:
        parts = root.findall('part')
        for part in parts:
            if part.get('id') == 'P1': # '질풍가도' 기준
                percussion_clef = part.find(".//clef/sign[.='percussion']")
                if percussion_clef is not None:
                    print(f"ElementTree: 'percussion' 악보 기호가 있는 파트(ID: {part.get('id')})를 찾았습니다.")
                    return part
    except Exception as e:
        print(f"ElementTree 파트 검색 오류: {e}")
        
    print("ElementTree: 드럼 파트를 찾지 못했습니다. 첫 번째 <part>를 사용합니다.")
    return root.find('part')


def process_drum_xml(xml_path, sensor_rate_hz=100, output_txt_path='drum_data.txt'):
    """
    (*** 로직 수정: ElementTree(ET)를 사용하여 XML 직접 파싱 ***)
    """
    
    # -----------------------------------------------------------------
    # 1~5단계: music21을 사용하여 '배율'과 '배열 길이'만 계산
    # -----------------------------------------------------------------
    try:
        print(f"'{xml_path}' 파일을 (1/2) music21로 파싱 중... (배율 계산용)")
        score = converter.parse(xml_path)
    except Exception as e:
        print(f"오류: '{xml_path}' 파일을 music21이 읽을 수 없습니다. {e}")
        return

    try:
        bpm = score.recurse().getElementsByClass(tempo.MetronomeMark)[0].number
        if bpm is None: raise IndexError
    except IndexError:
        print("경고: 악보에서 유효한 BPM 정보를 찾을 수 없습니다. 기본값 120으로 설정합니다.")
        bpm = 120

    # -----------------------------------------------------------------
    # (*** 여기가 수정된 부분 ***)
    # -----------------------------------------------------------------
    try:
        ts = score.recurse().getElementsByClass(meter.TimeSignature)[0]
        time_signature_str = ts.ratioString
    except IndexError:
        print("경고: 악보에서 박자표를 찾을 수 없습니다. 기본값 4/4로 설정합니다.")
        ts = meter.TimeSignature('4/4')
        time_signature_str = ts.ratioString # <-- 오류 수정
    # -----------------------------------------------------------------

    drum_part_m21 = find_drum_part_m21(score)
    if not drum_part_m21:
        print("치명적 오류: music21이 드럼 파트를 찾지 못했습니다. 분석을 중단합니다.")
        return

    all_elements_m21 = list(drum_part_m21.recurse().notesAndRests)
    min_duration_ql = float('inf')
    for el in all_elements_m21:
        if hasattr(el, 'duration'):
            duration_ql = float(el.duration.quarterLength)
            if duration_ql > 0: min_duration_ql = min(min_duration_ql, duration_ql)

    if min_duration_ql == float('inf'): min_duration_ql = 1.0
    if min_duration_ql < 0.001: min_duration_ql = 1.0
        
    scale_multiplier = 1.0 / min_duration_ql
    total_duration_ql = float(drum_part_m21.duration.quarterLength)
    array_length = int(total_duration_ql * scale_multiplier)
    
    beat_array_kick = [0] * array_length
    beat_array_snare = [0] * array_length
    beat_array_hit = [0] * array_length
    
    print(f"배열 길이: {array_length} (Part QL: {total_duration_ql} * Scale: {scale_multiplier})")
    print("-" * 30)

    # -----------------------------------------------------------------
    # 6단계: ElementTree를 사용하여 XML을 '직접' 파싱하고 배열 마킹
    # -----------------------------------------------------------------
    print(f"'{xml_path}' 파일을 (2/2) ElementTree로 파싱 중... (노트 마킹용)")
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        
        drum_part_et = find_drum_part_et(root)
        if drum_part_et is None:
            print("치명적 오류: ElementTree가 <part>를 찾지 못했습니다.")
            return

        divisions = 1.0
        current_offset_ql = 0.0
        
        kick_count, snare_count, hit_count = 0, 0, 0

        for measure in drum_part_et:
            if measure.tag != 'measure':
                continue

            for el in measure:
                if el.tag == 'attributes':
                    div_elem = el.find('divisions')
                    if div_elem is not None and div_elem.text:
                        divisions = float(div_elem.text)
                
                elif el.tag == 'note':
                    duration_elem = el.find('duration')
                    if duration_elem is None or not duration_elem.text:
                        continue 
                    
                    note_duration_ql = float(duration_elem.text) / divisions
                    
                    if el.find('rest') is None:
                        start_index = int(current_offset_ql * scale_multiplier)
                        
                        for unpitched_elem in el.findall('.//unpitched'):
                            step = unpitched_elem.findtext('display-step')
                            octave = unpitched_elem.findtext('display-octave')
                            pos = (step, octave)
                            
                            if pos in DISPLAY_MAP['kick']:
                                if 0 <= start_index < array_length:
                                    beat_array_kick[start_index] = 1
                                    kick_count += 1
                            elif pos in DISPLAY_MAP['snare']:
                                if 0 <= start_index < array_length:
                                    beat_array_snare[start_index] = 1
                                    snare_count += 1
                            elif pos in DISPLAY_MAP['hit']:
                                if 0 <= start_index < array_length:
                                    beat_array_hit[start_index] = 1
                                    hit_count += 1
                    
                    current_offset_ql += note_duration_ql

                elif el.tag == 'backup':
                    duration_elem = el.find('duration')
                    if duration_elem is not None and duration_elem.text:
                        backup_duration_ql = float(duration_elem.text) / divisions
                        current_offset_ql -= backup_duration_ql
                
                elif el.tag == 'forward':
                    duration_elem = el.find('duration')
                    if duration_elem is not None and duration_elem.text:
                        forward_duration_ql = float(duration_elem.text) / divisions
                        current_offset_ql += forward_duration_ql

        print(f"총 {kick_count}개의 킥, {snare_count}개의 스네어, {hit_count}개의 힛(심벌/하이햇)을 마킹했습니다.")
        if (kick_count + snare_count + hit_count) == 0:
            print("경고: 마킹된 노트가 0개입니다. DISPLAY_MAP의 ('F', '4') ('C', '5') 등이 악보와 일치하는지 확인하세요.")
        elif hit_count == 0:
            print("참고: '힛'이 0개입니다. (XML 파일 원본에 킥/스네어만 존재할 수 있습니다.)")

    except Exception as e:
        print(f"오류: ElementTree 파싱 중 심각한 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        return

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