"""MediaPipe Face Mesh landmark groups used by the scan-reconstruction passes."""

RIGHT_EYE = [33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246]
LEFT_EYE = [263, 249, 390, 373, 374, 380, 381, 382, 362, 398, 384, 385, 386, 387, 388, 466]
LIPS_OUTER = [61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 409, 270, 269, 267, 0, 37, 39, 40, 185]
LIPS_INNER = [78, 95, 88, 178, 87, 14, 317, 402, 318, 324, 308, 415, 310, 311, 312, 13, 82, 81, 80, 191]
NOSE = [1, 2, 98, 327, 129, 358, 49, 279, 48, 278, 64, 294, 168, 6, 197, 195, 5, 4, 19, 94,
        125, 141, 235, 236, 3, 51, 45, 44, 275, 281, 248, 456]
BROWS = [276, 283, 282, 295, 285, 300, 293, 334, 296, 336, 46, 53, 52, 65, 55, 70, 63, 105, 66, 107]
FACE_OVAL = [10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378, 400, 377,
             152, 148, 176, 149, 150, 136, 172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109]
IRIS = list(range(468, 478))
# Rigid, expression-light anchors for the similarity alignment.
STABLE = [33, 133, 362, 263, 168, 6, 197, 195, 5, 4, 1, 2, 98, 327, 61, 291, 152, 10, 234, 454, 127, 356]

GROUPS = {'eyes': RIGHT_EYE+LEFT_EYE, 'lips_outer': LIPS_OUTER, 'lips_inner': LIPS_INNER, 'nose': NOSE,
          'brows': BROWS, 'face_oval': FACE_OVAL}
FEATURE = set(RIGHT_EYE+LEFT_EYE+LIPS_OUTER+LIPS_INNER+NOSE)
