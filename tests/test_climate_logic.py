"""Tests for climate mode/setpoint behavior."""
from custom_components.watts_smarthome.climate import target_field_for_mode


def test_target_field_for_mode() -> None:
    """Target field should follow active control mode."""
    assert target_field_for_mode("0") == "consigne_confort"
    assert target_field_for_mode("3") == "consigne_eco"
    assert target_field_for_mode("2") == "consigne_hg"
    assert target_field_for_mode("4") == "consigne_boost"
    assert target_field_for_mode("8") == "consigne_confort"
    assert target_field_for_mode("11") == "consigne_eco"
    assert target_field_for_mode("13") == "consigne_manuel"
    assert target_field_for_mode("1") == "consigne_manuel"
