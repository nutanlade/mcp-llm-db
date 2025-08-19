CREATE TABLE users (
id SERIAL PRIMARY KEY, name VARCHAR (100) NOT NULL, email VARCHAR (100) UNIQUE NOT NULL,
created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
: );
-- Products table
CREATE TABLE products (
id SERIAL PRIMARY KEY, name VARCHAR (100) NOT
NULL,
description TEXT,
price NUMERIC(10, 2) NOT NULL,
created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
: );
-- Inventory table
CREATE TABLE inventories (
product_id INT PRIMARY KEY REFERENCES products (id) ON DELETE CASCADE, quantity INT NOT NULL DEFAULT 0,
updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
: );
- Orders table
CREATE TABLE orders (
id SERIAL PRIMARY KEY,
user_id INT REFERENCES users (id) ON DELETE CASCADE, order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP, status VARCHAR(20) DEFAULT 'pending'
: );
-- Order Items table (join table)
CREATE TABLE order_items ( id SERIAL PRIMARY KEY,
order_id INT REFERENCES orders (id) ON DELETE CASCADE, product_id INT REFERENCES products (id) ON DELETE CASCADE, quantity INT NOT NULL,
price NUMERIC(10, 2) NOT NULL, -- copy of product price at time of order
UNIQUE (order_id, product_id)
) ;