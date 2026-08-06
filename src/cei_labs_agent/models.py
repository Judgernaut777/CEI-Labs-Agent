"""Static model registry, RAM estimation, and recommendation helpers.

The registry describes every Ollama model the agent knows how to run, along
with the presets (context/prediction/thinking) that are safe for each. RAM
estimates and fit checks drive the UI's model/preset pickers.
"""

from __future__ import annotations

from pydantic import BaseModel

__all__ = [
    "Preset",
    "ModelSpec",
    "TIER_ORDER",
    "REGISTRY",
    "RECOMMENDED_TAG",
    "list_models",
    "get_model",
    "estimate_ram_gb",
    "preset_fits",
    "recommend_model",
    "models_view",
]


class Preset(BaseModel):
    """A named runtime preset for a model.

    Attributes:
        name: Human-readable preset name (e.g. ``Standard``).
        num_ctx: Context window size in tokens.
        num_predict: Maximum tokens to generate per turn.
        think: Whether the model's thinking mode is enabled.
    """

    name: str
    num_ctx: int
    num_predict: int
    think: bool


class ModelSpec(BaseModel):
    """Static description of a supported model.

    Attributes:
        tag: Ollama pull tag (registry key).
        display_name: Friendly name shown in the UI.
        tier: Capability tier (see :data:`TIER_ORDER`).
        download_gb: Approximate download size in gigabytes.
        min_ram_gb: Minimum system RAM (GB) required to run the model.
        native_max_ctx: Largest context window the model natively supports.
        kv_bytes_per_token: Bytes of KV cache consumed per context token.
        thinking_capable: Whether the model supports a thinking mode.
        hidden: Whether the model is hidden from default listings.
        presets: Available presets for this model.
        default_preset: Name of the default preset.
        notes: Free-form guidance about the model.
    """

    tag: str
    display_name: str
    tier: str
    download_gb: float
    min_ram_gb: float
    native_max_ctx: int
    kv_bytes_per_token: int
    thinking_capable: bool
    hidden: bool = False
    presets: list[Preset]
    default_preset: str
    notes: str = ""


TIER_ORDER: list[str] = [
    "featherweight",
    "default",
    "default-alt",
    "heavyweight",
    "max",
    "experimental",
]


