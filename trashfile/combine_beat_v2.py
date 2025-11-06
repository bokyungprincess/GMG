import xml.etree.ElementTree as ET
import os
import copy
from pathlib import Path

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

def save_formatted_xml(tree, output_path):
    """
    포맷팅된 XML을 파일로 저장하는 함수
    (이전 스크립트와 동일, Doctype 포함)
    """
    root = tree.getroot()
    format_xml_with_indentation(root)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write('<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0.3 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">\n')
        f.write(ET.tostring(root, encoding='unicode'))

def merge_measures_by_type(input_dir):
    """
    분할된 마디 파일들을 악기 유형별로 병합하는 메인 함수
    
    Args:
        input_dir (str): 'preprocessing.xml'과 마디 파일들이 있는 디렉토리
    """
    
    # 1. 헤더 파일 경로 확인
    header_file = os.path.join(input_dir, "preprocessing.xml")
    if not os.path.exists(header_file):
        print(f"오류: 헤더 파일({header_file})을 찾을 수 없습니다.")
        return

    # 2. 모든 마디 파일 찾기
    all_files = os.listdir(input_dir)
    measure_files = [f for f in all_files if f.startswith('measure_') and f.endswith('.xml')]
    
    if not measure_files:
        print(f"오류: '{input_dir}' 디렉토리에서 마디 파일을 찾을 수 없습니다.")
        return

    # 3. 병합할 악기 유형 정의
    types_to_merge = ['kick', 'snare', 'hit']
    
    # -------------------------------------------------------------------
    # (*** 수정된 부분: 새 출력 폴더 생성 ***)
    # -------------------------------------------------------------------
    
    # 1. 상위 디렉토리 찾기 (예: 'MySong_output'의 상위 폴더)
    parent_dir = os.path.abspath(os.path.join(input_dir, ".."))
    
    # 2. 'MySong_output'에서 'MySong_merged'와 같은 새 폴더 이름 생성
    base_name = os.path.basename(os.path.normpath(input_dir)) # 'MySong_output'
    if base_name.endswith('_output'):
        new_folder_name = base_name.replace('_output', '_merged')
    else:
        new_folder_name = f"{base_name}_merged" # '_output'이 아닌 경우

    # 3. 최종 출력 디렉토리 경로
    output_dir = os.path.join(parent_dir, new_folder_name)
    
    # 4. (중요) 새 디렉토리 생성 (폴더가 이미 있어도 오류 없음)
    try:
        os.makedirs(output_dir, exist_ok=True)
    except Exception as e:
        print(f"오류: 출력 디렉토리 '{output_dir}'를 생성할 수 없습니다. {e}")
        return
    # -------------------------------------------------------------------
    # (수정 끝)
    # -------------------------------------------------------------------

    print(f"'{input_dir}' 디렉토리의 파일들을 병합하여 '{output_dir}'에 저장합니다...")

    # 4. 유형별로 병합 실행
    for file_type in types_to_merge:
        print(f"\n--- {file_type.UPPER()} 파일 병합 중 ---")
        
        type_specific_files = [f for f in measure_files if f.endswith(f"_{file_type}.xml")]
        
        if not type_specific_files:
            print(f"{file_type} 유형의 파일을 찾지 못했습니다. 건너뜁니다.")
            continue
            
        type_specific_files.sort()
        
        print(f"총 {len(type_specific_files)}개의 마디를 병합합니다...")

        try:
            # 헤더 파일(preprocessing.xml)을 기본 틀로 로드
            header_tree = ET.parse(header_file)
            header_root = header_tree.getroot()
            
            # <part id="P1"> 태그 생성
            part_p1 = ET.Element('part', {'id': 'P1'})
            
            # 정렬된 마디 파일들을 순서대로 <part>에 추가
            for measure_file in type_specific_files:
                measure_path = os.path.join(input_dir, measure_file)
                measure_tree = ET.parse(measure_path)
                measure_root = measure_tree.getroot() 
                part_p1.append(measure_root)
            
            # 헤더의 마지막에 <part id="P1"> 태그 추가
            header_root.append(part_p1)
            
            # (수정됨) 최종 파일 저장 경로가 새 'output_dir'을 사용
            output_filename = f"{file_type}_merged.xml"
            output_path = os.path.join(output_dir, output_filename)
            
            final_tree = ET.ElementTree(header_root)
            save_formatted_xml(final_tree, output_path)
            
            print(f"성공: '{output_path}' 파일이 생성되었습니다.")
            
        except Exception as e:
            print(f"오류: {file_type} 병합 중 문제 발생: {e}")
            import traceback
            traceback.print_exc()

def main():
    """메인 실행 함수"""
    print("=== MusicXML 마디 병합기 (악기별) ===")
    
    input_dir = ""
    # 유효한 디렉토리를 입력할 때까지 반복
    while True:
        input_dir = input("분할된 파일이 있는 '..._output' 디렉토리 경로를 입력하세요: ").strip()
        
        if os.path.isdir(input_dir):
            break # 유효한 디렉토리, 루프 탈출
        else:
            print(f"오류: '{input_dir}'는 유효한 디렉토리가 아닙니다. 다시 입력해주세요.")
            
    # 병합 함수 실행
    merge_measures_by_type(input_dir)

if __name__ == "__main__":
    main()