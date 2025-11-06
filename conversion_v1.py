import xml.etree.ElementTree as ET
import os
import copy
from pathlib import Path

def format_xml_with_indentation(element, level=0):
    """
    XML 요소에 들여쓰기와 줄바꿈을 추가하여 가독성을 높이는 함수
    
    Args:
        element: XML 요소
        level: 들여쓰기 레벨
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
    
    Args:
        measure_element: 마디 XML 요소
    
    Returns:
        int: 제거된 print 요소의 수
    """
    removed_count = 0
    
    # 마디에서 모든 print 요소 찾기
    print_elements = measure_element.findall('.//print')
    
    for print_elem in print_elements:
        # print 요소의 부모를 찾아서 제거
        parent = measure_element
        for elem in measure_element.iter():
            if print_elem in list(elem):
                parent = elem
                break
        
        if parent is not None:
            parent.remove(print_elem)
            removed_count += 1
            print(f"<print> 요소 제거됨")
    
    return removed_count

def save_formatted_xml(tree, output_path):
    """
    포맷팅된 XML을 파일로 저장하는 함수
    
    Args:
        tree: ElementTree 객체
        output_path: 출력 파일 경로
    """
    # 루트 요소 포맷팅
    root = tree.getroot()
    format_xml_with_indentation(root)
    
    # XML 선언과 함께 저장
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write(ET.tostring(root, encoding='unicode'))

def add_time_modification_to_notes(measure_element, actual_notes=3, normal_notes=2):
    """
    마디의 모든 노트에 time-modification을 추가하는 함수
    
    Args:
        measure_element: 마디 XML 요소
        actual_notes: 실제 음표 수 (기본값: 3)
        normal_notes: 일반 음표 수 (기본값: 2)
    """
    notes = measure_element.findall('.//note')
    modified_count = 0
    
    for note in notes:
        # 이미 time-modification이 있는지 확인
        existing_time_mod = note.find('time-modification')
        
        if existing_time_mod is None:
            # time-modification 요소 생성
            time_mod = ET.Element('time-modification')
            
            actual_notes_elem = ET.SubElement(time_mod, 'actual-notes')
            actual_notes_elem.text = str(actual_notes)
            
            normal_notes_elem = ET.SubElement(time_mod, 'normal-notes')
            normal_notes_elem.text = str(normal_notes)
            
            # duration 다음에 time-modification 추가
            duration_elem = note.find('duration')
            if duration_elem is not None:
                # duration의 인덱스를 찾아서 그 다음에 삽입
                note_children = list(note)
                duration_index = note_children.index(duration_elem)
                note.insert(duration_index + 1, time_mod)
                modified_count += 1
            else:
                # duration이 없으면 마지막에 추가
                note.append(time_mod)
                modified_count += 1
    
    return modified_count

def add_bpm_to_notes(measure_element, bpm):
    """
    마디의 시작에 BPM 정보를 추가하는 함수

    Args:
        measure_element: <measure> XML 요소
        bpm: 템포 값 (예: 100)
    """
    
    # 이미 bpm이 있는지 확인
    existing_bpm = measure_element.find('direction')
    
    if existing_bpm is None:
        # <direction> 생성
        direction = ET.Element('direction')
        
        # <sound tempo="..."/> 생성
        sound = ET.SubElement(direction, 'sound')
        sound.set('tempo', str(bpm))
        
        # <measure> 가장 앞에 추가
        measure_element.insert(0, direction)
    
    return 1

def merge_attributes(target_attributes, source_attributes):
    """
    target_attributes에 source_attributes의 내용 중 없는 요소만 추가
    
    Args:
        target_attributes: 현재 마디의 <attributes>
        source_attributes: 첫 마디의 <attributes>
    """
    existing_tags = {child.tag for child in target_attributes}
    for elem in source_attributes:
        if elem.tag not in existing_tags:
            target_attributes.append(copy.deepcopy(elem))

