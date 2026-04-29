"""Maps Whoop's API sport_name strings to user-friendly display names.

The API returns technical names like "weightlifting_msk" while the Whoop
app shows users "Strength Trainer". This module bridges that gap. Add
overrides here as you see new sport names in the wild.
"""
from __future__ import annotations


# API sport_name (lowercased) -> friendly display name
_OVERRIDES: dict[str, str] = {
    "weightlifting_msk": "Strength Trainer",
    "weightlifting":     "Weightlifting",
    "stairmaster":       "StairMaster",
    "hiit":              "HIIT",
    "f45_training":      "F45 Training",
    "operations_tactical": "Operations — Tactical",
    "operations_medical":  "Operations — Medical",
    "operations_flying":   "Operations — Flying",
    "operations_water":    "Operations — Water",
    "obstacle_course_racing": "Obstacle Course Racing",
    "ultimate":          "Ultimate Frisbee",
    "barrys":            "Barry's",
    "barre3":            "Barre3",
    "jiu_jitsu":         "Jiu-Jitsu",
    "ice_bath":          "Ice Bath",
    "stretching":        "Stretching",
    "stadium_steps":     "Stadium Steps",
    "musical_performance": "Musical Performance",
    "stage_performance":  "Stage Performance",
    "high_stress_work":   "High Stress Work",
    "manual_labor":       "Manual Labour",
    "dedicated_parenting": "Dedicated Parenting",
    "stroller_walking":   "Stroller Walking",
    "stroller_jogging":   "Stroller Jogging",
    "toddlerwearing":     "Toddler-wearing",
    "babywearing":        "Baby-wearing",
    "australian_football": "Australian Football",
    "kite_boarding":      "Kite Boarding",
    "water_skiing":       "Water Skiing",
    "wakeboarding":       "Wakeboarding",
    "dog_walking":        "Dog Walking",
    "yard_work":          "Yard Work",
    "air_compression":    "Air Compression",
    "percussive_massage": "Percussive Massage",
    "ice_skating":        "Ice Skating",
    "rock_climbing":      "Rock Climbing",
    "mountain_biking":    "Mountain Biking",
    "horseback_riding":   "Horseback Riding",
    "hiking_rucking":     "Hiking / Rucking",
    "field_hockey":       "Field Hockey",
    "ice_hockey":         "Ice Hockey",
    "track_field":        "Track & Field",
    "water_polo":         "Water Polo",
    "cross_country_skiing": "Cross-Country Skiing",
    "functional_fitness": "Functional Fitness",
    "martial_arts":       "Martial Arts",
    "skateboarding":      "Skateboarding",
    "snowboarding":       "Snowboarding",
    "table_tennis":       "Table Tennis",
    "disc_golf":          "Disc Golf",
    "paddle_tennis":      "Paddle Tennis",
    "inline_skating":     "Inline Skating",
    "box_fitness":        "Box Fitness",
    "wheelchair_pushing": "Wheelchair Pushing",
    "circus_arts":        "Circus Arts",
    "massage_therapy":    "Massage Therapy",
    "watching_sports":    "Watching Sports",
    "assault_bike":       "Assault Bike",
    "kickboxing":         "Kickboxing",
    "jumping_rope":       "Jumping Rope",
    "motor_racing":       "Motor Racing",
    "motocross":          "Motocross",
    "public_speaking":    "Public Speaking",
    "gaelic_football":    "Gaelic Football",
    "hurling_camogie":    "Hurling / Camogie",
    "hot_yoga":           "Hot Yoga",
}


def friendly(name: str | None) -> str:
    """Return a display-ready name for an API sport_name."""
    if not name:
        return "(unknown)"
    key = name.strip().lower()
    if key in _OVERRIDES:
        return _OVERRIDES[key]
    # Fallback: replace underscores with spaces and title-case.
    return key.replace("_", " ").title()


def matches_strength(sport_name: str | None) -> bool:
    """True if this sport is what Whoop calls 'Strength Trainer' in the app.

    Covers both the API technical name and any close variants we've seen.
    """
    if not sport_name:
        return False
    s = sport_name.lower()
    return ("weightlifting_msk" in s
            or "strength" in s
            or s == "weightlifting")
