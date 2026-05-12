FROM osrf/ros:humble-desktop-full

ENV DEBIAN_FRONTEND=noninteractive

# 1. OD-only system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip \
    python3-colcon-common-extensions \
    ros-humble-rmw-cyclonedds-cpp \
    ros-humble-cv-bridge \
    ros-humble-vision-opencv \
    dos2unix \
    && rm -rf /var/lib/apt/lists/*

# 2. Python dependencies for YOLO-OBB
# numpy<2 is required by Ultralytics; setuptools pinned for ament_python build
RUN pip3 install --no-cache-dir \
    "numpy==1.26.4" \
    ultralytics \
    setuptools==58.2.0

# 3. Copy OD source + msg package + model weights into workspace
WORKDIR /home/ros2_ws
COPY cobot_object_detection/ /home/ros2_ws/src/cobot_object_detection/
COPY cobot_msgs/ /home/ros2_ws/src/cobot_msgs/
COPY experiments/cobot_OD_obb_nano/train_phase2_20260504_173049/weights/best.pt \
     /home/ros2_ws/src/experiments/cobot_OD_obb_nano/train_phase2_20260504_173049/weights/best.pt

# 4. Bake the workspace into install/
RUN /bin/bash -c "source /opt/ros/humble/setup.bash && \
    colcon build --packages-select cobot_msgs cobot_object_detection \
        --cmake-args -DCMAKE_BUILD_TYPE=Release"

# 5. Entrypoint (CRLF fix for Windows checkouts)
COPY entrypoint.sh /entrypoint.sh
RUN dos2unix /entrypoint.sh && chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["bash"]
