"""
price_intelligence.py — Market Price Analytics & Tax-Aware Competitive Strategy Engine
Designed by: عبدالله الخطيب (Abdullah Al-Khatib)
Part of: Odoo Price Comparator & Competitor Intelligence Suite

Features:
- Full Saudi Tax (VAT 15% / 0% Exempt) integration directly from Odoo tax configuration.
- Calculates net profit margins after deducting VAT for taxable products.
- Recognizes tax exemption (0% VAT) as a competitive pricing advantage.
- Generates psychological pricing ending in .99 / .50 / .75.
- Provides actionable executive recommendations based on cost and competitor prices.
"""

import math


def round_smart_price(price):
    """
    Rounds a retail price to a standard psychological retail ending:
    - If whole number, subtract 1 halala (e.g. 50.00 -> 49.99).
    - Otherwise rounds to .99, .50, or .75.
    """
    if price <= 0:
        return 0.0
    val = round(float(price), 2)
    diff_to_ceil = math.ceil(val) - val
    if diff_to_ceil < 0.05:
        return round(math.ceil(val) - 0.01, 2)
    return round(val, 2)


def analyze_market_competition(
    our_cost,
    our_retail,
    competitors_data,
    target_margin_pct=20.0,
    is_taxable=True,
    tax_rate=15.0
):
    """
    Perform deep financial and competitive analysis taking Saudi VAT into account:
    - Retail prices on competitor websites in Saudi Arabia are VAT-inclusive (15%).
    - For taxable items (is_taxable=True, tax_rate=15%):
        * Net selling revenue = Retail / (1 + tax_rate / 100)
        * Net Profit = Net Revenue - Net Cost
        * Net Margin % = (Net Profit / Net Revenue) * 100
        * Recommended retail prices include 15% VAT for POS / shelf display.
    - For tax-exempt items (is_taxable=False, 0% VAT):
        * Net revenue = 100% of retail price (no VAT deduction).
        * Tax exemption provides a major competitive margin advantage over taxable competitors.
    """
    our_cost = float(our_cost or 0.0)
    our_retail = float(our_retail or 0.0)
    target_margin = float(target_margin_pct or 20.0)
    tax_rate = float(tax_rate or 0.0) if is_taxable else 0.0

    tax_multiplier = (1.0 + (tax_rate / 100.0)) if (is_taxable and tax_rate > 0) else 1.0

    # Net our retail revenue
    our_retail_net = round(our_retail / tax_multiplier, 4) if our_retail > 0 else 0.0

    # Current Margin & Profit
    if our_retail_net > 0:
        current_margin_pct = round(((our_retail_net - our_cost) / our_retail_net) * 100.0, 1)
        current_profit_val = round(our_retail_net - our_cost, 2)
    else:
        current_margin_pct = 0.0
        current_profit_val = 0.0

    # Filter found competitors (strictly > 0.5 SAR)
    active_competitors = []
    for key, c in (competitors_data or {}).items():
        if c.get('found') and float(c.get('price') or 0.0) > 0.5:
            active_competitors.append({
                'key': key,
                'site_name': c.get('site_name', key),
                'domain': c.get('domain', ''),
                'price': float(c['price']),
                'in_stock': c.get('in_stock', True),
                'url': c.get('url', ''),
                'title': c.get('title', ''),
                'matched_by': c.get('matched_by', '')
            })

    # Tax note
    if is_taxable and tax_rate > 0:
        tax_status_label = f"خاضع للضريبة ({tax_rate:.0f}% VAT)"
        tax_status_note = f"⚠️ الصنف خاضع لضريبة القيمة المضافة ({tax_rate:.0f}%). تم احتساب هوامش الربح وصافي الأرباح بعد استقطاع مبلغ الضريبة من سعر البيع التنافسي."
    else:
        tax_status_label = "معفى من الضريبة (0% VAT)"
        tax_status_note = "✨ ميزة ضريبية خاصة: هذا الصنف معفى من الضريبة (0% VAT) وفق بيانات أودو، مما يمنح الشركة كامل قيمة البيع كإيراد صافٍ، ويوفر قدرة استثنائية على منافسة الأسعار دون ضغط ضريبي."

    # If target margin is valid, compute cost-safe retail price (including tax if taxable)
    if target_margin < 100.0 and our_cost > 0:
        net_needed = our_cost / (1.0 - (target_margin / 100.0))
        cost_safe_price = round_smart_price(net_needed * tax_multiplier)
    else:
        cost_safe_price = our_retail

    if not active_competitors:
        # No competitors found
        safe_suggested = cost_safe_price if our_cost > 0 else our_retail
        rec_lines = [
            "لم يتم رصد هذا الصنف بالباركود في أي من المتاجر المنافسة التي تم فحصها.",
            "• يتمتع الصنف بمرونة تسعيرية عالية وحرية كاملة دون ضغط تنافسي مباشر في السوق الرقمي.",
            f"• سعر البيع الحالي ({our_retail:.2f} ر.س) يحقق هامش ربح صافٍ {current_margin_pct:.1f}% (صافي ربح: {current_profit_val:.2f} ر.س).",
            f"• {tax_status_note}"
        ]
        return {
            'has_competitors': False,
            'competitors_count': 0,
            'lowest_price': None,
            'lowest_price_net': None,
            'lowest_store': None,
            'highest_price': None,
            'highest_store': None,
            'avg_price': None,
            'price_diff': 0.0,
            'price_diff_pct': 0.0,
            'current_margin_pct': current_margin_pct,
            'current_profit_val': current_profit_val,
            'potential_margin_pct': None,
            'potential_profit_val': None,
            'status_level': 'exclusive',
            'status_title': '💎 صنف حصري / غير معروض لدى المنافسين بالباركود',
            'status_badge': 'حصري',
            'status_color': '#3B82F6',  # Blue
            'recommendation_text': "\n".join(rec_lines),
            'suggested_price': safe_suggested,
            'is_taxable': is_taxable,
            'tax_rate': tax_rate,
            'tax_status_label': tax_status_label,
            'tax_status_note': tax_status_note,
            'active_competitors': []
        }

    # Prioritize IN-STOCK competitors for pricing strategy and market metrics
    in_stock_competitors = [c for c in active_competitors if c.get('in_stock', True)]
    pricing_pool = in_stock_competitors if in_stock_competitors else active_competitors

    # Sort competitors by price ascending
    pricing_pool.sort(key=lambda x: x['price'])
    active_competitors.sort(key=lambda x: x['price'])

    lowest_comp = pricing_pool[0]
    highest_comp = pricing_pool[-1]

    lowest_price = lowest_comp['price']
    lowest_store = lowest_comp['site_name']
    highest_price = highest_comp['price']
    highest_store = highest_comp['site_name']

    avg_price = round(sum(c['price'] for c in pricing_pool) / len(pricing_pool), 2)

    # Check if an out-of-stock competitor had a lower price than active in-stock pool
    stock_alert_note = ""
    if in_stock_competitors:
        cheaper_out_of_stock = [c for c in active_competitors if not c.get('in_stock', True) and c['price'] < lowest_price]
        if cheaper_out_of_stock:
            cheapest_oos = cheaper_out_of_stock[0]
            stock_alert_note = f"\n• تنبيه مخزون: متجر [{cheapest_oos['site_name']}] يعرض سعراً منخفضاً ({cheapest_oos['price']:.2f} ر.س) ولكنه نفد من المخزون لديهم حالياً، لذا تم اعتماد أفضل سعر متوفر فعلياً ({lowest_price:.2f} ر.س لدى {lowest_store})."

    # Price Difference vs lowest competitor (positive = we are more expensive, negative = we are cheaper)
    price_diff = round(our_retail - lowest_price, 2)
    price_diff_pct = round((price_diff / our_retail) * 100.0, 1) if our_retail > 0 else 0.0

    # Net potential price and margin if selling at lowest competitor's price
    lowest_price_net = round(lowest_price / tax_multiplier, 4)
    potential_profit_val = round(lowest_price_net - our_cost, 2)
    potential_margin_pct = round(((lowest_price_net - our_cost) / lowest_price_net) * 100.0, 1) if lowest_price_net > 0 else 0.0

    # Determine Strategy & Recommendation
    if price_diff <= 0:
        # Case A: We are already the cheapest or equal
        status_level = 'leader'
        status_badge = 'سعر متصدر 🏆'
        status_color = '#10B981'  # Vibrant Green
        if price_diff < -1.50:
            status_title = f"🏆 أنت الأرخص في السوق بفارق {abs(price_diff):.2f} ر.س عن {lowest_store}"
            sug_up = round_smart_price(lowest_price - 0.50)
            recommendation_text = (
                f"سعر شركتنا الحالي ({our_retail:.2f} ر.س) هو الأفضل في السوق ويتصدر المنافسين بفارق مريح!\n"
                f"• أرخص منافس مسجل ({lowest_store}) يعرضه بسعر: {lowest_price:.2f} ر.س (متوسط السوق: {avg_price:.2f} ر.س).\n"
                f"• هامش ربحك الصافي الحالي ({current_margin_pct:.1f}%) محمي وربح الوحدة ({current_profit_val:.2f} ر.س).\n"
                f"💡 خيار استراتيجي: يمكنك الاستمرار بهذا السعر لاكتساح المبيعات، أو رفعه قليلاً إلى ({sug_up:.2f} ر.س) لتعظيم الأرباح مع البقاء أرخص من الجميع.\n"
                f"• {tax_status_note}"
            )
            suggested_price = our_retail
        else:
            status_title = f"✅ سعرنا مطابق لأفضل سعر منافس في السوق ({lowest_store})"
            recommendation_text = (
                f"سعر شركتنا متطابق أو متقارب جداً مع أفضل سعر منافس ({lowest_price:.2f} ر.س لدى {lowest_store}).\n"
                f"• يحقق الصنف هامش ربح صافٍ آمن ({current_margin_pct:.1f}%).\n"
                f"• {tax_status_note}"
            )
            suggested_price = our_retail

    elif potential_margin_pct >= target_margin:
        # Case B: We are more expensive, but cost allows winning price while maintaining safe target margin
        status_level = 'opportunity'
        status_badge = 'فرصة تخفيض رابحة 🚀'
        status_color = '#F59E0B'  # Amber / Gold
        status_title = f"🚀 فرصة قوية للتفوق السعري بهامش ربح صافٍ آمن ({potential_margin_pct:.1f}%)"
        target_beat_price = round_smart_price(lowest_price - 0.50)
        net_beat = target_beat_price / tax_multiplier
        margin_at_beat = round(((net_beat - our_cost) / net_beat) * 100.0, 1) if net_beat > 0 else 0.0

        recommendation_text = (
            f"المنافس ({lowest_store}) يبيع بسعر أقل ({lowest_price:.2f} ر.س) بفارق {price_diff:.2f} ر.س.\n"
            f"• تكلفة الشراء لدينا ({our_cost:.2f} ر.س) تسمح بالتخفيض الفوري والتفوق عليه بأمان.\n"
            f"• في حال اعتماد السعر المقترح ({target_beat_price:.2f} ر.س شامل الضريبة):\n"
            f"  ستكون الأرخص في السوق وستحقق هامش ربح صافٍ {margin_at_beat:.1f}%، متجاوزاً هدفك ({target_margin:.0f}%).\n"
            f"• {tax_status_note}"
        )
        suggested_price = target_beat_price

    elif potential_margin_pct >= 5.0:
        # Case C: Tight margin (5% to target_margin)
        status_level = 'caution'
        status_badge = 'مقاربة حذرة ⚠️'
        status_color = '#EA580C'  # Warm Orange
        status_title = f"⚠️ مطابقة السعر ستخفض هامش الربح الصافي إلى {potential_margin_pct:.1f}%"
        recommendation_text = (
            f"أرخص منافس ({lowest_store}) يبيع بـ ({lowest_price:.2f} ر.س).\n"
            f"• مجاراة هذا السعر ممكنة ولكنها تضغط صافي الربح إلى ({potential_profit_val:.2f} ر.س) بنسبة {potential_margin_pct:.1f}% "
            f"(أقل من الهامش المستهدف {target_margin:.0f}%).\n"
            f"💡 التوصية: حافظ على السعر الحالي للكميات الفردية ما لم تكن هناك رغبة في التصفية، واطلب من المشتريات التفاوض لخفض تكلفة الشراء.\n"
            f"• {tax_status_note}"
        )
        suggested_price = lowest_price

    else:
        # Case D: Price War / Dump / Below Cost
        status_level = 'danger'
        status_badge = 'حرق أسعار 🛑'
        status_color = '#EF4444'  # Red
        status_title = f"🛑 تحذير: المنافس يبيع بسعر حرق أو بهامش خسارة!"
        recommendation_text = (
            f"المنافس ({lowest_store}) يعرض الصنف بـ ({lowest_price:.2f} ر.س)، وهو قريب جداً من تكلفتنا ({our_cost:.2f} ر.س) أو أقل منها!\n"
            f"• مطابقة هذا السعر ستؤدي لخسارة مباشرة أو هامش معدوم ({potential_margin_pct:.1f}%).\n"
            f"💡 التوصية: تجنب الدخول في حرب أسعار خاسرة. حافظ على السعر الذي يضمن ربحيتك ({cost_safe_price:.2f} ر.س).\n"
            f"• {tax_status_note}"
        )
        suggested_price = cost_safe_price

    if stock_alert_note:
        recommendation_text += stock_alert_note

    return {
        'has_competitors': True,
        'competitors_count': len(active_competitors),
        'lowest_price': lowest_price,
        'lowest_price_net': lowest_price_net,
        'lowest_store': lowest_store,
        'highest_price': highest_price,
        'highest_store': highest_store,
        'avg_price': avg_price,
        'price_diff': price_diff,
        'price_diff_pct': price_diff_pct,
        'current_margin_pct': current_margin_pct,
        'current_profit_val': current_profit_val,
        'potential_margin_pct': potential_margin_pct,
        'potential_profit_val': potential_profit_val,
        'status_level': status_level,
        'status_title': status_title,
        'status_badge': status_badge,
        'status_color': status_color,
        'recommendation_text': recommendation_text,
        'suggested_price': suggested_price,
        'is_taxable': is_taxable,
        'tax_rate': tax_rate,
        'tax_status_label': tax_status_label,
        'tax_status_note': tax_status_note,
        'active_competitors': active_competitors
    }