def extract_header_and_split_measures(input_file, output_dir="output", add_time_mod=True, add_bpm=True):
    """
    MusicXML 파일을 헤더와 마디별로 분할하는 함수
    
    Args:
        input_file (str): 입력 MusicXML 파일 경로
        output_dir (str): 출력 디렉토리 경로
        add_time_mod (bool): 모든 노트에 time-modification 추가 여부
        add_bpm (bool): 모든 노트에 bpm 추가 여부
    """
    
    # 출력 디렉토리 생성
    Path(output_dir).mkdir(exist_ok=True)
    
    try:
        # XML 파일 파싱
        tree = ET.parse(input_file)
        root = tree.getroot()
        
        print("=== 1단계: 전처리 파일 생성 ===")
        
        # 1단계: part id="P1" 위의 모든 내용을 헤더로 추출
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
        
        # 헤더 XML 파일 생성
        header_root = ET.Element(root.tag, root.attrib)
        for header_elem in header_elements:
            header_root.append(header_elem)
        
        # 전처리 파일 저장 (포맷팅 적용)
        header_file = os.path.join(output_dir, "preprocessing.xml")
        header_tree = ET.ElementTree(header_root)
        save_formatted_xml(header_tree, header_file)
        
        print(f"전처리 파일 생성 완료: preprocessing.xml")
        
        print("\n=== 2단계: 마디별 파일 생성 ===")
        
        # 2단계: P1 파트에서 마디별로 파일 분할
        measures = p1_part.findall('measure')
        
        if not measures:
            print("마디를 찾을 수 없습니다.")
            return
        
        total_measures = len(measures)
        length = len(str(total_measures))
        print(f"총 {total_measures}개의 마디를 찾았습니다.")
        
        if add_bpm == True:
            bpm = input("bpm 값을 입력해 주세요: ")
        
        # 첫 번째 마디에서 attributes 추출
        first_measure = measures[0]
        first_attributes = first_measure.find('attributes')
        
        if first_attributes is not None:
            print(f"첫 마디에서 attributes 발견: {len(list(first_attributes))}개 요소")
        else:
            print("첫 마디에 attributes가 없습니다.")
            
        # divisions 추출
        div = root.find(".//divisions")
        if div is not None:
            divisions = int(div.text)
            print(f"divisions 발견: {divisions}")
        else:
            print("divisions이 없습니다.")
            divisions = 1  # 기본값
        
        actual_notes, normal_notes = divisions, divisions
        
        # time-modification 설정 출력
        if add_time_mod:
            print(f"time-modification 설정: {actual_notes} -> {normal_notes}")
        
        print("첫 번째 마디는 <print> 요소를 유지하고, 나머지 마디에서는 제거합니다.")
        
        # 각 마디별로 개별 파일 생성
        total_print_removed = 0
        for i, measure in enumerate(measures):
            measure_number = measure.get('number')
            if measure_number is None:
                measure_number = str(i + 1)
            
            # 새로운 XML 구조 생성 (마디만 포함)
            measure_root = ET.Element('measure', measure.attrib)
            
            # attributes가 있는지 확인
            current_attributes = measure.find('attributes')

            if first_attributes is not None:
                if current_attributes is None:
                    # 없으면 새로 추가
                    attributes_copy = copy.deepcopy(first_attributes)
                    measure_root.append(attributes_copy)
                    print(f"마디 {measure_number}에 첫 마디의 attributes 추가됨")
                else:
                    # 있으면 병합
                    merge_attributes(current_attributes, first_attributes)
                    print(f"마디 {measure_number}의 attributes에 첫 마디의 부족한 요소 추가됨")
            
            # 마디의 모든 내용 복사
            for elem in measure:
                measure_root.append(elem)
            
            # 첫 번째 마디가 아닌 경우에만 <print> 요소 제거
            if i > 0:  # 첫 번째 마디(인덱스 0)가 아닌 경우
                print_removed = remove_print_elements(measure_root)
                total_print_removed += print_removed
                if print_removed > 0:
                    print(f"마디 {measure_number}: {print_removed}개의 <print> 요소 제거됨")
            else:
                print(f"마디 {measure_number}: 첫 번째 마디이므로 <print> 요소 유지")
            
            # 모든 노트에 time-modification 추가 (옵션)
            if add_time_mod:
                modified_count = add_time_modification_to_notes(measure_root, actual_notes, normal_notes)
                if modified_count > 0:
                    print(f"마디 {measure_number}: {modified_count}개 노트에 time-modification({actual_notes}->{normal_notes}) 추가됨")
            
            # 모든 노트에 bpm 추가 (옵션)
            if add_bpm:
                add_bpm_to_notes(measure_root, bpm)
                print(f"마디 {measure_number}: bpm({bpm}) 추가됨")
            
            # 파일 이름 생성
            filename = f"measure_{str(measure_number).zfill(length)}.xml"
            output_path = os.path.join(output_dir, filename)
            
            # XML 트리 생성 및 포맷팅하여 저장
            measure_tree = ET.ElementTree(measure_root)
            save_formatted_xml(measure_tree, output_path)
            
            print(f"마디 {measure_number} 저장 완료: {filename}")
        
        print(f"\n=== 완료 ===")
        print(f"전처리 파일: preprocessing.xml")
        print(f"마디 파일: measure_{str(1).zfill(length)}.xml ~ measure_{str(total_measures).zfill(length)}.xml")
        print(f"총 {total_measures + 1}개 파일이 '{output_dir}' 디렉토리에 생성되었습니다.")
        
        if total_print_removed > 0:
            print(f"첫 번째 마디를 제외하고 총 {total_print_removed}개의 <print> 요소가 제거되었습니다.")
        
    except ET.ParseError as e:
        print(f"XML 파싱 오류: {e}")
    except FileNotFoundError:
        print(f"파일을 찾을 수 없습니다: {input_file}")
    except Exception as e:
        print(f"오류 발생: {e}")

