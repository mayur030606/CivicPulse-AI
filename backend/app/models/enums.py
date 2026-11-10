import enum


class Priority(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class Severity(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class ComplaintCategory(str, enum.Enum):
    pothole = "pothole"
    garbage = "garbage"
    water_leakage = "water_leakage"
    streetlight = "streetlight"
    traffic_accident = "traffic_accident"
    road_blockage = "road_blockage"
    drainage = "drainage"
    other = "other"


class IncidentType(str, enum.Enum):
    accident = "accident"
    congestion = "congestion"
    roadblock = "roadblock"
    flooding = "flooding"
    infrastructure = "infrastructure"
    other = "other"


class IncidentStatus(str, enum.Enum):
    """Canonical incident workflow values.

    The live ``incidents.status`` column is a plain ``VARCHAR`` and currently
    stores title-case values. Keeping the allow-list here (rather than in the
    route layer) keeps request validation and future workflow code in sync.
    """

    submitted = "Submitted"
    in_progress = "In Progress"
    resolved = "Resolved"
    closed = "Closed"


class UserRole(str, enum.Enum):
    """Roles supported by the administrator authentication foundation."""

    admin = "admin"
    dispatcher = "dispatcher"
    viewer = "viewer"
