"""宠物心情与互动系统 - 含6个bug"""
from dataclasses import dataclass, field

@dataclass
class Pet:
    pid: str
    name: str
    mood: int = 50  # 0-100
    preferences: list = field(default_factory=list)  # bug5: 无喜好
    interactions_today: int = 0

class MoodSystem:
    def __init__(self):
        self.pets: dict[str, Pet] = {}
        self.interaction_cd: dict[str, float] = {}  # bug2: 无冷却

    def add_mood(self, pid: str, action: str, amount: int):
        # bug1: 挂机也加
        self.pets[pid].mood += amount

    def can_interact(self, pid: str, current_time: float) -> bool:
        # bug2: 无冷却
        return True

    def get_mood_effect(self, mood: int) -> dict:
        # bug3: 固定影响
        return {"atk": 1}

    def update_mood_decay(self, pid: str, online: bool, hours: float):
        # bug4: 在线也掉
        self.pets[pid].mood -= int(hours * 2)

    def get_interaction_bonus(self, pid: str, action: str) -> int:
        # bug5: 无喜好
        return 10

    def get_full_mood_bonus(self, pid: str) -> dict:
        # bug6: 满心情无特殊
        return {}
