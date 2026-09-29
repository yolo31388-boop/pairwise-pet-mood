"""宠物心情与互动系统。

修复点：
1. 心情只来自有效互动行为，挂机（idle）不增加心情。
2. 互动有冷却时间与每日次数上限，同一天重复同一动作收益递减。
3. 心情按区间显著影响属性：0-20 减属性，80-100 加属性。
4. 在线时心情不衰减；仅长期不互动（离线超过宽限时间）才缓慢下降。
5. 每只宠物有独立喜好表，喜欢的互动加更多心情，讨厌的互动扣心情。
6. 满心情解锁特殊互动，并在互动后有概率触发随机事件获得奖励。
"""
import random
import time
from dataclasses import dataclass, field

MOOD_MIN = 0
MOOD_MAX = 100
FULL_MOOD = 100

# 常规互动动作；idle（挂机）不是有效互动。
INTERACTIONS = ("pet", "feed", "play", "walk", "bathe", "groom")
# 满心情才解锁的特殊互动。
SPECIAL_INTERACTIONS = ("cuddle", "party", "treasure_hunt")

# 各互动的基础心情收益。
BASE_BONUS = {
    "pet": 8,
    "feed": 10,
    "play": 12,
    "walk": 10,
    "bathe": 6,
    "groom": 7,
    "cuddle": 15,
    "party": 20,
    "treasure_hunt": 10,
}
DEFAULT_BONUS = 5

LIKE_BONUS = 10        # 喜欢的互动额外增加的心情
DISLIKE_PENALTY = -12  # 讨厌的互动扣除的心情

COOLDOWN_SECONDS = 30.0      # 两次互动之间的冷却
MAX_DAILY_INTERACTIONS = 30  # 每只宠物每日互动次数上限
# 同一天内重复同一动作的收益系数（第 1、2、3... 次）。
DIMINISH_FACTORS = (1.0, 0.7, 0.5, 0.3, 0.15)
DAY_SECONDS = 86400.0

# 离线超过宽限时间后，每小时缓慢下降的心情。
DECAY_GRACE_HOURS = 8.0
DECAY_PER_HOUR = 1.0

RANDOM_EVENT_CHANCE = 0.3  # 满心情时互动触发随机事件的概率
REWARD_TABLE = (
    {"gold": 50, "exp": 20},
    {"gold": 100, "exp": 40, "item": "snack"},
    {"item": "lucky_charm", "exp": 30},
)


@dataclass
class Pet:
    pid: str
    name: str
    mood: int = 50  # 0-100
    preferences: list = field(default_factory=list)  # 喜欢的互动
    dislikes: list = field(default_factory=list)     # 讨厌的互动
    interactions_today: int = 0
    action_counts: dict = field(default_factory=dict)  # 当日各动作次数
    day_index: int = -1
    last_interaction_time: float = 0.0
    rewards: list = field(default_factory=list)


