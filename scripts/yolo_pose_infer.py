#!/usr/bin/env python3
import sys
import cv2
import numpy as np
from rknnlite.api import RKNNLite

MODEL_PATH = "/home/elf/Desktop/rknn/yolov8s-pose.rknn"
IMG_SIZE = 640
CONF_THR = 0.6
IOU_THR = 0.5

KPT_NAMES = [
    "nose", "left_eye", "right_eye", "left_ear", "right_ear",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_hip", "right_hip",
    "left_knee", "right_knee", "left_ankle", "right_ankle"
]

SKELETON = [
    (0, 1), (0, 2), (1, 3), (2, 4),
    (5, 6), (5, 7), (7, 9), (6, 8), (8, 10),
    (5, 11), (6, 12), (11, 12),
    (11, 13), (13, 15), (12, 14), (14, 16)
]

KPT_COLORS = [
    (255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0),
    (255, 0, 255), (0, 255, 255), (128, 0, 0), (0, 128, 0),
    (0, 0, 128), (128, 128, 0), (128, 0, 128), (0, 128, 128),
    (255, 128, 0), (128, 255, 0), (0, 255, 128), (255, 0, 128), (128, 0, 255)
]


def preprocess(img):
    h, w = img.shape[:2]
    scale = IMG_SIZE / max(h, w)
    new_h, new_w = int(h * scale), int(w * scale)
    resized = cv2.resize(img, (new_w, new_h))
    padded = np.full((IMG_SIZE, IMG_SIZE, 3), 114, dtype=np.uint8)
    top, left = (IMG_SIZE - new_h) // 2, (IMG_SIZE - new_w) // 2
    padded[top:top+new_h, left:left+new_w] = resized
    tensor = padded[..., ::-1].transpose(2, 0, 1)[np.newaxis]
    return tensor, scale, top, left, (h, w)


def nms(boxes_xyxy, scores, iou_thr):
    if len(boxes_xyxy) == 0:
        return np.array([], dtype=int)
    x1, y1 = boxes_xyxy[:, 0], boxes_xyxy[:, 1]
    x2, y2 = boxes_xyxy[:, 2], boxes_xyxy[:, 3]
    areas = (x2 - x1) * (y2 - y1)
    order = scores.argsort()[::-1]
    keep = []
    while order.size > 0:
        i = order[0]
        keep.append(i)
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        w = np.maximum(0.0, xx2 - xx1)
        h = np.maximum(0.0, yy2 - yy1)
        inter = w * h
        iou = inter / (areas[i] + areas[order[1:]] - inter + 1e-6)
        order = order[1:][iou < iou_thr]
    return np.array(keep)


