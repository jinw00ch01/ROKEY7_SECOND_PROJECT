FROM osrf/ros:humble-desktop-full

# Set noninteractive installation to avoid timezone/keyboard prompts
ENV DEBIAN_FRONTEND=noninteractive

# 1. Install Essential System Dependencies, Sound utilities & ROS Tools
# - alsa-utils, pulseaudio, portaudio for audio (web/voice packages)
# - udev, libserial-dev for Arduino & devices
# - cycloneDDS, cv-bridge, realsense for ROS perception
RUN apt-get update && apt-get install -y \
    python3-pip \
    python3-colcon-common-extensions \
    git \
    wget \
    curl \
    nano \
    vim \
    alsa-utils \
    pulseaudio \
    libasound2-dev \
    libportaudio2 \
    libportaudiocpp0 \
    portaudio19-dev \
    udev \
    libserial-dev \
    ros-humble-rmw-cyclonedds-cpp \
    ros-humble-cv-bridge \
    ros-humble-vision-opencv \
    ros-humble-realsense2-camera \
    ros-humble-realsense2-description \
    dos2unix \
    && rm -rf /var/lib/apt/lists/*

# 2. Install Project-Specific Python Packages
# Force numpy<2 (1.26.4) to avoid Ultralytics/AI library conflicts
RUN pip3 install --no-cache-dir \
    "numpy==1.26.4" \
    ultralytics \
    pyserial \
    pyaudio \
    sounddevice \
    firebase-admin \
    setuptools==58.2.0

# 3. Setup Workspace
WORKDIR /home/ros2_ws

# 4. Entrypoint and CRLF fix for Windows users
COPY ./entrypoint.sh /entrypoint.sh
RUN dos2unix /entrypoint.sh && chmod +x /entrypoint.sh

# 5. Default Command
ENTRYPOINT ["/entrypoint.sh"]
CMD ["bash"]
