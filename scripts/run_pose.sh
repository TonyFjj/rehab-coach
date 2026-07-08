#!/bin/bash
# YOLOv8s-Pose on RK3588 NPU
# Usage: ./run_pose.sh [image_path]
#   No args: use camera (device 21)
#   With image path: detect pose on image
python3 /home/elf/Desktop/rknn/yolo_pose_infer.py "$@"
