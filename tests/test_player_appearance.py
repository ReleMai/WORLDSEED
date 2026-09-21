from worldseed.presentation.visuals import VisualRegistry
from worldseed.systems.state import LivingWorldState


def test_visual_registry_exposes_male_and_female_player_variants() -> None:
    visuals = VisualRegistry.load_default()
    male = visuals.player_paths('male')
    female = visuals.player_paths('female')
    assert len(male) >= 10
    assert len(female) >= 10
    assert all(path.exists() for path in male[:10])
    assert all(path.exists() for path in female[:10])
    assert visuals.player_path('male', 3) == male[3]
    assert visuals.player_path('female', 7) == female[7]


def test_living_world_state_round_trips_player_appearance() -> None:
    state = LivingWorldState(player_name='Ayla', player_origin='custom', player_sex='female', player_sprite_index=8)
    restored = LivingWorldState.from_dict(state.to_dict())
    assert restored.player_name == 'Ayla'
    assert restored.player_origin == 'custom'
    assert restored.player_sex == 'female'
    assert restored.player_sprite_index == 8


def test_new_context_preserves_selected_appearance(tmp_path):
    from worldseed.app import _load_context
    from worldseed.ui.startup import StartSelection
    selection=StartSelection(tmp_path/'appearance.db',True,'Appearance',b'appearance-dev20'.hex(),player_name='Ayla',player_sex='female',player_sprite_index=8)
    ctx=_load_context(selection,prepare_world=False)
    try:
        assert ctx.sim.state.player_sex=='female'
        assert ctx.sim.state.player_sprite_index==8
    finally:
        ctx.db.close()
