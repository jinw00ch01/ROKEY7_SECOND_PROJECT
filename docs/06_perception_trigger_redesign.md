# Perception 트리거식 재설계 보고서

> **대상**: stream 기반 detection cache → on-demand trigger 기반 detect_once 로의 전환 결정 배경, 새 파이프라인의 단계별 동작, 그리고 이 변경으로 해결된 문제와 새로 보장되는 invariant.
>
> **관련 코드**: `cobot_perception/cobot_perception/perception_transform_node.py` (전면 재작성), `cobot_object_detection/cobot_object_detection/yolo_detector.py` (인터페이스만 유지)
>
> **시점**: 2026-05-09 작업 (`a3d2a8e feat(perception): redesign detect_once as trigger-based YOLO pipeline`)

---

## 1. 배경 — 기존 stream 방식의 문제

### 1.1 기존 구조

직전 구조는 두 노드로 분리되어 있었다.

```
[RealSense] ──color/depth──▶ [object_detection_node]
                                │
                                │ DetectedObjectArray (stream, ~30Hz)
                                ▼
                          [perception_transform_node]
                                │
                                │ cache: 최근 detection + TCP
                                ▼
                        /perception/detect_once  (서비스)
```

`object_detection_node`는 카메라 스트림에 subscribe하여 매 프레임 YOLO를
돌리고 `DetectedObjectArray`를 publish. `perception_transform_node`는 이를
구독하면서 별도로 TCP/depth/intrinsics를 cache하고, `detect_once` 호출 시
**가장 최근 캐시 detection**을 골라 base 프레임으로 변환했다.

### 1.2 관찰된 증상

운영 중 다음 두 패턴이 누적 보고됨.

#### (a) Y축 쏠림 — 첫 픽 정상, 2~4번째 픽이 X≈394로 쏠려 Y축 앞쪽으로 빗나감

원인 분석:
- 픽 사이클은 `home → detect_once → pick → place → home → detect_once → ...`
- `home` 직후 detect를 부르면, perception이 "최근 캐시"로 갖고 있는
  detection은 **이전 픽 동작 중 publish된 프레임** 일 수도 있음.
- 그 프레임의 검출 좌표(픽셀)는 모션 중 카메라 시점의 좌표인데,
  perception은 변환에 **현재 home 위치의 TCP**를 사용.
- 결과: "이전 카메라 시점의 픽셀" × "현재 TCP의 변환행렬" → 잘못된 base 좌표.
- 매 사이클 같은 패턴으로 ±30~100mm 오차 누적, 두 번째 픽부터 Y축 쏠림.

#### (b) `initial_verify_detect_failed` — 검증 단계 첫 detect 실패

원인 분석:
- BE-only subscriber + RELIABLE publisher 조합이 cyclonedds 대용량 메시지
  (color 1280×720×3 = 2.7MB) 환경에서 fragment delivery 실패
- object_detection_node가 detection을 받지 못하면 publish가 안 되고,
  perception_transform_node의 캐시도 비어 있어 detect_once가 실패
- QoS는 별건으로 RELIABLE/depth=1로 수정했지만, **stream 방식의 구조
  자체가 "캐시 freshness"라는 별도 invariant를 책임져야** 했음.

### 1.3 구조적 한계

이 두 증상은 **공통적으로 "캐시된 detection의 시점 ≠ 변환에 쓰인 TCP의
시점"**에서 비롯된다. stream 방식에서는 다음을 동시에 보장해야 한다:

1. detection이 발행된 시점의 카메라 프레임
2. 변환에 사용할 TCP의 시점
3. depth/intrinsics의 시점

각각 다른 sub-buffer에서 흘러오는 비동기 스트림이라, "셋이 같은 stationary
window에서 샘플링된 것"을 구조적으로 강제할 방법이 없다. 결국 사용자가
detect_once를 **호출한 시점**과 cache의 **마지막 publish 시점** 사이에
어떤 pose 변경이라도 있으면 mismatch가 발생.

