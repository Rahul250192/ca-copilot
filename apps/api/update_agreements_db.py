import asyncio
import json
from sqlalchemy.future import select
from app.db.session import AsyncSessionLocal
from app.models.agreements import AgreementType

AGREEMENTS_UPDATE = [
    {
        "id": "63eb5aa1-add2-4b0d-bc05-4f0a73b7d53d",
        "name": "Mortgage Deed",
        "path": "financial_and_lending/Mortgage_Deed_India.docx",
        "fields": [
            {"name": "mortgagor_name", "type": "text", "label": "Mortgagor (Borrower) Name", "required": True},
            {"name": "mortgagor_address", "type": "textarea", "label": "Mortgagor Address", "required": True},
            {"name": "mortgagee_name", "type": "text", "label": "Mortgagee (Lender) Name", "required": True},
            {"name": "mortgagee_address", "type": "textarea", "label": "Mortgagee Address", "required": True},
            {"name": "loan_amount", "type": "number", "label": "Loan Amount (₹)", "required": True},
            {"name": "property_address", "type": "textarea", "label": "Mortgaged Property Address", "required": True},
            {"name": "registration_date", "type": "date", "label": "Date of Registration", "required": True},
            {"name": "interest_rate", "type": "number", "label": "Interest Rate (%)", "required": True},
            {"name": "effective_date", "type": "date", "label": "Effective Date", "required": True}
        ]
    },
    {
        "id": "8f33816b-c53f-4fe0-b9b3-89c9e56e99d1",
        "name": "Distribution Agreement",
        "path": "vendor_and_procurement/Distribution_Agreement_India.docx",
        "fields": [
            {"name": "principal_name", "type": "text", "label": "Principal Name", "required": True},
            {"name": "distributor_name", "type": "text", "label": "Distributor Name", "required": True},
            {"name": "territory", "type": "text", "label": "Defined Territory", "required": True},
            {"name": "products", "type": "textarea", "label": "Products Description", "required": True},
            {"name": "moq", "type": "number", "label": "Minimum Purchase Commitment (₹)", "required": True},
            {"name": "commission_rate", "type": "number", "label": "Commission/Discount Rate (%)", "required": True},
            {"name": "effective_date", "type": "date", "label": "Effective Date", "required": True},
            {"name": "duration_months", "type": "number", "label": "Duration (Months)", "required": True}
        ]
    },
    {
        "id": "3addb788-abc4-4db2-ab69-c6db4ef1c82b",
        "name": "SLA Agreement",
        "path": "service_and_professionals/SLA_Agreement_India.docx",
        "fields": [
            {"name": "provider_name", "type": "text", "label": "Service Provider Name", "required": True},
            {"name": "client_name", "type": "text", "label": "Client Name", "required": True},
            {"name": "uptime_percent", "type": "number", "label": "Uptime Commitment (%)", "required": True},
            {"name": "response_time_hrs", "type": "number", "label": "Response Time (Hours)", "required": True},
            {"name": "penalty_percentage", "type": "number", "label": "Penalty Percentage (%)", "required": True},
            {"name": "effective_date", "type": "date", "label": "Effective Date", "required": True}
        ]
    },
    {
        "id": "42b5041c-3bee-46d0-ba92-fb96e4b54cc5",
        "name": "Agency Agreement",
        "path": "vendor_and_procurement/Agency_Agreement_India.docx",
        "fields": [
            {"name": "principal_name", "type": "text", "label": "Principal Name", "required": True},
            {"name": "agent_name", "type": "text", "label": "Agent Name", "required": True},
            {"name": "territory", "type": "text", "label": "Territory", "required": True},
            {"name": "commission_percent", "type": "number", "label": "Commission Rate (%)", "required": True},
            {"name": "authority_scope", "type": "textarea", "label": "Scope of Authority", "required": True},
            {"name": "effective_date", "type": "date", "label": "Effective Date", "required": True}
        ]
    },
    {
        "id": "1f90485b-83bf-4ae6-8e81-647aeadbc6c7",
        "name": "Non-Compete Agreement",
        "path": "employment_and_hr/Non_Compete_Agreement_India.docx",
        "fields": [
            {"name": "company_name", "type": "text", "label": "Company Name", "required": True},
            {"name": "employee_name", "type": "text", "label": "Employee Name", "required": True},
            {"name": "restriction_period_months", "type": "number", "label": "Restriction Period (Months)", "required": True},
            {"name": "geographic_scope", "type": "text", "label": "Geographic Scope", "required": True},
            {"name": "consideration_amount", "type": "number", "label": "Consideration Amount (₹)", "required": True},
            {"name": "effective_date", "type": "date", "label": "Effective Date", "required": True}
        ]
    },
    {
        "id": "04f62aca-594c-4b02-a6fe-e0599711e062",
        "name": "Sub-Lease Agreement",
        "path": "property_and_lease/Sub_Lease_Agreement_India.docx",
        "fields": [
            {"name": "sublessor_name", "type": "text", "label": "Sub-Lessor Name", "required": True},
            {"name": "sublessee_name", "type": "text", "label": "Sub-Lessee Name", "required": True},
            {"name": "landlord_name", "type": "text", "label": "Original Landlord Name", "required": True},
            {"name": "property_address", "type": "textarea", "label": "Property Address", "required": True},
            {"name": "monthly_rent", "type": "number", "label": "Monthly Sub-Lease Rent (₹)", "required": True},
            {"name": "duration_months", "type": "number", "label": "Sub-Lease Duration (Months)", "required": True},
            {"name": "effective_date", "type": "date", "label": "Effective Date", "required": True},
            {"name": "original_lease_date", "type": "date", "label": "Original Lease Date", "required": True}
        ]
    }
]

async def update_agreements():
    async with AsyncSessionLocal() as db:
        for data in AGREEMENTS_UPDATE:
            q = select(AgreementType).where(AgreementType.id == data["id"])
            res = await db.execute(q)
            atype = res.scalars().first()
            if atype:
                print(f"Updating {atype.name}...")
                atype.name = data["name"]
                atype.template_path = data["path"]
                atype.template_fields = data["fields"]
            else:
                print(f"Agreement ID {data['id']} not found!")
        
        await db.commit()
        print("Update complete!")

if __name__ == "__main__":
    asyncio.run(update_agreements())
