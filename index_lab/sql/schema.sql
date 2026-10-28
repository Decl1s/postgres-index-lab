-- Я создаю данные только в своём одноразовом кластере.
CREATE TABLE orders (
    order_id bigint PRIMARY KEY,
    merchant_id integer NOT NULL CHECK (merchant_id BETWEEN 1 AND 100),
    status text NOT NULL CHECK (status IN ('paid', 'cancelled', 'refunded')),
    created_at timestamptz NOT NULL,
    amount_minor bigint NOT NULL CHECK (amount_minor > 0),
    payload text NOT NULL
);

-- Я разделяю формулы merchant/status, чтобы они не делали продавца
-- полностью оплаченным или отменённым из-за случайной корреляции modulo.
INSERT INTO orders
SELECT g, (g % 100) + 1,
       CASE WHEN (g / 100) % 5 < 3 THEN 'paid'
            WHEN (g / 100) % 5 = 3 THEN 'cancelled' ELSE 'refunded' END,
       timestamptz '2026-09-01 00:00:00+00' + ((g * 7919) % 5184000) * interval '1 second',
       100 + (g * 37) % 100000,
       repeat('synthetic-', 16)
FROM generate_series(1, :row_count) AS g;

-- Я добавляю четыре контрольные строки для полуоткрытого периода и tie-breaker.
INSERT INTO orders VALUES
(:row_count + 1, 42, 'paid', '2026-09-20 00:00:00+00', 101, 'lower-bound'),
(:row_count + 2, 42, 'paid', '2026-10-01 00:00:00+00', 102, 'upper-bound'),
(:row_count + 3, 42, 'paid', '2026-09-19 23:59:59.999999+00', 103, 'before-lower'),
(:row_count + 4, 42, 'paid', '2026-09-20 00:00:00+00', 104, 'same-time');
VACUUM (ANALYZE) orders;
