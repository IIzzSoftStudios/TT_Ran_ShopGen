INSERT INTO Cities (name, size, population, region)
VALUES ('Megaplex Alpha', 'Large', 1000000, 'Urban'),
       ('Hamlet Beta', 'Small', 100, 'Rural');

INSERT INTO Shops (city_id, type)
VALUES (1, 'Weaponsmith'), (1, 'Armor'), (2, 'General Goods');

INSERT INTO Items (name, base_price, rarity, weight)
VALUES ('Sword', 100.00, 'Common', 5.0),
       ('Shield', 75.00, 'Uncommon', 10.0);

INSERT INTO Shop_Inventory (shop_id, item_id, stock, dynamic_price)
VALUES (1, 1, 10, 120.00),
       (1, 2, 5, 90.00),
       (2, 1, 2, 110.00);