REGISTRY: dict[str, ModelSpec] = {
    "qwen3:1.7b": ModelSpec(
        tag="qwen3:1.7b",
        display_name="Qwen3 1.7B",
        tier="featherweight",
        download_gb=1.4,
        min_ram_gb=3.0,
        native_max_ctx=40960,
        kv_bytes_per_token=30000,
        thinking_capable=False,
        hidden=False,
        presets=[Preset(name="Standard", num_ctx=8192, num_predict=640, think=False)],
        default_preset="Standard",
        notes="Fastest, weakest reasoning; last resort.",
    ),
    "qwen3:4b": ModelSpec(
        tag="qwen3:4b",
        display_name="Qwen3 4B",
        tier="default",
        download_gb=2.5,
        min_ram_gb=4.0,
        native_max_ctx=262144,
        kv_bytes_per_token=60000,
        thinking_capable=False,
        hidden=False,
        presets=[
            Preset(name="Standard", num_ctx=8192, num_predict=768, think=False),
            Preset(name="Extended", num_ctx=16384, num_predict=768, think=False),
        ],
        default_preset="Standard",
        notes="Recommended. Only measured option (JSON-parse 1.00).",
    ),
    "gemma4": ModelSpec(
        tag="gemma4",
        display_name="Gemma 4",
        tier="default-alt",
        download_gb=6.0,
        min_ram_gb=6.0,
        native_max_ctx=131072,
        kv_bytes_per_token=90000,
        thinking_capable=True,
        hidden=False,
        presets=[Preset(name="Standard", num_ctx=8192, num_predict=768, think=False)],
        default_preset="Standard",
        notes="Native tool-calling; model diversity. Thinking hard-disabled.",
    ),
    "qwen3:8b": ModelSpec(
        tag="qwen3:8b",
        display_name="Qwen3 8B",
        tier="heavyweight",
        download_gb=5.2,
        min_ram_gb=8.0,
        native_max_ctx=40960,
        kv_bytes_per_token=120000,
        thinking_capable=True,
        hidden=False,
        presets=[
            Preset(name="Standard", num_ctx=8192, num_predict=768, think=False),
            Preset(name="Extended", num_ctx=16384, num_predict=768, think=False),
        ],
        default_preset="Standard",
        notes="Stronger reasoning.",
    ),
    "qwen3:14b": ModelSpec(
        tag="qwen3:14b",
        display_name="Qwen3 14B",
        tier="max",
        download_gb=9.3,
        min_ram_gb=11.0,
        native_max_ctx=40960,
        kv_bytes_per_token=200000,
        thinking_capable=True,
        hidden=False,
        presets=[
            Preset(name="Standard", num_ctx=8192, num_predict=768, think=False),
            Preset(name="Reasoning", num_ctx=16384, num_predict=3072, think=True),
        ],
        default_preset="Standard",
        notes="Best quality; Reasoning preset for strong hardware only.",
    ),
    "qwen3.5:4b": ModelSpec(
        tag="qwen3.5:4b",
        display_name="Qwen3.5 4B",
        tier="experimental",
        download_gb=3.4,
        min_ram_gb=5.0,
        native_max_ctx=262144,
        kv_bytes_per_token=70000,
        thinking_capable=True,
        hidden=True,
        presets=[Preset(name="Standard", num_ctx=8192, num_predict=768, think=False)],
        default_preset="Standard",
        notes="Multimodal/hybrid-thinking; opt-in only if thinking-off proves reliable.",
    ),
    "MichelRosselli/bonsai-27b": ModelSpec(
        tag="MichelRosselli/bonsai-27b",
        display_name="Bonsai 27B (1-bit)",
        tier="experimental",
        # Unofficial Ollama upload of PrismML's 1-bit Q1_0_g128 build of
        # Qwen3.6-27B (HF: prism-ml/Bonsai-27B-gguf). Requires a recent
        # Ollama whose bundled llama.cpp has the Q1_0 hybrid-attention
        # kernels merged; older servers will fail to load it.
        download_gb=4.4,
        # Measured peak (weights + FP16 KV + runtime) is ~5.2 GB at 4K ctx
        # and ~5.6 GB at 10K ctx per the model card; 6 GB is the safe floor.
        min_ram_gb=6.0,
        native_max_ctx=262144,
        # Derived from the card's measured peaks: (5.6-5.2) GB over 4K-10K
        # ctx ~= 68 KB/token with an uncompressed KV cache (hybrid
        # attention keeps a full cache on only 16 of 64 layers).
        kv_bytes_per_token=68000,
        thinking_capable=True,
        hidden=True,
        presets=[Preset(name="Standard", num_ctx=8192, num_predict=768, think=False)],
        default_preset="Standard",
        notes=(
            "27B-class quality at a 4.4 GB pull, but 1-bit compression hits "
            "instruction following and multi-step tool use hardest (BFCL "
            "66.03 vs 80.00 FP16) -- exactly this agent's workload. "
            "MEASURED 2026-08-05 (MS-R1, CIX P1 aarch64 CPU-only, Ollama "
            "0.32.5, 3x10 temp-0 cases at this preset): action validity "
            "80.0% vs qwen3:14b's 100.0%, and ~5x slower wall-clock per "
            "call (81s vs 16s -- Q1_0 has no optimized ARM prompt-"
            "processing kernel). Fails the promotion bar (must beat "
            "qwen3:14b on action validity), so it stays hidden; the only "
            "remaining argument for it is footprint (4.4 GB vs 9.3 GB). "
            "Revisit only if a small-footprint tier becomes a requirement; "
            "re-run the eval on GPU then (validity is hardware-independent, "
            "speed is not). Format discipline was flawless (30/30 single "
            "well-formed JSON) -- both failures were wrong action CHOICE, "
            "so constrained decoding could narrow the gap."
        ),
    ),
}


RECOMMENDED_TAG = "qwen3:4b"

_TIER_INDEX: dict[str, int] = {tier: idx for idx, tier in enumerate(TIER_ORDER)}


def _tier_key(spec: ModelSpec) -> int:
    """Return a sort key placing ``spec`` in :data:`TIER_ORDER` order.

    Args:
        spec: The model specification.

    Returns:
        The tier's index, or a large value for unknown tiers.
    """
    return _TIER_INDEX.get(spec.tier, len(TIER_ORDER))


