"""MediaPipe Pose landmarks for a render (measurement aid for body registration).

    python3 tools/inez/pose_landmarks.py IMAGE

Model: pose_landmarker_heavy.task (Apache-2.0), path from INEZ_POSE_LANDMARKER
or ~/.cache/inez/pose_landmarker_heavy.task:
https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/latest/pose_landmarker_heavy.task

Prints one JSON line: {"pose": bool, "landmarks": [[x_px, y_px, z, visibility], ...33]}.
Keypoints approximate joint centres in the image; they are used only to
register two renders made with identical cameras, never as anatomy.
"""
import json
import os
import sys
from pathlib import Path

import numpy as np

MODEL = Path(os.environ.get('INEZ_POSE_LANDMARKER', Path.home()/'.cache/inez/pose_landmarker_heavy.task'))
NAMES = ['nose', 'left_eye_inner', 'left_eye', 'left_eye_outer', 'right_eye_inner', 'right_eye', 'right_eye_outer',
         'left_ear', 'right_ear', 'mouth_left', 'mouth_right', 'left_shoulder', 'right_shoulder', 'left_elbow',
         'right_elbow', 'left_wrist', 'right_wrist', 'left_pinky', 'right_pinky', 'left_index', 'right_index',
         'left_thumb', 'right_thumb', 'left_hip', 'right_hip', 'left_knee', 'right_knee', 'left_ankle',
         'right_ankle', 'left_heel', 'right_heel', 'left_foot_index', 'right_foot_index']


def main():
    from PIL import Image
    import mediapipe as mp
    from mediapipe.tasks import python as mpp
    from mediapipe.tasks.python import vision
    image = Image.open(sys.argv[1]).convert('RGB')
    options = vision.PoseLandmarkerOptions(base_options=mpp.BaseOptions(model_asset_path=str(MODEL)), num_poses=1)
    detector = vision.PoseLandmarker.create_from_options(options)
    result = detector.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(np.asarray(image))))
    if not result.pose_landmarks:
        print(json.dumps({'pose': False}))
        return 1
    w, h = image.size
    points = [[p.x*w, p.y*h, p.z*w, p.visibility] for p in result.pose_landmarks[0]]
    print(json.dumps({'pose': True, 'names': NAMES, 'landmarks': points}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
