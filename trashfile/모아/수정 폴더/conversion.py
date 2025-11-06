import xml.etree.ElementTree as ET
import os
import copy
from pathlib import Path
from fractions import Fraction

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
            
def calculate_integer_values(original_divisions, tempo_ratio):
    """
    템포 비율에 따라 divisions, actual-notes, normal-notes를 정수로 계산하는 함수
    
    Args:
        original_divisions (int): 원래 divisions 값
        tempo_ratio (float): 템포 비율 (예: 1.5배 빠르면 1.5)
    
    Returns:
        tuple: (new_divisions, actual_notes, normal_notes)
    """
    # 분수로 변환하여 정확한 계산
    ratio_fraction = Fraction(tempo_ratio).limit_denominator(1000)
    
    actual_notes = ratio_fraction.numerator
    normal_notes = ratio_fraction.denominator
    
    # divisions는 원래 값에 normal_notes를 곱해서 정수로 만듦
    # 이렇게 하면 duration 값들이 모두 정수가 됨
    new_divisions = original_divisions * normal_notes
    
    return new_divisions, actual_notes, normal_notes

def extract_drum_tempo_ratio(drum_xml_file, measure_number=1):
    """
    드럼 XML 파일에서 특정 마디의 템포 비율을 추출하는 함수
    
    Args:
        drum_xml_file (str): 드럼 XML 파일 경로
        measure_number (int): 추출할 마디 번호
    
    Returns:
        float: 템포 비율 (기본값 1.0)
    """
    try:
        tree = ET.parse(drum_xml_file)
        root = tree.getroot()
        
        # 드럼 파트 찾기 (보통 P1이지만 다를 수 있음)
        drum_part = None
        for part in root.findall('.//part'):
            drum_part = part
            break
        
        if drum_part is None:
            print("드럼 파트를 찾을 수 없습니다.")
            return 1.0
        
        # 특정 마디 찾기
        target_measure = None
        for measure in drum_part.findall('measure'):
            if measure.get('number') == str(measure_number):
                target_measure = measure
                break
        
        if target_measure is None:
            print(f"마디 {measure_number}를 찾을 수 없습니다.")
            return 1.0
        
        # 템포 정보 추출 (metronome, direction 등에서)
        # 여기서는 예시로 time-modification 값을 사용
        time_mods = target_measure.findall('.//time-modification')
        if time_mods:
            actual = int(time_mods[0].find('actual-notes').text)
            normal = int(time_mods[0].find('normal-notes').text)
            ratio = actual / normal
            print(f"드럼에서 추출된 템포 비율: {actual}/{normal} = {ratio}")
            return ratio
        
        # 템포 정보가 없으면 기본값
        print("드럼에서 템포 정보를 찾을 수 없습니다. 기본 비율 1.0 사용")
        return 1.0
        
    except Exception as e:
        print(f"드럼 파일 처리 중 오류: {e}")
        return 1.0

def apply_drum_tempo_to_measure(measure_file, drum_xml_file, measure_number):
    """
    드럼 박자를 기반으로 마디 파일의 템포를 조정하는 함수
    
    Args:
        measure_file (str): 조정할 마디 파일 경로
        drum_xml_file (str): 드럼 XML 파일 경로
        measure_number (int): 마디 번호
    """
    try:
        # 1. 드럼에서 템포 비율 추출
        tempo_ratio = extract_drum_tempo_ratio(drum_xml_file, measure_number)
        
        # 2. 마디 파일 로드
        tree = ET.parse(measure_file)
        root = tree.getroot()
        
        # 3. 현재 divisions 값 찾기
        attributes = root.find('.//attributes')
        if attributes is None:
            print(f"마디 {measure_number}에서 attributes를 찾을 수 없습니다.")
            return
        
        divisions_elem = attributes.find('divisions')
        if divisions_elem is None:
            print(f"마디 {measure_number}에서 divisions를 찾을 수 없습니다.")
            return
        
        original_divisions = int(divisions_elem.text)
        
        # 4. 새로운 정수 값들 계산
        new_divisions, actual_notes, normal_notes = calculate_integer_values(original_divisions, tempo_ratio)
        
        print(f"마디 {measure_number} 변환:")
        print(f"  템포 비율: {tempo_ratio}")
        print(f"  divisions: {original_divisions} -> {new_divisions}")
        print(f"  time-modification: {actual_notes}/{normal_notes}")
        
        # 5. divisions 업데이트
        divisions_elem.text = str(new_divisions)
        
        # 6. 모든 duration 값 조정
        for note in root.findall('.//note'):
            duration_elem = note.find('duration')
            if duration_elem is not None:
                original_duration = int(duration_elem.text)
                new_duration = original_duration * normal_notes
                duration_elem.text = str(new_duration)
        
        # 7. 모든 time-modification 업데이트
        for note in root.findall('.//note'):
            time_mod = note.find('time-modification')
            if time_mod is not None:
                actual_elem = time_mod.find('actual-notes')
                normal_elem = time_mod.find('normal-notes')
                
                if actual_elem is not None:
                    actual_elem.text = str(actual_notes)
                if normal_elem is not None:
                    normal_elem.text = str(normal_notes)
        
        # 8. 파일 저장
        with open(measure_file, 'wb') as f:
            tree.write(f, encoding='utf-8', xml_declaration=True)
        
        print(f"마디 {measure_number} 업데이트 완료!")
        
    except Exception as e:
        print(f"마디 {measure_number} 처리 중 오류: {e}")

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

