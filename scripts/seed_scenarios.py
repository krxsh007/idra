from __future__ import annotations

import asyncio
from typing import Any

from app.core.config import settings
from app.core.logging import logger, setup_logging
from app.db.models.enums import (
    DisasterType,
    EventStatus,
    Provenance,
    ReportSource,
    SeverityLevel,
)
from app.db.models.events import DisasterEvent, HazardZone, IncidentReport
from geoalchemy2.functions import ST_GeomFromText, ST_MakePoint, ST_SetSRID
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def get_scenario_definitions() -> list[dict[str, Any]]:
    """Return the three canonical M13 disaster scenarios within Chennai Core BBox."""
    return [
        {
            "key": "chennai_flood",
            "name": "Scenario 1: Chennai Adyar & Kotturpuram Monsoon Flood",
            "disaster_type": DisasterType.FLOOD,
            "epicenter": {"lon": 80.2450, "lat": 13.0150},
            "radius_m": 4000,
            "description": (
                "Severe northeast monsoon deluge causing Adyar river overflow across "
                "Kotturpuram, Saidapet, and Velachery low-lying residential sectors."
            ),
            "hazard_zones": [
                {
                    "label": "Kotturpuram Riverbank Overflow Zone",
                    "hazard_type": DisasterType.FLOOD,
                    "severity": SeverityLevel.SEVERE,
                    "is_impassable": True,
                    "coordinates": [
                        [
                            [80.240, 13.012],
                            [80.248, 13.012],
                            [80.248, 13.018],
                            [80.240, 13.018],
                            [80.240, 13.012],
                        ]
                    ],
                },
                {
                    "label": "Saidapet Bridge Submergence Corridor",
                    "hazard_type": DisasterType.FLOOD,
                    "severity": SeverityLevel.SEVERE,
                    "is_impassable": True,
                    "coordinates": [
                        [
                            [80.220, 13.018],
                            [80.230, 13.018],
                            [80.230, 13.025],
                            [80.220, 13.025],
                            [80.220, 13.018],
                        ]
                    ],
                },
                {
                    "label": "Velachery 100ft Road Waterlogging",
                    "hazard_type": DisasterType.FLOOD,
                    "severity": SeverityLevel.HIGH,
                    "is_impassable": True,
                    "coordinates": [
                        [
                            [80.215, 12.975],
                            [80.225, 12.975],
                            [80.225, 12.985],
                            [80.215, 12.985],
                            [80.215, 12.975],
                        ]
                    ],
                },
                {
                    "label": "Turnbulls Road Secondary Inundation",
                    "hazard_type": DisasterType.FLOOD,
                    "severity": SeverityLevel.MODERATE,
                    "is_impassable": False,
                    "coordinates": [
                        [
                            [80.248, 13.020],
                            [80.255, 13.020],
                            [80.255, 13.026],
                            [80.248, 13.026],
                            [80.248, 13.020],
                        ]
                    ],
                },
            ],
            "reports": [
                {
                    "lon": 80.2420 + (i % 5) * 0.0015,
                    "lat": 13.0130 + (i // 5) * 0.0015,
                    "casualties_reported": i < 3,
                    "people_affected": 15 + (i * 5),
                    "body": (
                        f"Flood sector report #{i + 1}: Chest-deep water in ground-floor homes; "
                        f"residents stranded on rooftops awaiting boat extraction."
                    ),
                }
                for i in range(16)
            ],
        },
        {
            "key": "coastal_cyclone",
            "name": "Scenario 2: Marina & Mylapore Severe Coastal Cyclone",
            "disaster_type": DisasterType.CYCLONE,
            "epicenter": {"lon": 80.2750, "lat": 13.0450},
            "radius_m": 4500,
            "description": (
                "Category-3 coastal cyclone landfall with 130 km/h gale winds, storm surge "
                "along Marina Beach foreshore, and downed high-tension transmission lines."
            ),
            "hazard_zones": [
                {
                    "label": "Marina Foreshore Storm Surge Zone",
                    "hazard_type": DisasterType.CYCLONE,
                    "severity": SeverityLevel.SEVERE,
                    "is_impassable": True,
                    "coordinates": [
                        [
                            [80.275, 13.035],
                            [80.285, 13.035],
                            [80.285, 13.055],
                            [80.275, 13.055],
                            [80.275, 13.035],
                        ]
                    ],
                },
                {
                    "label": "Santhome High Road Uprooted Tree Blockade",
                    "hazard_type": DisasterType.CYCLONE,
                    "severity": SeverityLevel.HIGH,
                    "is_impassable": True,
                    "coordinates": [
                        [
                            [80.270, 13.028],
                            [80.278, 13.028],
                            [80.278, 13.034],
                            [80.270, 13.034],
                            [80.270, 13.028],
                        ]
                    ],
                },
                {
                    "label": "Royapettah Power Grid Failure Perimeter",
                    "hazard_type": DisasterType.CYCLONE,
                    "severity": SeverityLevel.HIGH,
                    "is_impassable": False,
                    "coordinates": [
                        [
                            [80.260, 13.050],
                            [80.268, 13.050],
                            [80.268, 13.058],
                            [80.260, 13.058],
                            [80.260, 13.050],
                        ]
                    ],
                },
                {
                    "label": "Kasimedu Fishing Harbour Surge",
                    "hazard_type": DisasterType.CYCLONE,
                    "severity": SeverityLevel.SEVERE,
                    "is_impassable": True,
                    "coordinates": [
                        [
                            [80.290, 13.120],
                            [80.298, 13.120],
                            [80.298, 13.130],
                            [80.290, 13.130],
                            [80.290, 13.120],
                        ]
                    ],
                },
            ],
            "reports": [
                {
                    "lon": 80.2710 + (i % 5) * 0.0012,
                    "lat": 13.0380 + (i // 5) * 0.0020,
                    "casualties_reported": i < 2,
                    "people_affected": 20 + (i * 4),
                    "body": (
                        f"Cyclone incident report #{i + 1}: Severe wind damage to coastal "
                        f"settlements and fallen electrical poles blocking access roads."
                    ),
                }
                for i in range(15)
            ],
        },
        {
            "key": "building_collapse",
            "name": "Scenario 3: T. Nagar Commercial Structural Collapse",
            "disaster_type": DisasterType.EARTHQUAKE,
            "epicenter": {"lon": 80.2337, "lat": 13.0418},
            "radius_m": 2500,
            "description": (
                "Localized seismic tremor and multi-storey commercial building collapse "
                "near Usman Road, T. Nagar with trapped occupants and debris blockage."
            ),
            "hazard_zones": [
                {
                    "label": "Usman Road Core Collapse Debris Zone",
                    "hazard_type": DisasterType.EARTHQUAKE,
                    "severity": SeverityLevel.SEVERE,
                    "is_impassable": True,
                    "coordinates": [
                        [
                            [80.231, 13.039],
                            [80.236, 13.039],
                            [80.236, 13.044],
                            [80.231, 13.044],
                            [80.231, 13.039],
                        ]
                    ],
                },
                {
                    "label": "Pondy Bazaar Structural Instability Sector",
                    "hazard_type": DisasterType.EARTHQUAKE,
                    "severity": SeverityLevel.HIGH,
                    "is_impassable": True,
                    "coordinates": [
                        [
                            [80.236, 13.038],
                            [80.241, 13.038],
                            [80.241, 13.043],
                            [80.236, 13.043],
                            [80.236, 13.038],
                        ]
                    ],
                },
                {
                    "label": "North Usman Flyover Inspection Closure",
                    "hazard_type": DisasterType.EARTHQUAKE,
                    "severity": SeverityLevel.MODERATE,
                    "is_impassable": True,
                    "coordinates": [
                        [
                            [80.230, 13.045],
                            [80.235, 13.045],
                            [80.235, 13.050],
                            [80.230, 13.050],
                            [80.230, 13.045],
                        ]
                    ],
                },
                {
                    "label": "Mambalam Station Approach Dust & Debris Perimeter",
                    "hazard_type": DisasterType.EARTHQUAKE,
                    "severity": SeverityLevel.MODERATE,
                    "is_impassable": False,
                    "coordinates": [
                        [
                            [80.225, 13.036],
                            [80.230, 13.036],
                            [80.230, 13.041],
                            [80.225, 13.041],
                            [80.225, 13.036],
                        ]
                    ],
                },
            ],
            "reports": [
                {
                    "lon": 80.2315 + (i % 5) * 0.0010,
                    "lat": 13.0395 + (i // 5) * 0.0012,
                    "casualties_reported": i < 5,
                    "people_affected": 10 + (i * 3),
                    "body": (
                        f"Collapse sector report #{i + 1}: Persons reported trapped beneath "
                        f"masonry rubble; heavy cutting equipment and trauma ambulances needed."
                    ),
                }
                for i in range(15)
            ],
        },
    ]


async def seed_scenarios(db: AsyncSession) -> int:
    """Idempotently seed all three M13 scenarios with hazard polygons and incident reports."""
    scenarios = get_scenario_definitions()
    created_events = 0

    for sc in scenarios:
        # Remove existing scenario with same name to keep seeding idempotent
        existing_stmt = select(DisasterEvent).where(DisasterEvent.name == sc["name"])
        res = await db.execute(existing_stmt)
        for old_ev in res.scalars().all():
            await db.execute(delete(DisasterEvent).where(DisasterEvent.id == old_ev.id))

        ep = sc["epicenter"]
        event = DisasterEvent(
            name=sc["name"],
            disaster_type=sc["disaster_type"],
            status=EventStatus.ACTIVE,
            epicenter=ST_SetSRID(ST_MakePoint(ep["lon"], ep["lat"]), 4326),
            radius_m=sc["radius_m"],
            description=sc["description"],
        )
        db.add(event)
        await db.flush()

        for hz in sc["hazard_zones"]:
            ring = hz["coordinates"][0]
            wkt_coords = ", ".join(f"{pt[0]} {pt[1]}" for pt in ring)
            wkt_poly = f"SRID=4326;POLYGON(({wkt_coords}))"
            db.add(
                HazardZone(
                    event_id=event.id,
                    label=hz["label"],
                    hazard_type=hz["hazard_type"],
                    severity=hz["severity"],
                    geom=ST_GeomFromText(wkt_poly),
                    is_impassable=hz["is_impassable"],
                )
            )

        for rep in sc["reports"]:
            db.add(
                IncidentReport(
                    event_id=event.id,
                    source=ReportSource.SEED,
                    body=rep["body"],
                    location=ST_SetSRID(ST_MakePoint(rep["lon"], rep["lat"]), 4326),
                    casualties_reported=rep["casualties_reported"],
                    people_affected=rep["people_affected"],
                    data_provenance=Provenance.SYNTHETIC,
                )
            )

        created_events += 1

    await db.commit()
    logger.info("scenarios_seeded_successfully", scenario_count=created_events)
    return created_events


async def main() -> None:
    setup_logging("INFO")
    logger.info("seeding_m13_scenarios")
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async with session_maker() as session:
        await seed_scenarios(session)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
