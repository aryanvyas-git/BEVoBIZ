from datetime import date as date_type
from decimal import Decimal

from pydantic import BaseModel


class SalesOverTimePoint(BaseModel):
    date: date_type
    revenue: Decimal
    units: int


class TopProduct(BaseModel):
    name: str
    units: int
    revenue: Decimal


class CategorySales(BaseModel):
    category: str
    revenue: Decimal


class LowStockItem(BaseModel):
    id: int
    name: str
    quantity_in_stock: int
    reorder_level: int


class PeriodStats(BaseModel):
    revenue: Decimal
    profit: Decimal
    units_sold: int


class DashboardStats(BaseModel):
    inventory_cost_valuation: Decimal
    inventory_retail_valuation: Decimal
    product_count: int
    in_stock_count: int
    low_stock_count: int
    out_of_stock_count: int
    total_revenue: Decimal
    total_profit: Decimal
    total_units_sold: int
    period_stats: dict[str, PeriodStats]
    sales_over_time: list[SalesOverTimePoint]
    top_products: list[TopProduct]
    sales_by_category: list[CategorySales]
    low_stock_items: list[LowStockItem]
