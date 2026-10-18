from __future__ import annotations

import asyncio
from typing import Any

from app.core.config import settings
from app.core.logging import logger, setup_logging
from app.db.models.enums import FacilityType, Provenance
from app.db.models.facilities import Facility
from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

FACILITIES_SEED: list[dict[str, Any]] = [
    # Hospitals
    {
        "external_ref": "HOSP-001",
        "name": "Rajiv Gandhi Government General Hospital (RGGGH)",
        "facility_type": FacilityType.HOSPITAL,
        "lon": 80.279,
        "lat": 13.081,
        "address": "EVR Periyar Salai, Park Town, Chennai",
        "total_capacity": 2500,
        "current_occupancy": 1800,
        "specializations": ["Trauma", "ICU", "Burn Unit", "Emergency Surgery"],
        "has_generator": True,
        "wheelchair_access": True,
        "contact_phone": "+91-44-25305000",
        "is_operational": True,
    },
    {
        "external_ref": "HOSP-002",
        "name": "Government Stanley Hospital",
        "facility_type": FacilityType.HOSPITAL,
        "lon": 80.285,
        "lat": 13.105,
        "address": "Old Jail Rd, Royapuram, Chennai",
        "total_capacity": 1800,
        "current_occupancy": 1200,
        "specializations": ["General Surgery", "Pediatrics", "Trauma"],
        "has_generator": True,
        "wheelchair_access": True,
        "contact_phone": "+91-44-25281351",
        "is_operational": True,
    },
    {
        "external_ref": "HOSP-003",
        "name": "Kilpauk Medical College Hospital (KMCH)",
        "facility_type": FacilityType.HOSPITAL,
        "lon": 80.242,
        "lat": 13.078,
        "address": "EVR Periyar Salai, Kilpauk, Chennai",
        "total_capacity": 1200,
        "current_occupancy": 950,
        "specializations": ["Burns", "Plastic Surgery", "Trauma"],
        "has_generator": True,
        "wheelchair_access": True,
        "contact_phone": "+91-44-28364951",
        "is_operational": True,
    },
    {
        "external_ref": "HOSP-004",
        "name": "Government Hospital for Women and Children",
        "facility_type": FacilityType.HOSPITAL,
        "lon": 80.258,
        "lat": 13.072,
        "address": "Pantheon Rd, Egmore, Chennai",
        "total_capacity": 800,
        "current_occupancy": 600,
        "specializations": ["Maternity", "Pediatric ICU", "Neonatal"],
        "has_generator": True,
        "wheelchair_access": True,
        "contact_phone": "+91-44-28191982",
        "is_operational": True,
    },
    {
        "external_ref": "HOSP-005",
        "name": "Fortis Malar Hospital",
        "facility_type": FacilityType.HOSPITAL,
        "lon": 80.256,
        "lat": 13.007,
        "address": "Gandhi Nagar, Adyar, Chennai",
        "total_capacity": 250,
        "current_occupancy": 180,
        "specializations": ["Cardiac", "Critical Care"],
        "has_generator": True,
        "wheelchair_access": True,
        "contact_phone": "+91-44-42892222",
        "is_operational": True,
    },
    {
        "external_ref": "HOSP-006",
        "name": "Apollo Hospitals Greams Road",
        "facility_type": FacilityType.HOSPITAL,
        "lon": 80.251,
        "lat": 13.058,
        "address": "Greams Lane, Thousand Lights, Chennai",
        "total_capacity": 600,
        "current_occupancy": 490,
        "specializations": ["Multispecialty", "Trauma", "Cardiology"],
        "has_generator": True,
        "wheelchair_access": True,
        "contact_phone": "+91-44-28290200",
        "is_operational": True,
    },
    {
        "external_ref": "HOSP-007",
        "name": "MIOT International",
        "facility_type": FacilityType.HOSPITAL,
        "lon": 80.181,
        "lat": 13.024,
        "address": "Mount-Poonamallee Rd, Manapakkam, Chennai",
        "total_capacity": 1000,
        "current_occupancy": 700,
        "specializations": ["Orthopedics", "Trauma", "Emergency Care"],
        "has_generator": True,
        "wheelchair_access": True,
        "contact_phone": "+91-44-42002288",
        "is_operational": True,
    },
    # Shelters
    {
        "external_ref": "SHELT-001",
        "name": "Ripon Building Community Relief Center",
        "facility_type": FacilityType.SHELTER,
        "lon": 80.272,
        "lat": 13.082,
        "address": "Sydenhams Rd, Periamet, Chennai",
        "total_capacity": 500,
        "current_occupancy": 80,
        "specializations": ["Emergency Food", "Potable Water", "First Aid"],
        "has_generator": True,
        "wheelchair_access": True,
        "contact_phone": "+91-44-25619200",
        "is_operational": True,
    },
    {
        "external_ref": "SHELT-002",
        "name": "Guindy Higher Secondary School Camp",
        "facility_type": FacilityType.SHELTER,
        "lon": 80.215,
        "lat": 13.010,
        "address": "Guindy Industrial Estate, Chennai",
        "total_capacity": 400,
        "current_occupancy": 150,
        "specializations": ["Family Dormitory", "Community Kitchen"],
        "has_generator": True,
        "wheelchair_access": False,
        "contact_phone": "+91-44-22500112",
        "is_operational": True,
    },
    {
        "external_ref": "SHELT-003",
        "name": "Velachery Corporation Relief Hall",
        "facility_type": FacilityType.SHELTER,
        "lon": 80.218,
        "lat": 12.972,
        "address": "Velachery Main Rd, Chennai",
        "total_capacity": 600,
        "current_occupancy": 280,
        "specializations": ["Boat Staging", "Potable Water RO", "Medical Post"],
        "has_generator": True,
        "wheelchair_access": True,
        "contact_phone": "+91-44-22441188",
        "is_operational": True,
    },
    {
        "external_ref": "SHELT-004",
        "name": "Besant Nagar Community Shelter",
        "facility_type": FacilityType.SHELTER,
        "lon": 80.268,
        "lat": 13.002,
        "address": "2nd Avenue, Besant Nagar, Chennai",
        "total_capacity": 350,
        "current_occupancy": 40,
        "specializations": ["Emergency Shelter", "Sanitation Kits"],
        "has_generator": False,
        "wheelchair_access": True,
        "contact_phone": "+91-44-24911223",
        "is_operational": True,
    },
    {
        "external_ref": "SHELT-005",
        "name": "Koyambedu Wholesale Market Staging Center",
        "facility_type": FacilityType.SHELTER,
        "lon": 80.192,
        "lat": 13.069,
        "address": "Koyambedu Market Complex, Chennai",
        "total_capacity": 800,
        "current_occupancy": 120,
        "specializations": ["Mass Staging", "Dry Rations Depot", "Helipad Access"],
        "has_generator": True,
        "wheelchair_access": True,
        "contact_phone": "+91-44-24795566",
        "is_operational": True,
    },
    {
        "external_ref": "SHELT-006",
        "name": "Saidapet Model Higher Secondary School",
        "facility_type": FacilityType.SHELTER,
        "lon": 80.222,
        "lat": 13.023,
        "address": "Jones Rd, Saidapet, Chennai",
        "total_capacity": 450,
        "current_occupancy": 110,
        "specializations": ["Temporary Dormitory", "Sanitation Units"],
        "has_generator": True,
        "wheelchair_access": False,
        "contact_phone": "+91-44-24351122",
        "is_operational": True,
    },
    {
        "external_ref": "SHELT-007",
        "name": "T Nagar Corporation Ground Camp",
        "facility_type": FacilityType.SHELTER,
        "lon": 80.233,
        "lat": 13.042,
        "address": "Prakasam Rd, T Nagar, Chennai",
        "total_capacity": 500,
        "current_occupancy": 90,
        "specializations": ["Emergency Tents", "Drinking Water Tankers"],
        "has_generator": True,
        "wheelchair_access": True,
        "contact_phone": "+91-44-28151133",
        "is_operational": True,
    },
]


