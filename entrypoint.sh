#!/bin/bash
set -e

# 1. Setup ROS 2 Environment
source /opt/ros/humble/setup.bash

# 2. Workspace Setup
if [ -f "/home/ros2_ws/install/setup.bash" ]; then
    source /home/ros2_ws/install/setup.bash
    echo "[Entrypoint] Sourced local workspace: /home/ros2_ws/install/setup.bash"
else
    echo "[Entrypoint] Workspace not built yet. You can run 'colcon build' inside the container."
fi

# 3. DDS Configuration
if [ "$USE_CYCLONE_DDS" = "true" ]; then
    export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
    echo "[Entrypoint] Using CycloneDDS as RMW implementation."
    
    # Generate CycloneDDS config on the fly if NETWORK_INTERFACE is set
    if [ ! -z "$NETWORK_INTERFACE" ]; then
        export CYCLONEDDS_URI="<CycloneDDS><Domain><General><NetworkInterfaceAddress>$NETWORK_INTERFACE</NetworkInterfaceAddress></General></Domain></CycloneDDS>"
        echo "[Entrypoint] CycloneDDS Interface configured to: $NETWORK_INTERFACE"
    fi
else
    export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
    echo "[Entrypoint] Using FastRTPS as RMW implementation."
fi

export ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-0}
echo "[Entrypoint] ROS_DOMAIN_ID is set to: $ROS_DOMAIN_ID"

# 4. Sound & PulseAudio Support
# Give correct permissions for pulseaudio to run as root inside docker if needed
if [ -d "$XDG_RUNTIME_DIR/pulse" ]; then
    echo "[Entrypoint] Found PulseAudio socket at $XDG_RUNTIME_DIR/pulse."
fi

# Execute the given command
exec "$@"