def list_xml_files():
    """현재 디렉토리의 XML 파일들을 나열하는 함수"""
    xml_files = [f for f in os.listdir('.') if f.endswith('.xml')]
    return xml_files

def main():
    """메인 실행 함수"""
    print("=== MusicXML 파일 분할기 ===")
    print("첫 번째 마디를 제외하고 나머지 마디에서 <print> 요소를 제거합니다.")
    
    # 현재 디렉토리의 XML 파일들 확인
    xml_files = list_xml_files()
    
    if xml_files:
        print("\n현재 디렉토리의 XML 파일들:")
        for i, file in enumerate(xml_files, 1):
            print(f"{i}. {file}")
        
        # 파일 선택
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
        # XML 파일이 없는 경우 직접 입력
        print("현재 디렉토리에 XML 파일이 없습니다.")
        input_file = input("XML 파일의 전체 경로를 입력하세요: ")
    
    # 파일 존재 확인
    if not os.path.exists(input_file):
        print(f"파일을 찾을 수 없습니다: {input_file}")
        print(f"현재 작업 디렉토리: {os.getcwd()}")
        return
    
    # 출력 디렉토리 설정
    output_directory = input(f"출력 디렉토리 이름을 입력하세요 (기본값: {input_file}): ").strip()
    if not output_directory:
        output_directory = input_file[:-4]+"_output"
    
    # time-modification 추가 여부 선택
    add_time_mod_choice = input("모든 노트에 time-modification을 추가하시겠습니까? (y/n, 기본값: y): ").strip().lower()
    add_time_mod = add_time_mod_choice != 'n'
    
    # bpm 추가 여부 선택
    add_bpm_choice = input("모든 노트에 bpm을 추가하시겠습니까? (y/n, 기본값: y): ").strip().lower()
    add_bpm = add_bpm_choice != 'n'
        
    # 분할 실행
    extract_header_and_split_measures(input_file, output_directory, add_time_mod, add_bpm)

if __name__ == "__main__":
    main()