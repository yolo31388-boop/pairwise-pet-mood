"""宠物心情与互动系统

修复点:
1. 心情只由真实互动行为产生, 挂机(idle)不加心情
2. 互动有冷却 + 每日次数上限, 同一互动重复进行收益递减
3. 心情按区间影响属性: 0-20 减属性, 80-100 加属性, 差距显著
4. 心情只在长期不互动(离线超过宽限期)时缓慢下降, 在线互动可维持
5. 每只宠物有独立的喜好/厌恶表, 喜欢的互动加更多, 讨厌的互动减心情
6. 满心情解锁特殊互动并可触发随机事件, 事件有概率给予奖励
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import datetime

# --- 互动配置 ---
NORMAL_ACTIONS = frozenset({
    "pet",      # 抚摸
    "feed",     # 喂食
    "play",     # 玩耍
    "bathe",    # 洗澡
    "walk",     # 散步
    "train",    # 训练
    "talk",     # 说话
})
SPECIAL_ACTIONS = frozenset({
    "celebrate",    # 庆祝
    "treasure_hunt",  # 寻宝
})
VALID_ACTIONS = NORMAL_ACTIONS | SPECIAL_ACTIONS

# --- 数值配置 ---
MOOD_MIN = 0
MOOD_MAX = 100
FULL_MOOD = 100

BASE_INTERACTION_MOOD = 10      # 普通互动基础心情
LIKED_MOOD = 15                 # 喜欢的互动心情
DISLIKED_MOOD = -10             # 讨厌的互动心情
REPEAT_DECAY = 0.7              # 每次重复, 收益乘以该系数
MIN_POSITIVE_GAIN = 1           # 正收益的下限

INTERACTION_COOLDOWN = 30.0     # 互动冷却(秒)
DAILY_INTERACTION_LIMIT = 20    # 每日互动次数上限

OFFLINE_GRACE_HOURS = 6.0       # 离线宽限期: 期内不掉心情
DECAY_PER_HOUR = 1              # 宽限期后每小时衰减

EVENT_CHANCE = 0.35             # 满心情互动触发随机事件概率
EVENT_REWARDS = (
    {"gold": 50},
    {"item": "gift_box"},
    {"exp": 30},
)


@dataclass
class Pet:
    pid: str
    name: str
    mood: int = 50  # 0-100
    preferences: list = field(default_factory=list)   # 喜欢的互动
    disliked: list = field(default_factory=list)      # 讨厌的互动
    interactions_today: int = 0
    action_counts: dict = field(default_factory=dict)  # 当日每个互动的次数
    last_interaction_day: object = None
    last_interaction_time: float = 0.0


class MoodSystem:
    def __init__(self):
        self.pets: dict[str, Pet] = {}
        # 存储每个宠物冷却结束的时间戳
        self.interaction_cd: dict[str, float] = {}

    # ---------- bug1: 挂机不加心情 ----------
    def is_valid_interaction(self, action: str) -> bool:
        """判断是否为真实互动; idle/未知动作均不产生心情"""
        return action in VALID_ACTIONS

    def add_mood(self, pid: str, action: str, amount: int) -> None:
        """只有真实互动才会改变心情, 结果钳制在 [0, 100]"""
        if not self.is_valid_interaction(action):
            return
        self._change_mood(self.pets[pid], amount)

    # ---------- bug2: 冷却 + 每日上限 + 重复递减 ----------
    def can_interact(self, pid: str, current_time: float) -> bool:
        cooldown_until = self.interaction_cd.get(pid, 0.0)
        if current_time < cooldown_until:
            return False
        pet = self.pets.get(pid)
        if pet is not None:
            self._reset_daily_if_needed(pet, current_time)
            if pet.interactions_today >= DAILY_INTERACTION_LIMIT:
                return False
        return True

    def interact(self, pid: str, action: str, current_time: float = 0.0) -> dict:
        """执行一次互动, 返回互动结果(含心情变化与可能的随机事件)"""
        pet = self.pets[pid]
        self._reset_daily_if_needed(pet, current_time)
        result = {
            "success": False,
            "action": action,
            "mood_change": 0,
            "mood": pet.mood,
            "event": None,
        }

        if not self.is_valid_interaction(action):
            return result
        if self.is_special_interaction(action) and not self.is_special_unlocked(pid):
            return result
        if not self.can_interact(pid, current_time):
            return result

        base = self.get_interaction_bonus(pid, action)
        gain = self._apply_diminishing(base, pet.action_counts.get(action, 0))

        old_mood = pet.mood
        self._change_mood(pet, gain)
        actual_change = pet.mood - old_mood

        pet.action_counts[action] = pet.action_counts.get(action, 0) + 1
        pet.interactions_today += 1
        pet.last_interaction_time = current_time
        self.interaction_cd[pid] = current_time + INTERACTION_COOLDOWN

        result.update(
            success=True,
            mood_change=actual_change,
            mood=pet.mood,
        )
        result["event"] = self.roll_random_event(pid)
        return result

    def _apply_diminishing(self, amount: int, times: int) -> int:
        """同一互动第 times+1 次进行时的收益(正收益递减, 有下限)"""
        if amount <= 0 or times <= 0:
            return amount
        decayed = int(math.floor(amount * (REPEAT_DECAY ** times) + 0.5))
        return max(decayed, MIN_POSITIVE_GAIN)

    # ---------- bug3: 心情按区间显著影响属性 ----------
    def get_mood_effect(self, mood: int) -> dict:
        if mood <= 20:
            return {"atk": -10, "def": -5, "hp": -50}
        if mood < 80:
            return {"atk": 0, "def": 0, "hp": 0}
        return {"atk": 10, "def": 5, "hp": 50}

    # ---------- bug4: 仅长期不互动时缓慢衰减 ----------
    def update_mood_decay(self, pid: str, online: bool, hours: float) -> None:
        if online:
            return
        pet = self.pets[pid]
        inactive_hours = max(0.0, hours - OFFLINE_GRACE_HOURS)
        decay = int(inactive_hours * DECAY_PER_HOUR)
        self._change_mood(pet, -decay)

    # ---------- bug5: 每只宠物独立喜好表 ----------
    def get_interaction_bonus(self, pid: str, action: str) -> int:
        pet = self.pets[pid]
        if action in pet.preferences:
            return LIKED_MOOD
        if action in pet.disliked:
            return DISLIKED_MOOD
        return BASE_INTERACTION_MOOD

    # ---------- bug6: 满心情特殊互动 + 随机事件奖励 ----------
    def is_special_interaction(self, action: str) -> bool:
        return action in SPECIAL_ACTIONS

    def is_special_unlocked(self, pid_or_pet) -> bool:
        pet = self.pets[pid_or_pet] if isinstance(pid_or_pet, str) else pid_or_pet
        return pet.mood >= FULL_MOOD

    def get_full_mood_bonus(self, pid: str) -> dict:
        pet = self.pets[pid]
        if pet.mood < FULL_MOOD:
            return {}
        return {
            "unlocked_interactions": sorted(SPECIAL_ACTIONS),
            "event_chance": EVENT_CHANCE,
            "rewards": [dict(r) for r in EVENT_REWARDS],
            "stat_bonus": self.get_mood_effect(pet.mood),
        }

    def roll_random_event(self, pid_or_pet, rng: random.Random | None = None) -> dict | None:
        """满心情互动后按概率触发随机事件并发放奖励"""
        pet = self.pets[pid_or_pet] if isinstance(pid_or_pet, str) else pid_or_pet
        if pet.mood < FULL_MOOD:
            return None
        rng = rng or random
        if rng.random() >= EVENT_CHANCE:
            return None
        reward = dict(rng.choice(EVENT_REWARDS))
        return {"type": "lucky_event", "reward": reward}

    # ---------- 内部工具 ----------
    def _change_mood(self, pet: Pet, amount: int) -> None:
        pet.mood = max(MOOD_MIN, min(MOOD_MAX, pet.mood + amount))

    def _reset_daily_if_needed(self, pet: Pet, current_time: float) -> None:
        today = datetime.fromtimestamp(current_time).date()
        if pet.last_interaction_day != today:
            pet.last_interaction_day = today
            pet.interactions_today = 0
            pet.action_counts = {}
