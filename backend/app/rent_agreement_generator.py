from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
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
    Generate a standard Rent Agreement PDF.

    The structure follows the uploaded Rent Agreement template.
    """

    output = BytesIO()

    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "AgreementTitle",
        parent=styles["Title"],
        alignment=TA_CENTER,
        fontSize=16,
        leading=20,
        spaceAfter=4,
    )

    subtitle_style = ParagraphStyle(
        "AgreementSubtitle",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        fontSize=10,
        leading=13,
        spaceAfter=12,
    )

    heading_style = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading3"],
        fontSize=11,
        leading=14,
        spaceBefore=8,
        spaceAfter=5,
    )

    normal_style = ParagraphStyle(
        "AgreementText",
        parent=styles["Normal"],
        fontSize=9,
        leading=13,
        spaceAfter=4,
    )

    small_style = ParagraphStyle(
        "SmallText",
        parent=styles["Normal"],
        fontSize=8,
        leading=11,
    )

    def value(key, default="________________"):
        result = data.get(key)

        if result is None or str(result).strip() == "":
            return default

        return str(result)

    def checked(value_to_check, expected):
        return "☑" if str(value_to_check).upper() == expected.upper() else "☐"

    story = []

    # =========================================================
    # TITLE
    # =========================================================

    story.append(
        Paragraph(
            "RENT AGREEMENT",
            title_style,
        )
    )

    story.append(
        Paragraph(
            "(Residential Lease Agreement)",
            subtitle_style,
        )
    )

    story.append(
        Paragraph(
            f"""
            This Rent Agreement is made and entered into on this
            <b>{value("agreement_day")}</b> day of
            <b>{value("agreement_month")}</b>,
            <b>{value("agreement_year")}</b>,
            at <b>{value("agreement_place")}</b>.
            """,
            normal_style,
        )
    )

    # =========================================================
    # 1. PARTIES
    # =========================================================

    story.append(
        Paragraph(
            "1. PARTIES",
            heading_style,
        )
    )

    parties = [
        [
            Paragraph("<b>LANDLORD / OWNER:</b>", normal_style),
            Paragraph("<b>TENANT(S):</b>", normal_style),
        ],
        [
            Paragraph(
                f"""
                Name: {value("landlord_name")}<br/>
                Address: {value("landlord_address")}<br/>
                Phone / Email: {value("landlord_contact")}
                """,
                normal_style,
            ),
            Paragraph(
                f"""
                Name(s): {value("tenant_name")}<br/>
                Address: {value("tenant_address")}<br/>
                Phone / Email: {value("tenant_contact")}
                """,
                normal_style,
            ),
        ],
    ]

    parties_table = Table(
        parties,
        colWidths=[85 * mm, 85 * mm],
    )

    parties_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.black),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )

    story.append(parties_table)

    # =========================================================
    # 2. PROPERTY
    # =========================================================

    story.append(
        Paragraph(
            "2. PROPERTY",
            heading_style,
        )
    )

    story.append(
        Paragraph(
            f"""
            The Landlord hereby rents to the Tenant the residential
            premises located at:
            <br/>
            <b>Full Address:</b> {value("property_address")}
            <br/>
            <b>Type:</b> {value("property_type")}
            &nbsp;&nbsp;&nbsp;
            <b>Floor/Unit:</b> {value("property_floor_unit")}
            """,
            normal_style,
        )
    )

    # =========================================================
    # 3. TERM
    # =========================================================

    story.append(
        Paragraph(
            "3. TERM OF LEASE",
            heading_style,
        )
    )

    story.append(
        Paragraph(
            f"""
            This Agreement shall commence on
            <b>{value("start_date")}</b>
            and end on
            <b>{value("end_date")}</b>.
            <br/>
            The tenancy is for a fixed term of
            <b>{value("lease_duration")}</b>.
            """,
            normal_style,
        )
    )

    # =========================================================
    # 4. RENT
    # =========================================================

    story.append(
        Paragraph(
            "4. RENT",
            heading_style,
        )
    )

    payment_method = value(
        "payment_method",
        "",
    )

    story.append(
        Paragraph(
            f"""
            <b>Monthly Rent:</b> ₹ {value("rent_amount")}
            <br/>
            <b>In words:</b> {value("rent_in_words")}
            <br/>
            <b>Due on:</b> {value("rent_due_day")} day of each month.
            <br/>
            <b>Payment method:</b>
            {checked(payment_method, "CASH")} Cash
            &nbsp;
            {checked(payment_method, "BANK_TRANSFER")} Bank Transfer
            &nbsp;
            {checked(payment_method, "CHEQUE")} Cheque
            &nbsp;
            {checked(payment_method, "OTHER")} Other
            <br/>
            <b>Late fee:</b> ₹ {value("late_fee")}
            """,
            normal_style,
        )
    )

    # =========================================================
    # 5. SECURITY DEPOSIT
    # =========================================================

    story.append(
        Paragraph(
            "5. SECURITY DEPOSIT",
            heading_style,
        )
    )

    story.append(
        Paragraph(
            f"""
            <b>Security Deposit:</b> ₹ {value("security_deposit")}
            to be held by Landlord and refundable within
            <b>{value("deposit_refund_days")}</b> days after termination,
            subject to deductions for unpaid rent, damages beyond normal
            wear and tear, etc.
            """,
            normal_style,
        )
    )

    # =========================================================
    # 6. UTILITIES
    # =========================================================

    story.append(
        Paragraph(
            "6. UTILITIES & MAINTENANCE",
            heading_style,
        )
    )

    utilities = data.get("tenant_utilities", [])

    if not isinstance(utilities, list):
        utilities = []

    utility_text = ", ".join(
        str(item) for item in utilities
    )

    story.append(
        Paragraph(
            f"""
            Tenant shall pay:
            <b>{utility_text or "________________"}</b>.
            <br/>
            Landlord shall be responsible for structural repairs.
            Tenant shall keep the premises clean and in good condition
            and report any damage promptly.
            """,
            normal_style,
        )
    )

    # =========================================================
    # 7. USE OF PREMISES
    # =========================================================

    story.append(
        Paragraph(
            "7. USE OF PREMISES",
            heading_style,
        )
    )

    subletting = value(
        "subletting",
        "",
    )

    story.append(
        Paragraph(
            f"""
            The premises shall be used solely for residential purposes.
            Subletting is
            <b>{subletting or "________________"}</b>
            without prior written consent of the Landlord.
            <br/>
            <b>Maximum occupancy:</b>
            {value("maximum_occupancy")} persons.
            """,
            normal_style,
        )
    )

    # =========================================================
    # 8. TERMINATION
    # =========================================================

    story.append(
        Paragraph(
            "8. TERMINATION / NOTICE",
            heading_style,
        )
    )

    story.append(
        Paragraph(
            f"""
            Either party may terminate this Agreement by giving
            <b>{value("notice_period_days")}</b> days' written notice.
            Early termination may attract penalties as mutually agreed
            or as per applicable law.
            """,
            normal_style,
        )
    )

    # =========================================================
    # 9. GENERAL TERMS
    # =========================================================

    story.append(
        Paragraph(
            "9. GENERAL TERMS",
            heading_style,
        )
    )

    story.append(
        Paragraph(
            f"""
            This Agreement constitutes the entire understanding between
            the parties. It shall be governed by the laws of
            <b>{value("governing_law")}</b>.
            Any dispute shall first be attempted to be resolved amicably.
            """,
            normal_style,
        )
    )

    # =========================================================
    # 10. SIGNATURES
    # =========================================================

    story.append(
        Paragraph(
            "10. SIGNATURES",
            heading_style,
        )
    )

    signatures = [
        [
            Paragraph("<b>LANDLORD</b>", normal_style),
            Paragraph("<b>TENANT</b>", normal_style),
        ],
        [
            Paragraph(
                """
                Signature: _________________________<br/><br/>
                Name: ______________________________<br/><br/>
                Date: ______________________________
                """,
                normal_style,
            ),
            Paragraph(
                """
                Signature: _________________________<br/><br/>
                Name: ______________________________<br/><br/>
                Date: ______________________________
                """,
                normal_style,
            ),
        ],
    ]

    signature_table = Table(
        signatures,
        colWidths=[85 * mm, 85 * mm],
    )

    signature_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.black),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )

    story.append(signature_table)

    # =========================================================
    # WITNESSES
    # =========================================================

    story.append(
        Paragraph(
            "WITNESSES (Optional)",
            heading_style,
        )
    )

    witnesses = [
        [
            Paragraph(
                """
                1. Signature: _______________________<br/>
                Name: ______________________________
                """,
                normal_style,
            ),
            Paragraph(
                """
                2. Signature: _______________________<br/>
                Name: ______________________________
                """,
                normal_style,
            ),
        ]
    ]

    witness_table = Table(
        witnesses,
        colWidths=[85 * mm, 85 * mm],
    )

    witness_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.black),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )

    story.append(witness_table)

    story.append(Spacer(1, 8))

    story.append(
        Paragraph(
            """
            This is a standard template form. Parties should review and
            adapt clauses as needed. Consult local laws or a legal
            professional for jurisdiction-specific requirements.
            """,
            small_style,
        )
    )

    # =========================================================
    # BUILD PDF
    # =========================================================

    document.build(story)

    output.seek(0)

    return output
