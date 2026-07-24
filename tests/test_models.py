"""Tests for the static model registry and helpers (cei_labs_agent.models)."""

from __future__ import annotations

from cei_labs_agent.models import (
    REGISTRY,
    RECOMMENDED_TAG,
    TIER_ORDER,
    Preset,
    estimate_ram_gb,
    get_model,
    list_models,
    models_view,
    preset_fits,
    recommend_model,
)

EXPECTED_TAGS = {
    "qwen3:1.7b",
    "qwen3:4b",
    "gemma4",
    "qwen3:8b",
    "qwen3:14b",
    "qwen3.5:4b",
}


def test_all_six_tags_present() -> None:
    """The registry contains exactly the six contracted tags."""
    assert set(REGISTRY.keys()) == EXPECTED_TAGS


def test_presets_and_defaults_are_consistent() -> None:
    """Every spec has non-empty presets, a valid default, and in-range ctx."""
    for tag, spec in REGISTRY.items():
        assert spec.presets, f"{tag} has no presets"
        names = [p.name for p in spec.presets]
        assert spec.default_preset in names, f"{tag} default preset missing"
        for preset in spec.presets:
            assert preset.num_ctx <= spec.native_max_ctx, (
                f"{tag}/{preset.name} num_ctx exceeds native_max_ctx"
            )


def test_non_experimental_default_presets_disable_thinking() -> None:
    """Default presets of non-experimental models keep thinking off."""
    for tag, spec in REGISTRY.items():
        if spec.tier == "experimental":
            continue
        default = next(p for p in spec.presets if p.name == spec.default_preset)
        assert default.think is False, f"{tag} default preset enables thinking"


def test_estimate_ram_is_monotonic_in_num_ctx() -> None:
    """estimate_ram_gb never decreases as num_ctx grows, and grows overall."""
    spec = get_model("qwen3:14b")
    assert spec is not None
    ctxs = [1000, 4096, 8192, 16384, 32000, 40960]
    ests = [
        estimate_ram_gb(spec, Preset(name="p", num_ctx=c, num_predict=768, think=False))
        for c in ctxs
    ]
    assert ests == sorted(ests)
    assert ests[-1] > ests[0]


def test_estimate_ram_extended_exceeds_standard() -> None:
    """A larger-context preset estimates strictly more RAM than a smaller one."""
    spec = get_model("qwen3:4b")
    assert spec is not None
    standard = next(p for p in spec.presets if p.name == "Standard")
    extended = next(p for p in spec.presets if p.name == "Extended")
    assert estimate_ram_gb(spec, extended) > estimate_ram_gb(spec, standard)


def test_preset_fits_boundaries() -> None:
    """preset_fits returns True with ample RAM and False when starved."""
    spec = get_model("qwen3:4b")
    assert spec is not None
    preset = spec.presets[0]
    assert preset_fits(spec, preset, 16.0) is True
    assert preset_fits(spec, preset, 1.0) is False


def test_recommend_model_at_various_ram() -> None:
    """Recommends qwen3:4b when it fits and a small model when RAM is tight."""
    assert RECOMMENDED_TAG == "qwen3:4b"
    assert recommend_model(16.0) == "qwen3:4b"
    # qwen3:4b's minimum RAM is exactly 4 GB, so it still fits at 4.
    assert recommend_model(4.0) == "qwen3:4b"
    # Below qwen3:4b's minimum, the smallest fitting model is chosen.
    small = recommend_model(3.0)
    assert small == "qwen3:1.7b"
    small_spec = get_model(small)
    assert small_spec is not None
    assert small_spec.min_ram_gb <= 3.0


def test_models_view_flags_at_16gb() -> None:
    """installed / recommended / fits flags and preset estimates are correct."""
    view = models_view(16.0, ["qwen3:4b"])
    by_tag = {d["tag"]: d for d in view}

    # Hidden model excluded by default.
    assert "qwen3.5:4b" not in by_tag

    q4 = by_tag["qwen3:4b"]
    assert q4["installed"] is True
    assert q4["recommended"] is True
    assert q4["fits"] is True
    assert q4["default_preset"] == "Standard"

    q8 = by_tag["qwen3:8b"]
    assert q8["installed"] is False
    assert q8["recommended"] is False
    assert q8["fits"] is True  # min_ram 8 <= 16

    spec = get_model("qwen3:4b")
    assert spec is not None
    assert len(q4["presets"]) == len(spec.presets)
    for preset_view, spec_preset in zip(q4["presets"], spec.presets):
        assert preset_view["name"] == spec_preset.name
        expected_est = estimate_ram_gb(spec, spec_preset)
        assert preset_view["est_ram_gb"] == expected_est
        assert preset_view["fits"] == (expected_est <= 16.0)


def test_models_view_fit_false_when_constrained() -> None:
    """A model whose min RAM exceeds free RAM is marked as not fitting."""
    view = models_view(5.0, [])
    by_tag = {d["tag"]: d for d in view}
    assert by_tag["qwen3:14b"]["fits"] is False  # min_ram 11 > 5
    assert by_tag["qwen3:14b"]["installed"] is False
    # qwen3:4b (min_ram 4) still fits and is recommended at 5 GB.
    assert by_tag["qwen3:4b"]["recommended"] is True


def test_models_view_include_hidden() -> None:
    """include_hidden surfaces the experimental hidden model."""
    view = models_view(16.0, [], include_hidden=True)
    tags = {d["tag"] for d in view}
    assert "qwen3.5:4b" in tags


def test_list_models_excludes_hidden_by_default() -> None:
    """list_models hides qwen3.5:4b unless include_hidden is set."""
    visible = [m.tag for m in list_models(include_hidden=False)]
    assert "qwen3.5:4b" not in visible
    assert len(visible) == 5

    everything = [m.tag for m in list_models(include_hidden=True)]
    assert "qwen3.5:4b" in everything
    assert len(everything) == 6


def test_list_models_ordered_by_tier() -> None:
    """list_models returns specs in TIER_ORDER order."""
    specs = list_models(include_hidden=True)
    tier_indices = [TIER_ORDER.index(spec.tier) for spec in specs]
    assert tier_indices == sorted(tier_indices)
