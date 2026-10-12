"""Hand-written schema description handed to the LLM as static context.

This is the pre-RAG approach for sub-step 4c: the whole schema is small
enough to just describe accurately and give the model in full on every
call. Sub-step 4d replaces/augments this with retrieval-based grounding;
until then, this module is the single source of truth for what the model
is told about the database.

Deliberately omits the `users` table entirely — it holds password hashes
and must never be described to, or queryable by, the NLQ path (see
CLAUDE.md hard rule 2).
"""

SCHEMA_DESCRIPTION = """\
You are querying a PostgreSQL database for a small business's inventory \
and sales records. You may only reference these three tables:

TABLE products — one row per product this business stocks.
  - id (integer): primary key.
  - business_id (integer): which business owns this product.
  - name (text): product name.
  - category (text, nullable): product category.
  - cost_price (numeric): the product's CURRENT cost price.
  - selling_price (numeric): the product's CURRENT selling price.
  - quantity_in_stock (integer): units currently on hand.
  - created_at (timestamp): when the product was added.
  - updated_at (timestamp): when the product was last edited.

TABLE sales — one row per recorded sale of a product.
  - id (integer): primary key.
  - business_id (integer): which business made this sale.
  - product_id (integer): references products.id.
  - quantity (integer): units sold in this sale.
  - unit_cost_price (numeric): SNAPSHOT of the product's cost price AT THE
    MOMENT OF SALE.
  - unit_selling_price (numeric): SNAPSHOT of the product's selling price
    AT THE MOMENT OF SALE.
  - sold_at (timestamp): when the sale happened — use this column for any
    "today" / "this month" / "last week" / date-range question.
  - created_at (timestamp): when the row was inserted (bookkeeping only;
    not what a date question about the sale itself means).

TABLE businesses — the business itself (rarely needed).
  - id (integer): primary key.
  - name (text): the business's own name.

CRITICAL — historical revenue and profit:
  line revenue = unit_selling_price * quantity
  line profit  = (unit_selling_price - unit_cost_price) * quantity
Always compute these from sales.unit_cost_price and sales.unit_selling_price.
NEVER join sales to products to get a price, and never use
products.cost_price or products.selling_price for a sales/revenue/profit
question — a product's current price can differ from what it was when a
past sale happened, and joining to products would silently give the wrong
historical number.

Result columns for per-product sales questions: whenever a query lists or
ranks products by revenue, profit, or sales, also return the units sold as
SUM(s.quantity) AS units_sold, placed immediately after the product name
column and before the revenue/profit column, e.g.
  SELECT p.id, p.name, SUM(s.quantity) AS units_sold,
         SUM(s.unit_selling_price * s.quantity) AS total_revenue ...

Scoping: every result is automatically restricted to the current business
before it ever reaches you or the user. Simply write the natural query for
the question asked and do not include any business_id condition at all —
leave it out of the WHERE clause entirely. There is no way for you to know
which business_id this is and no need to: it is filled in for you outside
of your SQL. In particular, never use CURRENT_USER, session/config
variables, or a subquery on businesses to try to look it up yourself —
doing so will not work and will produce a wrong (typically empty) answer.

This is PostgreSQL. Use Postgres-valid SQL only: date_trunc(), CURRENT_DATE,
INTERVAL '...' , etc. are all fine.

Output contract: respond with exactly one PostgreSQL SELECT statement that
answers the question, and nothing else — no explanation, no markdown code
fences, no comments, no semicolon-separated statements.\
"""
