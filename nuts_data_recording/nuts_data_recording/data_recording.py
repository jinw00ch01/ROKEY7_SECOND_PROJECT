import os
import cv2
import json
import rclpy
import DR_init
from datetime import datetime

# 로봇 설정
ROBOT_ID = "dsr01"
ROBOT_MODEL = "m0609"
VELOCITY, ACC = 60, 60
DEVICE_NUMBER = 4 # 각자 노트북에 맞는 DEVICE_NUMBER가 다름, 수정할것

DR_init.__dsr__id = ROBOT_ID
DR_init.__dsr__model = ROBOT_MODEL


def main(args=None):
    rclpy.init(args=args)
    node = rclpy.create_node("nuts_data_recording_node", namespace=ROBOT_ID)
    DR_init.__dsr__node = node

    # 로봇 제어 모듈 가져오기
    try:
        from DSR_ROBOT2 import (
            get_current_posx,
            set_tool,
            set_tcp,
        )
    except ImportError as e:
        print(f"Error importing DSR_ROBOT2 : {e}")
        return

    # 공구 및 TCP 설정
    set_tool("Tool Weight_2FG")
    set_tcp("2FG_TCP")

    # 데이터 저장 경로 설정
    source_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
    source_path = os.path.abspath(source_path)
    os.makedirs(source_path, exist_ok=True)

    # 카메라 연결
    print(f"현재 선택된 device number는 {DEVICE_NUMBER}입니다.")
    print("디바이스 번호 확인: v4l2-ctl --list-devices")
    cap = cv2.VideoCapture(DEVICE_NUMBER)

    if not cap.isOpened():
        print("카메라를 열 수 없습니다. DEVICE_NUMBER를 확인해주세요.")
        rclpy.shutdown()
        return

    write_data = {}
    write_data["poses"] = []
    write_data["file_name"] = []

    print("=" * 50)
    print("Nuts Data Recording 시작")
    print("'q' 키: 현재 프레임 & TCP 좌표 저장")
    print("'Ctrl+C': 종료")
    print("=" * 50)

    try:
        while True:
            ret, frame = cap.read()

            if not ret:
                print("카메라를 찾을 수 없습니다. DEVICE_NUMBER를 변경해주세요.")
                break

            # 현재까지 저장된 이미지 수 표시
            info_frame = frame.copy()
            cv2.putText(
                info_frame,
                f"Saved: {len(write_data['file_name'])} images | Press 'q' to capture",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2,
            )
            cv2.imshow("Nuts Data Recording", info_frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                pos = get_current_posx()[0]
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                file_name = f"{timestamp}_{pos[0]}_{pos[1]}_{pos[2]}.jpg"

                # 현재 위치 기반 이미지 저장
                cv2.imwrite(os.path.join(source_path, file_name), frame)
                print(f"current position : {pos}")
                write_data["file_name"].append(file_name)
                write_data["poses"].append(pos)
                print(f"save img to {source_path}/{file_name}")
                print(f"총 {len(write_data['file_name'])}장 저장 완료")

                with open(os.path.join(source_path, "calibrate_data.json"), "w") as json_file:
                    json.dump(write_data, json_file, indent=4)

    except KeyboardInterrupt:
        print(f"\n종료합니다. 총 {len(write_data['file_name'])}장의 이미지가 저장되었습니다.")

    cap.release()
    cv2.destroyAllWindows()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
