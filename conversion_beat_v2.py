import xml.etree.ElementTree as ET
import os
import pygame
import tempfile
from fractions import Fraction
from tkinter import Tk, filedialog
from pathlib import Path

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
    new_divisions = original_divisions * normal_notes
    
    return new_divisions, actual_notes, normal_notes

def format_xml_with_indentation(element, level=0):
    """XML 요소에 들여쓰기와 줄바꿈을 추가하여 가독성을 높이는 함수"""
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

def merge_with_preprocessing(measure_file, preprocessing_file):
    """
    마디 파일과 preprocessing.xml을 병합하여 완전한 MusicXML 생성
    
    Args:
        measure_file (str): 마디 파일 경로
        preprocessing_file (str): preprocessing.xml 파일 경로
    
    Returns:
        str: 병합된 XML 파일 경로
    """
    try:
        # preprocessing.xml 로드 (헤더 정보)
        preprocessing_tree = ET.parse(preprocessing_file)
        preprocessing_root = preprocessing_tree.getroot()
        
        # 마디 파일 로드
        measure_tree = ET.parse(measure_file)
        measure_root = measure_tree.getroot()
        
        # 새로운 완전한 XML 구조 생성
        full_root = ET.Element(preprocessing_root.tag, preprocessing_root.attrib)
        
        # preprocessing의 모든 헤더 요소들 복사
        for child in preprocessing_root:
            full_root.append(child)
        
        # part 요소 생성 및 마디 추가
        part_elem = ET.SubElement(full_root, 'part', {'id': 'P1'})
        part_elem.append(measure_root)
        
        # 임시 파일로 저장
        temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.xml', 
                                               delete=False, encoding='utf-8')
        temp_path = temp_file.name
        
        # 포맷팅 적용
        format_xml_with_indentation(full_root)
        
        # XML 선언과 함께 저장
        with open(temp_path, 'w', encoding='utf-8') as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
            f.write(ET.tostring(full_root, encoding='unicode'))
        
        return temp_path
        
    except Exception as e:
        print(f"파일 병합 중 오류: {e}")
        return None

def xml_to_midi(xml_file, output_midi_file):
    """
    MusicXML 파일을 MIDI 파일로 변환
    (실제로는 music21 라이브러리가 필요하지만, 여기서는 예시 구조만 제공)
    
    Args:
        xml_file (str): MusicXML 파일 경로
        output_midi_file (str): 출력 MIDI 파일 경로
    
    Returns:
        bool: 변환 성공 여부
    """
    try:
        # music21 라이브러리 사용 예시
        # from music21 import converter
        # score = converter.parse(xml_file)
        # score.write('midi', fp=output_midi_file)
        
        # 실제 구현을 위해서는 music21 라이브러리가 필요합니다
        # pip install music21
        
        print(f"XML을 MIDI로 변환: {xml_file} -> {output_midi_file}")
        print("실제 변환을 위해서는 music21 라이브러리를 설치하고 위 주석을 해제하세요.")
        
        # 임시로 빈 MIDI 파일 생성 (실제로는 변환된 파일이 생성됨)
        with open(output_midi_file, 'wb') as f:
            f.write(b'')  # 임시 빈 파일
            
        return True
        
    except Exception as e:
        print(f"MIDI 변환 중 오류: {e}")
        return False

def play_midi_file(midi_file):
    """
    MIDI 파일을 재생
    
    Args:
        midi_file (str): MIDI 파일 경로
    """
    try:
        pygame.mixer.init()
        pygame.mixer.music.load(midi_file)
        pygame.mixer.music.play()
        
        print(f"재생 중: {midi_file}")
        print("재생을 중지하려면 Enter를 누르세요...")
        
        # 재생이 끝날 때까지 대기
        while pygame.mixer.music.get_busy():
            pygame.time.wait(100)
            
        print("재생 완료!")
        
    except Exception as e:
        print(f"MIDI 재생 중 오류: {e}")
    finally:
        pygame.mixer.quit()

def apply_drum_tempo_to_measure(measure_file, bpm, measure_number=1):
    """
    마디 파일에 BPM을 적용하는 함수
    
    Args:
        measure_file (str): 조정할 마디 파일 경로
        bpm (float): 적용할 BPM 값
        measure_number (int): 마디 번호
    """
    try:
        tempo_ratio = bpm / 120.0  # 기본 120 BPM 대비 비율
        
        # 마디 파일 로드
        tree = ET.parse(measure_file)
        root = tree.getroot()
        
        # 현재 divisions 값 찾기
        attributes = root.find('.//attributes')
        if attributes is None:
            print(f"파일 {measure_number}에서 attributes를 찾을 수 없습니다.")
            return False
        
        divisions_elem = attributes.find('divisions')
        if divisions_elem is None:
            print(f"파일 {measure_number}에서 divisions를 찾을 수 없습니다.")
            return False
        
        original_divisions = int(divisions_elem.text)
        
        # 새로운 정수 값들 계산
        new_divisions, actual_notes, normal_notes = calculate_integer_values(original_divisions, tempo_ratio)
        
        print(f"마디 {measure_number} BPM 적용:")
        print(f"BPM: {bpm}")
        print(f"divisions: {original_divisions} -> {new_divisions}")
        print(f"time-modification: {actual_notes}/{normal_notes}")
        
        # divisions 업데이트
        divisions_elem.text = str(new_divisions)
        
        # 모든 duration 값 조정
        for note in root.findall('.//note'):
            duration_elem = note.find('duration')
            if duration_elem is not None:
                original_duration = int(duration_elem.text)
                new_duration = original_duration * normal_notes
                duration_elem.text = str(new_duration)
        
        # 모든 time-modification 업데이트
        for note in root.findall('.//note'):
            time_mod = note.find('time-modification')
            if time_mod is not None:
                actual_elem = time_mod.find('actual-notes')
                normal_elem = time_mod.find('normal-notes')
                
                if actual_elem is not None:
                    actual_elem.text = str(actual_notes)
                if normal_elem is not None:
                    normal_elem.text = str(normal_notes)
        
        # 파일 저장
        with open(measure_file, 'wb') as f:
            tree.write(f, encoding='utf-8', xml_declaration=True)
        
        print(f"마디 {measure_number} BPM 적용 완료!")
        return True
        
    except Exception as e:
        print(f"마디 {measure_number} 처리 중 오류: {e}")
        return False

