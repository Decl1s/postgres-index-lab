-- Я храню только paid; merchant_id задаёт равенство, следующие ключи — порядок.
-- amount_minor включаю как payload индекса, не как дополнительный ключ поиска.
CREATE INDEX orders_paid_recent
ON orders (merchant_id, created_at DESC, order_id DESC)
INCLUDE (amount_minor)
WHERE status = 'paid';
VACUUM (ANALYZE) orders;
