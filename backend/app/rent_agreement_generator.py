from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.lib import colors


def generate_rent_agreement(data: dict) -> BytesIO:
    """
    Generate a standard 1-page Residential Lease / Rent Agreement PDF.
    Matches the user's provided official Rent Agreement template.
    """

    output = BytesIO()

    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "AgreementTitle",
        parent=styles["Title"],
        alignment=TA_CENTER,
        fontSize=15,
        leading=18,
        spaceAfter=2,
    )

    subtitle_style = ParagraphStyle(
        "AgreementSubtitle",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        fontSize=10,
        leading=13,
        spaceAfter=10,
    )

    heading_style = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading3"],
        fontSize=10,
        leading=13,
        spaceBefore=6,
        spaceAfter=3,
        fontName="Helvetica-Bold",
    )

    normal_style = ParagraphStyle(
        "AgreementText",
        parent=styles["Normal"],
        fontSize=8.5,
        leading=12,
        spaceAfter=3,
    )

    clause_style = ParagraphStyle(
        "ClauseText",
        parent=styles["Normal"],
        fontSize=8,
        leading=11.5,
        spaceAfter=3,
    )

    def value(key, default="________________________________________"):
        result = data.get(key)
        if result is None or str(result).strip() == "":
            return default
        return str(result)

    def short_value(key, default="______________"):
        result = data.get(key)
        if result is None or str(result).strip() == "":
            return default
        return str(result)

    def checked(value_to_check, expected):
        return "☑" if str(value_to_check).upper() == expected.upper() else "☐"

    story = []

    # =========================================================
    # HEADER / TITLE
    # =========================================================
    story.append(Paragraph("<b>RENT AGREEMENT</b>", title_style))
    story.append(Paragraph("(Residential Lease Agreement)", subtitle_style))

    # =========================================================
    # 1. PARTIES
    # =========================================================
    story.append(Paragraph("<b>1. PARTIES</b>", heading_style))

    parties_data = [
        [
            Paragraph("<b>LANDLORD / OWNER:</b>", normal_style),
            Paragraph("<b>TENANT(S):</b>", normal_style),
        ],
        [
            Paragraph(
                f"""
                <b>Name:</b> {value("landlord_name")}<br/>
                <b>Address:</b> {value("landlord_address")}<br/>
                <b>Phone / Email:</b> {value("landlord_contact", "____________________")}
                """,
                normal_style,
            ),
            Paragraph(
                f"""
                <b>Name(s):</b> {value("tenant_name")}<br/>
                <b>Address:</b> {value("tenant_address")}<br/>
                <b>Phone / Email:</b> {value("tenant_contact", "____________________")}
                """,
                normal_style,
            ),
        ],
    ]

    parties_table = Table(parties_data, colWidths=[90 * mm, 90 * mm])
    parties_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.gray),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(parties_table)
    story.append(Spacer(1, 2 * mm))

    # =========================================================
    # 2. PROPERTY
    # =========================================================
    story.append(Paragraph("<b>2. PROPERTY</b>", heading_style))
    prop_type = value("property_type", "").upper()
    prop_text = f"""
    The Landlord hereby rents to the Tenant the residential premises located at:<br/>
    <b>Full Address:</b> {value("property_address")}<br/>
    <b>Type:</b> {checked(prop_type, "APARTMENT")} Apartment &nbsp;&nbsp;&nbsp; {checked(prop_type, "HOUSE")} House &nbsp;&nbsp;&nbsp; {checked(prop_type, "ROOM")} Room &nbsp;&nbsp;&nbsp; {checked(prop_type, "OTHER")} Other &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; <b>Floor/Unit:</b> {short_value("property_floor_unit")}
    """
    story.append(Paragraph(prop_text, normal_style))

    # =========================================================
    # 3. TERM OF LEASE
    # =========================================================
    story.append(Paragraph("<b>3. TERM OF LEASE</b>", heading_style))
    term_text = f"""
    This Agreement shall commence on <b>{short_value("start_date")}</b> and end on <b>{short_value("end_date")}</b>. The tenancy is for a fixed term of <b>{short_value("lease_duration", "11")}</b> months / years.
    """
    story.append(Paragraph(term_text, normal_style))

    # =========================================================
    # 4. RENT
    # =========================================================
    story.append(Paragraph("<b>4. RENT</b> Month-to-month thereafter.", heading_style))
    pay_method = value("payment_method", "").upper()
    rent_text = f"""
    <b>Monthly Rent:</b> ₹ <b>{short_value("rent_amount")}</b> (in words: <i>{value("rent_in_words", "________________________________________")}</i>)<br/>
    Due on the <b>{short_value("rent_due_day", "1st")}</b> day of each month.<br/>
    <b>Payment method:</b> {checked(pay_method, "CASH")} Cash &nbsp;&nbsp;&nbsp; {checked(pay_method, "BANK_TRANSFER")} Bank Transfer &nbsp;&nbsp;&nbsp; {checked(pay_method, "CHEQUE")} Cheque &nbsp;&nbsp;&nbsp; {checked(pay_method, "OTHER")} Other<br/>
    <b>Late fee:</b> ₹ {short_value("late_fee", "100")} per day / week after due date (if applicable).
    """
    story.append(Paragraph(rent_text, normal_style))

    # =========================================================
    # 5. SECURITY DEPOSIT
    # =========================================================
    story.append(Paragraph("<b>5. SECURITY DEPOSIT</b>", heading_style))
    deposit_text = f"""
    <b>Security Deposit:</b> ₹ <b>{short_value("security_deposit")}</b> to be held by Landlord and refundable within <b>{short_value("deposit_refund_days", "30")}</b> days after termination, subject to deductions for unpaid rent, damages beyond normal wear and tear, etc.
    """
    story.append(Paragraph(deposit_text, normal_style))

    # =========================================================
    # 6. TERMS AND CONDITIONS
    # =========================================================
    story.append(Paragraph("<b>6. TERMS AND CONDITIONS</b>", heading_style))
    story.append(
        Paragraph(
            "❖ <b>RENT & SECURITY DEPOSIT:</b> Rent must be paid on time and will continue as long as the tenant's belongings remain on the property. The security deposit cannot be adjusted against rent and may be deducted for damages, cleaning, or pending dues.",
            clause_style,
        )
    )
    story.append(
        Paragraph(
            "❖ <b>GUESTS & PROPERTY:</b> Overnight guests require prior permission and may be charged ₹500 per night. Unauthorized occupants or damage to the property may result in termination and non-refund of the security deposit.",
            clause_style,
        )
    )
    story.append(
        Paragraph(
            "❖ <b>APPLIANCES & RULES:</b> Heavy electrical appliances are not allowed without permission. Violation of the property rules may result in a penalty, deduction from the security deposit, or termination of occupancy.",
            clause_style,
        )
    )
    story.append(Spacer(1, 3 * mm))

    # =========================================================
    # 10. SIGNATURES
    # =========================================================
    story.append(Paragraph("<b>10. SIGNATURES</b>", heading_style))

    signatures_data = [
        [
            Paragraph("<b>LANDLORD</b>", normal_style),
            Paragraph("<b>TENANT</b>", normal_style),
        ],
        [
            Paragraph(
                f"""
                Signature: _________________________<br/>
                Name: {value("landlord_name", "_____________________________")}<br/>
                Date: {short_value("signature_date")}
                """,
                normal_style,
            ),
            Paragraph(
                f"""
                Signature: _________________________<br/>
                Name: {value("tenant_name", "_____________________________")}<br/>
                Date: {short_value("signature_date")}
                """,
                normal_style,
            ),
        ],
    ]

    signatures_table = Table(signatures_data, colWidths=[90 * mm, 90 * mm])
    signatures_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.transparent),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    story.append(signatures_table)

    document.build(story)
    output.seek(0)
    return output
