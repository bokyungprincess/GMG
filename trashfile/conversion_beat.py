import xml.etree.ElementTree as ET
import os
import tempfile
from tkinter import Tk, filedialog

# 라이브러리 설치 여부 확인
try:
    from music21 import converter
    MUSIC21_AVAILABLE = True
    print("✅ music21 설치됨 - MIDI 변환 가능")
except ImportError:
    MUSIC21_AVAILABLE = False
    print("❌ music21 미설치 - MIDI 변환 불가 (pip install music21)")

try:
    import pygame
    PYGAME_AVAILABLE = True
    print("✅ pygame 설치됨 - MIDI 재생 가능")
except ImportError:
    PYGAME_AVAILABLE = False
    print("❌ pygame 미설치 - MIDI 재생 불가 (pip install pygame)")

def list_xml_files():
    """현재 폴더의 XML 파일들을 나열하는 함수"""
    xml_files = [f for f in os.listdir('.') if f.endswith('.xml')]
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

def change_tempo_in_xml(xml_file, new_tempo):
    """
    XML 파일에서 템포를 찾아서 새로운 템포로 변경하는 함수
    
    Args:
        xml_file (str): XML 파일 경로
        new_tempo (int): 새로운 템포 값
    """
    try:
        tree = ET.parse(xml_file)
        root = tree.getroot()
        
        # <sound tempo="XXX" /> 요소 찾기
        sound_elements = root.findall('.//sound[@tempo]')
        
        if not sound_elements:
            print(f"파일 {xml_file}에서 템포 정보(<sound tempo>)를 찾을 수 없습니다.")
            return False
        
        # 모든 템포 정보 업데이트
        for sound_elem in sound_elements:
            old_tempo = sound_elem.get('tempo')
            sound_elem.set('tempo', str(new_tempo))
            print(f"파일 {xml_file}: 템포 {old_tempo} -> {new_tempo}")
        
        # 파일 저장
        with open(xml_file, 'wb') as f:
            tree.write(f, encoding='utf-8', xml_declaration=True)
        
        print(f"파일 {xml_file} 템포 변경 완료!")
        return True
        
    except Exception as e:
        print(f"파일 {xml_file} 처리 중 오류: {e}")
        return False

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
    
    Args:
        xml_file (str): MusicXML 파일 경로
        output_midi_file (str): 출력 MIDI 파일 경로
    
    Returns:
        bool: 변환 성공 여부
    """
    if not MUSIC21_AVAILABLE:
        print("music21이 설치되지 않아 MIDI 변환을 할 수 없습니다.")
        print("설치: pip install music21")
        return False
    
    try:
        print(f"XML을 MIDI로 변환: {os.path.basename(xml_file)} -> {os.path.basename(output_midi_file)}")
        score = converter.parse(xml_file)
        score.write('midi', fp=output_midi_file)
        print("MIDI 변환 성공!")
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
    if not PYGAME_AVAILABLE:
        print("pygame이 설치되지 않아 재생할 수 없습니다.")
        print("파일은 생성되었습니다. 수동으로 재생해주세요.")
        input("계속하려면 Enter를 누르세요...")
        return
        
    try:
        pygame.mixer.init()
        pygame.mixer.music.load(midi_file)
        pygame.mixer.music.play()
        
        print(f"재생 중: {os.path.basename(midi_file)}")
        print("재생을 중지하려면 Enter를 누르세요...")
        
        # 재생이 끝날 때까지 대기 또는 사용자 입력 대기
        while pygame.mixer.music.get_busy():
            pygame.time.wait(100)
            
        print("재생 완료!")
        
    except Exception as e:
        print(f"MIDI 재생 중 오류: {e}")
    finally:
        if PYGAME_AVAILABLE:
            pygame.mixer.quit()

def process_single_file(measure_file, preprocessing_file, new_tempo, output_dir):
    """
    단일 마디 파일을 처리하는 함수: BPM 변경 → 병합 → MIDI 변환 → 재생
    
    Args:
        measure_file (str): 마디 파일 경로
        preprocessing_file (str): preprocessing.xml 파일 경로
        new_tempo (int): 새로운 템포
        output_dir (str): 출력 디렉토리
    
    Returns:
        bool: 처리 성공 여부
    """
    print(f"\n=== {measure_file} 처리 시작 ===")
    
    # 1단계: BPM 변경
    print(f"1단계: BPM {new_tempo} 적용 중...")
    if not change_tempo_in_xml(measure_file, new_tempo):
        print(f"BPM 변경 실패: {measure_file}")
        return False
    
    # 2단계: preprocessing과 병합
    print("2단계: preprocessing.xml과 병합 중...")
    merged_xml = merge_with_preprocessing(measure_file, preprocessing_file)
    if not merged_xml:
        print(f"병합 실패: {measure_file}")
        return False
    
    # 3단계: MIDI 변환
    print("3단계: MIDI 변환 중...")
    base_name = os.path.splitext(measure_file)[0]
    midi_file = os.path.join(output_dir, f"{base_name}.mid")
    
    if not xml_to_midi(merged_xml, midi_file):
        print(f"MIDI 변환 실패: {measure_file}")
        os.unlink(merged_xml)  # 임시 XML 파일 삭제
        return False
    
    # 4단계: MIDI 재생
    print("4단계: MIDI 재생 중...")
    if os.path.exists(midi_file):
        play_midi_file(midi_file)
    
    # 임시 파일 정리
    os.unlink(merged_xml)
    
    print(f"✅ {measure_file} 처리 완료!")
    return True

def change_tempo_for_each_file():
    """
    현재 폴더의 각 XML 파일에 대해 개별적으로 템포를 변경하고 MIDI로 변환하는 함수
    """
    print("=== XML 파일 개별 템포 변경 및 MIDI 생성기 ===")
    print("처리 순서: BPM 변경 → preprocessing 병합 → MIDI 변환 → 재생")
    
    # 폴더 선택
    if change_to_selected_folder() is None:
        return
    
    # preprocessing.xml 파일 확인
    preprocessing_file = "preprocessing.xml"
    if not os.path.exists(preprocessing_file):
        print(f"preprocessing.xml 파일을 찾을 수 없습니다.")
        print("conversion.py를 먼저 실행하여 파일을 분할해주세요.")
        return
    
    # XML 파일 목록 가져오기 (measure_ 파일만)
    all_xml_files = list_xml_files()
    measure_files = [f for f in all_xml_files if f.startswith('measure_')]
    
    if not measure_files:
        print("현재 폴더에 measure_ XML 파일이 없습니다.")
        print("conversion.py를 먼저 실행하여 파일을 분할해주세요.")
        return
    
    # 파일명으로 정렬
    measure_files.sort()
    
    print(f"\n현재 폴더의 마디 파일들 ({len(measure_files)}개):")
    for i, file in enumerate(measure_files, 1):
        print(f"{i}. {file}")
    
    # MIDI 출력 폴더 생성
    output_dir = "midi_output"
    os.makedirs(output_dir, exist_ok=True)
    print(f"\nMIDI 파일은 '{output_dir}' 폴더에 저장됩니다.")
    
    print(f"\n각 파일마다 템포를 개별적으로 설정하고 MIDI로 변환합니다.")
    print("(엔터만 치면 해당 파일은 건너뜁니다)")
    
    # 각 파일에 대해 개별 템포 입력받기 및 처리
    success_count = 0
    for i, measure_file in enumerate(measure_files, 1):
        print(f"\n=== {i}/{len(measure_files)}: {measure_file} ===")
        
        while True:
            tempo_input = input(f"{measure_file}의 새로운 템포를 입력하세요 (예: 120, 엔터=건너뛰기): ").strip()
            
            # 엔터만 친 경우 건너뛰기
            if not tempo_input:
                print(f"{measure_file} 건너뛰기")
                break
            
            try:
                new_tempo = int(tempo_input)
                if new_tempo <= 0:
                    print("템포는 0보다 큰 숫자여야 합니다.")
                    continue
                
                # 파일 처리 (BPM 변경 → 병합 → MIDI 변환 → 재생)
                if process_single_file(measure_file, preprocessing_file, new_tempo, output_dir):
                    success_count += 1
                
                # 다음 파일로 진행할지 묻기
                continue_input = input("다음 파일로 진행하려면 Enter, 종료하려면 'q': ").strip().lower()
                if continue_input == 'q':
                    print("사용자 요청으로 종료합니다.")
                    return
                
                break
                
            except ValueError:
                print("올바른 숫자를 입력해주세요.")
    
    print(f"\n=== 작업 완료! ===")
    print(f"{success_count}/{len(measure_files)} 파일이 처리되었습니다.")
    print(f"MIDI 파일들이 '{output_dir}' 폴더에 저장되었습니다.")

def main():
    """메인 실행 함수"""
    change_tempo_for_each_file()

if __name__ == "__main__":
    main()