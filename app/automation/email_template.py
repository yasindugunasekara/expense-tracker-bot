from datetime import date
from html import escape


def format_lkr(value) -> str:
    try:
        amount = float(value or 0)
        return f"LKR {amount:,.2f}"
    except (ValueError, TypeError):
        return "LKR 0.00"


def build_summary_email(
    period_name: str,
    start_date: date,
    end_date_exclusive: date,
    summary_data: dict,
) -> str:
    # Your API returns the totals inside the "summary" object.
    metrics = summary_data.get("summary") or {}

    total_spent = format_lkr(metrics.get("total_spent", 0))
    expense_count = int(metrics.get("expense_count") or 0)

    last_included_date = (
        end_date_exclusive.fromordinal(
            end_date_exclusive.toordinal() - 1
        )
    )

    if start_date == last_included_date:
        period_text = start_date.strftime("%d %B %Y")
    else:
        period_text = (
            f"{start_date.strftime('%d %b %Y')} – "
            f"{last_included_date.strftime('%d %b %Y')}"
        )

    safe_period_name = escape(period_name)
    safe_period_text = escape(period_text)

    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{safe_period_name} Expense Summary</title>
</head>
<body style="margin:0; padding:0; background-color:#F0F4F8;
             font-family:Arial,Helvetica,sans-serif; color:#0F172A;">

<table role="presentation" width="100%" cellpadding="0" cellspacing="0"
       border="0" style="background-color:#F0F4F8;">
<tr>
<td align="center" style="padding:28px 12px;">

<table role="presentation" width="600" cellpadding="0" cellspacing="0"
       border="0"
       style="width:100%;max-width:600px;background-color:#FFFFFF;
              border-radius:14px;overflow:hidden;box-shadow: 0 4px 6px rgba(0,0,0,0.05);">

    <!-- Brand header -->
    <tr>
    <td style="background-color:#FFFFFF;padding:28px 30px;border-bottom:1px solid #E2E8F0;">
        <table role="presentation" width="100%" cellpadding="0"
               cellspacing="0" border="0">
        <tr>
            <td valign="middle">
                <!-- Included Logo -->
                <img src="image_690e43.png" alt="EXPENSA" width="140" style="display:block; border:none;">
            </td>
            <td align="right" valign="middle"
                style="color:#64748B;font-size:11px;font-weight:bold;letter-spacing:1px;">
                YOUR MONEY,<br>ORGANIZED.
            </td>
        </tr>
        </table>
    </td>
    </tr>

    <!-- Report title -->
    <tr>
    <td style="padding:32px 30px 20px;">
        <div style="font-size:11px;font-weight:bold;letter-spacing:2px;
                    color:#4F67FF;">
            YOUR FINANCIAL OVERVIEW
        </div>
        <h1 style="margin:12px 0 8px;font-size:27px;line-height:1.3;
                   color:#0F172A;">
            {safe_period_name} Expense Summary
        </h1>
        <p style="margin:0;font-size:14px;color:#64748B;">
            {safe_period_text}
        </p>
    </td>
    </tr>

    <!-- Total spending card -->
    <tr>
    <td style="padding:0 30px 20px;">
        <table role="presentation" width="100%" cellpadding="0"
               cellspacing="0" border="0"
               style="background-color:#F0F4FF;border:1px solid #DCE4FF;
                      border-radius:12px;">
        <tr>
        <td style="padding:25px 24px;">
            <div style="font-size:12px;font-weight:bold;
                        letter-spacing:1px;color:#475569;">
                TOTAL SPENDING
            </div>
            <div style="font-size:34px;font-weight:bold;color:#4F67FF;
                        margin-top:12px;word-break:break-word;">
                {total_spent}
            </div>
            <div style="font-size:12px;color:#64748B;margin-top:8px;">
                All recorded expenses for this reporting period
            </div>
        </td>
        </tr>
        </table>
    </td>
    </tr>

    <!-- Transaction count -->
    <tr>
    <td style="padding:0 30px 28px;">
        <table role="presentation" width="100%" cellpadding="0"
               cellspacing="0" border="0">
        <tr>
            <td width="100%" valign="top"
                style="padding:19px;border:1px solid #E2E8F0;
                       border-radius:10px;">
                <div style="font-size:12px;color:#64748B;">
                    TRANSACTIONS
                </div>
                <div style="font-size:25px;font-weight:bold;
                            color:#0F172A;margin-top:8px;">
                    {expense_count}
                </div>
                <div style="font-size:12px;color:#64748B;margin-top:5px;">
                    Recorded expenses
                </div>
            </td>
        </tr>
        </table>
    </td>
    </tr>

    <!-- Helpful message -->
    <tr>
    <td style="padding:0 30px 30px;">
        <div style="border-left:4px solid #4F67FF;padding:15px 17px;
                    background-color:#F8FAFC;">
            <div style="font-size:14px;font-weight:bold;color:#0F172A;">
                Small steps. Better financial habits.
            </div>
            <div style="font-size:13px;line-height:1.7;color:#475569;
                        margin-top:7px;">
                Your expenses are organized in one place.
                Review your spending regularly and stay aware
                of where your money goes.
            </div>
        </div>
    </td>
    </tr>

    <!-- Footer -->
    <tr>
    <td align="center"
        style="background-color:#F8FAFC;padding:24px 20px;
               border-top:1px solid #E2E8F0;">
        <div style="font-size:14px;font-weight:bold;letter-spacing:1px;
                    color:#0F172A;">
            EXPENSA
        </div>
        <div style="font-size:12px;color:#64748B;margin-top:8px;">
            Your personal expense tracker
        </div>
        <div style="font-size:11px;color:#94A3B8;margin-top:12px;">
            This is an automated expense summary.
        </div>
    </td>
    </tr>

