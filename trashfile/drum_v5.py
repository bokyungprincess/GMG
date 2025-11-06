import os
from music21 import converter, instrument, note, chord, stream, tempo, meter, clef

def list_xml_files():
    """현재 디렉토리의 MusicXML 파일들을 나열하는 함수"""
    extensions = ('.xml', '.mxl', '.musicxml')
    xml_files = [f for f in os.listdir('.') if f.endswith(extensions)]
    return xml_files

def get_drum_elements(score):
    """
    Music21 Score 객체에서 드럼/타악기 파트의 elements를 우선적으로 추출합니다.
    (*** 수정됨: .flat 대신 .recurse() 사용하여 오프셋 오류 수정 ***)
    """
    print("악보에서 드럼 파트 검색 중...")
    
    drum_part = None
    
    # 1. (최우선) 퍼커션 악보 기호(Clef)가 있는 파트 검색
    for part in score.parts:
        first_measure = part.getElementsByClass('Measure').first()
        if first_measure:
            part_clef = first_measure.getElementsByClass('Clef').first()
            if part_clef and part_clef.sign == 'percussion':
                print(f"'percussion' 악보 기호가 있는 파트(ID: {part.id})를 찾았습니다.")
                drum_part = part
                break
            
    # 2. (차선) 악기 정보를 스캔하여 'Percussion' 악기가 있는지 확인
    if drum_part is None:
        print("퍼커션 악보 기호를 찾지 못했습니다. 악기 정보에서 'Percussion' 검색 중...")
        for part in score.parts:
            instr = part.getInstrument(returnDefault=False)
            if isinstance(instr, instrument.Percussion):
                print(f"'{instr.instrumentName}' 타악기 파트를 찾았습니다.")
                drum_part = part
                break
            
    # 3. (삼선) 파트 이름에 'Drum'이 들어간 파트 검색
    if drum_part is None:
        print("Percussion 악기 타입을 찾지 못했습니다. 파트 이름에서 'Drum' 검색 중...")
        for part in score.parts:
            part_name = part.partName or ""
            if 'drum' in part_name.lower():
                print(f"'{part_name}' 파트를 드럼 파트로 간주합니다.")
                drum_part = part
                break

    # 4. 드럼 파트를 찾은 경우
    if drum_part:
        # *** 핵심 수정 ***
        # .flat.notesAndRests 대신 .recurse().notesAndRests 사용
        # .recurse()는 하위 (Measure 등)를 탐색하며 오프셋을 더 정확하게 계산합니다.
        print("드럼 파트의 노트를 재귀적으로 탐색합니다 (.recurse() 사용)")
        return drum_part.recurse().notesAndRests
    
    # 5. 드럼 파트를 못찾은 경우 (경고 후 전체 노트 반환)
    print("경고: 드럼 파트를 특정하지 못했습니다. 악보 전체를 분석합니다.")
    # 여기도 .recurse()로 통일합니다.
    return score.recurse().notesAndRests