---

## 2. 설계 결정 — Trigger 기반으로 전환

### 2.1 핵심 아이디어

> detect_once 호출 시점부터 **정해진 개수의 새 color frame**을 능동적으로
> 모은 뒤, **그 캡처 윈도우 안에서 샘플링된 depth + TCP** 만으로 변환한다.

캐시를 없애는 것이 아니라, **cache를 trigger 시점 이후로만 유효**하게
좁힌다. 이로써 "변환에 쓰인 TCP는 캡처 윈도우 안의 샘플" 이라는 timing
invariant가 호출 한 번 안에서 닫혀 보장된다.

### 2.2 단일 노드로 통합

`object_detection_node`를 `perception_transform_node` 안으로 흡수.

| 이전 | 이후 |
|---|---|
| 노드 2개, ROS topic으로 detection 전달 | 노드 1개, `YoloObbDetector` 직접 import |
| 30Hz publish (필요 없는 추론 비용) | trigger 시에만 추론 |
| QoS 이슈에 노출 | DDS publish/subscribe 경로 자체 제거 |

`object_detection_node` 자체는 archive되었고, bringup launch에서도
spawn하지 않음 (`cobot_bringup/launch/perception.launch.py` 수정).

### 2.3 trade-off

| 잃는 것 | 얻는 것 |
|---|---|
| 외부에서 detection을 stream으로 받을 수 있는 노드 | timing invariant, QoS 부담 제거, 추론 비용 절감 |
| stream 시각화 (rviz에서 실시간 OBB 보기) | 결정성 (같은 입력 ↔ 같은 출력) |

stream 시각화가 필요하면 별도 디버그 도구로 분리 가능하지만, 본 프로젝트의
주 흐름(픽 사이클)은 stream을 필요로 하지 않으므로 net win.

---

## 3. 새 파이프라인 — detect_once 호출당 9 단계

`PerceptionTransformNode._handle_detect_once` (`perception_transform_node.py:318`)
는 다음 9단계를 거친다.

```
┌─ caller: task_manager_node ──▶ /perception/detect_once 호출
│
│   1. 트리거 시점 기록 (self.get_clock().now())
│
│   2. fresh color frame N장 수집
│      while collected < N and not timeout:
│        msg = self._latest_color (subscribe 캐시)
│        if msg.header.stamp <= trigger: skip
│        if msg.header.stamp == last_processed: skip   ← 중복 방지
│        YOLO 추론 → aggregator.add(..., time.time())
│        collected += 1
│
│   3. aggregator.fuse() — N장 결과를 픽셀 거리 기준 클러스터링 후 fuse
│
│   4. depth = self._latest_depth
│      (color N장과 같은 stationary window의 마지막 publish)
│
│   5. tcp_xyz, tcp_zyz = self._current_tcp()
│      (mode='service'면 /robot/get_current_pose 호출,
│       mode='fixed'면 yaml 상수)
│
│   6. base2cam 동차변환 행렬 생성:
│      base2gripper = tcp_to_base2gripper(tcp_xyz, tcp_zyz)
│      base2cam = base2gripper @ gripper2cam (npy 캘리브레이션)
│
│   7. fused detection 각각:
│      z = median_inside_obb(depth, cx, cy, w, h, theta)
│      if not finite: transform_valid=False, skip
│
│   8. pinhole lift + base 변환:
│      X = (cx - ppx) * z / fx
│      Y = (cy - ppy) * z / fy
│      (bx, by, bz) = base2cam @ (X, Y, z)
│      bz = max(bz + depth_offset_mm, min_depth_base_mm)
│
│   9. grasp_yaw, short_axis_mm, long_axis_mm 계산 후 emit
│
└─ response.objects = DetectedObjectArray with 변환된 결과
```

### 3.1 Trigger 시점 비교 (단계 2)

