import xml.etree.ElementTree as ET
import os
import copy
from pathlib import Path

# -------------------------------------------------------------------
# (추가) 악기 ID 맵
# -------------------------------------------------------------------
# 사용자의 악보 파일(예: 질풍가도.xml)의 <part-list>를 보고 ID를 맞춤 설정해야 합니다.
# 이 값은 '질풍가도.xml' 기준의 예시입니다.
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
        'P1-I59', # Ride_Cymbal_2
        # 탐/봉고 등은 'hit'에 포함시키지 않았습니다. 필요시 추가하세요.
        # 'P1-I41', 'P1-I43', 'P1-I45', 'P1-I47', 'P1-I48', 'P1-I50'
    ]
}

def format_xml_with_indentation(element, level=0):
    """
    XML 요소에 들여쓰기와 줄바꿈을 추가하여 가독성을 높이는 함수
    """
    indent = "\n" + "  " * level
    
    if len(element):
        if not element.text or not element.text.strip():
            element.text = indent + "  "
        if not element.tail or not element.tail.strip():
            element.tail = indent
        for child in element:
            format_xml_with_indentation(child, level + 1)
        if not child.tail or not child.tail.strip():
            child.tail = indent
    else:
        if level and (not element.tail or not element.tail.strip()):
            element.tail = indent

def remove_print_elements(measure_element):
    """
    마디에서 <print> 요소들을 제거하는 함수
    """
    removed_count = 0
    print_elements = measure_element.findall('.//print')
    
    for print_elem in print_elements:
        parent = measure_element
        for elem in measure_element.iter():
            if print_elem in list(elem):
                parent = elem
                break
        
        if parent is not None:
            parent.remove(print_elem)
            removed_count += 1
    
    return removed_count

def save_formatted_xml(tree, output_path):
    """
    포맷팅된 XML을 파일로 저장하는 함수
    """
    root = tree.getroot()
    format_xml_with_indentation(root)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        # MusicXML DTD 선언을 추가해야 할 수 있습니다. (질풍가도 파일 기준)
        f.write('<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0.3 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">\n')
        f.write(ET.tostring(root, encoding='unicode'))

def add_time_modification_to_notes(measure_element, actual_notes=3, normal_notes=2):
    """
    마디의 모든 노트에 time-modification을 추가하는 함수
    """
    notes = measure_element.findall('.//note')
    modified_count = 0
    
    for note in notes:
        existing_time_mod = note.find('time-modification')
        
        if existing_time_mod is None:
            time_mod = ET.Element('time-modification')
            
            actual_notes_elem = ET.SubElement(time_mod, 'actual-notes')
            actual_notes_elem.text = str(actual_notes)
            
            normal_notes_elem = ET.SubElement(time_mod, 'normal-notes')
            normal_notes_elem.text = str(normal_notes)
            
            duration_elem = note.find('duration')
            if duration_elem is not None:
                note_children = list(note)
                duration_index = note_children.index(duration_elem)
                note.insert(duration_index + 1, time_mod)
                modified_count += 1
            else:
                note.append(time_mod)
                modified_count += 1
    
    return modified_count

def add_bpm_to_notes(measure_element, bpm):
    """
    마디의 시작에 BPM 정보를 추가하는 함수
    """
    existing_bpm = measure_element.find('direction')
    
    if existing_bpm is None:
        direction = ET.Element('direction')
        sound = ET.SubElement(direction, 'sound')
        sound.set('tempo', str(bpm))
        measure_element.insert(0, direction)
        return 1
    return 0

def merge_attributes(target_attributes, source_attributes):
    """
    target_attributes에 source_attributes의 내용 중 없는 요소만 추가
    """
    existing_tags = {child.tag for child in target_attributes}
    for elem in source_attributes:
        if elem.tag not in existing_tags:
            target_attributes.append(copy.deepcopy(elem))

# -------------------------------------------------------------------
# (신규) 노트를 제거하기 위해 부모를 찾는 함수
# -------------------------------------------------------------------
def find_parent(root, element):
    """
    root 트리에서 element의 부모 요소를 찾아 반환
    """
    for parent in root.iter():
        if element in list(parent):
            return parent
    return None