def list_models(include_hidden: bool = False) -> list[ModelSpec]:
    """List known models ordered by tier.

    Args:
        include_hidden: Whether to include hidden models.

    Returns:
        Model specifications ordered per :data:`TIER_ORDER`.
    """
    specs = [
        spec
        for spec in REGISTRY.values()
        if include_hidden or not spec.hidden
    ]
    return sorted(specs, key=_tier_key)


def get_model(tag: str) -> ModelSpec | None:
    """Look up a model by tag.

    Args:
        tag: The Ollama pull tag.

    Returns:
        The matching :class:`ModelSpec`, or ``None`` if unknown.
    """
    return REGISTRY.get(tag)


def estimate_ram_gb(spec: ModelSpec, preset: Preset) -> float:
    """Estimate peak RAM (GB) to run a model under a preset.

    The estimate is monotonic increasing in ``preset.num_ctx``.

    Args:
        spec: The model specification.
        preset: The preset to size for.

    Returns:
        Estimated RAM usage in gigabytes, rounded to one decimal.
    """
    return round(
        spec.download_gb * 1.1 + preset.num_ctx * spec.kv_bytes_per_token / 1e9,
        1,
    )


def preset_fits(spec: ModelSpec, preset: Preset, free_ram_gb: float) -> bool:
    """Report whether a preset fits within available RAM.

    Args:
        spec: The model specification.
        preset: The preset to check.
        free_ram_gb: Free system RAM in gigabytes.

    Returns:
        ``True`` when the estimated RAM usage fits.
    """
    return estimate_ram_gb(spec, preset) <= free_ram_gb


def recommend_model(free_ram_gb: float) -> str:
    """Recommend the best model tag for the available RAM.

    Prefers :data:`RECOMMENDED_TAG` when it fits, otherwise the smallest
    fitting non-hidden model, otherwise the smallest model overall.

    Args:
        free_ram_gb: Free system RAM in gigabytes.

    Returns:
        The recommended model tag.
    """
    visible = list_models(include_hidden=False)
    recommended = get_model(RECOMMENDED_TAG)
    if (
        recommended is not None
        and not recommended.hidden
        and recommended.min_ram_gb <= free_ram_gb
    ):
        return RECOMMENDED_TAG

    fitting = [spec for spec in visible if spec.min_ram_gb <= free_ram_gb]
    pool = fitting if fitting else visible
    smallest = min(pool, key=lambda spec: (spec.min_ram_gb, spec.download_gb))
    return smallest.tag


def models_view(
    free_ram_gb: float,
    local_tags: list[str],
    include_hidden: bool = False,
) -> list[dict]:
    """Build a UI-friendly view of all models with fit/install annotations.

    Args:
        free_ram_gb: Free system RAM in gigabytes.
        local_tags: Tags of models already pulled locally.
        include_hidden: Whether to include hidden models.

    Returns:
        A list of plain dicts (one per model, tier-ordered) carrying display
        metadata plus ``installed``/``recommended``/``fits`` flags and per-preset
        RAM estimates.
    """
    recommended_tag = recommend_model(free_ram_gb)
    local = set(local_tags)
    view: list[dict] = []
    for spec in list_models(include_hidden=include_hidden):
        presets = [
            {
                "name": preset.name,
                "num_ctx": preset.num_ctx,
                "num_predict": preset.num_predict,
                "think": preset.think,
                "est_ram_gb": estimate_ram_gb(spec, preset),
                "fits": preset_fits(spec, preset, free_ram_gb),
            }
            for preset in spec.presets
        ]
        view.append(
            {
                "tag": spec.tag,
                "display_name": spec.display_name,
                "tier": spec.tier,
                "download_gb": spec.download_gb,
                "min_ram_gb": spec.min_ram_gb,
                "native_max_ctx": spec.native_max_ctx,
                "thinking_capable": spec.thinking_capable,
                "hidden": spec.hidden,
                "notes": spec.notes,
                "installed": spec.tag in local,
                "recommended": spec.tag == recommended_tag,
                "fits": spec.min_ram_gb <= free_ram_gb,
                "default_preset": spec.default_preset,
                "presets": presets,
            }
        )
    return view