def postprocess(outputs, img_shape, scale, pad_top, pad_left):
    h_orig, w_orig = img_shape
    strides = [8, 16, 32]
    
    det_parts, grid_parts, stride_parts, anchor_ids = [], [], [], []
    
    for i in range(3):
        out = np.squeeze(outputs[i])  # (65, H, W)
        H, W = out.shape[1], out.shape[2]
        n = H * W
        out = out.reshape(65, n).T  # (n, 65)
        det_parts.append(out)
        
        yv, xv = np.meshgrid(np.arange(H), np.arange(W), indexing='ij')
        grid = np.stack([xv, yv], axis=-1).reshape(-1, 2).astype(np.float32) + 0.5
        grid_parts.append(grid)
        stride_parts.append(np.full(n, strides[i], dtype=np.float32))
        anchor_ids.append(np.arange(n))

    det = np.concatenate(det_parts, axis=0)  # (8400, 65)
    grids = np.concatenate(grid_parts, axis=0)  # (8400, 2)
    all_strides = np.concatenate(stride_parts, axis=0)  # (8400,)

    bbox_raw = det[:, :64].reshape(-1, 4, 16)
    es = np.exp(bbox_raw - bbox_raw.max(axis=-1, keepdims=True))
    es = es / es.sum(axis=-1, keepdims=True)
    dfl_dist = (es * np.arange(16)).sum(axis=-1)  # (8400, 4)

    cls_score = 1.0 / (1.0 + np.exp(-det[:, 64]))  # (8400,)

    mask = cls_score > CONF_THR
    cls_score = cls_score[mask]
    dfl_dist = dfl_dist[mask]
    grids = grids[mask]
    all_strides = all_strides[mask]
    indices = np.where(mask)[0]

    if len(cls_score) == 0:
        return np.array([]), np.array([]), np.array([])

    cx = grids[:, 0] * all_strides
    cy = grids[:, 1] * all_strides
    x1 = cx - dfl_dist[:, 0] * all_strides
    y1 = cy - dfl_dist[:, 1] * all_strides
    x2 = cx + dfl_dist[:, 2] * all_strides
    y2 = cy + dfl_dist[:, 3] * all_strides

    boxes_xyxy = np.stack([x1, y1, x2, y2], axis=1)
    keep = nms(boxes_xyxy, cls_score, IOU_THR)

    boxes_xyxy = boxes_xyxy[keep]
    scores = cls_score[keep]
    keep_indices = indices[keep]

    gain = scale
    boxes_xyxy[:, [0, 2]] = (boxes_xyxy[:, [0, 2]] - pad_left) / gain
    boxes_xyxy[:, [1, 3]] = (boxes_xyxy[:, [1, 3]] - pad_top) / gain
    boxes_xyxy = np.clip(boxes_xyxy, 0, [w_orig, h_orig, w_orig, h_orig])

    valid = (boxes_xyxy[:, 2] > boxes_xyxy[:, 0] + 1) & (boxes_xyxy[:, 3] > boxes_xyxy[:, 1] + 1)
    boxes_xyxy = boxes_xyxy[valid]
    scores = scores[valid]
    keep_indices = keep_indices[valid]

    if len(boxes_xyxy) == 0:
        return np.array([]), np.array([]), np.array([])

    kpt_raw = np.squeeze(outputs[3])  # (17, 3, 8400)
    keypoints = []
    for idx in keep_indices:
        k = kpt_raw[:, :, idx].T.copy()  # (3, 17)
        k[:, 0] = (k[:, 0] - pad_left) / gain
        k[:, 1] = (k[:, 1] - pad_top) / gain
        k[:, :2] = np.clip(k[:, :2], 0, [w_orig, h_orig])
        keypoints.append(k)

    return boxes_xyxy, scores, keypoints