# -------------------------------------------------------------------
# (신규) 악기 ID로 노트를 필터링하는 함수
# -------------------------------------------------------------------
def filter_measure_by_instrument(measure_element, allowed_ids):
    """
    마디 요소에서 allowed_ids에 없는 악기 노트를 모두 제거 (쉼표는 유지)
    
    Args:
        measure_element: <measure> XML 요소 (복사본)
        allowed_ids: 유지할 instrument ID 리스트
    """
    notes_to_remove = []
    all_notes = measure_element.findall('.//note') # 쉼표(rest)는 포함되지 않음

    for note in all_notes:
        # 쉼표(<rest/>)가 있는지 확인
        if note.find('rest') is not None:
            continue # 쉼표는 제거하지 않고 유지

        instrument_elem = note.find('instrument')
        
        # 악기 ID가 없거나, ID가 allowed_ids에 없으면 제거 대상
        if instrument_elem is None or instrument_elem.get('id') not in allowed_ids:
            notes_to_remove.append(note)

    removed_count = 0
    for note in notes_to_remove:
        parent = find_parent(measure_element, note)
        if parent is not None:
            try:
                parent.remove(note)
                removed_count += 1
            except ValueError:
                # 이미 제거된 경우 등 예외 처리
                pass
    
    # print(f"  > {removed_count}개의 불필요한 노트 제거됨.")


def extract_header_and_split_measures(input_file, output_dir="output", add_time_mod=True, add_bpm=True):
    """
    MusicXML 파일을 헤더와 마디별(악기별 분리)로 분할하는 함수
    """
    
    # 출력 디렉토리 생성
    Path(output_dir).mkdir(exist_ok=True)
    
    try:
        # XML 파일 파싱
        tree = ET.parse(input_file)
        root = tree.getroot()
        
        print("=== 1단계: 전처리 파일 생성 ===")
        
        header_elements = []
        p1_part = None
        
        for child in root:
            if child.tag == 'part' and child.get('id') == 'P1':
                p1_part = child
                break
            else:
                header_elements.append(child)
        
        if p1_part is None:
            print("part id='P1'을 찾을 수 없습니다.")
            return
        
        header_root = ET.Element(root.tag, root.attrib)
        for header_elem in header_elements:
            header_root.append(header_elem)
        
        header_file = os.path.join(output_dir, "preprocessing.xml")
        header_tree = ET.ElementTree(header_root)
        save_formatted_xml(header_tree, header_file)
        
        print(f"전처리 파일 생성 완료: preprocessing.xml")
        
        print("\n=== 2단계: 마디별/악기별 파일 생성 ===")
        
        measures = p1_part.findall('measure')
        
        if not measures:
            print("마디를 찾을 수 없습니다.")
            return
        
        total_measures = len(measures)
        length = len(str(total_measures))
        print(f"총 {total_measures}개의 마디를 찾았습니다.")
        
        bpm = "120" # 기본값
        if add_bpm == True:
            bpm_input = input("bpm 값을 입력해 주세요 (기본값 120): ")
            if bpm_input:
                bpm = bpm_input
        
        first_measure = measures[0]
        first_attributes = first_measure.find('attributes')
        
        if first_attributes is not None:
            print(f"첫 마디에서 attributes 발견: {len(list(first_attributes))}개 요소")
        else:
            print("첫 마디에 attributes가 없습니다.")
            
        div = root.find(".//divisions")
        if div is not None:
            divisions = int(div.text)
            print(f"divisions 발견: {divisions}")
        else:
            print("divisions이 없습니다.")
            divisions = 1
        
        actual_notes, normal_notes = divisions, divisions
        
        if add_time_mod:
            print(f"time-modification 설정: {actual_notes} -> {normal_notes}")
        
        print("첫 번째 마디는 <print> 요소를 유지하고, 나머지 마디에서는 제거합니다.")
        
        # -------------------------------------------------------------------
        # (수정) 마디별 루프
        # -------------------------------------------------------------------
        for i, measure in enumerate(measures):
            measure_number = measure.get('number')
            if measure_number is None:
                measure_number = str(i + 1)
            
            # (수정) 3가지 악기(kick, snare, hit)에 대한 마디 Element 생성
            measure_copies = {
                'kick': ET.Element('measure', measure.attrib),
                'snare': ET.Element('measure', measure.attrib),
                'hit': ET.Element('measure', measure.attrib)
            }
            
            # 마디의 모든 내용(attributes, note, backup 등)을 3개의 복사본에 동일하게 추가
            for elem in measure:
                measure_copies['kick'].append(copy.deepcopy(elem))
                measure_copies['snare'].append(copy.deepcopy(elem))
                measure_copies['hit'].append(copy.deepcopy(elem))
            
            print(f"\n--- 마디 {measure_number} 처리 중 ---")
            
            # 각 복사본에 대해 후처리 (attributes 병합, <print> 제거, 옵션 추가)
            for instrument_type, measure_root in measure_copies.items():
                
                # attributes가 있는지 확인
                current_attributes = measure_root.find('attributes')
                if first_attributes is not None:
                    if current_attributes is None:
                        attributes_copy = copy.deepcopy(first_attributes)
                        measure_root.insert(0, attributes_copy) # attributes는 보통 맨 앞에
                    else:
                        merge_attributes(current_attributes, first_attributes)
                
                # 첫 번째 마디가 아닌 경우에만 <print> 요소 제거
                if i > 0:
                    remove_print_elements(measure_root)
                
                # (신규) 악기별 필터링 적용
                filter_measure_by_instrument(measure_root, INSTRUMENT_MAP[instrument_type])
                
                # 옵션: time-modification 추가
                if add_time_mod:
                    add_time_modification_to_notes(measure_root, actual_notes, normal_notes)
                
                # 옵션: bpm 추가
                if add_bpm:
                    add_bpm_to_notes(measure_root, bpm)
                
                # 파일 이름 생성 (예: measure_01_kick.xml)
                filename = f"measure_{str(measure_number).zfill(length)}_{instrument_type}.xml"
                output_path = os.path.join(output_dir, filename)
                
                # XML 트리 생성 및 포맷팅하여 저장
                measure_tree = ET.ElementTree(measure_root)
                save_formatted_xml(measure_tree, output_path)
            
            print(f"마디 {measure_number} 저장 완료 (kick, snare, hit 3개 파일)")
        
        print(f"\n=== 완료 ===")
        print(f"전처리 파일: preprocessing.xml")
        print(f"총 {total_measures * 3}개의 마디 파일이 '{output_dir}' 디렉토리에 생성되었습니다.")
        
    except ET.ParseError as e:
        print(f"XML 파싱 오류: {e}")
    except FileNotFoundError:
        print(f"파일을 찾을 수 없습니다: {input_file}")
    except Exception as e:
        print(f"오류 발생: {e}")
        import traceback
        traceback.print_exc()