class MoodSystem:
    def __init__(self, rng=None):
        self.pets: dict[str, Pet] = {}
        # pid -> 下次允许互动的时间戳（冷却结束时间）
        self.interaction_cd: dict[str, float] = {}
        self._rng = rng if rng is not None else random

    def is_valid_interaction(self, action: str) -> bool:
        """挂机等非互动行为无效，不会带来心情。"""
        return action in INTERACTIONS or action in SPECIAL_INTERACTIONS

    def is_special_interaction(self, action: str) -> bool:
        return action in SPECIAL_INTERACTIONS

    def can_interact(self, pid: str, current_time: float) -> bool:
        """冷却未结束不能互动。"""
        return current_time >= self.interaction_cd.get(pid, 0.0)

    def daily_limit_reached(self, pid: str) -> bool:
        pet = self.pets[pid]
        return pet.interactions_today >= MAX_DAILY_INTERACTIONS

    def set_preferences(self, pid: str, liked=(), disliked=()):
        """为单只宠物配置独立的喜好表。"""
        pet = self.pets[pid]
        pet.preferences = list(liked)
        pet.dislikes = list(disliked)

    def add_mood(self, pid: str, action: str, amount: int) -> bool:
        """只接受有效互动带来的心情变化，挂机/非法动作不加心情。"""
        if not self.is_valid_interaction(action):
            return False
        pet = self.pets[pid]
        pet.mood = max(MOOD_MIN, min(MOOD_MAX, pet.mood + amount))
        return True

    def get_mood_effect(self, mood: int) -> dict:
        """心情按区间显著影响属性：低落减属性，满心情加属性。"""
        mood = max(MOOD_MIN, min(MOOD_MAX, mood))
        if mood <= 20:
            return {"label": "低落", "atk": -20, "def": -15, "hp": -100, "exp": -20}
        if mood <= 39:
            return {"label": "沮丧", "atk": -10, "def": -8, "hp": -50, "exp": -10}
        if mood <= 59:
            return {"label": "平静", "atk": 0, "def": 0, "hp": 0, "exp": 0}
        if mood <= 79:
            return {"label": "愉悦", "atk": 10, "def": 8, "hp": 50, "exp": 10}
        return {"label": "满心情", "atk": 20, "def": 15, "hp": 100, "exp": 20}

    def update_mood_decay(self, pid: str, online: bool, hours: float) -> int:
        """在线不掉心情；离线超过宽限时间后才按小时缓慢下降。"""
        pet = self.pets[pid]
        if online:
            return 0
        idle_hours = max(0.0, float(hours) - DECAY_GRACE_HOURS)
        loss = int(idle_hours * DECAY_PER_HOUR)
        pet.mood = max(MOOD_MIN, pet.mood - loss)
        return loss

    def get_interaction_bonus(self, pid: str, action: str) -> int:
        """依据该宠物独立喜好表返回基础心情收益（讨厌的互动为负）。"""
        pet = self.pets[pid]
        base = BASE_BONUS.get(action, DEFAULT_BONUS)
        if action in pet.preferences:
            return base + LIKE_BONUS
        if action in pet.dislikes:
            return DISLIKE_PENALTY
        return base

    def get_full_mood_bonus(self, pid: str) -> dict:
        """满心情的特殊效果：属性加成、特殊互动解锁、随机事件。"""
        if self.pets[pid].mood < FULL_MOOD:
            return {}
        return {
            "atk_pct": 20,
            "def_pct": 15,
            "exp_pct": 25,
            "unlocked_interactions": list(SPECIAL_INTERACTIONS),
            "random_event_chance": RANDOM_EVENT_CHANCE,
        }

    def interact(self, pid: str, action: str, current_time: float | None = None) -> dict:
        """执行一次互动，综合计算心情（冷却/上限/递减/喜好/满心情事件）。"""
        pet = self.pets[pid]
        if not self.is_valid_interaction(action):
            return {"ok": False, "reason": "invalid_action", "mood": pet.mood}
        if self.is_special_interaction(action) and pet.mood < FULL_MOOD:
            return {"ok": False, "reason": "locked_full_mood_only", "mood": pet.mood}
        if current_time is None:
            current_time = time.time()
        current_time = float(current_time)
        if not self.can_interact(pid, current_time):
            return {"ok": False, "reason": "cooldown", "mood": pet.mood}

        day_index = int(current_time // DAY_SECONDS)
        if pet.day_index != day_index:
            pet.day_index = day_index
            pet.interactions_today = 0
            pet.action_counts = {}
        if pet.interactions_today >= MAX_DAILY_INTERACTIONS:
            return {"ok": False, "reason": "daily_limit", "mood": pet.mood}

        base = self.get_interaction_bonus(pid, action)
        used = pet.action_counts.get(action, 0)
        factor = DIMINISH_FACTORS[min(used, len(DIMINISH_FACTORS) - 1)]
        delta = int(base * factor) if base > 0 else base

        self.add_mood(pid, action, delta)
        pet.interactions_today += 1
        pet.action_counts[action] = used + 1
        pet.last_interaction_time = current_time
        self.interaction_cd[pid] = current_time + COOLDOWN_SECONDS

        result = {
            "ok": True,
            "action": action,
            "mood_delta": delta,
            "mood": pet.mood,
            "liked": action in pet.preferences,
            "disliked": action in pet.dislikes,
            "event": None,
            "rewards": [],
        }
        if pet.mood >= FULL_MOOD and self._rng.random() < RANDOM_EVENT_CHANCE:
            reward = dict(self._rng.choice(REWARD_TABLE))
            pet.rewards.append({"time": current_time, "reward": reward})
            result["event"] = "random_gift"
            result["rewards"] = [reward]
        return result
