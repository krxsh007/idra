from __future__ import annotations

import asyncio

from app.core.config import settings
from app.core.logging import logger, setup_logging
from app.db.models.enums import FacilityType, Provenance, ResourceKind
from app.db.models.facilities import Facility, Resource
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

RESOURCES_TEMPLATE = [
    (ResourceKind.AMBULANCE, "Emergency ALS Ambulance", 8, 6),
    (ResourceKind.BOAT, "Inflatable Rescue Motorboat (Zodiac)", 4, 3),
    (ResourceKind.FOOD_RATIONS, "Emergency 3-Day Meal Kits (1000 pack)", 20, 18),
    (ResourceKind.WATER_PURIFICATION, "Mobile RO Water Purification Unit (500L/hr)", 6, 5),
    (ResourceKind.GENERATOR, "150 kVA Industrial Diesel Generator", 3, 2),
    (ResourceKind.MEDICAL_KIT, "Mass Casualty Trauma First Response Kit", 15, 12),
    (ResourceKind.PERSONNEL_TEAM, "SDRF Urban Flood Search & Rescue Team (6-person)", 4, 3),
]


async def seed_resources(db: AsyncSession) -> int:
    """Seed relief resources linked to active facilities."""
    fac_stmt = select(Facility).where(Facility.is_operational == True)  # noqa: E712
    res = await db.execute(fac_stmt)
    facilities = res.scalars().all()

    if not facilities:
        logger.warning("no_facilities_found_for_resource_seeding")
        return 0

    # Clear existing simulated resources to reseed idempotently
    await db.execute(delete(Resource).where(Resource.data_provenance == Provenance.SIMULATED))

    total_created = 0
    for fac in facilities:
        for kind, label, total, free in RESOURCES_TEMPLATE:
            # Hospitals get more ambulances and medical kits; shelters get more food and water
            if fac.facility_type == FacilityType.HOSPITAL and kind in (
                ResourceKind.AMBULANCE,
                ResourceKind.MEDICAL_KIT,
            ):
                total_qty = total * 2
                free_qty = free * 2
            elif fac.facility_type == FacilityType.SHELTER and kind in (
                ResourceKind.FOOD_RATIONS,
                ResourceKind.WATER_PURIFICATION,
                ResourceKind.BOAT,
            ):
                total_qty = total * 2
                free_qty = free * 2
            else:
                total_qty = total
                free_qty = free

            resource = Resource(
                resource_kind=kind,
                label=f"{fac.name} - {label}",
                quantity_total=total_qty,
                quantity_free=free_qty,
                depot_facility_id=fac.id,
                depot_location=fac.location,
                data_provenance=Provenance.SIMULATED,
            )
            db.add(resource)
            total_created += 1

    await db.commit()
    logger.info("resources_seeded_successfully", total_resources=total_created)
    return total_created


async def main() -> None:
    setup_logging("INFO")
    logger.info("seeding_resources_for_facilities")
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async with session_maker() as session:
        await seed_resources(session)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
