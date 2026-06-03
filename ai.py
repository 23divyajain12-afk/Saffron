import json
import re
import os
from pathlib import Path
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from typing import Literal
from PIL import Image
import dotenv

# Load environment variables from .env file in project root
project_root = Path(__file__).parent
dotenv.load_dotenv(project_root / '.env')

# Get API key from environment
api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

def get_genai_client():
    """
    Initializes and returns the Google GenAI Client if an API key is available.
    """
    if not api_key or "your_actual_" in api_key or "your_gemini_" in api_key or api_key.strip() == "":
        print("\n[WARNING] Gemini API Key not found! Please set GEMINI_API_KEY in your environment or a .env file.")
        print("Example in .env file:")
        print("GEMINI_API_KEY=AIzaSy...")
        return None
    try:
        return genai.Client(api_key=api_key)
    except Exception as e:
        print(f"\n[ERROR] Failed to initialize Gemini Client: {e}")
        return None


def clean_ai_json_response(raw_response):
    raw_response = raw_response.strip()
    if raw_response.startswith("```"):
        match = re.search(r'```(?:json\s*)?(.*?)```$', raw_response, re.DOTALL)
        return match.group(1).strip() if match else raw_response
    return raw_response


def parse_ai_json(raw_response):
    cleaned = clean_ai_json_response(raw_response)
    return json.loads(cleaned)


# ---------------------------------------------------------------------------
# Receipt Scanner Definitions and Function
# ---------------------------------------------------------------------------

class BillItem(BaseModel):
    name: str = Field(description="Name of the food ingredient or pantry item")
    qty: float = Field(description="Numerical quantity or weight of the item")


class BillAnalysis(BaseModel):
    items: list[BillItem] = Field(description="List of all items found on the receipt")


def scan_bill_with_ai(image_path):
    """
    Analyzes a receipt image using Gemini API, extracting items and their quantities.
    """
    client = get_genai_client()
    if not client:
        print("Error: Gemini API Client could not be initialized (missing API key).")
        return []

    prompt = """
    Analyze the attached receipt image.
    Extract every line item name and its corresponding numerical quantity.
    
    Ensure all items are listed in the 'items' list with their names and quantities.
    Keep item names simple and lowercased (e.g. 'banana', 'tomato', 'chilli').
    """

    try:
        print(f"Sending receipt image '{image_path}' to Gemini...")
        if not os.path.exists(image_path):
            print(f"Error: Image file not found at {image_path}")
            return []

        img = Image.open(image_path)
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[img, prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=BillAnalysis,
            ),
        )

        
        if response.parsed and hasattr(response.parsed, 'items'):
            result = []
            for item in response.parsed.items:
                result.append({
                    "name": item.name,
                    "qty": item.qty
                })
            return result
        
        # Fallback to manual parsing if Pydantic parsing didn't work but text is returned
        print("Gemini response did not contain parsed items structure. Attempting fallback parse.")
        raw_response = response.text
        data = parse_ai_json(raw_response)
        if isinstance(data, dict) and "items" in data:
            return data["items"]
        elif isinstance(data, list):
            return data
        return []

    except json.JSONDecodeError:
        print(f"Parsing Error: AI output was not clean JSON.")
        return []
    except Exception as e:
        print(f"Gemini API Call Failed: {e}.")
        return []


# ---------------------------------------------------------------------------
# Ingredient Info Definitions and Function
# ---------------------------------------------------------------------------

def is_valid_exotic_response(data):
    if not isinstance(data, dict):
        return False

    required_keys = {"unit", "shelf_life"}
    if set(data.keys()) != required_keys:
        return False

    allowed_units = {"kg", "grams", "liters", "ml", "units", "bunches", "packets"}
    if data.get("unit") not in allowed_units:
        return False

    if not isinstance(data.get("shelf_life"), int):
        return False

    return True


class IngredientInfo(BaseModel):
    unit: Literal["kg", "grams", "liters", "ml", "units", "bunches", "packets"] = Field(
        description="Standard unit of measurement for household recipes"
    )
    shelf_life: int = Field(description="Typical shelf life in days when stored correctly in an Indian home")


def get_exotic_ingredient_info(item_name, max_retries=3):
    """
    Queries Gemini to retrieve shelf life and unit information for a given ingredient name.
    """
    client = get_genai_client()
    if not client:
        print("Error: Gemini API Client could not be initialized (missing API key).")
        return {}

    prompt = f"""
    You are an expert culinary database assistant specializing in Indian kitchens.
    Analyze the food ingredient provided.
    Determine its typical storage shelf life (in days) when stored correctly in a standard Indian household.
    Also determine its standard unit of measurement.

    Input ingredient: {item_name}
    """

    for attempt in range(1, max_retries + 1):
        try:
            print(f"Querying exotic ingredient info for '{item_name}' via Gemini (attempt {attempt})...")
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=IngredientInfo,
                ),
            )

            if response.parsed:
                return {
                    "unit": response.parsed.unit,
                    "shelf_life": response.parsed.shelf_life
                }

            # Fallback
            raw_response = response.text
            data = parse_ai_json(raw_response)
            if is_valid_exotic_response(data):
                return data

            print(f"Validation failed on attempt {attempt}. Response did not match expected schema: {data}")
        except json.JSONDecodeError:
            print(f"Parsing Error on attempt {attempt}: AI output was not clean JSON.")
        except Exception as e:
            print(f"Gemini Call Failed on attempt {attempt}: {e}.")

    print(f"Failed to get valid exotic ingredient info after {max_retries} attempts.")
    return {}


