from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models.product import Product
from app.models.sale import Sale
from app.models.user import User
from app.schemas.dashboard import (
    CategorySales,
    DashboardStats,
    LowStockItem,
    PeriodStats,
    SalesOverTimePoint,
    TopProduct,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

SALES_CHART_DAYS = 30
TOP_PRODUCTS_LIMIT = 5
LOW_STOCK_LIMIT = 10


@router.get("/stats", response_model=DashboardStats)
def get_dashboard_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    business_id = current_user.business_id

    (
        cost_valuation,
        retail_valuation,
        product_count,
        out_of_stock_count,
        low_stock_count,
    ) = (
        db.query(
            func.coalesce(func.sum(Product.cost_price * Product.quantity_in_stock), 0),
            func.coalesce(func.sum(Product.selling_price * Product.quantity_in_stock), 0),
            func.count(Product.id),
            func.coalesce(func.sum(case((Product.quantity_in_stock == 0, 1), else_=0)), 0),
            func.coalesce(
                func.sum(
                    case(
                        (
                            (Product.quantity_in_stock > 0)
                            & (Product.quantity_in_stock <= Product.reorder_level),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
        )
        .filter(Product.business_id == business_id)
        .one()
    )
    in_stock_count = product_count - out_of_stock_count - low_stock_count

    total_revenue, total_profit, total_units_sold = (
        db.query(
            func.coalesce(func.sum(Sale.unit_selling_price * Sale.quantity), 0),
            func.coalesce(
                func.sum((Sale.unit_selling_price - Sale.unit_cost_price) * Sale.quantity), 0
            ),
            func.coalesce(func.sum(Sale.quantity), 0),
        )
        .filter(Sale.business_id == business_id)
        .one()
    )

    now = datetime.now(timezone.utc)
    today = now.date()
    today_start = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)
    week_start = today_start - timedelta(days=today.weekday())
    month_start = today_start.replace(day=1)
    period_bounds = {"today": today_start, "week": week_start, "month": month_start}

    period_cols = []
    for start in period_bounds.values():
        in_period = Sale.sold_at >= start
        period_cols.extend(
            [
                func.coalesce(
                    func.sum(case((in_period, Sale.unit_selling_price * Sale.quantity), else_=0)),
                    0,
                ),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                in_period,
                                (Sale.unit_selling_price - Sale.unit_cost_price) * Sale.quantity,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ),
                func.coalesce(func.sum(case((in_period, Sale.quantity), else_=0)), 0),
            ]
        )
    period_row = db.query(*period_cols).filter(Sale.business_id == business_id).one()
    period_stats = {
        key: PeriodStats(
            revenue=period_row[i * 3],
            profit=period_row[i * 3 + 1],
            units_sold=period_row[i * 3 + 2],
        )
        for i, key in enumerate(period_bounds)
    }

    period_start = now - timedelta(days=SALES_CHART_DAYS - 1)
    day_expr = func.date(Sale.sold_at)
    daily_rows = (
        db.query(
            day_expr.label("day"),
            func.coalesce(func.sum(Sale.unit_selling_price * Sale.quantity), 0).label("revenue"),
            func.coalesce(func.sum(Sale.quantity), 0).label("units"),
        )
        .filter(Sale.business_id == business_id, Sale.sold_at >= period_start)
        .group_by(day_expr)
        .all()
    )
    by_day = {row.day: row for row in daily_rows}
    sales_over_time = [
        SalesOverTimePoint(
            date=d,
            revenue=by_day[d].revenue if d in by_day else 0,
            units=by_day[d].units if d in by_day else 0,
        )
        for d in (today - timedelta(days=offset) for offset in range(SALES_CHART_DAYS - 1, -1, -1))
    ]

    top_rows = (
        db.query(
            Product.name,
            func.coalesce(func.sum(Sale.quantity), 0).label("units"),
            func.coalesce(func.sum(Sale.unit_selling_price * Sale.quantity), 0).label("revenue"),
        )
        .join(Product, Sale.product_id == Product.id)
        .filter(Sale.business_id == business_id, Product.business_id == business_id)
        .group_by(Product.id, Product.name)
        .order_by(func.sum(Sale.quantity).desc())
        .limit(TOP_PRODUCTS_LIMIT)
        .all()
    )
    top_products = [TopProduct(name=r.name, units=r.units, revenue=r.revenue) for r in top_rows]

    category_expr = func.coalesce(Product.category, "Uncategorized")
    category_rows = (
        db.query(
            category_expr.label("category"),
            func.coalesce(func.sum(Sale.unit_selling_price * Sale.quantity), 0).label("revenue"),
        )
        .join(Product, Sale.product_id == Product.id)
        .filter(Sale.business_id == business_id, Product.business_id == business_id)
        .group_by(category_expr)
        .order_by(func.sum(Sale.unit_selling_price * Sale.quantity).desc())
        .all()
    )
    sales_by_category = [
        CategorySales(category=r.category, revenue=r.revenue) for r in category_rows
    ]

    low_stock_rows = (
        db.query(Product)
        .filter(
            Product.business_id == business_id,
            Product.quantity_in_stock <= Product.reorder_level,
        )
        .order_by(Product.quantity_in_stock.asc())
        .limit(LOW_STOCK_LIMIT)
        .all()
    )
    low_stock_items = [
        LowStockItem(
            id=p.id,
            name=p.name,
            quantity_in_stock=p.quantity_in_stock,
            reorder_level=p.reorder_level,
        )
        for p in low_stock_rows
    ]

    return DashboardStats(
        inventory_cost_valuation=cost_valuation,
        inventory_retail_valuation=retail_valuation,
        product_count=product_count,
        in_stock_count=in_stock_count,
        low_stock_count=low_stock_count,
        out_of_stock_count=out_of_stock_count,
        total_revenue=total_revenue,
        total_profit=total_profit,
        total_units_sold=total_units_sold,
        period_stats=period_stats,
        sales_over_time=sales_over_time,
        top_products=top_products,
        sales_by_category=sales_by_category,
        low_stock_items=low_stock_items,
    )
