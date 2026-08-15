"""Strict human-authored scenario models.

These models validate structure and local constraints. Unit conversion and standards-domain
cross-checks occur in :mod:`nr_ran_sim.config.normalize`.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

Identifier = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9-]{0,63}$")]
PositiveDecimal = Annotated[Decimal, Field(gt=0)]
NonNegativeDecimal = Annotated[Decimal, Field(ge=0)]


class FrozenStrictModel(BaseModel):
    """Fail-closed base model used for all configuration nodes."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
    )


class QuantityInput(FrozenStrictModel):
    value: Decimal
    unit: str = Field(min_length=1, max_length=16)

    @field_validator("value")
    @classmethod
    def finite_value(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("quantity magnitude must be finite")
        return value


class SimulationConfig(FrozenStrictModel):
    warmup: QuantityInput
    measurement: QuantityInput
    drain: QuantityInput


class RadioConfig(FrozenStrictModel):
    direction: Literal["downlink"]
    frequency_range: Literal["FR1", "FR2-1"]
    carrier_frequency: QuantityInput
    channel_bandwidth: QuantityInput
    subcarrier_spacing: QuantityInput
    cyclic_prefix: Literal["normal"]
    layers: Literal[1]
    cqi_table: Literal["table1"]
    mcs_table: Literal["table1"]
    target_bler: Decimal
    implementation_margin: QuantityInput
    data_re_overhead_fraction: Decimal = Field(ge=0, lt=1)

    @field_validator("target_bler")
    @classmethod
    def baseline_bler(cls, value: Decimal) -> Decimal:
        if value != Decimal("0.1"):
            raise ValueError("Tier A target_bler must equal 0.1")
        return value


class ModelConfig(FrozenStrictModel):
    fidelity_profile: Literal[
        "tier-a-fr1-static-v1",
        "tier-b-fr1-dynamic-v1",
        "tier-b-fr2-availability-v1",
    ]
    propagation: Literal["3gpp-tr38901-r18-v18.1.0"]
    los_state: Literal["explicit", "probability_static"]
    shadowing: Literal["off", "independent_static", "correlated_dynamic"]
    interference: Literal[
        "noise_limited-v1",
        "full_buffer_reuse1-v1",
        "activity-coupled-reuse1-v1",
    ]
    link_adaptation: Literal["analytical-awgn-gap-v1"]


class PositionConfig(FrozenStrictModel):
    x: QuantityInput
    y: QuantityInput
    z: QuantityInput


class CellConfig(FrozenStrictModel):
    position: PositionConfig
    transmit_power: QuantityInput
    antenna_gain: QuantityInput
    miscellaneous_loss: QuantityInput


class UniformRectanglePlacement(FrozenStrictModel):
    mode: Literal["uniform_rectangle"]
    x_min: QuantityInput
    x_max: QuantityInput
    y_min: QuantityInput
    y_max: QuantityInput
    height: QuantityInput
    minimum_2d_distance: QuantityInput | None = None
    attempt_budget: int = Field(default=10_000, gt=0)


class ExplicitPlacement(FrozenStrictModel):
    mode: Literal["explicit"]
    positions: tuple[PositionConfig, ...] = Field(min_length=1)
    minimum_2d_distance: QuantityInput | None = None


PlacementConfig = Annotated[
    UniformRectanglePlacement | ExplicitPlacement,
    Field(discriminator="mode"),
]


class UEGroupConfig(FrozenStrictModel):
    count: int = Field(gt=0)
    placement: PlacementConfig
    receiver_noise_figure: QuantityInput
    antenna_gain: QuantityInput
    penetration_loss: QuantityInput = Field(
        default_factory=lambda: QuantityInput(value=Decimal(0), unit="dB")
    )
    explicit_link_states: dict[Identifier, tuple[Literal["los", "nlos"], ...]] | None = None
    bearers: tuple[Identifier, ...] = Field(min_length=1)


class PropagationEnvironmentConfig(FrozenStrictModel):
    average_building_height: QuantityInput
    average_street_width: QuantityInput


class TopologyConfig(FrozenStrictModel):
    scenario: Literal["rma", "uma", "umi_street_canyon"]
    coordinate_system: Literal["local-cartesian"]
    propagation_environment: PropagationEnvironmentConfig | None = None
    cells: dict[Identifier, CellConfig] = Field(min_length=1)
    ue_groups: dict[Identifier, UEGroupConfig] = Field(min_length=1)


class PeriodicSource(FrozenStrictModel):
    type: Literal["periodic"]
    interval: QuantityInput
    initial_offset: QuantityInput | None = None


class PoissonSource(FrozenStrictModel):
    type: Literal["poisson"]
    mean_interarrival: QuantityInput


class BoundedUniformSource(FrozenStrictModel):
    type: Literal["bounded_uniform"]
    minimum_interarrival: QuantityInput
    maximum_interarrival: QuantityInput


SourceConfig = Annotated[
    PeriodicSource | PoissonSource | BoundedUniformSource,
    Field(discriminator="type"),
]


class ConstantPacketSize(FrozenStrictModel):
    type: Literal["constant"]
    payload: QuantityInput


class UniformPacketSize(FrozenStrictModel):
    type: Literal["discrete_uniform"]
    minimum_payload: QuantityInput
    maximum_payload: QuantityInput


PacketSizeConfig = Annotated[
    ConstantPacketSize | UniformPacketSize,
    Field(discriminator="type"),
]


class QueueConfig(FrozenStrictModel):
    max_packets: int | None = Field(default=None, gt=0)
    max_payload: QuantityInput | None = None

    @model_validator(mode="after")
    def finite_capacity(self) -> QueueConfig:
        if self.max_packets is None and self.max_payload is None:
            raise ValueError("queue must define max_packets, max_payload, or both")
        return self


class TrafficProfileConfig(FrozenStrictModel):
    source: SourceConfig
    packet_size: PacketSizeConfig
    queue: QueueConfig
    deadline: QuantityInput | None
    qos_reference_5qi: int | None = Field(default=None, ge=1, le=255)


class SchedulerParameters(FrozenStrictModel):
    averaging_alpha: Decimal | None = Field(default=None, gt=0, le=1)
    initial_rate_floor: QuantityInput | None = None


class SchedulerConfig(FrozenStrictModel):
    policy: Literal["round-robin", "max-ci", "proportional-fair"]
    parameters: SchedulerParameters = Field(default_factory=SchedulerParameters)

    @model_validator(mode="after")
    def policy_parameters(self) -> SchedulerConfig:
        has_pf_parameters = (
            self.parameters.averaging_alpha is not None
            or self.parameters.initial_rate_floor is not None
        )
        if self.policy == "proportional-fair" and (
            self.parameters.averaging_alpha is None or self.parameters.initial_rate_floor is None
        ):
            raise ValueError("proportional-fair requires averaging_alpha and initial_rate_floor")
        if self.policy != "proportional-fair" and has_pf_parameters:
            raise ValueError(f"{self.policy} accepts no tuning parameters in Tier A")
        return self


class ScenarioConfig(FrozenStrictModel):
    schema_version: Literal["1.0"]
    scenario_id: Identifier
    description: str = Field(min_length=1, max_length=500)
    simulation: SimulationConfig
    radio: RadioConfig
    models: ModelConfig
    topology: TopologyConfig
    traffic_profiles: dict[Identifier, TrafficProfileConfig] = Field(min_length=1)
    scheduler: SchedulerConfig
    extensions: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def references_exist(self) -> ScenarioConfig:
        profiles = set(self.traffic_profiles)
        for group_id, group in self.topology.ue_groups.items():
            missing = sorted(set(group.bearers) - profiles)
            if missing:
                raise ValueError(f"UE group {group_id!r} references unknown bearers: {missing}")
            if isinstance(group.placement, ExplicitPlacement) and (
                len(group.placement.positions) != group.count
            ):
                raise ValueError(
                    f"UE group {group_id!r} explicit placement must contain exactly "
                    f"{group.count} positions"
                )
            states = group.explicit_link_states
            if self.models.los_state == "explicit":
                if states is None:
                    raise ValueError(
                        f"UE group {group_id!r} requires explicit_link_states when "
                        "models.los_state is explicit"
                    )
                expected_cells = set(self.topology.cells)
                if set(states) != expected_cells:
                    raise ValueError(
                        f"UE group {group_id!r} explicit_link_states must contain exactly "
                        f"the configured cells: {sorted(expected_cells)}"
                    )
                for cell_id, link_states in states.items():
                    if len(link_states) != group.count:
                        raise ValueError(
                            f"UE group {group_id!r} states for cell {cell_id!r} must "
                            f"contain exactly {group.count} entries"
                        )
            elif states is not None:
                raise ValueError(
                    f"UE group {group_id!r} must omit explicit_link_states when "
                    "models.los_state is probability_static"
                )
        if self.topology.scenario == "rma" and self.topology.propagation_environment is None:
            raise ValueError("RMa requires topology.propagation_environment")
        if self.topology.scenario != "rma" and self.topology.propagation_environment is not None:
            raise ValueError("propagation_environment is only valid for RMa in Tier A")
        return self