def draw(img, boxes, scores, keypoints):
    for i in range(len(boxes)):
        x1, y1, x2, y2 = boxes[i].astype(int)
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2
        h = y2 - y1
        cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(img, f"P {scores[i]:.2f}", (x1, max(y1-10, 10)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

        kpts = keypoints[i]  # shape (3, 17)
        valid_mask = np.zeros(17, dtype=bool)
        for j in range(17):
            kx, ky = int(kpts[0, j]), int(kpts[1, j])
            # skip keypoints at origin or far from box
            if kx <= 1 and ky <= 1:
                continue
            dist = np.sqrt((kx - cx)**2 + (ky - cy)**2)
            if dist > h * 1.5:
                continue
            cv2.circle(img, (kx, ky), 4, KPT_COLORS[j], -1)
            valid_mask[j] = True
        for a, b in SKELETON:
            if valid_mask[a] and valid_mask[b]:
                pt1 = (int(kpts[0, a]), int(kpts[1, a]))
                pt2 = (int(kpts[0, b]), int(kpts[1, b]))
                cv2.line(img, pt1, pt2, KPT_COLORS[a], 2)

    return img


class YOLOPoseTracker:
    def __init__(self, model_path=MODEL_PATH, smooth=0.6):
        self.rknn = RKNNLite()
        self.rknn.load_rknn(model_path)
        self.rknn.init_runtime(core_mask=RKNNLite.NPU_CORE_0)
        self.smooth = smooth
        self.tracked_box = None
        self.tracked_kpts = None
        self.lost_frames = 0

    def __call__(self, img):
        tensor, scale, top, left, orig = preprocess(img)
        outputs = self.rknn.inference(inputs=[tensor])
        boxes_all, scores_all, kpts_all = postprocess(outputs, orig, scale, top, left)

        if len(boxes_all) == 0:
            self.lost_frames += 1
            if self.lost_frames > 30:
                self.tracked_box = None
                self.tracked_kpts = None
                self.lost_frames = 0
                return np.array([]), np.array([]), np.array([])
            if self.tracked_box is not None:
                return np.array([self.tracked_box]), np.array([0.0]), np.array([self.tracked_kpts])
            return boxes_all, scores_all, kpts_all

        self.lost_frames = 0

        # match closest box to tracked position
        if self.tracked_box is not None and len(boxes_all) > 0:
            tc = self.tracked_box.reshape(1, 4)
            bc = boxes_all[:, :4]

            # IoU-based matching
            xi1 = np.maximum(tc[:, 0], bc[:, 0])
            yi1 = np.maximum(tc[:, 1], bc[:, 1])
            xi2 = np.minimum(tc[:, 2], bc[:, 2])
            yi2 = np.minimum(tc[:, 3], bc[:, 3])
            iw = np.maximum(0, xi2 - xi1)
            ih = np.maximum(0, yi2 - yi1)
            i_area = iw * ih
            tc_area = (tc[:, 2] - tc[:, 0]) * (tc[:, 3] - tc[:, 1])
            bc_area = (bc[:, 2] - bc[:, 0]) * (bc[:, 3] - bc[:, 1])
            iou = i_area / (tc_area + bc_area - i_area + 1e-6)

            best_match = np.argmax(iou)
            if iou[best_match] > 0.3:
                best = best_match
            else:
                best = np.argmax(scores_all)
        else:
            best = np.argmax(scores_all)

        box = boxes_all[best].copy()
        score = scores_all[best]
        kpts = kpts_all[best].copy() if len(kpts_all) > best else None

        # EMA smoothing
        if self.tracked_box is not None:
            a = self.smooth
            box = a * self.tracked_box + (1 - a) * box
            if self.tracked_kpts is not None and kpts is not None and len(kpts) == len(self.tracked_kpts):
                kpts[:2] = a * self.tracked_kpts[:2] + (1 - a) * kpts[:2]

        self.tracked_box = box.copy()
        self.tracked_kpts = kpts.copy() if kpts is not None else None

        results_box = np.array([box]) if len(box) > 0 else np.array([])
        results_kpts = [kpts] if kpts is not None else []

        return results_box, np.array([score]), results_kpts

    def release(self):
        self.rknn.release()


class YOLOPose:
    def __init__(self, model_path=MODEL_PATH):
        self.tracker = YOLOPoseTracker(model_path)

    def __call__(self, img):
        return self.tracker(img)

    def release(self):
        self.tracker.release()


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else None

    print("Loading YOLOv8s-Pose on RK3588 NPU...")
    model = YOLOPose()

    if path:
        img = cv2.imread(path)
        if img is None:
            print(f"Failed to read: {path}")
            return
        boxes, scores, kpts = model(img)
        print(f"Detected {len(boxes)} person(s)")
        for i in range(len(boxes)):
            print(f"  [{i}] score={scores[i]:.3f} box={boxes[i].astype(int).tolist()}")
        img_out = draw(img, boxes, scores, kpts)
        out = path.rsplit('.', 1)[0] + "_pose.jpg"
        cv2.imwrite(out, img_out)
        print(f"Saved: {out}")
    else:
        cap = cv2.VideoCapture(21)
        if not cap.isOpened():
            print("Camera 21 failed")
            return
        print("Press 'q' to quit")
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            boxes, scores, kpts = model(frame)
            frame = draw(frame, boxes, scores, kpts)
            cv2.imshow("YOLOv8s-Pose", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
        cap.release()
        cv2.destroyAllWindows()

    model.release()


if __name__ == "__main__":
    main()
