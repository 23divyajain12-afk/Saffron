import os
import shutil
from datetime import date, timedelta
import pantry_engine
from ai import scan_bill_with_ai, generate_recipes_from_pantry
import ui
from ui import RECIPES, scale_recipe, can_make_recipe
from utils import get_singular_name

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List

# Global cache for AI-generated and fallback dynamic recipes
DYNAMIC_RECIPES_CACHE = {}

# Initialize FastAPI App
app = FastAPI(title="Saffron Pantry API", version="1.0.0")

# Enable CORS (Cross-Origin Resource Sharing)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class ItemPayload(BaseModel):
    name: str
    qty: float
    expiry: Optional[str] = None
    price: Optional[float] = 0.0

class RecipeCheckPayload(BaseModel):
    recipe_name: str
    people: int

class CookPayload(BaseModel):
    recipe_name: str
    people: int

# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/inventory")
def get_inventory():
    """
    Returns the current pantry inventory.
    """
    inventory_list = []
    for item in pantry_engine.inventory:
        inventory_list.append({
            "name": item["name"],
            "expiry": str(item["expiry"]) if item["expiry"] else None,
            "qty": item["qty"],
            "unit": item["unit"],
            "price": item["price"]
        })
    return inventory_list


@app.post("/api/inventory")
def add_new_item(payload: ItemPayload):
    """
    Adds a single item to the pantry.
    """
    try:
        pantry_engine.add_item(payload.name, payload.qty, raw_expiry=payload.expiry, price=payload.price)
        pantry_engine.inventory_sort()
        return {"success": True, "message": f"Added {payload.qty} of {payload.name} successfully."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/inventory/{name}/{expiry}")
def delete_item_batch(name: str, expiry: str):
    """
    Removes a specific batch of an item from the pantry.
    """
    try:
        target_name = get_singular_name(name)
        # Find the batch
        for idx, item in enumerate(pantry_engine.inventory):
            item_expiry_str = str(item["expiry"]) if item["expiry"] else "None"
            if item["name"] == target_name and item_expiry_str == expiry:
                removed = pantry_engine.inventory.pop(idx)
                # Update stock hash map
                pantry_engine.stock_hash_map[target_name] = max(
                    0.0, 
                    pantry_engine.stock_hash_map.get(target_name, 0.0) - removed["qty"]
                )
                pantry_engine.save_pantry_data()
                return {"success": True, "message": f"Removed batch of {name} expiring {expiry}"}
        
        raise HTTPException(status_code=404, detail="Batch not found")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/inventory/upload")
async def upload_receipt(file: UploadFile = File(...)):
    """
    Uploads a receipt image and scans it with Gemini AI, returning the parsed list of items.
    """
    try:
        temp_dir = "temp_uploads"
        os.makedirs(temp_dir, exist_ok=True)
        temp_path = os.path.join(temp_dir, file.filename)
        
        # Save uploaded file
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        print(f"Scanning uploaded receipt: {temp_path}")
        parsed_items = scan_bill_with_ai(temp_path)
        
        # Clean up local file
        if os.path.exists(temp_path):
            os.remove(temp_path)
            
        return {"success": True, "items": parsed_items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/inventory/bulk-add")
def bulk_add_items(items: List[ItemPayload]):
    """
    Adds multiple items at once (e.g. after confirming bill items).
    """
    try:
        for item in items:
            pantry_engine.add_item(item.name, item.qty, raw_expiry=item.expiry, price=item.price)
        pantry_engine.inventory_sort()
        return {"success": True, "message": f"Successfully bulk added {len(items)} items to the pantry."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/recipes")
def get_recipes(people: int = 2):
    """
    Lists all available culinary recipes with smart recommendation details sorted by priority.
    """
    today = date.today()
    
    recommended_recipes = []
    for recipe in RECIPES:
        scaled = scale_recipe(recipe, people)
        missing = can_make_recipe(scaled)
        
        # Calculate availability match score
        # match_score is the average ratio of (available / required) capped at 1.0
        total_ingredients = len(scaled)
        if total_ingredients == 0:
            match_score = 0.0
        else:
            match_sum = 0.0
            for ing_name, required_qty in scaled.items():
                available = pantry_engine.get_total_stock(ing_name)
                match_sum += min(1.0, available / required_qty if required_qty > 0 else 1.0)
            match_score = match_sum / total_ingredients
            
        # Check expiring soon ingredients in the pantry used by this recipe
        expiring_ingredients = []
        expiry_boost = 0.0
        
        for ing_name in scaled.keys():
            # Find batches of this ingredient in the pantry
            # Saffron pantry items are already sorted by expiry
            for item in pantry_engine.inventory:
                if item["name"] == ing_name and item["expiry"] is not None:
                    # check if expiring soon (within 3 days or already expired)
                    days_left = (item["expiry"] - today).days
                    if days_left <= 3:
                        if ing_name not in expiring_ingredients:
                            expiring_ingredients.append(ing_name)
                        # Expiry boost: closer to expiry = higher boost
                        # Expired or 0 days left gets 60, 1 day left gets 40, 2 days gets 20, etc.
                        boost = max(0, 4 - max(0, days_left)) * 20.0
                        expiry_boost += boost
                        break # Only apply boost once per ingredient (from the earliest expiring batch)
                        
        # Base priority score: match_score (0 to 1) * 100
        # Plus expiry boost
        priority_score = (match_score * 100.0) + expiry_boost
        
        recommended_recipes.append({
            "name": recipe["name"],
            "serves": recipe["serves"],
            "ingredients": recipe["ingredients"],
            "match_score": round(match_score * 100, 1),
            "can_make": len(missing) == 0,
            "expiring_ingredients": expiring_ingredients,
            "priority_score": round(priority_score, 1)
        })
        
    # Sort by priority score in descending order
    recommended_recipes.sort(key=lambda r: r["priority_score"], reverse=True)
    return recommended_recipes


@app.post("/api/recipes/check")
def check_recipe_stock(payload: RecipeCheckPayload):
    """
    Checks if there is enough pantry stock to make a recipe, return details.
    """
    recipe = DYNAMIC_RECIPES_CACHE.get(payload.recipe_name)
    if not recipe:
        recipe = next((r for r in RECIPES if r["name"] == payload.recipe_name), None)
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
        
    scaled = scale_recipe(recipe, payload.people)
    missing = can_make_recipe(scaled)
    
    today = date.today()
    ingredients_status = []
    for name, required_qty in scaled.items():
        available_qty = pantry_engine.get_total_stock(name)
        unit = pantry_engine.constants.get(name, {}).get("unit", "units")
        
        # Check if any batch in stock is expiring soon
        is_expiring_soon = False
        for item in pantry_engine.inventory:
            if item["name"] == name and item["expiry"] is not None:
                if (item["expiry"] - today).days <= 3:
                    is_expiring_soon = True
                    break

        ingredients_status.append({
            "name": name,
            "required": round(required_qty, 3),
            "available": round(available_qty, 3),
            "unit": unit,
            "is_enough": available_qty >= required_qty,
            "is_expiring_soon": is_expiring_soon
        })
        
    return {
        "recipe_name": payload.recipe_name,
        "people": payload.people,
        "can_make": len(missing) == 0,
        "ingredients": ingredients_status
    }


@app.post("/api/recipes/cook")
def cook_recipe(payload: CookPayload):
    """
    Cooks a recipe and deducts the ingredients from pantry stock.
    """
    recipe = DYNAMIC_RECIPES_CACHE.get(payload.recipe_name)
    if not recipe:
        recipe = next((r for r in RECIPES if r["name"] == payload.recipe_name), None)
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
        
    scaled = scale_recipe(recipe, payload.people)
    missing = can_make_recipe(scaled)
    if missing:
        raise HTTPException(status_code=400, detail="Cannot cook recipe due to missing ingredients")
        
    pantry_engine.process_deductions(scaled)
    return {"success": True, "message": f"Successfully cooked {payload.recipe_name}! Ingredients deducted from stock."}


def get_local_fallback_recipes(pantry_items, people):
    # Scale helper
    scale = people / 2.0
    
    # Check what items we have in pantry
    available_names = {item["name"] for item in pantry_items if item["qty"] > 0}
    
    fallback_list = []
    
    # 1. Salad recommendation
    salad_ingredients = []
    if "cucumber" in available_names: salad_ingredients.append("cucumber")
    if "tomato" in available_names: salad_ingredients.append("tomato")
    if "onion" in available_names: salad_ingredients.append("onion")
    if "carrot" in available_names: salad_ingredients.append("carrot")
    if "cabbage" in available_names: salad_ingredients.append("cabbage")
    
    if len(salad_ingredients) >= 2:
        fallback_list.append({
            "name": "Fresh Garden Salad",
            "serves": people,
            "time_mins": 10,
            "ingredients": {name: round(0.1 * scale, 2) for name in salad_ingredients},
            "recommendation_reason": f"Uses your fresh {', '.join(salad_ingredients)} to make a crisp, dynamic garden salad!"
        })
        
    # 2. Shake / Smoothie recommendation
    has_milk_or_curd = "milk" in available_names or "curd" in available_names
    fruits = [f for f in ["banana", "mango", "apple", "grapes", "saffron"] if f in available_names]
    
    if has_milk_or_curd and fruits:
        main_fruit = fruits[0]
        liquid = "milk" if "milk" in available_names else "curd"
        fallback_list.append({
            "name": f"Creamy {main_fruit.capitalize()} Shake",
            "serves": people,
            "time_mins": 5,
            "ingredients": {
                main_fruit: round(1.0 * scale, 1),
                liquid: round(0.25 * scale, 2)
            },
            "recommendation_reason": f"Blends your rich {liquid} and fresh {main_fruit} for a refreshing energy shake!"
        })
        
    # 3. Quick Paneer Bhurji (only if paneer available)
    if "paneer" in available_names:
        ingredients_map = {"paneer": round(150.0 * scale, 1)}
        if "onion" in available_names: ingredients_map["onion"] = round(0.15 * scale, 2)
        if "tomato" in available_names: ingredients_map["tomato"] = round(0.1 * scale, 2)
        fallback_list.append({
            "name": "Quick Paneer Bhurji",
            "serves": people,
            "time_mins": 15,
            "ingredients": ingredients_map,
            "recommendation_reason": "High protein delight! Dynamically prepared using your available paneer and veggies."
        })
        
    # 4. Warm Vegetable Soup
    soup_ingredients = [f for f in ["carrot", "tomato", "onion", "cabbage"] if f in available_names]
    if len(soup_ingredients) >= 2:
        fallback_list.append({
            "name": "Warm Cozy Vegetable Soup",
            "serves": people,
            "time_mins": 20,
            "ingredients": {name: round(0.15 * scale, 2) for name in soup_ingredients},
            "recommendation_reason": f"Soothing soup dynamically made from your available {', '.join(soup_ingredients)}."
        })

    # 5. Tomato Onion Curry (if we have tomatoes and onions)
    if "tomato" in available_names and "onion" in available_names:
        fallback_list.append({
            "name": "Quick Tomato Onion Curry",
            "serves": people,
            "time_mins": 20,
            "ingredients": {
                "tomato": round(0.3 * scale, 2),
                "onion": round(0.2 * scale, 2),
            },
            "recommendation_reason": "A simple base curry utilizing your basic stock ingredients."
        })
        
    # If fallback list is still less than 3, add generic ones from ui.RECIPES
    if len(fallback_list) < 3:
        for r in ui.RECIPES:
            if not any(f["name"] == r["name"] for f in fallback_list):
                fallback_list.append({
                    "name": r["name"],
                    "serves": people,
                    "time_mins": 30,
                    "ingredients": ui.scale_recipe(r, people),
                    "recommendation_reason": "Traditional Saffron kitchen favorite."
                })
                
    return fallback_list[:5]


@app.get("/api/recipes/recommendations")
def get_pantry_recommendations(people: int = 2):
    """
    Returns AI-generated or rule-based fallback recipe recommendations based on the live pantry stock.
    """
    global DYNAMIC_RECIPES_CACHE
    today = date.today()
    
    # 1. Fetch current inventory from pantry engine
    inventory_items = []
    for item in pantry_engine.inventory:
        if item["qty"] > 0:
            inventory_items.append({
                "name": item["name"],
                "qty": item["qty"],
                "unit": item["unit"],
                "expiry": str(item["expiry"]) if item["expiry"] else None
            })
            
    # 2. Try to generate using Gemini AI
    recipes_data = generate_recipes_from_pantry(inventory_items, people)
    
    # 3. Fallback to Local Engine if Gemini fails or API key is not configured
    is_ai = True
    if not recipes_data:
        print("Gemini generation unavailable or failed. Using smart rule-based local generator.")
        recipes_data = get_local_fallback_recipes(inventory_items, people)
        is_ai = False
        
    # 4. Score, format and CACHE the recommendations against live pantry inventory
    # Scale back to a base of 2 servings for cache, so the frontend can dynamically scale to any servos count!
    base_factor = 2.0 / people
    
    scored_recommendations = []
    for recipe in recipes_data:
        scaled_ingredients = recipe["ingredients"]
        
        # Cache normalized base recipe
        base_ingredients = {}
        for ing_name, qty in scaled_ingredients.items():
            base_ingredients[ing_name] = qty * base_factor
            
        DYNAMIC_RECIPES_CACHE[recipe["name"]] = {
            "name": recipe["name"],
            "serves": 2,
            "ingredients": base_ingredients
        }
        
        # Calculate missing items
        missing = {}
        for name, qty in scaled_ingredients.items():
            available = pantry_engine.get_total_stock(name)
            if available < qty:
                missing[name] = {"required": qty, "available": available}
                
        # Calculate availability match score
        total_ingredients = len(scaled_ingredients)
        if total_ingredients == 0:
            match_score = 0.0
        else:
            match_sum = 0.0
            for name, qty in scaled_ingredients.items():
                available = pantry_engine.get_total_stock(name)
                match_sum += min(1.0, available / qty if qty > 0 else 1.0)
            match_score = match_sum / total_ingredients
            
        # Check expiring soon ingredients in the pantry used by this recipe
        expiring_ingredients = []
        expiry_boost = 0.0
        
        for ing_name in scaled_ingredients.keys():
            for item in pantry_engine.inventory:
                if item["name"] == ing_name and item["expiry"] is not None:
                    days_left = (item["expiry"] - today).days
                    if days_left <= 3:
                        if ing_name not in expiring_ingredients:
                            expiring_ingredients.append(ing_name)
                        boost = max(0, 4 - max(0, days_left)) * 20.0
                        expiry_boost += boost
                        break
                        
        priority_score = (match_score * 100.0) + expiry_boost
        
        # Determine Category
        category = "Other"
        name_lower = recipe["name"].lower()
        if any(w in name_lower for w in ["shake", "smoothie", "lassi", "juice", "beverage"]):
            category = "Beverage"
        elif any(w in name_lower for w in ["salad", "kachumber", "raita"]):
            category = "Salad"
        elif any(w in name_lower for w in ["curry", "bhurji", "sabzi", "gravy", "paneer"]):
            category = "Curry"
        elif any(w in name_lower for w in ["soup", "broth"]):
            category = "Soup"
        elif any(w in name_lower for w in ["snack", "potato", "fry", "pakora"]):
            category = "Snack"
            
        scored_recommendations.append({
            "name": recipe["name"],
            "serves": recipe["serves"],
            "time_mins": recipe.get("time_mins", 20),
            "ingredients": recipe["ingredients"],
            "match_score": round(match_score * 100, 1),
            "can_make": len(missing) == 0,
            "expiring_ingredients": expiring_ingredients,
            "priority_score": round(priority_score, 1),
            "recommendation_reason": recipe.get("recommendation_reason", "Zero-waste recommendation option."),
            "category": category,
            "is_ai": is_ai
        })
        
    # Sort recommendations by priority score in descending order
    scored_recommendations.sort(key=lambda r: r["priority_score"], reverse=True)
    return scored_recommendations


# ---------------------------------------------------------------------------
# Serve Single-Page Frontend
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def serve_dashboard():
    """
    Serves the main premium frontend dashboard file.
    """
    if os.path.exists("index.html"):
        return FileResponse("index.html")
    else:
        return "<html><body><h1>Dashboard file (index.html) not found. Building...</h1></body></html>"


if __name__ == "__main__":
    import uvicorn
    # Start the server on port 8000
    print("Starting Saffron Web Server on http://127.0.0.1:8000/")
    uvicorn.run(app, host="127.0.0.1", port=8000)