`trigger_tuple = (sec, nanosec)`로 트리거 시점을 정수 튜플로 캐시한다.
새 frame의 `header.stamp`도 같은 형식 튜플로 변환해 lexicographic 비교.
header.stamp가 **트리거 시점 이전**이면 그 frame은 motion 잔재일 수 있어
배제된다.

```python
# perception_transform_node.py:294
if stamp <= trigger_tuple:
    time.sleep(0.005); continue
```

camera publisher가 `self.get_clock().now()`와 같은 ROS clock을 쓰므로
직접 비교 가능. system clock과의 혼동은 없다.

### 3.2 다중 프레임 fusion (단계 3)

기존 `DetectionAggregator`를 그대로 재사용. N장의 단일 프레임 추론 결과를:
- 픽셀 평면에서 cluster_distance_threshold_px 이내인 검출들끼리 묶어
- confidence 가중 평균으로 cx/cy/w/h/theta를 fuse

이 단계의 의미: 단일 프레임 노이즈(YOLO confidence 흔들림, depth dropout
등)를 N장으로 평균화. N=5, capture_timeout=2.0sec이 기본.

### 3.3 depth/TCP의 freshness (단계 4-5)

depth는 `self._latest_depth` (subscribe 캐시)에서 직접 읽는다. color N장을
모은 직후이므로 같은 정지 구간의 frame.

TCP는 단계 5에서 `_current_tcp()`로 한 번만 조회. mode가 `service`면
`/robot/get_current_pose`를 동기적으로 호출. 픽 사이클에서 detect_once가
**호출되는 시점은 항상 home 자세**이므로 한 번 조회로 충분.

### 3.4 변환 체인 구성 (단계 6)

```
base2gripper :  TCP (xyz_mm, zyz_deg) → 4×4 동차변환 (mm 단위)
gripper2cam  :  hand-eye 캘리브레이션 npy 파일 (handeye_transform.load_gripper2camera)
base2cam     :  base2gripper @ gripper2cam
```

`gripper2cam`은 launch 시 1회 로드해 캐시. `base2gripper`는 TCP가 매번
다르므로 detect_once 호출당 새로 만든다.

### 3.5 픽셀→카메라→베이스 변환 (단계 7-8)

```python
# perception_transform_node.py:400-411
X = (obj.cx - ppx) * z_mm / fx
Y = (obj.cy - ppy) * z_mm / fy
obj.camera_xyz = (X, Y, z_mm)
bx, by, bz = transform_camera_to_base(base2cam, (X, Y, z_mm))
bz = max(bz + depth_offset, min_depth_base)   # bias 보정 + 안전 하한
```

`depth_offset_mm = -5.0` (yaml 기본): RealSense의 depth 측정 편향 보정.
`min_depth_base_mm = 2.0`: 변환 후 base z가 너무 낮아 그리퍼가 테이블
아래로 내려가지 않도록 클램프.

---

## 4. 보장되는 invariant

이 설계가 깨질 수 없는 시간 관계 (단조성):

```
trigger_now
   ≤ color_frame[i].header.stamp  for all i in capture batch
   ≈ depth.publish_time            (RealSense는 color/depth 동기 publish)
   ≈ TCP.read_time                 (캡처 직후 service call)
```

즉 **변환에 쓰인 모든 데이터(N장의 color, depth, TCP)가 trigger_now 이후의
같은 정지 구간에서 샘플링됨**이 단계 2의 `stamp > trigger` 가드 하나로
구조적으로 보장된다.

이전 stream 방식에서는 caller가 호출 직전에 home에 도착했음에도 cache의
detection이 motion 잔재일 수 있었지만, 이제는 trigger_now 이전 frame이
명시적으로 reject되므로 같은 사고가 발생할 수 없다.

---

## 5. 파라미터 (`cobot_perception/config/perception.yaml`)

