"""
Seed production services into the database.
This script clears existing test services and adds the production service list.
"""
import asyncio
from sqlalchemy.future import select
from sqlalchemy import delete

import sys
sys.path.insert(0, '/app')

from app.db.session import AsyncSessionLocal
from app.models.models import Service, Firm, service_kits, client_services

PRODUCTION_SERVICES = [
    {"name": "GST Refund", "description": "GST refund filing and processing services"},
    {"name": "Income Tax", "description": "Income tax return filing and advisory"},
    {"name": "Valuation", "description": "Business and asset valuation services"},
    {"name": "Import / Export", "description": "Import/Export compliance and documentation"},
    {"name": "Company Law", "description": "Company law compliance and advisory"},
    {"name": "Startup Advisory", "description": "Startup registration and advisory services"},
    {"name": "Audit", "description": "Statutory and internal audit services"},
]

async def seed_services():
    async with AsyncSessionLocal() as db:
        try:
            # Get the first firm (assuming test firm exists)
            result = await db.execute(select(Firm).limit(1))
            firm = result.scalars().first()
            
            if not firm:
                print("❌ No firm found. Please run signup first.")
                return
            
            print(f"🏢 Using firm: {firm.name} ({firm.id})")
            
            # Get all service IDs for this firm
            svc_result = await db.execute(select(Service.id).where(Service.firm_id == firm.id))
            service_ids = [row[0] for row in svc_result.all()]
            
            if service_ids:
                # Delete foreign key relationships first
                await db.execute(delete(service_kits).where(service_kits.c.service_id.in_(service_ids)))
                await db.execute(delete(client_services).where(client_services.c.service_id.in_(service_ids)))
                await db.commit()
                print("🗑️  Cleared service relationships")
                
                # Now delete the services
                await db.execute(delete(Service).where(Service.firm_id == firm.id))
                await db.commit()
                print("🗑️  Cleared existing test services")
            
            # Add production services
            for svc_data in PRODUCTION_SERVICES:
                service = Service(
                    name=svc_data["name"],
                    description=svc_data["description"],
                    firm_id=firm.id
                )
                db.add(service)
            
            await db.commit()
            print(f"✅ Added {len(PRODUCTION_SERVICES)} production services:")
            for svc in PRODUCTION_SERVICES:
                print(f"   - {svc['name']}")
            
        except Exception as e:
            print(f"❌ Error seeding services: {e}")
            await db.rollback()

if __name__ == "__main__":
    asyncio.run(seed_services())
