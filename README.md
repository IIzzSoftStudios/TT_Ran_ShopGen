**Objective:**   
Update the shop generator from google sheets to SQL database to increase performance and add additional features.   
	Each city, City sizes will range from Megaplex with Millions of residents to small hamlets with maybe 100 at max residents, will have its own shops, the shops will be the same but the size of the city will determine what is for sale, Items and their price. Each shop within the city will have its own Inventory based on its specialty, Armor, Weaponsmith/Gunsmith, Medical, Tech/Magic, ect. I want to be able to save each city's inventory for when players visit in the future.  
	Prices will have a base value, from there the price will be determined by what is in stock, how popular the item is, and how rare the item is.  
	Stock will be set at the start, from there a script will be run to simulate the buying and selling of goods for a period of time. This script will be able to be run whenever I wish. To bring variety to prices and goods in stock.   
	Interfaces, I want there to be a Game Master interface that has a section to set the current city size for the players to see what inventory is available, the options to add new items and select which shop type it belongs to, what the baseline price and stock will be as well. The Second interface should be a player interface, it will show the players their current funds, their current items and what inventory is available with its price based on what the Game Master has set. 

Optional probably needed: login system and save so players can only see their own characters  
Secondary Purley Optional: Create an android app for the players. 

**Databases:**  
**Cities**

* City ID (PK)  
  * Name  
  * Size  
  * Population  
  * Region  
  * Profile (Industrial, Agriculture, Technology, ect)  
* Shop ID (FK)

**City Shops:**

* City ID (FK)  
* Shop ID (PK)  
* Item ID (FK)  
* Stock  
* Last Updated

**Player Inventory**

* Player ID (FK)  
* Item ID (FK)  
* Funds


**Inventory**

* Item ID (PK)  
* Name  
* Category  
* Damage  
* Range  
* Base Price  
* Weight  
* Rarity  
* Notes

**Pricing Log**

* Shop ID (FK)  
* Item ID (FK)  
* Timestamp  
* Price

**Login System**:

* Store credentials securely using hashed passwords.  
* Add a `User_Roles` column (`GameMaster` or `Player`)

**Data format:**  
**Gunsmith example current:**

| Gunsmith | Range | Damage | Rate of Fire | Shots | Min STR | Notes |
| :---- | :---- | :---- | ----- | ----- | :---- | :---- |
| Derringer (.44)(S) | 5/20/40 | 2D6+1 | 1 | 2 |  | AP1 |
| Colt Dragoon (.44)(S) | 12/24/48 | 2D6+1 | 1 | 6 |  | Revolver |
| Colt 1911 (.45)(S) | 12/24/48 | 2D6+1 | 1 | 7 |  | Semi-Auto |
| Glock (9mm)(M) | 12/24/48 | 2D6 | 1 | 17 |  | Semi-Auto |
| Ruger (.22)(S) | 10/20/40 | 2D6-1 | 1 | 9 |  | Revolver |

Shop: Gunsmith, Item: Derringer (.44)(S), Range: 5/20/40, Damage: 2D6+1, Rate of Fire: 1, Shots: 2, Min STR: N/A, Notes: AP1

**Derringer example update:**  
ID(Primary Key): \*number\*  
Shop: Gunsmith  
Name: Derringer  
Range: 5/20/40  
Rate of Fire: 1  
Shots: 2  
Min STR: N/A  
Notes: AP1

**Item Template:**  
ID(Primary Key): \*number\*  
Shop: Text String  
Name: Text String  
Range:  Whole \# / Whole \# / Whole \#  
Damage: Combination of Text and Whole \#s  
Rate of Fire: Whole \#  
Min STR: if no current number than N/A else Whole \#  
Notes: Text Strings

**Shop Template:**  
ID (Primary Key):  
Item DataFrame

**UI:**  
**Game Master:**

* Dropdown City  
  * Name  
  * Population (Size)  
  * Active Shops and their Stock  
* Form for adding Items to the database  
* Controls to manually adjust inventories  
* Button to run the simulation script  
* Transaction History Log


**Players:**

* Current Player inventory  
* Current Player Funds  
* Shops for the city the player is currently in set by the GM  
  * Search function

**Companion App in React?**

**Scripts:**

* Initialization of stock prices and inventory  
* Dynamic buying and selling goods  
  *  \`dynamic\_price \= base\_price \* (1 \+ (rarity\_modifier \* demand\_modifier) \- (stock\_modifier))\`   
  * Rarity and high demand increase price while excess stock decrease price
