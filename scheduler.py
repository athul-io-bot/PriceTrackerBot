import time
from pymongo import MongoClient
import os
from scraper import scrape
from dotenv import load_dotenv
from database import compare_prices

load_dotenv()

# Add environment variable validation
required_env_vars = ["MONGO_URI", "DATABASE", "COLLECTION", "PRODUCTS"]
for var in required_env_vars:
    if not os.getenv(var):
        raise ValueError(f"Environment variable {var} is not set")

dbclient = MongoClient(os.getenv("MONGO_URI"))
database = dbclient[os.getenv("DATABASE")]
collection = database[os.getenv("COLLECTION")]
PRODUCTS = database[os.getenv("PRODUCTS")]

async def check_prices(app):
    print("Checking Price for Products...")
    for product in PRODUCTS.find():
        try:
            _, current_price = await scrape(product["url"])
            time.sleep(1)
            
            if current_price is not None:
                # Get current values with defaults
                current_product_price = product.get("price", current_price)
                current_lower = product.get("lower", current_price)
                current_upper = product.get("upper", current_price)
                
                if current_price != current_product_price:
                    PRODUCTS.update_one(
                        {"_id": product["_id"]},
                        {
                            "$set": {
                                "price": current_price,
                                "previous_price": current_product_price,
                                "lower": min(current_price, current_lower),
                                "upper": max(current_price, current_upper),
                            }
                        },
                    )
                    print(f"Updated price for {product.get('product_name', 'Unknown')}")
        
        except Exception as e:
            print(f"Error processing {product.get('product_name', 'Unknown')}: {str(e)}")
            continue
    
    print("Completed price checking")
    
    # Send notifications
    changed_products = await compare_prices()
    for changed_product in changed_products:
        cursor = collection.find({"product_id": changed_product})
        users = list(cursor)
        for user in users:
            try:
                product_data = PRODUCTS.find_one({"_id": user.get("product_id")})
                if product_data:
                    previous_price = product_data.get("previous_price", 0)
                    if previous_price > 0:
                        percentage_change = (
                            (product_data["price"] - previous_price) / previous_price
                        ) * 100
                    else:
                        percentage_change = 0
                    
                    text = (
                        f"🎉 Price update for {product_data['product_name']}!\n"
                        f"   - Previous: ₹{previous_price:.2f}\n"
                        f"   - Current: ₹{product_data['price']:.2f}\n"
                        f"   - Change: {percentage_change:.2f}%\n"
                        f"   - [View product]({product_data['url']})"
                    )
                    await app.send_message(
                        chat_id=user.get("user_id"), 
                        text=text, 
                        disable_web_page_preview=True
                    )
            except Exception as e:
                print(f"Error sending message: {str(e)}")