def extract_header_and_split_measures(input_file, output_dir="output", add_time_mod=True, actual_notes=3, normal_notes=2):
    """
    MusicXML 파일을 헤더와 마디별로 분할하는 함수
    
    Args:
        input_file (str): 입력 MusicXML 파일 경로
        output_dir (str): 출력 디렉토리 경로
        add_time_mod (bool): 모든 노트에 time-modification 추가 여부
        actual_notes (int): time-modification의 actual-notes 값
        normal_notes (int): time-modification의 normal-notes 값
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
        print(f"총 {total_measures}개의 마디를 찾았습니다.")
        
        # 첫 번째 마디에서 attributes 추출
        first_measure = measures[0]
        first_attributes = first_measure.find('attributes')
        
        if first_attributes is not None:
            print(f"첫 마디에서 attributes 발견: {len(list(first_attributes))}개 요소")
        else:
            print("첫 마디에 attributes가 없습니다.")
        
        # time-modification 설정 출력
        if add_time_mod:
            print(f"time-modification 설정: {actual_notes} -> {normal_notes}")
        
        # 각 마디별로 개별 파일 생성
        for i, measure in enumerate(measures):
            measure_number = measure.get('number')
            if measure_number is None:
                measure_number = str(i + 1)
            
            # 새로운 XML 구조 생성 (마디만 포함)
            measure_root = ET.Element('measure', measure.attrib)
            
            # attributes가 있는지 확인
            current_attributes = measure.find('attributes')
            
            if current_attributes is None and first_attributes is not None:
                # 현재 마디에 attributes가 없고 첫 마디에 있으면 추가
                attributes_copy = copy.deepcopy(first_attributes)
                measure_root.append(attributes_copy)
                print(f"마디 {measure_number}에 첫 마디의 attributes 추가됨")
            
            # 마디의 모든 내용 복사
            for elem in measure:
                measure_root.append(elem)
            
            # 모든 노트에 time-modification 추가 (옵션)
            if add_time_mod:
                modified_count = add_time_modification_to_notes(measure_root, actual_notes, normal_notes)
                if modified_count > 0:
                    print(f"마디 {measure_number}: {modified_count}개 노트에 time-modification({actual_notes}->{normal_notes}) 추가됨")
            
            # 파일 이름 생성
            filename = f"measure_{measure_number}.xml"
            output_path = os.path.join(output_dir, filename)
            
            # XML 트리 생성 및 포맷팅하여 저장
            measure_tree = ET.ElementTree(measure_root)
            save_formatted_xml(measure_tree, output_path)
            
            print(f"마디 {measure_number} 저장 완료: {filename}")
        
        print(f"\n=== 완료 ===")
        print(f"전처리 파일: preprocessing.xml")
        print(f"마디 파일: measure_1.xml ~ measure_{total_measures}.xml")
        print(f"총 {total_measures + 1}개 파일이 '{output_dir}' 디렉토리에 생성되었습니다.")
        
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
    
    actual_notes, normal_notes = 3, 2  # 기본값
    
    if add_time_mod:
        # time-modification 값 설정
        try:
            actual_input = input("actual-notes 값을 입력하세요 (기본값: 3): ").strip()
            if actual_input:
                actual_notes = int(actual_input)
            
            normal_input = input("normal-notes 값을 입력하세요 (기본값: 2): ").strip()
            if normal_input:
                normal_notes = int(normal_input)
                
            print(f"time-modification 설정: {actual_notes} -> {normal_notes}")
        except ValueError:
            print("잘못된 입력. 기본값 3->2 사용")
            actual_notes, normal_notes = 3, 2
    
    print(f"\n'{input_file}' 파일을 처리 중...")
    
    # 분할 실행
    extract_header_and_split_measures(input_file, output_directory, add_time_mod, actual_notes, normal_notes)

if __name__ == "__main__":
    main()