def list_xml_files():
    """현재 디렉토리의 XML 파일들을 나열하는 함수"""
    xml_files = [f for f in os.listdir('.') if f.endswith('.xml')]
    return xml_files

def main():
    """메인 실행 함수"""
    print("=== MusicXML 파일 분할기 (악기 분리 버전) ===")
    print("Kick / Snare / Hit(심벌/하이햇) 악보를 분리하여 마디별로 저장합니다.")
    
    xml_files = list_xml_files()
    
    if xml_files:
        print("\n현재 디렉토리의 XML 파일들:")
        for i, file in enumerate(xml_files, 1):
            print(f"{i}. {file}")
        
        try:
            choice = int(input(f"\n처리할 파일 번호를 입력하세요 (1-{len(xml_files)}): ")) - 1
            if 0 <= choice < len(xml_files):
                input_file = xml_files[choice]
            else:
                print("잘못된 번호입니다.")
                return
        except ValueError:
            print("숫자를 입력해주세요.")
            return
    else:
        print("현재 디렉토리에 XML 파일이 없습니다.")
        input_file = input("XML 파일의 전체 경로를 입력하세요: ")
    
    if not os.path.exists(input_file):
        print(f"파일을 찾을 수 없습니다: {input_file}")
        return
    
    output_directory = input(f"출력 디렉토리 이름을 입력하세요 (기본값: {input_file[:-4]}_output): ").strip()
    if not output_directory:
        output_directory = input_file[:-4] + "_output"
    
    add_time_mod_choice = input("모든 노트에 time-modification을 추가하시겠습니까? (y/n, 기본값: y): ").strip().lower()
    add_time_mod = add_time_mod_choice != 'n'
    
    add_bpm_choice = input("모든 노트에 bpm을 추가하시겠습니까? (y/n, 기본값: y): ").strip().lower()
    add_bpm = add_bpm_choice != 'n'
        
    extract_header_and_split_measures(input_file, output_directory, add_time_mod, add_bpm)

if __name__ == "__main__":
    main()