class DynamicRecipeIngredient(BaseModel):
    name: str = Field(description="Ingredient name, matching available pantry items where possible")
    qty: float = Field(description="Required quantity for this serves count")
    unit: str = Field(description="Standard unit of measurement (e.g. kg, grams, liters, ml, units, bunches)")

class DynamicRecipe(BaseModel):
    name: str = Field(description="Name of the recipe")
    serves: int = Field(description="Number of servings/people this quantity satisfies")
    time_mins: int = Field(description="Total prep and cooking time in minutes")
    ingredients: list[DynamicRecipeIngredient] = Field(description="List of ingredients required")
    recommendation_reason: str = Field(description="Reason for suggesting, highlighting soon-to-expire or high-stock ingredient usage")

class DynamicRecipesResponse(BaseModel):
    recipes: list[DynamicRecipe] = Field(description="List of dynamically recommended recipes")


def generate_recipes_from_pantry(pantry_items, people=2):
    """
    Given currently available pantry items, uses Gemini to dynamically generate 5 delicious recipe recommendations.
    """
    client = get_genai_client()
    if not client:
        print("Error: Gemini API Client could not be initialized (missing API key).")
        return None

    # Format the ingredients cleanly for the prompt
    pantry_description = []
    for item in pantry_items:
        expiry_info = f" (Expires: {item['expiry']})" if item.get('expiry') else ""
        pantry_description.append(f"- {item['name']}: {item['qty']} {item['unit']}{expiry_info}")

    pantry_str = "\n".join(pantry_description)

    prompt = f"""
    You are a professional chef specializing in zero-waste cooking for Indian households.
    Below is a list of currently available ingredients in the pantry (some have expiry dates listed).

    Current Pantry Inventory:
    {pantry_str}

    Your tasks:
    1. Recommend exactly 5 creative, delicious recipes (such as milkshakes, smoothies, salads, snacks, quick curries, etc.) that can be prepared using the available items.
    2. Prioritize utilizing ingredients that are close to their expiration dates or have high stock volumes to minimize waste.
    3. You can suggest adding standard basic kitchen supplies (like water, salt, basic oils, sugar) if needed, but the primary ingredients MUST come from the pantry inventory listed above.
    4. For each recipe, provide the exact scaled quantities for {people} servings.
    5. Keep the ingredient names EXACTLY matching the names in the pantry inventory where possible to ensure seamless stock deduction (e.g., use 'tomato' instead of 'tomatoes').
    6. Extremely Important: Pay close attention to the UNIT of each ingredient in the Pantry Inventory list. The quantity you return MUST be in that exact same unit. For example, if 'potato' has unit 'kg' and you want to use 200 grams, you MUST return quantity `0.2` and unit `kg` (DO NOT return `200` and unit `kg`, as that means 200 kilograms!). If 'milk' has unit 'liters' and you want to use 250 ml, you MUST return quantity `0.25` and unit `liters`.
    """

    try:
        print(f"Sending pantry inventory to Gemini to generate custom recommendations for {people} people...")
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=DynamicRecipesResponse,
            ),
        )

        if response.parsed and hasattr(response.parsed, 'recipes'):
            result = []
            for r in response.parsed.recipes:
                ing_dict = {}
                for ing in r.ingredients:
                    ing_dict[ing.name.lower().strip()] = ing.qty
                result.append({
                    "name": r.name,
                    "serves": r.serves,
                    "time_mins": r.time_mins,
                    "ingredients": ing_dict,
                    "recommendation_reason": r.recommendation_reason
                })
            return result

        raw_response = response.text
        data = parse_ai_json(raw_response)
        if isinstance(data, dict) and "recipes" in data:
            result = []
            for r in data["recipes"]:
                ing_dict = {}
                for ing in r.get("ingredients", []):
                    ing_dict[ing["name"].lower().strip()] = float(ing["qty"])
                result.append({
                    "name": r["name"],
                    "serves": r.get("serves", people),
                    "time_mins": r.get("time_mins", 30),
                    "ingredients": ing_dict,
                    "recommendation_reason": r.get("recommendation_reason", "")
                })
            return result
        return None
    except Exception as e:
        print(f"Failed to generate dynamic recipes via Gemini: {e}")
        return None


if __name__ == "__main__":
    ingredient = "kashmiri chili"
    result = get_exotic_ingredient_info(ingredient)
    print(f"Result: {result}")