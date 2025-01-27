CREATE TABLE Cities (
    city_id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    size VARCHAR(50),
    population INT,
    region VARCHAR(100)
);

CREATE TABLE Shops (
    shop_id SERIAL PRIMARY KEY,
    city_id INT REFERENCES Cities(city_id),
    type VARCHAR(50) NOT NULL
);

CREATE TABLE Items (
    item_id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    base_price DECIMAL(10, 2),
    rarity VARCHAR(50),
    weight DECIMAL(5, 2)
);

CREATE TABLE Shop_Inventory (
    inventory_id SERIAL PRIMARY KEY,
    shop_id INT REFERENCES Shops(shop_id),
    item_id INT REFERENCES Items(item_id),
    stock INT DEFAULT 0,
    dynamic_price DECIMAL(10, 2)
);

