"""宠物心情与互动系统 - 红态测试"""
import pytest, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pet.mood import MoodSystem, Pet

class TestIdleNoMood:
    def test_idle_does_not_increase_mood(self):
        ms = MoodSystem()
        ms.pets["p1"] = Pet("p1", "pet", mood=50)
        before = ms.pets["p1"].mood
        assert hasattr(ms, "is_valid_interaction")
        assert ms.is_valid_interaction("idle") == False  # bug1: 可能有效

class TestInteractionCooldown:
    def test_interaction_has_cooldown(self):
        ms = MoodSystem()
        ms.interaction_cd["p1"] = 100.0
        assert ms.can_interact("p1", 50.0) == False  # bug2: True
        assert ms.can_interact("p1", 150.0) == True

class TestMoodEffect:
    def test_high_mood_gives_better_stats(self):
        ms = MoodSystem()
        low = ms.get_mood_effect(0)
        high = ms.get_mood_effect(100)
        assert high["atk"] > low["atk"]  # bug3: 都是1

class TestDecayOnlyOffline:
    def test_online_no_mood_decay(self):
        ms = MoodSystem()
        ms.pets["p1"] = Pet("p1", "pet", mood=80)
        before = ms.pets["p1"].mood
        ms.update_mood_decay("p1", online=True, hours=10)
        assert ms.pets["p1"].mood == before  # bug4: 在线也掉

class TestPreferences:
    def test_liked_action_gives_more_mood(self):
        ms = MoodSystem()
        ms.pets["p1"] = Pet("p1", "pet", preferences=["pet"])
        bonus_liked = ms.get_interaction_bonus("p1", "pet")
        bonus_disliked = ms.get_interaction_bonus("p1", "bathe")
        assert bonus_liked > bonus_disliked  # bug5: 都是10

class TestFullMoodBonus:
    def test_full_mood_has_special_effect(self):
        ms = MoodSystem()
        ms.pets["p1"] = Pet("p1", "pet", mood=100)
        bonus = ms.get_full_mood_bonus("p1")
        assert bonus != {}  # bug6: 空
