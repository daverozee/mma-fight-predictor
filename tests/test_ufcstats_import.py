from scripts.import_ufcstats_features import (
    FighterAggregate,
    add_fight_values,
    career_profile_payload,
)


def test_career_profile_payload_uses_ufcstats_rates() -> None:
    payload = career_profile_payload(
        {
            "fighter_name": "Ciryl Gane",
            "fighter_dob": "1990-04-12",
            "fighter_height_cm": "193.04",
            "fighter_weight_lbs": "245",
            "fighter_reach_cm": "205.74",
            "fighter_wins": "12",
            "fighter_losses": "2",
            "fighter_td_acc_%": "0.21",
            "fighter_td_def_%": "0.50",
            "fighter_slpm": "5.49",
            "fighter_sapm": "2.19",
        }
    )

    assert payload["name"] == "Ciryl Gane"
    assert payload["weight_class"] == "Heavyweight"
    assert payload["height_cm"] == 193.04
    assert payload["reach_cm"] == 205.74
    assert payload["wins"] == 12
    assert payload["losses"] == 2
    assert payload["takedown_accuracy"] == 0.21
    assert payload["takedown_defense"] == 0.5
    assert payload["strikes_landed_per_min"] == 5.49
    assert payload["strikes_absorbed_per_min"] == 2.19
    assert payload["source"] == "ufcstats-enriched"


def test_add_fight_values_maps_ufcstats_split_columns() -> None:
    aggregate = FighterAggregate(name="Sample Fighter", ufc_id="abc123")

    add_fight_values(
        aggregate,
        {
            "f1_age_during": "29",
            "f1_height_cm": "180",
            "f1_total_fight_time": "300",
            "f1_knockdowns": "1",
            "f1_sig_strikes": "25",
            "f1_sig_strike_atts": "50",
            "f1_tot_strikes": "40",
            "f1_tot_strike_atts": "80",
            "f1_takedowns": "2",
            "f1_takedown_atts": "4",
            "f1_submissions": "1",
            "f1_reversals": "0",
            "f1_ctrl_time": "60",
            "f1_head_strikes": "10",
            "f1_head_strike_atts": "20",
            "f1_body_strikes": "5",
            "f1_body_strike_atts": "10",
            "f1_leg_strikes": "4",
            "f1_leg_strike_atts": "8",
            "f1_dist_strikes": "12",
            "f1_dist_strike_atts": "24",
            "f1_clinchs": "7",
            "f1_clinch_atts": "14",
            "f1_grounds": "6",
            "f1_ground_atts": "12",
        },
        "f1",
    )

    assert aggregate.latest_age == 29
    assert aggregate.height_cm == 180
    assert aggregate.fight_seconds == 300
    assert aggregate.sig_strikes == 25
    assert aggregate.takedowns == 2
    assert aggregate.strike_splits["distance_strikes"] == 12
    assert aggregate.strike_splits["distance_attempts"] == 24
    assert aggregate.strike_splits["clinch_strikes"] == 7
    assert aggregate.strike_splits["clinch_attempts"] == 14
    assert aggregate.strike_splits["ground_strikes"] == 6
    assert aggregate.strike_splits["ground_attempts"] == 12
