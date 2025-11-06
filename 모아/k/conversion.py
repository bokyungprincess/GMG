import xml.etree.ElementTree as ET
import os
import copy
from pathlib import Path

def extract_header_and_split_measures(input_file, output_dir="output"):
    """
    MusicXML 파일을 헤더와 마디별로 분할하는 함수
    
    Args:
        input_file (str): 입력 MusicXML 파일 경로
        output_dir (str): 출력 디렉토리 경로
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
        
        # 전처리 파일 저장
        header_file = os.path.join(output_dir, "preprocessing.xml")
        header_tree = ET.ElementTree(header_root)
        
        with open(header_file, 'wb') as f:
            header_tree.write(f, encoding='utf-8', xml_declaration=True)
        
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
                import copy
                attributes_copy = copy.deepcopy(first_attributes)
                measure_root.append(attributes_copy)
                print(f"마디 {measure_number}에 첫 마디의 attributes 추가됨")
                
            # time-modification가 있는지 확인
            current_time  = measure.find('time-modification')
            
            # 마디의 모든 내용 복사
            for elem in measure:
                measure_root.append(elem)
            
            # 파일 이름 생성
            filename = f"measure_{measure_number}.xml"
            output_path = os.path.join(output_dir, filename)
            
            # XML 트리 생성 및 저장
            measure_tree = ET.ElementTree(measure_root)
            
            with open(output_path, 'wb') as f:
                measure_tree.write(f, encoding='utf-8', xml_declaration=True)
            
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
    output_directory = input("출력 디렉토리 이름을 입력하세요 (기본값: output): ").strip()
    if not output_directory:
        output_directory = "output"
    
    print(f"\n'{input_file}' 파일을 처리 중...")
    
    # 분할 실행
    extract_header_and_split_measures(input_file, output_directory)

if __name__ == "__main__":
    main()
