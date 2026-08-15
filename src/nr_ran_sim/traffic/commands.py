"""Typed commands are the only supported mutation boundary for bearer queues."""

from __future__ import annotations

from dataclasses import dataclass

from nr_ran_sim.domain.identifiers import PacketId
from nr_ran_sim.domain.packets import PacketRecord


@dataclass(frozen=True, slots=True)
class EnqueuePacket:
    tick: int
    packet: PacketRecord


@dataclass(frozen=True, slots=True)
class ApplyService:
    tick: int
    capacity_bits: int


@dataclass(frozen=True, slots=True)
class ExpirePacket:
    tick: int
    packet_id: PacketId


@dataclass(frozen=True, slots=True)
class FailPacket:
    tick: int
    packet_id: PacketId


@dataclass(frozen=True, slots=True)
class CensorQueue:
    tick: int


QueueCommand = EnqueuePacket | ApplyService | ExpirePacket | FailPacket | CensorQueue
