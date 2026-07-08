"""训练分块（上肢 / 下肢 / 整合课）配置与场次统计。"""

from __future__ import annotations

import json
import os
import time
from typing import Dict, Optional

import yaml

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_BLOCKS_PATH = os.path.join(PROJECT_ROOT, 'config', 'training_blocks.yaml')
SESSION_LOG_PATH = os.path.join(PROJECT_ROOT, 'data', 'training_session_log.json')

VALID_REGIONS = ('upper', 'lower', 'integration')

# 未在 yaml 标注 body_region 时的默认映射（按动作 ID 后缀）
_SUFFIX_DEFAULT = {
    '_A1': 'upper',
    '_A2': 'upper',
    '_A3': 'lower',
}


def load_blocks_config(path: str = None) -> dict:
    cfg_path = path or DEFAULT_BLOCKS_PATH
    if not os.path.isfile(cfg_path):
        return {'blocks': {}, 'rest_between_blocks_sec': 120}
    with open(cfg_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


def get_block_info(body_region: str, config: dict = None) -> dict:
    cfg = config or load_blocks_config()
    blocks = cfg.get('blocks') or {}
    region = normalize_region(body_region)
    info = dict(blocks.get(region) or {})
    if not info.get('label'):
        labels = {
            'upper': '上肢训练',
            'lower': '下肢训练',
            'integration': '整合课',
        }
        info['label'] = labels.get(region, region)
    info['body_region'] = region
    return info


def normalize_region(body_region: Optional[str]) -> str:
    if not body_region:
        return 'upper'
    r = str(body_region).strip().lower()
    aliases = {
        'upper_body': 'upper',
        'lower_body': 'lower',
        'full': 'integration',
        'full_body': 'integration',
        'integrate': 'integration',
        'coord': 'integration',
    }
    r = aliases.get(r, r)
    return r if r in VALID_REGIONS else 'upper'


def infer_body_region(action: dict) -> str:
    explicit = action.get('body_region')
    if explicit:
        return normalize_region(explicit)
    aid = str(action.get('id') or '')
    for suffix, region in _SUFFIX_DEFAULT.items():
        if aid.endswith(suffix):
            return region
    if aid.endswith('_A4'):
        return 'integration'
    return 'upper'


def training_allows_companion(actions: list) -> bool:
    """护理者辅助训练：允许多人入镜，不播报「请其他人离开」。"""
    if not actions:
        return False
    for action in actions:
        if action.get('caregiver_assisted'):
            return True
        name = str(action.get('name') or '')
        desc = str(action.get('description') or '')
        if '被动' in name or '护理者' in desc:
            return True
    return False


def filter_warnings_for_companion(warnings: list, allow_companion: bool) -> list:
    if not allow_companion or not warnings:
        return list(warnings or [])
    blocked = ('请其他人暂时离开画面',)
    return [w for w in warnings if w not in blocked]


def filter_actions_by_region(actions: list, body_region: str) -> list:
    region = normalize_region(body_region)
    return [a for a in actions if infer_body_region(a) == region]


class TrainingSessionLog:
    """记录本周训练次数，用于整合课推荐。"""

    def __init__(self, path: str = SESSION_LOG_PATH):
        self.path = path
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)

    def _load(self) -> dict:
        if not os.path.isfile(self.path):
            return {'week_key': '', 'count': 0, 'regions': []}
        try:
            with open(self.path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {'week_key': '', 'count': 0, 'regions': []}

    def _save(self, data: dict):
        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _week_key() -> str:
        return time.strftime('%Y-W%W')

    def record_session(self, body_region: str):
        data = self._load()
        wk = self._week_key()
        if data.get('week_key') != wk:
            data = {'week_key': wk, 'count': 0, 'regions': []}
        data['count'] = int(data.get('count', 0)) + 1
        regions = list(data.get('regions') or [])
        regions.append(normalize_region(body_region))
        data['regions'] = regions[-40:]
        self._save(data)

    def weekly_count(self) -> int:
        data = self._load()
        if data.get('week_key') != self._week_key():
            return 0
        return int(data.get('count', 0))

    def should_suggest_integration(self, config: dict = None) -> bool:
        cfg = config or load_blocks_config()
        n = int(cfg.get('integration_suggest_every_n_sessions', 5))
        count = self.weekly_count()
        return n > 0 and count > 0 and count % n == 0
