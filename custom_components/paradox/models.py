"""Paradox models."""
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class SupportedModuleInfo:
    """Represent a module."""
    default_domain: List
    supported_domains: List


@dataclass
class DiscoveredModuleInfo:
    """Represent discovered module."""
    name: str
    model: str
    serial: str
    host: str
    port: int
    mac: str


@dataclass
class DeviceInfo:
    """Represent device information."""
    manufacturer: str
    model: str
    name: str
    sw_version: str
    serial: str
    mac: Optional[str] = None
