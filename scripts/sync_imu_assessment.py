#!/usr/bin/env python3
"""
将 IMU_measure（优化版）的 assessment_log.csv 最新一条双侧记录
同步为 rehab-coach 所需的 assessment_result.txt（一行 JSON）。

方案 A：六维度之和为唯一官方总分；左右手分仅作 lr_scores / note 补充。
"""

import csv
import json
import os
import sys
import time
from typing import Dict, Optional, Tuple

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DIM_KEYS = [
    ('range_of_motion', 'rom'),
    ('smoothness', 'smooth'),
    ('tremor', 'tremor'),
    ('symmetry', 'symmetry'),
    ('speed', 'speed'),
    ('endurance', 'endurance'),
]


def _level_from_score(score: float) -> str:
    if score <= 30:
        return 'L1'
    if score <= 60:
        return 'L2'
    if score <= 80:
        return 'L3'
    return 'L4'


def _float(row: dict, key: str) -> float:
    try:
        return float(row.get(key, 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def _hand_dimension_scores(row: dict) -> Dict[str, float]:
    scores = {}
    for out_key, col in DIM_KEYS:
        scores[out_key] = round(_float(row, col), 1)
    return scores


def _hand_total(row: dict) -> float:
    """单手总分：优先 CSV total，否则六维之和。"""
    total = _float(row, 'total')
    if total > 0:
        return round(total, 1)
    return round(sum(_hand_dimension_scores(row).values()), 1)


def find_latest_dual_pair(log_path: str) -> Optional[Tuple[dict, dict]]:
    """按 time 字段匹配最新一组 L/R 双侧记录。"""
    if not os.path.isfile(log_path):
        return None

    pairs = {}
    order = []
    with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get('mode') != 'dual':
                continue
            hand = str(row.get('hand', '')).upper()
            if hand not in ('L', 'R'):
                continue
            ts = row.get('time') or row.get('timestamp') or ''
            if ts not in pairs:
                order.append(ts)
            pairs.setdefault(ts, {})[hand] = row

    for ts in reversed(order):
        pair = pairs.get(ts, {})
        if 'L' in pair and 'R' in pair:
            return pair['L'], pair['R']

    rows_l, rows_r = [], []
    with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get('mode') != 'dual':
                continue
            hand = str(row.get('hand', '')).upper()
            if hand == 'L':
                rows_l.append(row)
            elif hand == 'R':
                rows_r.append(row)
    if rows_l and rows_r:
        return rows_l[-1], rows_r[-1]
    return None


def parse_latest_dual_row(log_path: str) -> Optional[dict]:
    pair = find_latest_dual_pair(log_path)
    if not pair:
        return None

    rl, rr = pair

    dimension_scores = {}
    for out_key, col in DIM_KEYS:
        dimension_scores[out_key] = round(
            (_float(rl, col) + _float(rr, col)) / 2.0, 1
        )

    # 方案 A：官方总分恒为六维之和
    total = round(sum(dimension_scores.values()), 1)
    total = float(max(0.0, min(100.0, total)))

    total_l = _hand_total(rl)
    total_r = _hand_total(rr)
    avg_lr = (total_l + total_r) / 2.0
    if abs(avg_lr - total) > 2.0:
        print(
            f'[sync_imu] 方案A QC: 六维总分={total:.1f} '
            f'左右均值={avg_lr:.1f} 差={abs(avg_lr - total):.1f}'
        )

    level = _level_from_score(total)

    return {
        'event': 'assessment_result',
        'timestamp': time.time(),
        'total_score': total,
        'level': level,
        'dimension_scores': dimension_scores,
        'lr_scores': {
            'left': total_l,
            'right': total_r,
        },
        'note': f'左{total_l:.1f} 右{total_r:.1f}',
        'scoring_mode': 'A',
        'source': 'imu_dual_measure',
        'csv_time': rl.get('time') or rr.get('time'),
    }


def sync_assessment(log_path: str, out_path: str) -> bool:
    result = parse_latest_dual_row(log_path)
    if not result:
        print(f'[sync_imu] 未在 {log_path} 找到 dual 评估记录')
        return False

    os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(json.dumps(result, ensure_ascii=False) + '\n')
    lr = result.get('lr_scores') or {}
    print(
        f'[sync_imu] 已写入 {out_path}: '
        f'total={result["total_score"]} level={result["level"]} '
        f'(左={lr.get("left")} 右={lr.get("right")})'
    )
    return True


def main():
    log_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        PROJECT_ROOT, 'data', 'imu', 'assessment_log.csv'
    )
    out_path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(
        PROJECT_ROOT, 'data', 'imu', 'assessment_result.txt'
    )
    ok = sync_assessment(log_path, out_path)
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