def process_drum_xml(xml_path, sensor_rate_hz=100, output_txt_path='drum_data.txt'):
    """
    MusicXML 드럼 악보를 파싱하여 비트 배열과 동기화 정보를 TXT 파일로 저장합니다.
    (스트림 -> 리스트 변환 로직 포함)
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
        bpm = score.flat.getElementsByClass(tempo.MetronomeMark)[0].number
    except IndexError:
        print("경고: 악보에서 BPM 정보를 찾을 수 없습니다. 기본값 120으로 설정합니다.")
        bpm = 120

    try:
        ts = score.flat.getElementsByClass(meter.TimeSignature)[0]
        time_signature_str = ts.ratioString
    except IndexError:
        print("경고: 악보에서 박자표를 찾을 수 없습니다. 기본값 4/4로 설정합니다.")
        ts = meter.TimeSignature('4/4')
        time_signature_str = ts.ratioString

    # 3. 드럼 파트 요소(Elements) 추출 및 리스트 변환
    # (*** 중요 ***) '일회용' 스트림을 '재사용' 가능한 리스트로 변환
    all_elements = list(get_drum_elements(score))
    
    print(f"총 {len(all_elements)}개의 음표/쉼표 요소를 리스트로 변환했습니다.")
    
    min_duration_ql = float('inf')
    
    # 첫 번째 반복 (최소 길이 찾기)
    for el in all_elements:
        duration_ql = float(el.duration.quarterLength)
        if duration_ql > 0:
            min_duration_ql = min(min_duration_ql, duration_ql)

    if min_duration_ql == float('inf'):
        print("경고: 악보에서 유효한 음표를 찾지 못했습니다.")
        min_duration_ql = 1.0
        
    if min_duration_ql < 0.001:
        print(f"경고: 최소 음표 길이가 너무 짧습니다({min_duration_ql}). 1.0으로 강제 설정합니다.")
        min_duration_ql = 1.0
        
    # 4. '배율' 및 '비트 배열' 생성
    scale_multiplier = 1.0 / min_duration_ql
    total_duration_ql = float(score.duration.quarterLength)
    array_length = int(total_duration_ql * scale_multiplier)
    beat_array = [0] * array_length

    # 5. 비트 배열 채우기
    note_found_count = 0
    
    # 두 번째 반복 (배열에 '1' 마킹)
    for el in all_elements:
        if el.isNote or el.isChord: # 쉼표가 아닌 '음표'나 '화음'일 때
            offset_ql = float(el.offset)
            start_index = int(offset_ql * scale_multiplier)
            
            if 0 <= start_index < array_length:
                beat_array[start_index] = 1
                note_found_count += 1
            else:
                # (디버깅) 혹시 모를 오류를 위해 범위 밖 노트 정보 출력
                # print(f"  [디버그] 노트 (offset: {offset_ql})가 배열 범위 밖입니다. (index: {start_index} vs array_len: {array_length})")
                pass


    if note_found_count == 0:
        print("경고: 노트 위치를 배열에 마킹하지 못했습니다. (배열이 0일 수 있음)")
    else:
        print(f"총 {note_found_count}개의 노트(타격)를 배열에 마킹했습니다.")


    # 6. 실시간 센서 동기화 정보 계산
    samples_per_quarter_note = (sensor_rate_hz * 60.0) / bpm
    samples_per_array_element = samples_per_quarter_note / scale_multiplier

    # 7. TXT 파일로 모든 정보 저장
    print(f"'{output_txt_path}' 파일에 결과 저장 중...")
    try:
        with open(output_txt_path, 'w', encoding='utf-8') as f:
            f.write(f"## 드럼 악보 분석 및 동기화 정보 ##\n\n")
            f.write(f"# 악보 기본 정보\n")
            f.write(f"source_xml: {os.path.basename(xml_path)}\n")
            f.write(f"bpm: {bpm} (경고: 파일에 BPM 정보가 없어 기본값을 사용했을 수 있습니다)\n")
            f.write(f"time_signature: {time_signature_str}\n")
            f.write(f"total_quarter_length: {total_duration_ql}\n")
            
            f.write(f"\n# 배열 해상도 정보\n")
            f.write(f"smallest_note_ql: {min_duration_ql}\n")
            f.write(f"scale_multiplier: {scale_multiplier}\n")
            
            f.write(f"\n# 실시간 센서 동기화 정보 (중요)\n")
            f.write(f"sensor_rate_hz: {sensor_rate_hz}\n")
            f.write(f"samples_per_quarter_note: {samples_per_quarter_note}\n")
            f.write(f"samples_per_array_element: {samples_per_array_element}\n")
            
            f.write(f"\n# 생성된 비트 배열\n")
            f.write(f"beat_array_len: {len(beat_array)}\n")
            beat_array_str = ",".join(map(str, beat_array))
            f.write(f"beat_array: {beat_array_str}\n")
            
        print(f"성공! '{output_txt_path}' 파일이 생성되었습니다.")
        print("-" * 30)
        print(f"BPM: {bpm} (파일에 BPM 정보가 없는지 확인하세요!)")
        print(f"박자: {time_signature_str}")
        print(f"최소 음표 단위(ql): {min_duration_ql} (배율: {scale_multiplier})")
        print(f"총 배열 길이: {len(beat_array)}")
        print(f"배열 요소당 센서 샘플 수: {samples_per_array_element}")
        print("-" * 30)

    except Exception as e:
        print(f"오류: TXT 파일 저장에 실패했습니다.")
        print(f"에러 상세: {e}")


# --- 메인 실행 부분 (파일 선택 로직) ---
if __name__ == "__main__":
    
    input_file = None
    xml_files_list = list_xml_files()
    
    if xml_files_list:
        print("\n현재 디렉토리에서 MusicXML 파일들을 찾았습니다:")
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
                    input_file = xml_files_list[choice]
                    print(f"-> '{input_file}' 파일을 선택했습니다.")
                    break
                else:
                    print(f"잘못된 번호입니다. 1에서 {len(xml_files_list)} 사이의 숫자를 입력하세요.")
            
            except ValueError:
                print("숫자만 입력해주세요.")

    else:
        print("현재 디렉토리에 XML 파일이 없습니다.")
        input_file = input("XML 파일의 전체 경로를 입력하세요: ")

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