| 파라미터 | 기본값 | 의미 |
|---|---|---|
| `num_capture_frames` | 5 | 트리거 후 모을 color frame 수 |
| `capture_timeout_sec` | 2.0 | 위 수집 한도 |
| `multi_frame_window_sec` | 0.5 | aggregator의 동시 프레임 윈도우 |
| `cluster_distance_threshold_px` | 30.0 | aggregator 픽셀 클러스터 임계 |
| `min_depth_camera_mm` / `max_depth_camera_mm` | 50 / 1500 | depth 유효 범위 |
| `depth_offset_mm` | -5.0 | base z 편향 보정 |
| `min_depth_base_mm` | 2.0 | base z 클램프 하한 |
| `tcp_source` | `service` | `service` 또는 `fixed` |
| `tcp_service_timeout_sec` | 5.0 | TCP 서비스 호출 한도 |

---

## 6. 검증

### 6.1 정성

- 같은 장면에서 detect_once를 10회 호출 → 동일 너트 인스턴스의 base xyz가
  ±1mm 이내로 안정적 (이전 stream에서는 픽 사이클별로 ±30~100mm 흔들림).
- "y축 쏠림" 패턴이 사라짐 — 두 번째 픽 이후도 모두 정확한 base 좌표 사용.

### 6.2 정량 (서비스 레이턴시)

trigger부터 response까지의 wall-clock:
- N=5, RTX 3060급 GPU에서 ~250-400 ms (color N장 수집 + YOLO N회 + 변환).
- 이는 "픽 사이클의 home 자세 settle 시간(~0.5s)" 안에 들어가므로 사이클
  타임에 영향 없음.

### 6.3 회귀 테스트

`detect_once` 직접 호출 (`ros2 service call /perception/detect_once
cobot_msgs/srv/DetectOnce {}`)이 정상 동작하면 OK. response.message에
`transformed N/M detections` 형태로 변환 성공 비율을 보고.

---

## 7. 알려진 한계 / 향후 과제

### 7.1 capture window 동안 robot이 정지해 있어야 함

현재 설계는 **trigger 후 capture window 동안 TCP가 움직이지 않음**을 가정.
픽 사이클은 항상 home에서 detect를 부르므로 자연스럽게 만족하지만, 만약
moving capture가 필요하다면 frame별 TCP 기록이 필요해 구조 재설계가 필요.

### 7.2 N=5 frame 동안 outlier에 취약할 수 있음

5장의 단순 fusion이라 1-2장이 노이즈에 흔들리면 평균이 끌려갈 수 있다.
median fusion 또는 frame별 confidence weighting으로 개선 여지.

### 7.3 stream 디버그 시각화 부재

이전에 가능했던 "rviz에서 실시간 OBB 보기"는 더 이상 자동으로 되지 않는다.
필요 시 별도 디버그 노드를 옵션으로 살리는 것이 가능하지만, 현재 보고된
필요는 없음.

---

## 8. 참고 코드 위치

| 파일 | 라인 | 내용 |
|---|---|---|
| `perception_transform_node.py` | 262-314 | `_capture_and_infer` (단계 1-3) |
| `perception_transform_node.py` | 318-428 | `_handle_detect_once` (단계 4-9) |
| `perception_transform_node.py` | 229-258 | `_current_tcp` / `_current_tcp_via_service` |
| `cobot_object_detection/yolo_detector.py` | 전체 | `YoloObbDetector` (재사용) |
| `cobot_object_detection/detection_postprocess.py` | — | `DetectionAggregator` (재사용) |
| `cobot_perception/handeye_transform.py` | — | `tcp_to_base2gripper`, `compose_base2camera`, `transform_camera_to_base` |

## 9. 관련 문서

- `docs/changelog/2026-05-09_130418.md` §5 — 이 변경의 라이브 일지
- `docs/02_ros_node_architecture.md` — 노드 인터페이스 레퍼런스
- `docs/01_system_architecture.md` §3 — 런타임 구성요소 개요
