"""Recorder keeps every lap by default (0: no limit) & records out/in laps, former defaults updated once"""

from neopedal.module import module_recorder
from neopedal.setting_preupdate import preupdate_user_setting
from neopedal.template.setting_module import MODULE_DEFAULT


def test_no_lap_removed_when_limit_is_zero(tmp_path):
    for lap in range(60):
        module_recorder.save_lap(f"{tmp_path}/", "Monza - GT3", lap, 110.0 + lap / 10, [], max_saved_laps=0,
                                 timestamp=1000.0 + lap)
    assert len(list((tmp_path / "Monza - GT3").glob("*.csv"))) == 60


def test_limit_still_removes_oldest_laps(tmp_path):
    for lap in range(6):
        module_recorder.save_lap(f"{tmp_path}/", "Monza - GT3", lap, 110.0 + lap, [], max_saved_laps=4,
                                 timestamp=1000.0 + lap)
    assert len(list((tmp_path / "Monza - GT3").glob("*.csv"))) == 4


def test_defaults_keep_every_lap_and_record_out_in_laps():
    recorder = MODULE_DEFAULT["module_recorder"]
    assert recorder["number_of_saved_laps_per_track"] == 0
    assert recorder["enable_out_and_in_lap_recording"] is True


def test_former_defaults_updated_once_other_values_kept():
    user = {"module_recorder": {"number_of_saved_laps_per_track": 50, "enable_out_and_in_lap_recording": False}}
    preupdate_user_setting((2, 51, 9), user)
    assert user["module_recorder"] == {"number_of_saved_laps_per_track": 0, "enable_out_and_in_lap_recording": True}

    custom = {"module_recorder": {"number_of_saved_laps_per_track": 200, "enable_out_and_in_lap_recording": True}}
    preupdate_user_setting((2, 51, 9), custom)
    assert custom["module_recorder"]["number_of_saved_laps_per_track"] == 200

    current = {"module_recorder": {"number_of_saved_laps_per_track": 50, "enable_out_and_in_lap_recording": False}}
    preupdate_user_setting((2, 51, 10), current)  # chosen again after update: kept
    assert current["module_recorder"]["number_of_saved_laps_per_track"] == 50
