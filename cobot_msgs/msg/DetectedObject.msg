# Detection identity
string class_name              # "almond" | "cashew" | "pistachio" | "walnut"
float32 confidence             # [0, 1]

# OBB pixel coordinates (image plane)
float32 cx                     # OBB center pixel x
float32 cy                     # OBB center pixel y
float32 width                  # OBB width in pixels
float32 height                 # OBB height in pixels
float32 theta                  # OBB rotation (rad, [-pi/2, pi/2], +x axis ccw)

# Camera frame 3D position (filled by object_detection_node)
# Units: millimeters
geometry_msgs/Point camera_xyz

# Base frame 3D position + grasp yaw (filled by perception_transform_node)
# Units: position mm, grasp_yaw rad
geometry_msgs/Point base_xyz
float32 grasp_yaw              # gripper yaw derived from OBB theta

# Physical dimensions in millimeters (filled by perception_transform_node).
# Computed via the pinhole model from OBB pixel size and the measured depth,
# so they reflect the actual nut size at the workspace.
float32 short_axis_mm          # min(width_px, height_px) * z / fx
float32 long_axis_mm           # max(width_px, height_px) * z / fx

# True after perception_transform_node populates base_xyz / grasp_yaw / *_mm.
# object_detection_node leaves this false on initial publish.
bool transform_valid
