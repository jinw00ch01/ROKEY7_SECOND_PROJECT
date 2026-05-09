# 한국어 요약:
#   task_manager 루프의 상태 enum이다. 각 값은 _set_state()에서 /task/status로
#   문자열 publish되어 외부(voice flow, 모니터링 UI)에서 진행 상황을 추적한다.
"""State enum for the task manager loop."""

from enum import Enum


class TaskState(str, Enum):
    IDLE = "idle"                      # 노드 생성 직후 초기값. emit 없음.
    INIT = "init"                      # _run() 시작 시 emit. 주문 fetch 직전.
    DETECT = "detect"                  # 매 루프 시작, detect_once 호출 직전.
    SELECT_TARGET = "select_target"    # detection 받은 뒤 target_selector 진입.
    PICK_AND_PLACE = "pick_and_place"  # pick_and_place 액션 goal 전송 직전.
    VERIFY = "verify"                  # 사이클 마무리 검증 라운드 진입 시 emit.
    DONE = "done"                      # 주문 모두 처리 후 정상 종료.
    ABORTED = "aborted"                # ABORT 분기(home/order/action 실패)에서 emit.
    SAFETY_STOP = "safety_stop"        # stop_event가 set되어 worker가 빠져나간 경우.