def list_xml_files():
    """현재 폴더의 XML 파일들을 나열하는 함수"""
    xml_files = [f for f in os.listdir('.') if f.endswith('.xml') and f.startswith('measure_')]
    xml_files.sort()  # 파일명 순으로 정렬
    return xml_files

def change_to_selected_folder():
    """사용자가 선택한 폴더로 현재 작업 폴더를 변경"""
    root = Tk()
    root.withdraw()  # Tk 창 숨기기

    folder_path = filedialog.askdirectory(title="작업할 폴더를 선택하세요")
    if not folder_path:
        print("폴더 선택이 취소되었습니다.")
        return None

    os.chdir(folder_path)
    print(f"현재 작업 폴더가 변경되었습니다: {os.getcwd()}")
    return folder_path

def main():
    """메인 실행 함수"""
    print("=== MusicXML BPM 적용 및 MIDI 재생기 ===")
    print("처리 순서: 작은 마디 파일에서 BPM 변경 → preprocessing과 병합 → MIDI 변환 → 재생")
    
    # 현재 폴더의 위치 변환
    if not change_to_selected_folder():
        return
    
    # preprocessing.xml 파일 확인
    preprocessing_file = "preprocessing.xml"
    if not os.path.exists(preprocessing_file):
        print(f"preprocessing.xml 파일을 찾을 수 없습니다.")
        print("conversion.py를 먼저 실행하여 파일을 분할해주세요.")
        return
    
    # 현재 폴더의 마디 XML 파일들 확인
    xml_files = list_xml_files()
    
    if not xml_files:
        print("현재 폴더에 마디 XML 파일이 없습니다.")
        print("conversion.py를 먼저 실행하여 파일을 분할해주세요.")
        return
        
    print(f"\n{len(xml_files)}개의 마디 파일을 찾았습니다.")
    
    # BPM 입력
    try:
        bpm = float(input("적용할 BPM을 입력하세요 (예: 120): "))
        if bpm <= 0:
            print("BPM은 0보다 큰 값이어야 합니다.")
            return
    except ValueError:
        print("올바른 숫자를 입력해주세요.")
        return
    
    # 임시 폴더 생성
    temp_dir = tempfile.mkdtemp()
    print(f"임시 폴더: {temp_dir}")
    
    try:
        # 각 마디 파일 처리 (방법 2: 작은 파일에서 BPM 변경 후 병합)
        for i, measure_file in enumerate(xml_files, 1):
            print(f"\n=== 마디 {i}/{len(xml_files)} 처리 중 ===")
            
            # 1단계: 작은 마디 파일에서 BPM 적용 (빠른 처리)
            print(f"1단계: 마디 파일에서 BPM {bpm} 적용 중...")
            if not apply_drum_tempo_to_measure(measure_file, bpm, i):
                print(f"마디 {i} BPM 적용 실패. 다음 마디로...")
                continue
            
            # 2단계: BPM이 적용된 마디 파일과 preprocessing 병합
            print(f"2단계: preprocessing.xml과 병합 중...")
            merged_xml = merge_with_preprocessing(measure_file, preprocessing_file)
            if not merged_xml:
                print(f"마디 {i} 병합 실패. 다음 마디로...")
                continue
            
            # 3단계: 완성된 XML을 MIDI로 변환
            print(f"3단계: MIDI 변환 중...")
            midi_file = os.path.join(temp_dir, f"measure_{i:03d}.mid")
            if not xml_to_midi(merged_xml, midi_file):
                print(f"마디 {i} MIDI 변환 실패. 다음 마디로...")
                os.unlink(merged_xml)  # 임시 XML 파일 삭제
                continue
            
            # 4단계: MIDI 재생
            print(f"4단계: MIDI 재생 중...")
            if os.path.exists(midi_file):
                play_midi_file(midi_file)
            else:
                print(f"MIDI 파일이 생성되지 않았습니다: {midi_file}")
            
            # 5단계: 임시 파일들 정리
            os.unlink(merged_xml)
            if os.path.exists(midi_file):
                os.unlink(midi_file)
                
            # 사용자 입력 대기 (옵션)
            user_input = input("다음 마디로 진행하려면 Enter, 종료하려면 'q': ").strip().lower()
            if user_input == 'q':
                break
    
    finally:
        # 임시 폴더 정리
        try:
            os.rmdir(temp_dir)
        except:
            pass
    
    print("\n=== 완료 ===")
    print("방법 2 사용: 작은 마디 파일에서 BPM 변경 → 병합 (빠른 처리)")

if __name__ == "__main__":
    main()