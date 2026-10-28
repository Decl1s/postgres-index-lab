-- Я сохраняю один и тот же SELECT до и после индекса.
-- Нижнюю границу включаю, верхнюю исключаю; время сравниваю в UTC.
SELECT order_id, created_at, amount_minor
FROM orders
WHERE merchant_id = :merchant_id
  AND status = 'paid'
  AND created_at >= timestamptz '2026-09-20 00:00:00+00'
  AND created_at < timestamptz '2026-10-01 00:00:00+00'
ORDER BY created_at DESC, order_id DESC
LIMIT :row_limit