async def seed_facilities(db: AsyncSession) -> int:
    """Insert or update seed facilities idempotently on external_ref."""
    inserted = 0
    updated = 0

    for item in FACILITIES_SEED:
        stmt = select(Facility).where(Facility.external_ref == item["external_ref"])
        res = await db.execute(stmt)
        fac = res.scalar_one_or_none()

        geom_point = from_shape(Point(item["lon"], item["lat"]), srid=4326)

        if fac:
            fac.name = item["name"]
            fac.facility_type = item["facility_type"]
            fac.location = geom_point
            fac.address = item["address"]
            fac.total_capacity = item["total_capacity"]
            fac.current_occupancy = item["current_occupancy"]
            fac.specializations = item["specializations"]
            fac.has_generator = item["has_generator"]
            fac.wheelchair_access = item["wheelchair_access"]
            fac.contact_phone = item["contact_phone"]
            fac.is_operational = item["is_operational"]
            updated += 1
        else:
            fac = Facility(
                external_ref=item["external_ref"],
                name=item["name"],
                facility_type=item["facility_type"],
                location=geom_point,
                address=item["address"],
                total_capacity=item["total_capacity"],
                current_occupancy=item["current_occupancy"],
                specializations=item["specializations"],
                has_generator=item["has_generator"],
                wheelchair_access=item["wheelchair_access"],
                contact_phone=item["contact_phone"],
                is_operational=item["is_operational"],
                location_provenance=Provenance.REAL,
                capacity_provenance=Provenance.SIMULATED,
            )
            db.add(fac)
            inserted += 1

    await db.commit()
    logger.info("facilities_seed_completed", inserted=inserted, updated=updated)
    return inserted + updated


async def main() -> None:
    setup_logging("INFO")
    logger.info("seeding_facilities_for_chennai")
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async with session_maker() as session:
        await seed_facilities(session)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