</table>
</td>
</tr>
</table>

</body>
</html>
"""


def build_threshold_alert_email(
    task_name: str,
    category: str,
    period_name: str,
    start_date: date,
    end_date_exclusive: date,
    threshold_amount: float,
    spent_amount: float,
    transactions: list[dict],
) -> str:
    """
    Generate a high-impact, professional HTML email alert when category
    spending reaches or exceeds an established threshold.
    """
    last_included_date = (
        end_date_exclusive.fromordinal(
            end_date_exclusive.toordinal() - 1
        )
    )

    if start_date == last_included_date:
        period_text = start_date.strftime("%d %B %Y")
    else:
        period_text = (
            f"{start_date.strftime('%d %b %Y')} – "
            f"{last_included_date.strftime('%d %b %Y')}"
        )

    formatted_limit = format_lkr(threshold_amount)
    formatted_spent = format_lkr(spent_amount)

    overage = max(0.0, float(spent_amount) - float(threshold_amount))
    formatted_overage = format_lkr(overage)

    pct = (
        (float(spent_amount) / float(threshold_amount) * 100)
        if float(threshold_amount) > 0
        else 100.0
    )
    pct_text = f"{pct:.1f}%"

    safe_task_name = escape(task_name or f"{category} Limit Alert")
    safe_category = escape(category or "General")
    safe_period_name = escape(period_name)
    safe_period_text = escape(period_text)

    # Build transaction rows (up to 15 items)
    rows_html = []
    for tx in transactions[:15]:
        tx_date = escape(str(tx.get("expense_date") or ""))
        title = escape(str(tx.get("title") or "Expense"))
        subcat = escape(str(tx.get("subcategory") or ""))
        if subcat and subcat.lower() != title.lower():
            display_title = (
                f"{title} "
                f"<span style=\"color:#94A3B8;font-size:12px;\">({subcat})</span>"
            )
        else:
            display_title = title

        amt_str = format_lkr(tx.get("amount") or 0)
        rows_html.append(
            f"""
            <tr style="border-bottom:1px solid #F1F5F9;">
                <td style="padding:11px 14px;font-size:13px;color:#64748B;">{tx_date}</td>
                <td style="padding:11px 14px;font-size:13px;color:#0F172A;font-weight:500;">{display_title}</td>
                <td align="right" style="padding:11px 14px;font-size:13px;font-weight:600;color:#0F172A;">{amt_str}</td>
            </tr>
            """
        )

    if not rows_html:
        transactions_markup = """
        <tr>
            <td colspan="3" align="center" style="padding:18px;font-size:13px;color:#94A3B8;">
                No individual transactions recorded for this period.
            </td>
        </tr>
        """
    else:
        transactions_markup = "\n".join(rows_html)
        if len(transactions) > 15:
            transactions_markup += f"""
            <tr>
                <td colspan="3" align="center" style="padding:12px;font-size:12px;color:#94A3B8;font-style:italic;">
                    + {len(transactions) - 15} additional transactions in this period
                </td>
            </tr>
            """

    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Budget Alert: {safe_category} Limit Exceeded</title>
</head>
<body style="margin:0; padding:0; background-color:#F8FAFC;
             font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
             color:#0F172A; -webkit-font-smoothing:antialiased;">

<table role="presentation" width="100%" cellpadding="0" cellspacing="0"
       border="0" style="background-color:#F8FAFC;">
<tr>
<td align="center" style="padding:32px 12px;">

<table role="presentation" width="600" cellpadding="0" cellspacing="0"
       border="0"
       style="width:100%;max-width:600px;background-color:#FFFFFF;
              border-radius:16px;overflow:hidden;border:1px solid #FEE2E2;
              box-shadow: 0 10px 25px -5px rgba(220, 38, 38, 0.08), 0 8px 10px -6px rgba(220, 38, 38, 0.04);">

    <!-- Top alert accent bar -->
    <tr>
    <td style="background: linear-gradient(90deg, #DC2626 0%, #EF4444 100%); height:5px; line-height:5px; font-size:1px;">&nbsp;</td>
    </tr>

    <!-- Brand header with warning badge -->
    <tr>
    <td style="background-color:#FFFFFF;padding:24px 30px;border-bottom:1px solid #F1F5F9;">
        <table role="presentation" width="100%" cellpadding="0"
               cellspacing="0" border="0">
        <tr>
            <td valign="middle">
                <span style="font-size:20px;font-weight:900;letter-spacing:2px;color:#0F172A;">EXPEN<span style="color:#DC2626;">SA</span></span>
            </td>
            <td align="right" valign="middle">
                <span style="background-color:#FEF2F2;color:#DC2626;border:1px solid #FCA5A5;
                             padding:5px 12px;border-radius:20px;font-size:11px;font-weight:700;
                             letter-spacing:0.8px;display:inline-block;">
                    ⚠️ LIMIT REACHED
                </span>
            </td>
        </tr>
        </table>
    </td>
    </tr>

    <!-- Alert Title -->
    <tr>
    <td style="padding:28px 30px 16px;">
        <div style="font-size:11px;font-weight:800;letter-spacing:1.5px;
                    color:#DC2626;text-transform:uppercase;">
            {safe_period_name} Budget Alert • {safe_category}
        </div>
        <h1 style="margin:10px 0 6px;font-size:24px;line-height:1.3;
                   color:#0F172A;font-weight:800;">
            {safe_category} spending reached limit
        </h1>
        <p style="margin:0;font-size:14px;color:#64748B;">
            {safe_task_name} &bull; {safe_period_text}
        </p>
    </td>
    </tr>

    <!-- Primary comparison card -->
    <tr>
    <td style="padding:0 30px 20px;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
               style="background-color:#FFF5F5;border:1px solid #FED7D7;border-radius:14px;">
        <tr>
        <td style="padding:22px;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
            <tr>
                <!-- Actual Spent -->
                <td width="50%" valign="top" style="padding-right:12px;">
                    <div style="font-size:11px;font-weight:700;letter-spacing:1px;color:#991B1B;">
                        TOTAL SPENT ({safe_category.upper()})
                    </div>
                    <div style="font-size:28px;font-weight:800;color:#DC2626;margin-top:6px;word-break:break-word;">
                        {formatted_spent}
                    </div>
                    <div style="font-size:12px;color:#991B1B;margin-top:4px;font-weight:600;">
                        {pct_text} of period limit
                    </div>
                </td>
                <!-- Budget Limit -->
                <td width="50%" valign="top" style="border-left:1px solid #FECACA;padding-left:16px;">
                    <div style="font-size:11px;font-weight:700;letter-spacing:1px;color:#64748B;">
                        BUDGET LIMIT
                    </div>
                    <div style="font-size:22px;font-weight:700;color:#334155;margin-top:6px;word-break:break-word;">
                        {formatted_limit}
                    </div>
                    <div style="font-size:12px;color:#DC2626;margin-top:4px;font-weight:600;">
                        +{formatted_overage} over limit
                    </div>
                </td>
            </tr>
            </table>

            <!-- Progress bar -->
            <div style="margin-top:18px;background-color:#FEE2E2;height:8px;border-radius:4px;overflow:hidden;">
                <div style="background-color:#DC2626;width:100%;height:8px;border-radius:4px;"></div>
            </div>
        </td>
        </tr>
        </table>
    </td>
    </tr>

    <!-- Transaction list header -->
    <tr>
    <td style="padding:10px 30px 10px;">
        <div style="font-size:13px;font-weight:700;letter-spacing:0.5px;color:#334155;text-transform:uppercase;">
            Contributing Transactions ({len(transactions)})
        </div>
    </td>
    </tr>

    <!-- Transactions table -->
    <tr>
    <td style="padding:0 30px 24px;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
               style="border:1px solid #E2E8F0;border-radius:10px;overflow:hidden;border-collapse:collapse;">
            <thead>
                <tr style="background-color:#F8FAFC;border-bottom:1px solid #E2E8F0;">
                    <th align="left" style="padding:10px 14px;font-size:11px;font-weight:700;color:#64748B;letter-spacing:0.5px;text-transform:uppercase;">Date</th>
                    <th align="left" style="padding:10px 14px;font-size:11px;font-weight:700;color:#64748B;letter-spacing:0.5px;text-transform:uppercase;">Description</th>
                    <th align="right" style="padding:10px 14px;font-size:11px;font-weight:700;color:#64748B;letter-spacing:0.5px;text-transform:uppercase;">Amount</th>
                </tr>
            </thead>
            <tbody>
                {transactions_markup}
            </tbody>
        </table>
    </td>
    </tr>

    <!-- Mindful spending advice note -->
    <tr>
    <td style="padding:0 30px 28px;">
        <div style="border-left:4px solid #DC2626;padding:14px 16px;
                    background-color:#FEF2F2;border-radius:0 8px 8px 0;">
            <div style="font-size:13px;font-weight:700;color:#991B1B;">
                💡 Budget Reminder
            </div>
            <div style="font-size:13px;line-height:1.6;color:#7F1D1D;margin-top:4px;">
                You have reached your <strong>{safe_period_name.lower()}</strong> spending cap for <strong>{safe_category}</strong>.
                Consider pausing non-essential purchases in this category until the next {safe_period_name.lower()} cycle.
            </div>
        </div>
    </td>
    </tr>

    <!-- Footer -->
    <tr>
    <td align="center"
        style="background-color:#F8FAFC;padding:22px 20px;
               border-top:1px solid #E2E8F0;">
        <div style="font-size:13px;font-weight:800;letter-spacing:1px;
                    color:#0F172A;">
            EXPENSA
        </div>
        <div style="font-size:12px;color:#64748B;margin-top:6px;">
            Personal Expense &amp; Budget Automation
        </div>
        <div style="font-size:11px;color:#94A3B8;margin-top:10px;">
            This is an automated threshold notification triggered by your active spending alerts.
        </div>
    </td>
    </tr>

</table>
</td>
</tr>
</table>

</body>
</html>
"""