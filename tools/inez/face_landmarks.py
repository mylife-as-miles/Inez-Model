"""MediaPipe face landmarks and frontal proportion ratios (measurement aid).

    python3 tools/inez/face_landmarks.py IMAGE [--box x0,y0,x1,y1] [--metrics]

Requires `pip install mediapipe` and the Face Landmarker model:
https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task
Set INEZ_FACE_LANDMARKER to its path (default ~/.cache/inez/face_landmarker.task).

Ratios are normalized by inter-pupil distance and describe 2D image geometry
only. They support proportion fitting/review; they are not biometric
similarity scores and do not decide likeness.
"""
import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np

MODEL = Path(os.environ.get('INEZ_FACE_LANDMARKER', Path.home()/'.cache/inez/face_landmarker.task'))
IDX = dict(pupil_L=468, pupil_R=473, inner_L=133, inner_R=362, outer_L=33, outer_R=263, nose_tip=1,
           subnasale=2, alar_L=129, alar_R=358, mouth_L=61, mouth_R=291, upper_lip_top=0, lip_seam=13,
           lower_lip_bottom=17, chin=152, brow_L=105, brow_R=334, forehead=10, cheek_L=234, cheek_R=454,
           jaw_L=172, jaw_R=397, upper_lid_L=159, lower_lid_L=145, upper_lid_R=386, lower_lid_R=374)


def detect(path, box=None):
    from PIL import Image
    import mediapipe as mp
    from mediapipe.tasks import python as mpp
    from mediapipe.tasks.python import vision
    if not MODEL.exists():
        raise SystemExit('Face Landmarker model missing: '+str(MODEL))
    options = vision.FaceLandmarkerOptions(base_options=mpp.BaseOptions(model_asset_path=str(MODEL)), num_faces=1,
                                           output_facial_transformation_matrixes=True)
    detector = vision.FaceLandmarker.create_from_options(options)
    image = Image.open(path).convert('RGB')
    offset = (0, 0)
    if box:
        image = image.crop(box)
        offset = box[:2]
    array = np.ascontiguousarray(np.asarray(image))
    result = detector.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=array))
    if not result.face_landmarks:
        return None, None
    w, h = image.size
    points = np.array([[p.x*w+offset[0], p.y*h+offset[1], p.z*w] for p in result.face_landmarks[0]])
    pose = None
    if result.facial_transformation_matrixes:
        R = np.array(result.facial_transformation_matrixes[0])[:3, :3]
        pose = {'yaw': float(np.degrees(np.arctan2(-R[2, 0], np.hypot(R[2, 1], R[2, 2])))),
                'pitch': float(np.degrees(np.arctan2(R[2, 1], R[2, 2])))}
    return points, pose


def metrics(points):
    P = {k: np.asarray(points[v]) for k, v in IDX.items()}

    def d(a, b):
        return float(np.linalg.norm(P[a][:2]-P[b][:2]))
    ipd = d('pupil_L', 'pupil_R')
    eye_y = (P['pupil_L'][1]+P['pupil_R'][1])/2
    eye_w = (d('inner_L', 'outer_L')+d('inner_R', 'outer_R'))/2
    result = dict(
        ipd_px=ipd, mouth_w=d('mouth_L', 'mouth_R')/ipd, alar_w=d('alar_L', 'alar_R')/ipd,
        inner_gap=d('inner_L', 'inner_R')/ipd, eye_w=eye_w/ipd,
        eye_open=(d('upper_lid_L', 'lower_lid_L')+d('upper_lid_R', 'lower_lid_R'))/2/eye_w,
        eye_to_chin=abs(P['chin'][1]-eye_y)/ipd, eye_to_subnasale=abs(P['subnasale'][1]-eye_y)/ipd,
        subnasale_to_seam=abs(P['lip_seam'][1]-P['subnasale'][1])/ipd,
        seam_to_chin=abs(P['chin'][1]-P['lip_seam'][1])/ipd,
        upper_lip_h=abs(P['lip_seam'][1]-P['upper_lip_top'][1])/ipd,
        lower_lip_h=abs(P['lower_lip_bottom'][1]-P['lip_seam'][1])/ipd,
        face_w_cheek=d('cheek_L', 'cheek_R')/ipd, jaw_w=d('jaw_L', 'jaw_R')/ipd,
        brow_to_eye=abs((P['brow_L'][1]+P['brow_R'][1])/2-eye_y)/ipd,
        forehead_to_eye=abs(P['forehead'][1]-eye_y)/ipd)
    return {k: round(float(v), 4) for k, v in result.items()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('image')
    parser.add_argument('--box')
    parser.add_argument('--metrics', action='store_true')
    args = parser.parse_args()
    box = tuple(int(v) for v in args.box.split(',')) if args.box else None
    points, pose = detect(args.image, box)
    if points is None:
        print(json.dumps({'face': False}))
        return 1
    out = {'face': True, 'pose': pose, 'landmarks': points.round(3).tolist()}
    if args.metrics:
        out['metrics'] = metrics(points)
    print(json.dumps(out))
    return 0


if __name__ == '__main__':
    sys.exit(main())
